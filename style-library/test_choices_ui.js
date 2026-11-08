/* Task 10: a vm-sandbox unit test for choices-ui.js (the same style test_materials_ui.js
   and test_new_video_ui.js already use). Run with: node --test style-library/test_choices_ui.js
   (no browser or packages needed).

   choices-ui.js builds its tap-card grid with document.createElement rather than
   innerHTML strings, so the fake DOM below is the same small, generic node graph
   test_materials_ui.js already uses (append/insertBefore/remove/classList/
   addEventListener/dispatch). */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/choices-ui.js'), 'utf8');
const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));

function i18nStub(lang = 'he') {
  const strings = lang === 'he' ? he : JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));
  return {
    lang: () => lang,
    t(key, vars) {
      const value = strings[key] ?? key;
      if (!vars) return value;
      return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value);
    },
  };
}

// --- a tiny, generic fake DOM: only what choices-ui.js actually calls ---

// Supports the only selector shapes choices-ui.js's closest()/querySelectorAll() calls
// actually use: `[role="radio"]`, `[role="radiogroup"]`.
function matchesSelector(node, selector) {
  const m = /^\[([a-zA-Z-]+)(?:="([^"]*)")?\]$/.exec(selector);
  if (!m) return false;
  const [, attr, value] = m;
  if (!node.attributes) return false;
  return value === undefined ? attr in node.attributes : node.attributes[attr] === value;
}

function makeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null,
    dataset: {}, style: {}, attributes: {}, _classes: new Set(), _listeners: {},
    isConnected: true, checked: false, value: '', textContent: '', maxLength: 0, tabIndex: 0, focused: false,
    get className() { return [...this._classes].join(' '); },
    set className(v) { this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); },
    get classList() {
      const self = this;
      return {
        add: c => self._classes.add(c), remove: c => self._classes.delete(c), contains: c => self._classes.has(c),
        toggle: (c, force) => { const on = force !== undefined ? force : !self._classes.has(c); if (on) self._classes.add(c); else self._classes.delete(c); },
      };
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name]; },
    append(...nodes) { nodes.forEach(n => { n.parentNode = this; this.children.push(n); }); },
    prepend(...nodes) { nodes.forEach(n => { n.parentNode = this; this.children.unshift(n); }); },
    appendChild(n) { n.parentNode = this; this.children.push(n); return n; },
    remove() {
      if (!this.parentNode) return;
      const i = this.parentNode.children.indexOf(this);
      if (i !== -1) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    },
    closest(selector) {
      let n = this;
      while (n) { if (matchesSelector(n, selector)) return n; n = n.parentNode; }
      return null;
    },
    querySelectorAll(selector) { return findAll(this, n => n !== this && matchesSelector(n, selector)); },
    focus() { this.focused = true; },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    dispatch(type, evt = {}) { (this._listeners[type] || []).slice().forEach(fn => fn({preventDefault() {}, ...evt})); },
    click() { this.dispatch('click', {target: this}); },
    set innerHTML(v) { if (v === '') this.children = []; },
    get innerHTML() { return ''; },
  };
  return node;
}

function findAll(root, predicate) {
  const out = [];
  (function walk(n) {
    if (!n) return;
    if (predicate(n)) out.push(n);
    (n.children || []).forEach(walk);
  })(root);
  return out;
}
function find(root, predicate) { return findAll(root, predicate)[0] || null; }
const hasClass = cls => n => n.className && n.className.split(/\s+/).includes(cls);
const byTag = tag => n => n.tagName === tag;

const CONFIG = {
  cut: {label_key: 'choices.step.cut', options: [
    {id: 'tight', label_key: 'choices.cut.tight'}, {id: 'natural', label_key: 'choices.cut.natural'},
    {id: 'keep-pauses', label_key: 'choices.cut.keepPauses'},
  ]},
  look: {label_key: 'choices.step.look', ref_label_key: 'choices.look.fromInspiration'},
  sound: {label_key: 'choices.step.sound', options: [
    {id: 'music-calm', label_key: 'choices.sound.musicCalm'}, {id: 'music-energetic', label_key: 'choices.sound.musicEnergetic'},
    {id: 'no-music', label_key: 'choices.sound.noMusic'},
  ], sfx_label_key: 'choices.sound.sfx', with_sfx_brief_label_key: 'choices.brief.withSfx'},
  finish: {label_key: 'choices.step.finish', captions_label_key: 'choices.finish.captions', length_options: [
    {id: '15-30', label_key: 'choices.finish.length.short'}, {id: '30-60', label_key: 'choices.finish.length.medium'},
    {id: '60-90', label_key: 'choices.finish.length.long'},
  ]},
  extra: {ui_label_key: 'choices.extra.label', brief_label_key: 'choices.brief.extra'},
  effects: {brief_label_key: 'choices.brief.effects'},
};

