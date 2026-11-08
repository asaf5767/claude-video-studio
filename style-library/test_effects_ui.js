/* Task 12: dist/effects-ui.js -- the "אפקטים ומראה" board. vm sandbox + the same small fake DOM
   style test_choices_ui.js uses. Run with: node --test style-library/test_effects_ui.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/effects-ui.js'), 'utf8');
const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));
const EFFECTS = JSON.parse(readFileSync(join(__dirname, '..', 'effects', 'effects.json'), 'utf8'));
const LOOKS = JSON.parse(readFileSync(join(__dirname, '..', 'looks', 'presenter.json'), 'utf8'));

const i18n = {
  lang: () => 'he',
  t(key, vars) {
    const value = he[key] ?? key;
    return vars ? Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value) : value;
  },
};

function makeNode(tag) {
  return {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, dataset: {}, style: {}, attributes: {},
    _classes: new Set(), _listeners: {}, isConnected: true, value: '', textContent: '', hidden: false, open: false,
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
    appendChild(n) { this.append(n); return n; },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    dispatch(type, evt = {}) { (this._listeners[type] || []).slice().forEach(fn => fn(evt)); },
    click() { this.dispatch('click', {}); },
    showModal() { this.open = true; },
    focus() { this.focused = true; },
    close() { if (!this.open) return; this.open = false; this.dispatch('close'); },
    set innerHTML(v) { if (v === '') this.children = []; },
    get innerHTML() { return ''; },
  };
}

function findAll(root, predicate) {
  const out = [];
  (function walk(n) { if (!n) return; if (predicate(n)) out.push(n); (n.children || []).forEach(walk); })(root);
  return out;
}
const hasClass = cls => n => n._classes && n._classes.has(cls);
const text = n => n.textContent + (n.children || []).map(text).join('');

function harness({initialChoices = {}, projects = [{id: 'demo', title: 'הסרטון שלי'}], postImpl, reduced = false, effects = EFFECTS} = {}) {
  const posts = [], gets = [], replaced = [];
  const fetch = async (url, init = {}) => {
    if (init.method === 'POST') {
      posts.push(JSON.parse(init.body));
      if (postImpl) return postImpl(init);
      const body = JSON.parse(init.body);
      delete body.project;
      return {ok: true, json: async () => ({...initialChoices, ...body})};
    }
    gets.push(url);
    if (url === '/effects') return {ok: true, json: async () => ({effects, looks: LOOKS})};
    if (url === '/projects.json') return {ok: true, json: async () => ({projects})};
    if (url.startsWith('/choices?')) return {ok: true, json: async () => ({choices: initialChoices, config: {}})};
    return {ok: false, json: async () => ({})};
  };
  const timers = [];
  const document = {
    createElement: makeNode, body: makeNode('body'), hidden: false, activeElement: null, _listeners: {}, documentElement: {dir: 'rtl'},
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
  };
  const motionQuery = {matches: reduced, listeners: [], addEventListener(type, fn) { if (type === 'change') this.listeners.push(fn); }};
  const window = {matchMedia: () => motionQuery};
  const context = {
    window, document, I18N: i18n, fetch, URLSearchParams, console,
    setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; }, clearTimeout: id => { if (timers[id - 1]) timers[id - 1].fn = () => {}; },
    history: {replaceState: (_s, _t, url) => replaced.push(url)},
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return {Board: context.window.EffectsBoard, document, posts, gets, replaced, timers, window, motionQuery};
}

const flush = async () => { for (let i = 0; i < 6; i++) await new Promise(resolve => setImmediate(resolve)); };
const cardsIn = root => findAll(root, hasClass('fx-card'));
const card = (root, id) => cardsIn(root).find(c => c.dataset.fxId === id);
const addButton = c => findAll(c, hasClass('fx-add'))[0];
const whenInput = c => findAll(c, hasClass('fx-when'))[0];
const tab = (root, id) => findAll(root, n => n.dataset && n.dataset.tab === id)[0];
const chips = root => findAll(root, hasClass('fx-chip'));

test('motion logic: off and reduced draw stills, always animates', () => {
  const {Board} = harness();
  assert.equal(Board.logic.animate('always', true), true);
  assert.equal(Board.logic.animate('off', false), false);
  assert.equal(Board.logic.animate('auto', true), false);
  assert.equal(Board.logic.animate('auto', false), true);
});

test('effect list helpers keep order, replace a when and clip it to 80 characters', () => {
  const {Board} = harness();
  const list = Board.logic.withEffect([{effect: 'a', when: ''}], 'b', '  hi  ');
  assert.deepEqual(JSON.parse(JSON.stringify(list)), [{effect: 'a', when: ''}, {effect: 'b', when: 'hi'}]);
  const replacedWhen = Board.logic.withEffect(list, 'a', 'x'.repeat(100));
  assert.equal(replacedWhen[0].when.length, 80);
  assert.deepEqual(JSON.parse(JSON.stringify(Board.logic.withoutEffect(list, 'a'))), [{effect: 'b', when: 'hi'}]);
});

test('renders every effect card, then the looks tab with no "when I say" field', async () => {
  const {Board} = harness();
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  assert.equal(cardsIn(root).length, EFFECTS.length);
  assert.ok(whenInput(card(root, 'zoomthru')));
  tab(root, 'look').click();
  assert.equal(cardsIn(root).length, LOOKS.length);
  assert.equal(whenInput(card(root, 'popout')), undefined);
});

test('mount(el, project, "look") opens the presenter-looks tab directly', async () => {
  const {Board} = harness();
  const root = makeNode('section');
  Board.mount(root, 'demo', 'look');
  await flush();
  assert.equal(cardsIn(root).length, LOOKS.length);
  assert.equal(tab(root, 'look').getAttribute('aria-selected'), 'true');
});

test('category filter narrows the grid', async () => {
  const {Board} = harness();
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  findAll(root, n => n.dataset && n.dataset.cat === 'transition')[0].click();
  const shown = cardsIn(root).map(c => c.dataset.fxId);
  assert.deepEqual(shown, EFFECTS.filter(e => e.category === 'transition').map(e => e.id));
});

test('with a project: add sends the whole effects list with the when word, and the tray shows it', async () => {
  const {Board, posts} = harness({initialChoices: {effects: [{effect: 'marker', when: ''}]}});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  assert.equal(addButton(card(root, 'marker')).textContent, he['effects.added']);
  whenInput(card(root, 'zoomthru')).value = 'סוכנים';
  addButton(card(root, 'zoomthru')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', effects: [{effect: 'marker', when: ''}, {effect: 'zoomthru', when: 'סוכנים'}]});
  assert.equal(addButton(card(root, 'zoomthru')).textContent, he['effects.added']);
  const trayText = chips(root).map(text).join(' | ');
  assert.match(trayText, /זום דרך מילה · כשאני אומר "סוכנים"/);
  assert.match(trayText, /מרקר מדגיש/);
});

test('saved choices with unknown effect ids or legacy items without "when" are cleaned before re-sending', async () => {
  const {Board, posts} = harness({initialChoices: {effects: [{effect: 'gone-effect', when: ''}, {effect: 'marker'}, {effect: 'marker', when: 'x'}, 'junk'], presenter: 'gone-look'}});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  assert.equal(chips(root).length, 1, 'only the known effect shows in the tray');
  addButton(card(root, 'zoomthru')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', effects: [{effect: 'marker', when: ''}, {effect: 'zoomthru', when: ''}]});
});

test('clicking a chosen effect, or its tray ×, removes it', async () => {
  const {Board, posts} = harness({initialChoices: {effects: [{effect: 'marker', when: ''}, {effect: 'pop', when: 'x'}]}});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  addButton(card(root, 'marker')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', effects: [{effect: 'pop', when: 'x'}]});
  findAll(root, hasClass('fx-chip-remove'))[0].click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', effects: []});
});

test('presenter looks: one per project, chosen again clears it', async () => {
  const {Board, posts} = harness();
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  tab(root, 'look').click();
  addButton(card(root, 'popout')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', presenter: 'popout'});
  addButton(card(root, 'green')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', presenter: 'green'});
  assert.equal(addButton(card(root, 'popout')).textContent, he['effects.add']);
  addButton(card(root, 'green')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', presenter: null});
});

test('a failed save reverts the card and shows the error', async () => {
  const {Board} = harness({postImpl: () => ({ok: false, json: async () => ({error: 'choices.error.unknownOption'})})});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  addButton(card(root, 'marker')).click();
  await flush();
  assert.equal(addButton(card(root, 'marker')).textContent, he['effects.add']);
  assert.equal(findAll(root, hasClass('effects-status'))[0].textContent, he['choices.error.unknownOption']);
});

test('the 21st effect is refused with a message, nothing is posted', async () => {
  // a catalog bigger than the 20-per-video limit (the shipped one has 18)
  const big = [...EFFECTS, ...[1, 2, 3, 4].map(n => ({...EFFECTS[0], id: 'extra' + n, demo: 'extra' + n}))];
  const twenty = big.slice(0, 20).map(e => ({effect: e.id, when: ''}));
  const {Board, posts} = harness({initialChoices: {effects: twenty}, effects: big});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  tab(root, 'fx').click();
  const notChosen = big.find(e => !twenty.some(t => t.effect === e.id));
  addButton(card(root, notChosen.id)).click();
  await flush();
  assert.equal(posts.length, 0);
  assert.equal(findAll(root, hasClass('effects-status'))[0].textContent, he['effects.limit']);
});

test('without a project: "add" asks which video, then saves into it and remembers it in the hash', async () => {
  const {Board, posts, document, replaced, gets} = harness({projects: [{id: 'demo', title: 'הסרטון שלי'}, {id: 'other', title: 'אחר'}]});
  const root = makeNode('section');
  Board.mount(root, null);
  await flush();
  assert.match(text(findAll(root, hasClass('effects-tray'))[0]), new RegExp(he['effects.tray.noProject']));
  whenInput(card(root, 'kinetic')).value = 'לא';
  addButton(card(root, 'kinetic')).click();
  await flush();
  const dialog = findAll(document.body, n => n.tagName === 'DIALOG')[0];
  assert.equal(dialog.open, true);
  const options = findAll(dialog, hasClass('fx-picker-item'));
  assert.deepEqual(options.map(o => o.dataset.project), ['demo', 'other']);
  assert.equal(posts.length, 0);
  options[1].click();
  await flush();
  assert.equal(dialog.open, false);
  assert.deepEqual(replaced, ['#effects?project=other']);
  assert.ok(gets.includes('/choices?project=other'));
  assert.deepEqual(posts.at(-1), {project: 'other', effects: [{effect: 'kinetic', when: 'לא'}]});
  assert.match(text(findAll(root, hasClass('effects-target'))[0]), /אחר/);
});

test('the picker offers a new video when there are no projects', async () => {
  const {Board, document} = harness({projects: []});
  const root = makeNode('section');
  Board.mount(root, null);
  await flush();
  addButton(card(root, 'kinetic')).click();
  await flush();
  const dialog = findAll(document.body, n => n.tagName === 'DIALOG')[0];
  assert.match(text(dialog), new RegExp(he['effects.picker.empty']));
  const start = findAll(dialog, n => n.attributes && 'data-new-video' in n.attributes)[0];
  assert.ok(start);
  start.click();
  assert.equal(dialog.open, false);
});

test('demos: with motion off every card draws a still; leaving stops live ones; hidden tab pauses', async () => {
  const {Board, window, document} = harness();
  const calls = [];
  const live = [];
  const demos = {};
  for (const item of [...EFFECTS, ...LOOKS]) {
    demos[item.demo] = async (stage, ctx) => { calls.push({id: item.demo, still: ctx.still}); if (!ctx.still) live.push(ctx); };
  }
  Object.defineProperty(demos, 'context', {value: ({still} = {}) => {
    const ctx = {still: !!still, cancelled: false, cancel() { this.cancelled = true; }, wait: () => new Promise(() => {})};
    // live: the start delay resolves, then the demo plays once and the loop gap never ends
    if (!still) { let waits = 0; ctx.wait = () => (waits++ ? new Promise(() => {}) : Promise.resolve()); }
    return ctx;
  }});
  Object.defineProperty(demos, 'CANCELLED', {value: 'x'});
  window.FxDemos = demos;
  const root = makeNode('section');
  Board.setMotion('off');
  Board.mount(root, 'demo');
  await flush();
  assert.equal(calls.filter(c => c.still).length, EFFECTS.length);
  assert.equal(calls.filter(c => !c.still).length, 0);
  assert.match(findAll(root, hasClass('effects-note'))[0].textContent, new RegExp(he['effects.motionOff']));
  Board.setMotion('always'); // no IntersectionObserver in the sandbox: every card counts as visible
  await flush();
  assert.ok(live.length >= EFFECTS.length);
  const running = live.filter(ctx => !ctx.cancelled).length;
  assert.ok(running > 0);
  document.hidden = true;
  document._listeners.visibilitychange.forEach(fn => fn());
  assert.equal(live.filter(ctx => !ctx.cancelled).length, 0);
  document.hidden = false;
  Board.leave();
  assert.equal(live.filter(ctx => !ctx.cancelled).length, 0);
});

test('no demo (live or still) plays before FxDemos.presenterReady resolves, so the presenter never flashes an empty stage', async () => {
  const {Board, window} = harness();
  const calls = [];
  const demos = {};
  for (const item of [...EFFECTS, ...LOOKS]) {
    demos[item.demo] = async (_stage, ctx) => { calls.push({id: item.demo, still: ctx.still}); };
  }
  Object.defineProperty(demos, 'context', {value: ({still} = {}) => {
    const ctx = {still: !!still, cancelled: false, cancel() { this.cancelled = true; }, wait: () => new Promise(() => {})};
    // live: the start delay resolves once, then the loop gap never ends (one play per card)
    if (!still) { let waits = 0; ctx.wait = () => (waits++ ? new Promise(() => {}) : Promise.resolve()); }
    return ctx;
  }});
  Object.defineProperty(demos, 'CANCELLED', {value: 'x'});
  let resolvePresenter;
  Object.defineProperty(demos, 'presenterReady', {value: new Promise(resolve => { resolvePresenter = resolve; })});
  window.FxDemos = demos;
  const root = makeNode('section');
  Board.setMotion('always'); // no IntersectionObserver in the sandbox: every card counts as visible
  Board.mount(root, 'demo');
  await flush();
  assert.equal(calls.length, 0, 'no demo plays while the presenter photo is still decoding');
  resolvePresenter();
  await flush();
  assert.ok(calls.length > 0, 'demos play once the presenter has decoded');
});

test('wiring: "אפקטים" sits in the nav between השראה and איך זה עובד, with its own screen, scripts and route', () => {
  const html = readFileSync(join(__dirname, 'dist/index.html'), 'utf8');
  const nav = html.slice(html.indexOf('<nav class="studio-nav"'), html.indexOf('</nav>'));
  const order = ['data-section="projects"', 'data-section="library"', 'data-section="effects"', 'data-section="guide"'].map(s => nav.indexOf(s));
  assert.ok(order.every(i => i >= 0), 'all four nav links exist');
  assert.deepEqual([...order].sort((a, b) => a - b), order, 'nav order');
  assert.match(nav, /<a href="#effects" data-section="effects" data-i18n="app.nav.effects">/);
  assert.match(html, /<section id="effects-page"[^>]*hidden><\/section>/);
  for (const file of ['fx-demos.js', 'effects-ui.js']) assert.match(html, new RegExp('<script src="' + file.replace('.', '\.') + '" defer></script>'));
  assert.match(html, /<link rel="stylesheet" href="effects\.css">/);
  assert.equal(he['app.nav.effects'], 'אפקטים');
  const studio = readFileSync(join(__dirname, 'dist/studio.js'), 'utf8');
  assert.match(studio, /hash==='effects'\|\|hash\.startsWith\('effects\?'\)/);
  assert.match(studio, /EffectsBoard\?\.mount\(\$\('#effects-page'\)/);
  assert.match(studio, /if\(next!=='effects'\)window\.EffectsBoard\?\.leave\(\)/);
  const release = readFileSync(join(__dirname, '..', 'release-files.txt'), 'utf8').split(/\r?\n/);
  for (const file of ['effects/effects.json', 'looks/presenter.json', 'style-library/effects.py', 'style-library/dist/fx-demos.js',
    'style-library/dist/effects-ui.js', 'style-library/dist/effects.css']) assert.ok(release.includes(file), 'release-files.txt lists ' + file);
});

test('add buttons say their state in the label only (no aria-pressed)', async () => {
  const {Board} = harness({initialChoices: {effects: [{effect: 'marker', when: ''}]}});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  for (const c of cardsIn(root)) assert.equal(addButton(c).getAttribute('aria-pressed'), undefined);
  assert.equal(addButton(card(root, 'marker')).textContent, he['effects.added']);
});

test('tabs: tablist/tabpanel wiring and arrow-key roving (RTL: ArrowLeft moves forward)', async () => {
  const {Board} = harness();
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  const grid = findAll(root, hasClass('effects-grid'))[0];
  assert.equal(grid.getAttribute('role'), 'tabpanel');
  const fx = tab(root, 'fx');
  assert.equal(fx.getAttribute('role'), 'tab');
  assert.equal(fx.getAttribute('aria-controls'), grid.id);
  assert.equal(grid.getAttribute('aria-labelledby'), fx.id);
  assert.equal(fx.tabIndex, 0);
  assert.equal(tab(root, 'look').tabIndex, -1);
  let prevented = false;
  fx.dispatch('keydown', {key: 'ArrowLeft', preventDefault() { prevented = true; }});
  assert.ok(prevented);
  const look = tab(root, 'look');
  assert.equal(look.getAttribute('aria-selected'), 'true');
  assert.equal(look.focused, true);
  assert.equal(cardsIn(root).length, LOOKS.length);
  look.dispatch('keydown', {key: 'Home', preventDefault() {}});
  assert.equal(tab(root, 'fx').getAttribute('aria-selected'), 'true');
});

test('a change of the system reduced-motion setting redraws the cards', async () => {
  const {Board, window, motionQuery} = harness({reduced: false});
  const calls = [];
  const demos = {};
  for (const item of [...EFFECTS, ...LOOKS]) demos[item.demo] = async (stage, ctx) => { calls.push(ctx.still); };
  Object.defineProperty(demos, 'context', {value: ({still} = {}) => ({still: !!still, cancelled: false, cancel() { this.cancelled = true; }, wait: () => new Promise(() => {})})});
  window.FxDemos = demos;
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  assert.equal(calls.filter(Boolean).length, 0);
  motionQuery.matches = true;
  motionQuery.listeners.forEach(fn => fn({matches: true}));
  await flush();
  assert.equal(calls.filter(Boolean).length, EFFECTS.length);
  Board.leave();
});

test('a pending "when" save is dropped when the board is left', async () => {
  const {Board, posts, timers} = harness({initialChoices: {effects: [{effect: 'marker', when: ''}]}});
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  const input = whenInput(card(root, 'marker'));
  input.value = 'מילה';
  input.dispatch('input');
  Board.leave();
  timers.splice(0).forEach(t => t.fn());
  await flush();
  assert.equal(posts.length, 0);
});

test('the "when" word is saved verbatim (trim and 80 characters only), arrows and markers included', async () => {
  const {Board, posts} = harness();
  const root = makeNode('section');
  Board.mount(root, 'demo');
  await flush();
  whenInput(card(root, 'marker')).value = '  לפני --> אחרי <!-- x  ';
  addButton(card(root, 'marker')).click();
  await flush();
  assert.deepEqual(posts.at(-1), {project: 'demo', effects: [{effect: 'marker', when: 'לפני --> אחרי <!-- x'}]});
});
