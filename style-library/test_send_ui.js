/* Task 15: "שליחה לקלוד" (Send to Claude) with live progress and the quiet "או העתקה לצ׳אט"
   fallback. A vm-sandbox unit test in the same style as test_choices_ui.js / test_materials_ui.js.
   Run with: node --test style-library/test_send_ui.js (no browser or packages needed).

   Part 1 covers SendUI.view(status), the pure mapping from a runner status to what the card
   shows. Part 2 mounts the card on a tiny fake DOM with a scripted fetch, fake timers, a fake
   clipboard and a fake document.hidden, to cover polling, reload resume, cancel, and the copy
   fallbacks. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/send-ui.js'), 'utf8');
const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));
const en = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));

function i18nStub(lang = 'he') {
  const strings = lang === 'he' ? he : en;
  return {
    lang: () => lang,
    t(key, vars) {
      const value = strings[key] ?? key;
      if (!vars) return value;
      return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value);
    },
  };
}

// ---------------------------------------------------------------- fake DOM

function makeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, _root: false,
    dataset: {}, style: {}, attributes: {}, _classes: new Set(), _listeners: {},
    hidden: false, disabled: false, value: '', textContent: '', focused: false, selected: false,
    get isConnected() { let n = this; while (n) { if (n._root) return true; n = n.parentNode; } return false; },
    get className() { return [...this._classes].join(' '); },
    set className(v) { this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); },
    get classList() {
      const self = this;
      return {
        add: (...c) => c.forEach(x => self._classes.add(x)), remove: (...c) => c.forEach(x => self._classes.delete(x)),
        contains: c => self._classes.has(c),
        toggle: (c, force) => { const on = force !== undefined ? force : !self._classes.has(c); if (on) self._classes.add(c); else self._classes.delete(c); return on; },
      };
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; },
    removeAttribute(name) { delete this.attributes[name]; },
    append(...nodes) { nodes.forEach(n => { if (n.parentNode) n.remove(); n.parentNode = this; this.children.push(n); }); },
    replaceChildren(...nodes) { this.children.forEach(n => { n.parentNode = null; }); this.children = []; this.append(...nodes); },
    remove() {
      if (!this.parentNode) return;
      const i = this.parentNode.children.indexOf(this);
      if (i !== -1) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    },
    focus() { this.focused = true; },
    select() { this.selected = true; },
    scrollIntoView() {},
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    dispatch(type, evt = {}) { (this._listeners[type] || []).slice().forEach(fn => fn({preventDefault() {}, target: this, ...evt})); },
    click() { if (!this.disabled) this.dispatch('click'); },
  };
  return node;
}

function findAll(root, predicate) {
  const out = [];
  (function walk(n) { if (!n) return; if (predicate(n)) out.push(n); (n.children || []).forEach(walk); })(root);
  return out;
}
const byClass = cls => n => n._classes && n._classes.has(cls);
const find = (root, cls) => findAll(root, byClass(cls))[0] || null;
const visible = node => { let n = node; while (n) { if (n.hidden) return false; n = n.parentNode; } return true; };

// ---------------------------------------------------------------- harness

function harness(options = {}) {
  const fetchCalls = [];
  const routes = options.routes || {};
  const timers = [];
  let timerId = 0;
  const docListeners = {};
  const clipboardWrites = [];
  const refreshCalls = [];
  const routeCalls = [];
  const document = {
    hidden: false,
    documentElement: makeNode('html'),
    createElement: tag => makeNode(tag),
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
  };
  async function fetchImpl(url, init = {}) {
    const method = (init.method || 'GET').toUpperCase();
    const call = {url, method, headers: init.headers || {}, body: init.body ? JSON.parse(init.body) : undefined};
    fetchCalls.push(call);
    const path = url.split('?')[0];
    const handler = routes[method + ' ' + path] || routes[method + ' ' + url];
    if (!handler) return {ok: false, status: 404, json: async () => ({error: 'not-routed'})};
    const result = await handler(call);
    if (result instanceof Error) throw result;
    const status = result.status || 200;
    return {ok: status >= 200 && status < 300, status, json: async () => result.body};
  }
  const context = {
    I18N: i18nStub(options.lang || 'he'),
    document,
    navigator: {clipboard: {writeText: async text => { clipboardWrites.push(text); if (options.clipboardFails) throw Error('denied'); }}},
    fetch: fetchImpl,
    setTimeout: (fn, ms) => { const id = ++timerId; timers.push({id, fn, ms}); return id; },
    clearTimeout: id => { const i = timers.findIndex(t => t.id === id); if (i !== -1) timers.splice(i, 1); },
    Date: {now: () => (options.now || 1_000_000) * 1000},
    console,
    JSON, Math, Number, String, Array, Object, Map, Set, Promise, Error, TypeError, encodeURIComponent, isFinite,
  };
  context.window = context;
  context.Studio = {refresh: force => { refreshCalls.push(force); }, route: () => { routeCalls.push(true); }};
  context.history = {replaceState() {}};
  context.location = {hash: ''};
  vm.createContext(context);
  vm.runInContext(source, context);
  const page = makeNode('div');
  page._root = true;
  const el = makeNode('div');
  page.append(el);
  return {
    context, document, el, page, fetchCalls, timers, clipboardWrites, refreshCalls, routeCalls,
    SendUI: context.SendUI,
    // Fire every currently pending timer once (a "2 s later" tick), then let promises settle.
    async tick() { const due = timers.splice(0); due.forEach(t => t.fn()); await settle(); },
    setHidden(value) { document.hidden = value; (docListeners.visibilitychange || []).forEach(fn => fn()); },
  };
}

const settle = async () => { for (let i = 0; i < 20; i++) await new Promise(resolve => setImmediate(resolve)); };

const STEPS = [
  {key: 'transcribe', state: 'done', detail: '1,284 מילים'},
  {key: 'cut', state: 'running'},
  {key: 'captions', state: 'todo'},
];

// ================================================================ Part 1: view()

test('view: running shows each step done / running / todo with Hebrew labels and a stop button', () => {
  const {SendUI} = harness();
  const v = SendUI.view({state: 'running', steps: STEPS, started: 1_000_000 - 200}, {now: 1_000_000});
  assert.deepEqual(v.steps.map(s => [s.key, s.state, s.label]), [
    ['transcribe', 'done', he['claude.step.transcribe']],
    ['cut', 'running', he['claude.step.cut']],
    ['captions', 'todo', he['claude.step.captions']],
  ]);
  assert.deepEqual(v.steps.map(s => s.number), [1, 2, 3]);
  assert.equal(v.steps[0].detail, '1,284 מילים');
  assert.equal(v.primary.action, 'cancel');
  assert.equal(v.primary.label, 'עצירה');
  assert.equal(v.secondary, null);
  assert.equal(v.support, null);
  assert.equal(v.running, true);
  assert.equal(v.title, he['claude.title.running']);
  assert.equal(v.label, he['claude.state.running'].replace('{step}', he['claude.step.cut']));
  assert.ok(v.progress > 1 / 3 && v.progress < 2 / 3, 'one done + one running of three');
  assert.equal(v.elapsed, he['claude.elapsed'].replace('{time}', he['claude.elapsed.minutes'].replace('{n}', '3')));
});

test('view: running with no steps yet says Claude is getting started (no progress number)', () => {
  const {SendUI} = harness();
  const v = SendUI.view({state: 'running', steps: []});
  assert.equal(v.label, he['claude.state.gettingStarted']);
  assert.equal(v.progress, null);
  assert.deepEqual(v.steps, []);
});

test('view: idle offers "שליחה לקלוד" with the quiet "או העתקה לצ׳אט" link', () => {
  const {SendUI} = harness();
  const v = SendUI.view(null);
  assert.deepEqual([v.primary.action, v.primary.label], ['send', 'שליחה לקלוד']);
  assert.deepEqual([v.secondary.action, v.secondary.label], ['copy', 'או העתקה לצ׳אט']);
  assert.equal(v.running, false);
  assert.equal(v.title, he['claude.title.idle']);
});

test('view: claude-missing makes "העתקה לצ׳אט" the primary action (no retry, no support link)', () => {
  const {SendUI} = harness();
  const v = SendUI.view({state: 'failed', message_key: 'claude-missing'});
  assert.deepEqual([v.primary.action, v.primary.label], ['copy', 'העתקה לצ׳אט']);
  assert.equal(v.secondary, null);
  assert.equal(v.support, null);
  assert.equal(v.label, he['claude-missing']);
});

test('view: an unknown project kind also falls back to copy as the primary action', () => {
  const {SendUI} = harness();
  assert.equal(SendUI.view({state: 'failed', message_key: 'claude.unknown-kind'}).primary.action, 'copy');
});

test('view: failed shows the translated message, "לנסות שוב", "העתקה לצ׳אט" and the quiet support link', () => {
  const {SendUI} = harness();
  for (const key of ['claude.limit', 'claude.not-logged-in', 'claude.failed']) {
    const v = SendUI.view({job: 'a'.repeat(32), state: 'failed', message_key: key, steps: STEPS});
    assert.equal(v.label, he[key]);
    assert.deepEqual([v.primary.action, v.primary.label], ['retry', 'לנסות שוב']);
    assert.deepEqual([v.secondary.action, v.secondary.label], ['copy', 'העתקה לצ׳אט']);
    assert.deepEqual([v.support.action, v.support.label], ['support', 'העתקת פרטים לתמיכה']);
    assert.equal(v.title, he['claude.title.failed']);
  }
});

test('view: a failure with no message key reads as the generic claude.failed text', () => {
  const {SendUI} = harness();
  assert.equal(SendUI.view({job: 'a'.repeat(32), state: 'failed', message_key: null}).label, he['claude.failed']);
});

test('view: failed before a job existed has no support link (there is no log to copy)', () => {
  const {SendUI} = harness();
  assert.equal(SendUI.view({state: 'failed', message_key: 'claude.failed'}).support, null);
});

test('view: stopped shows "נעצר — …" and offers to try again', () => {
  const {SendUI} = harness();
  const v = SendUI.view({job: 'a'.repeat(32), state: 'stopped', steps: STEPS});
  assert.ok(v.label.startsWith('נעצר — '), v.label);
  assert.ok(v.label.includes('לנסות שוב'));
  assert.equal(v.primary.action, 'retry');
  assert.equal(v.secondary.action, 'copy');
  assert.equal(v.running, false);
});

test('view: done opens the new version; learn-style says the card is ready', () => {
  const {SendUI} = harness();
  const v = SendUI.view({state: 'done', steps: STEPS.map(s => ({...s, state: 'done'}))});
  assert.equal(v.primary.action, 'review');
  assert.equal(v.primary.label, he['claude.review']);
  assert.equal(v.progress, 1);
  assert.equal(v.label, he['claude.state.done']);
  const style = SendUI.view({state: 'done', steps: []}, {task: 'learn-style'});
  assert.equal(style.label, he['claude.state.doneStyle']);
  assert.equal(style.primary, null);
});

test('view: unknown step keys show the key itself; a matting step shows its percentage detail', () => {
  const {SendUI} = harness();
  const v = SendUI.view({state: 'running', steps: [{key: 'matte', state: 'running', detail: '42%'}, {key: 'mystery-step', state: 'todo'}]});
  assert.equal(v.steps[0].label, he['claude.step.matte']);
  assert.equal(v.steps[0].detail, '42%');
  assert.equal(v.steps[1].label, 'mystery-step');
});

test('view: follows the UI language (English)', () => {
  const {SendUI} = harness({lang: 'en'});
  assert.equal(SendUI.view(null).primary.label, 'Send to Claude');
  assert.equal(SendUI.view({state: 'running', steps: STEPS}).primary.label, 'Stop');
});

test('elapsed: under a minute, minutes, and hours', () => {
  const {SendUI} = harness();
  assert.equal(SendUI.elapsed(20), he['claude.elapsed.under']);
  assert.equal(SendUI.elapsed(65), he['claude.elapsed.oneMinute']);
  assert.equal(SendUI.elapsed(25 * 60 + 5), he['claude.elapsed.minutes'].replace('{n}', '25'));
  assert.equal(SendUI.elapsed(3600 + 7 * 60), he['claude.elapsed.hours'].replace('{h}', '1').replace('{mm}', '07'));
});

test('readableLog turns stream-json into short plain lines (assistant text and tool calls)', () => {
  const {SendUI} = harness();
  const log = [
    JSON.stringify({type: 'system', subtype: 'init'}),
    JSON.stringify({type: 'assistant', message: {content: [{type: 'text', text: 'Transcribing the take now.\nMore.'}]}}),
    JSON.stringify({type: 'assistant', message: {content: [{type: 'tool_use', name: 'Bash', input: {command: 'ffmpeg -i raw.mp4 -af silencedetect out.wav'}}]}}),
    JSON.stringify({type: 'user', message: {content: [{type: 'tool_result', content: 'x'.repeat(500)}]}}),
    'plain stderr line',
  ].join('\n');
  assert.deepEqual([...SendUI.readableLog(log, 10)], [
    'Transcribing the take now.',
    'Bash · ffmpeg -i raw.mp4 -af silencedetect out.wav',
    'plain stderr line',
  ]);
  assert.equal(SendUI.readableLog(log, 2).length, 2);
});

test('every runner message key and every step key has Hebrew and English text', () => {
  const {SendUI} = harness();
  const keys = [...SendUI.MESSAGE_KEYS, ...SendUI.STEP_KEYS.map(k => 'claude.step.' + k)];
  for (const key of ['claude.not-logged-in', 'claude.limit', 'claude.failed', 'claude-missing', 'busy',
    'claude.invalid-request', 'claude.unknown-project', 'claude.unknown-reference', 'claude.unknown-job', 'claude.unknown-kind'])
    assert.ok(SendUI.MESSAGE_KEYS.includes(key), key);
  for (const key of ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard', 'voice', 'scenes', 'watch', 'analyze', 'card'])
    assert.ok(SendUI.STEP_KEYS.includes(key), key);
  for (const key of keys) {
    assert.ok(typeof he[key] === 'string' && he[key], 'he.json: ' + key);
    assert.ok(typeof en[key] === 'string' && en[key], 'en.json: ' + key);
  }
});

// ================================================================ Part 2: mount()

const JOB = 'c'.repeat(32);

function running(steps = STEPS) { return {job: JOB, state: 'running', steps, message_key: null, started: 1_000_000 - 30}; }

test('mount: an idle project shows the send button and the quiet copy link, and asks for a running job', async () => {
  const h = harness({routes: {'GET /claude-job': () => ({body: {job: null}})}});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  assert.equal(h.fetchCalls[0].url, '/claude-job?project=reel-one');
  const primary = find(h.el, 'send-primary'), quiet = find(h.el, 'send-copy');
  assert.equal(primary.textContent, 'שליחה לקלוד');
  assert.equal(quiet.textContent, 'או העתקה לצ׳אט');
  assert.ok(visible(quiet));
  assert.equal(visible(find(h.el, 'send-progress')), false);
  assert.equal(h.timers.length, 0, 'nothing to poll');
});

test('send: posts the job, polls every 2 s while running, and refreshes the project when done', async () => {
  let polls = 0;
  const h = harness({routes: {
    'GET /claude-job': call => {
      if (call.url.includes('project=')) return {body: {job: null}};
      polls++;
      return {body: polls < 2 ? running() : {...running(STEPS.map(s => ({...s, state: 'done'}))), state: 'done'}};
    },
    'POST /claude-job': () => ({status: 202, body: {job: JOB}}),
    'GET /claude-job-log': () => ({body: {log: JSON.stringify({type: 'assistant', message: {content: [{type: 'text', text: 'Cutting silences'}]}})}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  find(h.el, 'send-primary').click();
  await settle();
  const post = h.fetchCalls.find(c => c.method === 'POST');
  assert.equal(post.url, '/claude-job');
  assert.deepEqual(post.body, {project: 'reel-one', task: 'edit'});
  assert.equal(post.headers['X-Studio-Action'], 'claude-job');
  assert.ok(visible(find(h.el, 'send-progress')));
  assert.deepEqual(h.timers.map(t => t.ms), [2000]);

  await h.tick(); // first poll: running
  assert.equal(h.fetchCalls.filter(c => c.url === '/claude-job?id=' + JOB).length, 1);
  const items = findAll(h.el, byClass('send-step'));
  assert.deepEqual(items.map(n => n.dataset.state), ['done', 'running', 'todo']);
  assert.equal(find(h.el, 'send-step-label').textContent, he['claude.step.transcribe']);
  assert.equal(find(h.el, 'send-primary').textContent, 'עצירה');
  assert.equal(find(h.el, 'send-note').textContent, he['claude.closeNote']);
  assert.ok(find(h.el, 'send-elapsed').textContent.length > 0);
  assert.equal(find(h.el, 'send-log').textContent, 'Cutting silences');
  assert.deepEqual(h.timers.map(t => t.ms), [2000]);

  assert.equal(h.fetchCalls.filter(c => c.url.startsWith('/claude-job-log')).length, 1, 'log preview every other poll');
  await h.tick(); // second poll: done
  assert.deepEqual(h.refreshCalls, [true]);
  assert.equal(h.timers.length, 0, 'polling stops when done');
  assert.equal(find(h.el, 'send-primary').textContent, he['claude.review']);
});

test('a running job survives a page reload: mount asks the server and resumes polling', async () => {
  const h = harness({routes: {
    'GET /claude-job': call => ({body: running()}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  assert.ok(visible(find(h.el, 'send-progress')));
  assert.equal(find(h.el, 'send-primary').textContent, 'עצירה');
  assert.deepEqual(h.timers.map(t => t.ms), [2000]);
  await h.tick();
  assert.ok(h.fetchCalls.some(c => c.url === '/claude-job?id=' + JOB));
});

test('an old finished job (done, or failed over 12 h ago) is not shown again on a fresh page load', async () => {
  for (const body of [{job: JOB, state: 'failed', message_key: 'claude.limit', steps: [], started: 1_000_000 - 13 * 3600},
    {job: JOB, state: 'done', message_key: null, steps: [], started: 1_000_000 - 60}]) {
    const h = harness({routes: {'GET /claude-job': () => ({body})}});
    h.SendUI.mount(h.el, 'reel-one');
    await settle();
    assert.equal(find(h.el, 'send-primary').textContent, 'שליחה לקלוד', body.state);
    assert.equal(h.timers.length, 0);
  }
});

test('a job that failed or stopped while the window was closed (under 12 h) is shown on reload', async () => {
  for (const [state, key] of [['failed', 'claude.limit'], ['stopped', null]]) {
    const h = harness({routes: {'GET /claude-job': () => ({body: {job: JOB, state, message_key: key, steps: STEPS, started: 1_000_000 - 3 * 3600}})}});
    h.SendUI.mount(h.el, 'reel-one');
    await settle();
    assert.equal(find(h.el, 'send-primary').textContent, 'לנסות שוב', state);
    assert.equal(find(h.el, 'send-copy').textContent, 'העתקה לצ׳אט');
    assert.equal(find(h.el, 'send-message').textContent, state === 'failed' ? he['claude.limit'] : he['claude.stopped']);
    assert.equal(h.timers.length, 0);
  }
});

test('polling stops while the tab is hidden and resumes when it is visible again', async () => {
  const h = harness({routes: {'GET /claude-job': () => ({body: running()}), 'GET /claude-job-log': () => ({body: {log: ''}})}});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  assert.equal(h.timers.length, 1);
  h.setHidden(true);
  assert.equal(h.timers.length, 0, 'hidden: pending poll cleared');
  await h.tick();
  const before = h.fetchCalls.length;
  h.setHidden(false);
  await settle();
  assert.ok(h.fetchCalls.slice(before).some(c => c.url === '/claude-job?id=' + JOB), 'visible: polls right away');
  assert.equal(h.timers.length, 1, 'and keeps polling');
});

test('cancel ("עצירה") posts the cancel request, shows stopped, and stops polling', async () => {
  const h = harness({routes: {
    'GET /claude-job': () => ({body: running()}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
    'POST /claude-job-cancel': () => ({body: {...running(), state: 'stopped'}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  find(h.el, 'send-primary').click();
  await settle();
  const post = h.fetchCalls.find(c => c.method === 'POST');
  assert.equal(post.url, '/claude-job-cancel');
  assert.deepEqual(post.body, {job: JOB});
  assert.equal(post.headers['X-Studio-Action'], 'claude-job-cancel');
  assert.ok(find(h.el, 'send-message').textContent.startsWith('נעצר — '));
  assert.equal(find(h.el, 'send-primary').textContent, 'לנסות שוב');
  assert.equal(h.timers.length, 0);
});

test('copy to chat: fetches the project request in the UI language and copies it', async () => {
  const h = harness({routes: {
    'GET /claude-job': () => ({body: {job: null}}),
    'GET /claude-request': () => ({body: {text: '/talking-head projects/reel-one\nענו בעברית.'}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  find(h.el, 'send-copy').click();
  await settle();
  assert.ok(h.fetchCalls.some(c => c.url === '/claude-request?project=reel-one'));
  assert.deepEqual(h.clipboardWrites, ['/talking-head projects/reel-one\nענו בעברית.']);
  assert.equal(find(h.el, 'send-status').textContent, he['claude.copied']);
  assert.equal(visible(find(h.el, 'send-fallback')), false);
});

test('copy to chat: when the clipboard is blocked, the text appears selected for manual copying', async () => {
  const h = harness({clipboardFails: true, routes: {
    'GET /claude-job': () => ({body: {job: null}}),
    'GET /claude-request': () => ({body: {text: 'the request'}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  find(h.el, 'send-copy').click();
  await settle();
  const fallback = find(h.el, 'send-fallback'), area = findAll(fallback, n => n.tagName === 'TEXTAREA')[0];
  assert.ok(visible(fallback));
  assert.equal(area.value, 'the request');
  assert.ok(area.selected && area.focused);
  assert.equal(find(h.el, 'send-status').textContent, he['claude.copyManual']);
});

test('claude-missing on send turns the primary button into copy-to-chat', async () => {
  const h = harness({routes: {
    'GET /claude-job': () => ({body: {job: null}}),
    'POST /claude-job': () => ({status: 409, body: {error: 'claude-missing'}}),
    'GET /claude-request': () => ({body: {text: 'req'}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  find(h.el, 'send-primary').click();
  await settle();
  assert.equal(find(h.el, 'send-message').textContent, he['claude-missing']);
  assert.equal(find(h.el, 'send-primary').textContent, 'העתקה לצ׳אט');
  assert.equal(visible(find(h.el, 'send-copy')), false);
  find(h.el, 'send-primary').click();
  await settle();
  assert.deepEqual(h.clipboardWrites, ['req']);
});

test('busy on send resumes the job that is already running', async () => {
  let lookups = 0;
  const h = harness({routes: {
    'GET /claude-job': call => (call.url.includes('project=') && lookups++ === 0 ? {body: {job: null}} : {body: running()}),
    'POST /claude-job': () => ({status: 409, body: {error: 'busy'}}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  find(h.el, 'send-primary').click();
  await settle();
  assert.equal(find(h.el, 'send-primary').textContent, 'עצירה');
  assert.equal(h.timers.length, 1);
});

test('failure: the quiet support link copies the last 40 log lines of that job', async () => {
  let polls = 0;
  const h = harness({routes: {
    'GET /claude-job': call => (call.url.includes('project=') ? {body: running()} :
      (++polls, {body: {...running(), state: 'failed', message_key: 'claude.limit'}})),
    'GET /claude-job-log': call => ({body: {log: call.url.includes('lines=40') ? 'line 1\nline 2' : ''}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  await h.tick();
  assert.equal(find(h.el, 'send-message').textContent, he['claude.limit']);
  assert.equal(find(h.el, 'send-primary').textContent, 'לנסות שוב');
  assert.equal(find(h.el, 'send-copy').textContent, 'העתקה לצ׳אט');
  const support = find(h.el, 'send-support');
  assert.ok(visible(support));
  assert.equal(support.textContent, 'העתקת פרטים לתמיכה');
  assert.equal(h.timers.length, 0, 'failed: polling stops');
  support.click();
  await settle();
  assert.ok(h.fetchCalls.some(c => c.url === `/claude-job-log?id=${JOB}&lines=40`));
  assert.deepEqual(h.clipboardWrites, [he['claude.supportNote'] + '\n\nline 1\nline 2']);
  assert.equal(find(h.el, 'send-status').textContent, he['claude.supportCopied']);
});

test('failure: when the job left no log, the support link says so instead of copying', async () => {
  const h = harness({routes: {
    'GET /claude-job': call => (call.url.includes('project=') ? {body: running()} : {body: {...running(), state: 'failed', message_key: 'claude.failed'}}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  await h.tick();
  find(h.el, 'send-support').click();
  await settle();
  assert.deepEqual(h.clipboardWrites, []);
  assert.equal(find(h.el, 'send-status').textContent, he['claude.supportEmpty']);
});

test('remount while running, then the job ends: the new card picks up the end state (no stuck "running")', async () => {
  let jobState = 'running';
  const h = harness({routes: {
    'GET /claude-job': call => ({body: jobState === 'running' ? running() : {...running(STEPS.map(s => ({...s, state: 'done'}))), state: jobState}}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  // The old card's poll goes out and would carry "done", but the page re-renders (language
  // switch / auto-refresh) before it lands, so that answer is dropped.
  jobState = 'done';
  h.timers.splice(0).forEach(t => t.fn());
  const second = makeNode('div');
  h.page.append(second);
  h.el.remove();
  h.SendUI.mount(second, 'reel-one');
  await settle();
  assert.equal(second.children[0].dataset.state, 'done');
  assert.equal(find(second, 'send-primary').textContent, he['claude.review']);
  assert.deepEqual(h.refreshCalls, [true]);
  assert.equal(h.timers.length, 0);
});

test('after done, the card the refreshed page renders is cleared back to send (with a short note)', async () => {
  const h = harness({routes: {
    'GET /claude-job': call => (call.url.includes('project=') ? {body: running()} : {body: {...running(), state: 'done'}}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
  }});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  await h.tick();
  assert.equal(find(h.el, 'send-primary').textContent, he['claude.review']);
  // Studio.refresh(true) re-rendered the project page with the new version: a fresh mount.
  const second = makeNode('div');
  h.page.append(second);
  h.el.remove();
  h.SendUI.mount(second, 'reel-one');
  await settle();
  assert.equal(find(second, 'send-primary').textContent, 'שליחה לקלוד');
  assert.equal(find(second, 'send-status').textContent, he['claude.state.done']);
  const third = makeNode('div');
  h.page.append(third);
  second.remove();
  h.SendUI.mount(third, 'reel-one');
  await settle();
  assert.equal(find(third, 'send-status').textContent, '');
});

test('remounting the same project (language switch, page refresh) keeps a single poller', async () => {
  const h = harness({routes: {'GET /claude-job': () => ({body: running()}), 'GET /claude-job-log': () => ({body: {log: ''}})}});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  const second = makeNode('div');
  h.page.append(second);
  h.el.remove();
  h.SendUI.mount(second, 'reel-one');
  await settle();
  assert.equal(h.timers.length, 1);
  assert.equal(find(second, 'send-primary').textContent, 'עצירה');
});

test('leaving the project page stops polling', async () => {
  const h = harness({routes: {'GET /claude-job': () => ({body: running()}), 'GET /claude-job-log': () => ({body: {log: ''}})}});
  h.SendUI.mount(h.el, 'reel-one');
  await settle();
  h.el.remove();
  await h.tick();
  assert.equal(h.timers.length, 0);
});

test('learn-style mode posts the reference and copies the learn-style request', async () => {
  const h = harness({routes: {
    'GET /claude-job': () => ({body: {job: null}}),
    'POST /claude-job': () => ({status: 202, body: {job: JOB}}),
    'GET /claude-job-log': () => ({body: {log: ''}}),
  }});
  h.SendUI.mount(h.el, 'ref-one', {task: 'learn-style'});
  await settle();
  assert.equal(h.fetchCalls[0].url, '/claude-job?reference=ref-one');
  find(h.el, 'send-copy').click();
  await settle();
  assert.deepEqual(h.clipboardWrites, ['/learn-style references/ref-one\nענו בעברית.']);
  find(h.el, 'send-primary').click();
  await settle();
  assert.deepEqual(h.fetchCalls.find(c => c.method === 'POST').body, {reference: 'ref-one', task: 'learn-style'});
});