const LOOKS = [
  {id: 'soft', name_he: 'רך', name_en: 'Soft', sample: '/look-files/soft/sample.jpg'},
  {id: 'collage', name_he: 'קולאז', name_en: 'Collage', sample: '/look-files/collage/sample.jpg'},
];

function harness(options = {}) {
  const fetchCalls = [];
  const deferredPosts = []; // {body, resolve} -- only populated when options.deferPosts is true
  const defaultFetch = async (url, init = {}) => {
    fetchCalls.push({url, init});
    if (typeof url === 'string' && url.startsWith('/choices?')) {
      return {ok: true, json: async () => ({choices: options.initialChoices || {}, config: options.config || CONFIG})};
    }
    if (url === '/looks') return {ok: true, json: async () => ({items: options.looks || LOOKS})};
    if (url === '/choices') {
      if (options.deferPosts) return new Promise(resolve => deferredPosts.push({body: JSON.parse(init.body), resolve}));
      return options.postImpl ? options.postImpl(init) : {ok: true, json: async () => ({...JSON.parse(init.body)})};
    }
    return {ok: true, json: async () => ({})};
  };

  let nextTimerId = 0;
  const pendingTimers = new Map();
  const fakeSetTimeout = (fn, ms) => { const id = ++nextTimerId; pendingTimers.set(id, {fn, ms}); return id; };
  const fakeClearTimeout = id => pendingTimers.delete(id);
  const flushTimers = () => { const due = [...pendingTimers.values()]; pendingTimers.clear(); due.forEach(({fn}) => fn()); };

  const document = {createElement: tag => makeNode(tag)};
  const context = {
    document, window: {}, I18N: options.i18n || i18nStub(),
    URLSearchParams, setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout,
    fetch: options.fetchImpl || defaultFetch,
  };
  vm.createContext(context);
  vm.runInContext(source, context);

  return {
    ChoicesUI: context.window.ChoicesUI, fetchCalls, flushTimers, pendingTimers, deferredPosts,
    ContextTypeError: vm.runInContext('TypeError', context),
    mountEl() { return makeNode('div'); },
  };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

// --- mount(): loads /choices and /looks, renders four steps + extra textarea ---

test('mount() renders four steps and the extra textarea', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const steps = findAll(el, hasClass('choice-step'));
  assert.equal(steps.length, 4);
  const textarea = find(el, byTag('TEXTAREA'));
  assert.ok(textarea);
  assert.equal(textarea.getAttribute('placeholder'), he['choices.extra.placeholder']);
});

test('mount() links "+ אפקט" to the effects board aimed at this project (Task 12)', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'my-video');
  const link = find(el, hasClass('choices-add-effect'));
  assert.ok(link);
  assert.equal(link.tagName, 'A');
  assert.equal(link.href, '#effects?project=my-video');
  assert.equal(link.textContent, he['choices.addEffect']);
});

test('the Look step links "+ איך אתם נראים" to the presenter-looks tab of the board (Task 12 fix round 1)', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'my-video');
  await flush();
  const link = find(el, hasClass('choices-add-look'));
  assert.ok(link);
  assert.equal(link.href, '#effects?project=my-video&tab=look');
  assert.equal(link.textContent, he['choices.addLook']);
});

test('mount() marks the saved cut option selected', async () => {
  const {ChoicesUI, mountEl} = harness({initialChoices: {cut: 'natural'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const selected = findAll(el, hasClass('choice-option')).filter(hasClass('on'));
  assert.equal(selected.length, 1);
  assert.equal(selected[0].dataset.value, 'natural');
});

// --- tapping an option: optimistic select + save, revert on failure ---

test('tapping a cut option selects it and saves {cut: value}', async () => {
  const {ChoicesUI, mountEl, fetchCalls} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  tight.click();
  await flush();
  assert.ok(tight.classList.contains('on'));
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.ok(postCall);
  assert.deepEqual(JSON.parse(postCall.init.body), {project: 'demo', cut: 'tight'});
});

test('tapping an already-selected option does not re-save', async () => {
  const {ChoicesUI, mountEl, fetchCalls} = harness({initialChoices: {cut: 'tight'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const before = fetchCalls.length;
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  tight.click();
  await flush();
  assert.equal(fetchCalls.length, before);
});

test('a failed save reverts the selection and shows the translated error', async () => {
  const {ChoicesUI, mountEl} = harness({
    postImpl: () => ({ok: false, json: async () => ({error: 'choices.error.unknownOption'})}),
  });
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  tight.click();
  await flush();
  assert.ok(!tight.classList.contains('on'));
  const status = find(el, hasClass('choices-status'));
  assert.equal(status.textContent, he['choices.error.unknownOption']);
});

test('a network error during save reverts and shows the generic save error', async () => {
  const {ChoicesUI, mountEl, ContextTypeError} = harness({
    postImpl: () => { throw new ContextTypeError('network down'); },
  });
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  tight.click();
  await flush();
  assert.ok(!tight.classList.contains('on'));
  const status = find(el, hasClass('choices-status'));
  assert.equal(status.textContent, he['choices.saveError']);
});

// --- switches: sfx / captions ---

test('toggling the sfx switch saves {sfx: true}', async () => {
  const {ChoicesUI, mountEl, fetchCalls} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const checkbox = findAll(el, byTag('INPUT')).find(i => i.type === 'checkbox');
  checkbox.checked = true;
  checkbox.dispatch('change', {});
  await flush();
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.deepEqual(JSON.parse(postCall.init.body), {project: 'demo', sfx: true});
  const track = find(el, hasClass('choice-switch'));
  assert.ok(track.classList.contains('on'));
});

test('a failed sfx toggle reverts the switch', async () => {
  const {ChoicesUI, mountEl} = harness({postImpl: () => ({ok: false, json: async () => ({error: 'choices.saveError'})})});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const checkbox = findAll(el, byTag('INPUT')).find(i => i.type === 'checkbox');
  checkbox.checked = true;
  checkbox.dispatch('change', {});
  await flush();
  assert.equal(checkbox.checked, false);
  const track = find(el, hasClass('choice-switch'));
  assert.ok(!track.classList.contains('on'));
});

// --- extra textarea: debounced save ---

test('typing in the extra textarea saves after the debounce delay', async () => {
  const {ChoicesUI, mountEl, fetchCalls, flushTimers} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const textarea = find(el, byTag('TEXTAREA'));
  textarea.value = 'עוד פרט חשוב';
  textarea.dispatch('input', {});
  assert.equal(fetchCalls.filter(c => c.url === '/choices' && c.init.method === 'POST').length, 0);
  flushTimers();
  await flush();
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.deepEqual(JSON.parse(postCall.init.body), {project: 'demo', extra: 'עוד פרט חשוב'});
});

test('line breaks and other control characters in the extra note become spaces (the server rejects them)', async () => {
  const {ChoicesUI, mountEl, fetchCalls, flushTimers} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const textarea = find(el, byTag('TEXTAREA'));
  textarea.value = 'שורה\nשנייה\tוטאב';
  textarea.dispatch('input', {});
  assert.equal(textarea.value, 'שורה שנייה וטאב');
  flushTimers();
  await flush();
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.equal(JSON.parse(postCall.init.body).extra, 'שורה שנייה וטאב');
});

test('the first converted line break shows a one-time inline hint', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const hint = find(el, hasClass('choices-extra-hint'));
  assert.ok(hint);
  assert.equal(hint.hidden, true);
  const textarea = find(el, byTag('TEXTAREA'));
  textarea.value = 'בלי שבירה';
  textarea.dispatch('input', {});
  assert.equal(hint.hidden, true, 'no hint without a line break');
  textarea.value = 'א\nב';
  textarea.dispatch('input', {});
  assert.equal(hint.hidden, false);
  assert.equal(hint.textContent, he['choices.extra.newlineHint']);
});

test('a failed extra save puts the textarea back in sync with the saved note and shows the server message', async () => {
  const {ChoicesUI, mountEl, flushTimers} = harness({
    initialChoices: {extra: 'מה שנשמר'},
    postImpl: () => ({ok: false, json: async () => ({error: 'choices.error.extraTooLong'})}),
  });
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const textarea = find(el, byTag('TEXTAREA'));
  textarea.value = 'משהו חדש';
  textarea.dispatch('input', {});
  flushTimers();
  await flush();
  assert.equal(textarea.value, 'מה שנשמר');
  assert.equal(find(el, hasClass('choices-status')).textContent, he['choices.error.extraTooLong']);
});

test('markers like <!-- and --> in the extra note are sent verbatim', async () => {
  const {ChoicesUI, mountEl, fetchCalls, flushTimers} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const textarea = find(el, byTag('TEXTAREA'));
  textarea.value = 'א --> ב <!-- ג';
  textarea.dispatch('input', {});
  flushTimers();
  await flush();
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.equal(JSON.parse(postCall.init.body).extra, 'א --> ב <!-- ג');
});

test('typing twice before the debounce fires only saves once, with the latest value', async () => {
  const {ChoicesUI, mountEl, fetchCalls, flushTimers} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const textarea = find(el, byTag('TEXTAREA'));
  textarea.value = 'א';
  textarea.dispatch('input', {});
  textarea.value = 'אב';
  textarea.dispatch('input', {});
  flushTimers();
  await flush();
  const posts = fetchCalls.filter(c => c.url === '/choices' && c.init.method === 'POST');
  assert.equal(posts.length, 1);
  assert.deepEqual(JSON.parse(posts[0].init.body), {project: 'demo', extra: 'אב'});
});

// --- look step: built-in looks plus an inspiration card ---

test('the look step renders a card per built-in look with its sample image', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const cards = findAll(el, hasClass('choice-look-card'));
  assert.equal(cards.length, LOOKS.length);
  const img = find(cards[0], byTag('IMG'));
  assert.equal(img.src, LOOKS[0].sample);
});

test('an existing ref: look adds an inspiration card and marks it selected', async () => {
  const {ChoicesUI, mountEl} = harness({initialChoices: {look: 'ref:cool-reference'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const cards = findAll(el, hasClass('choice-look-card'));
  assert.equal(cards.length, LOOKS.length + 1);
  const refCard = cards.find(c => c.dataset.value === 'ref:cool-reference');
  assert.ok(refCard);
  assert.ok(refCard.classList.contains('on'));
});

test('tapping a look card saves {look: value}', async () => {
  const {ChoicesUI, mountEl, fetchCalls} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const collage = findAll(el, hasClass('choice-look-card')).find(c => c.dataset.value === 'collage');
  collage.click();
  await flush();
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.deepEqual(JSON.parse(postCall.init.body), {project: 'demo', look: 'collage'});
});

// --- loading failure ---

test('a failed /choices load shows the translated load error', async () => {
  const {ChoicesUI, mountEl} = harness({fetchImpl: async url => (
    typeof url === 'string' && url.startsWith('/choices?') ? {ok: false, json: async () => ({})} : {ok: true, json: async () => ({items: []})}
  )});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const status = find(el, hasClass('choices-status'));
  assert.equal(status.textContent, he['choices.loadError']);
});

// --- fix round 1, finding 1: switches are keyboard-operable (a real, focusable checkbox,
// never hidden/display:none) ---

test('the sfx/captions switch is a real checkbox that is never [hidden] and stays in the tab order', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const checkboxes = findAll(el, byTag('INPUT')).filter(i => i.type === 'checkbox');
  assert.equal(checkboxes.length, 2); // sfx + captions
  for (const checkbox of checkboxes) {
    assert.notEqual(checkbox.hidden, true, 'a [hidden] control is unreachable by Tab (dist/styles.css [hidden]{display:none!important})');
    assert.ok(checkbox.className.split(/\s+/).includes('sr-only'), 'visually hidden via .sr-only (clip), not [hidden]/display:none, so it stays focusable');
    assert.notEqual(checkbox.tabIndex, -1);
  }
});

test('the switch is operable by keyboard: a native checkbox change toggles it, no click required', async () => {
  // A real <input type="checkbox"> is natively Space-toggleable once focused -- the test
  // harness doesn't simulate real key events, so this exercises the same 'change' path a
  // keyboard activation fires, confirming the control (not a div/span) carries the
  // interaction, and that focusing it (not clicking) is enough to reach and flip it.
  const {ChoicesUI, mountEl, fetchCalls} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const checkbox = findAll(el, byTag('INPUT')).find(i => i.type === 'checkbox');
  checkbox.focus();
  assert.equal(checkbox.focused, true);
  checkbox.checked = true;
  checkbox.dispatch('change', {});
  await flush();
  assert.ok(fetchCalls.some(c => c.url === '/choices' && c.init.method === 'POST'));
});

// --- fix round 1, finding 4: radiogroup/radio roles + roving tabindex ---

test('each single-select step is a radiogroup of radios with aria-checked reflecting the selection', async () => {
  const {ChoicesUI, mountEl} = harness({initialChoices: {cut: 'natural'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const groups = findAll(el, n => n.getAttribute('role') === 'radiogroup');
  assert.equal(groups.length, 4); // cut, look, sound, length
  const cutGroup = groups.find(g => findAll(g, n => n.getAttribute('role') === 'radio').some(r => r.dataset.value === 'tight'));
  const radios = findAll(cutGroup, n => n.getAttribute('role') === 'radio');
  assert.equal(radios.length, 3);
  const natural = radios.find(r => r.dataset.value === 'natural');
  assert.equal(natural.getAttribute('aria-checked'), 'true');
  assert.equal(natural.tabIndex, 0);
  for (const other of radios.filter(r => r !== natural)) {
    assert.equal(other.getAttribute('aria-checked'), 'false');
    assert.equal(other.tabIndex, -1);
  }
});

test('with nothing selected yet, the first radio in the group is the roving-tabindex entry point', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const radios = findAll(el, n => n.getAttribute('role') === 'radio' && ['tight', 'natural', 'keep-pauses'].includes(n.dataset.value));
  assert.equal(radios[0].tabIndex, 0);
  assert.ok(radios.slice(1).every(r => r.tabIndex === -1));
});

test('ArrowDown moves focus to and selects the next radio in the same group, wrapping at the end', async () => {
  const {ChoicesUI, mountEl, fetchCalls} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const section = find(el, hasClass('choices-section'));
  const radios = findAll(el, n => n.getAttribute('role') === 'radio' && ['tight', 'natural', 'keep-pauses'].includes(n.dataset.value));
  const [tight, natural, keepPauses] = radios;
  section.dispatch('keydown', {target: tight, key: 'ArrowDown'});
  await flush();
  assert.equal(natural.focused, true);
  assert.ok(natural.classList.contains('on'));
  section.dispatch('keydown', {target: natural, key: 'ArrowDown'});
  await flush();
  assert.ok(keepPauses.classList.contains('on'));
  section.dispatch('keydown', {target: keepPauses, key: 'ArrowDown'}); // wraps back to the first
  await flush();
  assert.ok(tight.classList.contains('on'));
  const cutSaves = fetchCalls.filter(c => c.url === '/choices' && c.init.method === 'POST' && JSON.parse(c.init.body).cut);
  assert.equal(cutSaves.length, 3);
});

test('Home/End jump to the first/last radio in the group', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const section = find(el, hasClass('choices-section'));
  const radios = findAll(el, n => n.getAttribute('role') === 'radio' && ['tight', 'natural', 'keep-pauses'].includes(n.dataset.value));
  const [tight, , keepPauses] = radios;
  section.dispatch('keydown', {target: tight, key: 'End'});
  await flush();
  assert.ok(keepPauses.classList.contains('on'));
  section.dispatch('keydown', {target: keepPauses, key: 'Home'});
  await flush();
  assert.ok(tight.classList.contains('on'));
});

test('arrow navigation in one group never affects a different radiogroup', async () => {
  const {ChoicesUI, mountEl} = harness({initialChoices: {sound: 'music-calm'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const section = find(el, hasClass('choices-section'));
  const cutRadios = findAll(el, n => n.getAttribute('role') === 'radio' && ['tight', 'natural', 'keep-pauses'].includes(n.dataset.value));
  const soundRadios = findAll(el, n => n.getAttribute('role') === 'radio' && ['music-calm', 'music-energetic', 'no-music'].includes(n.dataset.value));
  section.dispatch('keydown', {target: cutRadios[0], key: 'ArrowDown'});
  await flush();
  assert.ok(soundRadios.find(r => r.dataset.value === 'music-calm').classList.contains('on'));
});

// --- fix round 2, controller ruling R33: same-field rapid taps are serialized
// client-only (never more than one /choices request per field in flight); no seq, no
// server bookkeeping, so none of this can go stale across a reload or a second tab. ---

test('reload scenario: a fresh mount against a project that already has server-side choices still saves a new tap normally', async () => {
  // Simulates reloading the page after a previous session set `cut`: this mount's
  // fieldInFlight/fieldQueued/confirmed all start completely empty -- there is no
  // leftover client-side counter (the old seq bug) that could make a legitimate new tap
  // look "stale" to a server that remembers more than this fresh page load does.
  const {ChoicesUI, mountEl, fetchCalls} = harness({initialChoices: {cut: 'natural'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  tight.click();
  await flush();
  assert.ok(tight.classList.contains('on'));
  const postCall = fetchCalls.find(c => c.url === '/choices' && c.init.method === 'POST');
  assert.deepEqual(JSON.parse(postCall.init.body), {project: 'demo', cut: 'tight'});
  const status = find(el, hasClass('choices-status'));
  assert.equal(status.textContent, '');
});

test('two-tab scenario: two independent page loads never share save state and each saves its own tap correctly', async () => {
  // A real second browser tab is a completely separate JS runtime -- its own fresh
  // evaluation of choices-ui.js, with its own `window.ChoicesUI`, its own module-level
  // `run` counter, and its own mount()-closure fieldInFlight/fieldQueued/confirmed. Two
  // separate harness() instances (each does its own vm.createContext + a fresh
  // vm.runInContext of the source) is the faithful equivalent of that, not two mount()
  // calls sharing one harness -- this app only ever mounts ChoicesUI once per real page.
  const tabA = harness();
  const tabB = harness();
  const elA = tabA.mountEl(), elB = tabB.mountEl();
  tabA.ChoicesUI.mount(elA, 'demo');
  tabB.ChoicesUI.mount(elB, 'demo');
  await flush();
  findAll(elA, hasClass('choice-option')).find(b => b.dataset.value === 'tight').click();
  findAll(elB, hasClass('choice-option')).find(b => b.dataset.value === 'natural').click();
  await flush();
  assert.ok(findAll(elA, hasClass('choice-option')).find(b => b.dataset.value === 'tight').classList.contains('on'));
  assert.ok(findAll(elB, hasClass('choice-option')).find(b => b.dataset.value === 'natural').classList.contains('on'));
  const postsA = tabA.fetchCalls.filter(c => c.url === '/choices' && c.init.method === 'POST').map(c => JSON.parse(c.init.body));
  const postsB = tabB.fetchCalls.filter(c => c.url === '/choices' && c.init.method === 'POST').map(c => JSON.parse(c.init.body));
  assert.deepEqual(postsA, [{project: 'demo', cut: 'tight'}]);
  assert.deepEqual(postsB, [{project: 'demo', cut: 'natural'}]);
});

test('rapid same-field taps: only the first tap is sent immediately -- the rest are not yet in flight (out-of-order is impossible by construction)', async () => {
  const {ChoicesUI, mountEl, deferredPosts} = harness({deferPosts: true});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  const natural = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'natural');
  const keepPauses = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'keep-pauses');
  tight.click();
  await flush();
  assert.equal(deferredPosts.length, 1, 'the first tap is sent right away');
  natural.click(); // queued -- replaces nothing yet
  keepPauses.click(); // queued -- overwrites the queued "natural", which is never sent at all
  await flush();
  // Still exactly one request on the wire: there is structurally never a second
  // in-flight request for the same field for a response to arrive "out of order" with.
  assert.equal(deferredPosts.length, 1);
  assert.deepEqual(deferredPosts[0].body, {project: 'demo', cut: 'tight'});
  deferredPosts[0].resolve({ok: true, json: async () => ({cut: 'tight'})});
  await flush();
  // Only now -- after the first settles -- does the (coalesced) next request go out.
  assert.equal(deferredPosts.length, 2);
  assert.deepEqual(deferredPosts[1].body, {project: 'demo', cut: 'keep-pauses'}, '"natural" was superseded before ever being sent');
  deferredPosts[1].resolve({ok: true, json: async () => ({cut: 'keep-pauses'})});
  await flush();
  assert.ok(keepPauses.classList.contains('on'), 'final persisted value is the last tap');
  assert.ok(!tight.classList.contains('on'));
  assert.ok(!natural.classList.contains('on'));
});

test("an in-flight request's failure is discarded -- not applied as a revert -- once a newer tap is queued behind it", async () => {
  const {ChoicesUI, mountEl, deferredPosts} = harness({deferPosts: true});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  const natural = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'natural');
  tight.click();
  await flush();
  natural.click();
  await flush();
  deferredPosts[0].resolve({ok: false, json: async () => ({error: 'choices.error.unknownOption'})});
  await flush();
  // The failed request's error must not surface -- a newer tap already superseded it.
  const status = find(el, hasClass('choices-status'));
  assert.equal(status.textContent, '');
  assert.ok(natural.classList.contains('on'), 'the queued newer tap is still shown, not reverted by the stale failure');
  assert.equal(deferredPosts.length, 2, 'the queued request for "natural" was sent once the failed one settled');
  deferredPosts[1].resolve({ok: true, json: async () => ({cut: 'natural'})});
  await flush();
  assert.ok(natural.classList.contains('on'));
});

test('when the final request in a chain fails, it reverts to the last server-confirmed value, not an intermediate unconfirmed tap', async () => {
  const {ChoicesUI, mountEl, deferredPosts} = harness({deferPosts: true, initialChoices: {cut: 'keep-pauses'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const tight = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'tight');
  const natural = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'natural');
  const keepPauses = findAll(el, hasClass('choice-option')).find(b => b.dataset.value === 'keep-pauses');
  tight.click(); // in flight
  await flush();
  natural.click(); // queued, then superseded -- never confirmed, never individually reverted
  await flush();
  deferredPosts[0].resolve({ok: true, json: async () => ({cut: 'tight'})}); // discarded (natural queued)
  await flush();
  deferredPosts[1].resolve({ok: false, json: async () => ({error: 'choices.saveError'})}); // the real, final failure
  await flush();
  // Reverts all the way back to "keep-pauses" (the original server-confirmed value from
  // load), not to "tight" (an intermediate tap that was itself never confirmed).
  assert.ok(keepPauses.classList.contains('on'));
  assert.ok(!tight.classList.contains('on'));
  assert.ok(!natural.classList.contains('on'));
  const status = find(el, hasClass('choices-status'));
  assert.equal(status.textContent, he['choices.saveError']);
});

// --- fix round 1, finding 3: a broken look thumbnail falls back to a gradient placeholder ---

test('a look thumbnail that fails to load is replaced by a placeholder, not left as a broken image', async () => {
  const {ChoicesUI, mountEl} = harness();
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const card = findAll(el, hasClass('choice-look-card'))[0];
  const img = find(card, byTag('IMG'));
  assert.ok(img);
  img.dispatch('error', {});
  assert.equal(find(card, byTag('IMG')), null);
  assert.ok(card.classList.contains('choice-look-placeholder'));
});

test('the inspiration card (no sample image at all) never needs the error fallback', async () => {
  const {ChoicesUI, mountEl} = harness({initialChoices: {look: 'ref:cool-reference'}});
  const el = mountEl();
  ChoicesUI.mount(el, 'demo');
  await flush();
  const refCard = findAll(el, hasClass('choice-look-card')).find(c => c.dataset.value === 'ref:cool-reference');
  assert.equal(find(refCard, byTag('IMG')), null);
  assert.ok(!refCard.classList.contains('choice-look-placeholder'));
});
