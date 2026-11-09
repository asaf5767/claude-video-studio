/* Task 13: the Inspiration tab's style card (inspiration-ui.js) and the reference demo's
   moment list (app.js). vm sandbox with a tiny generic fake DOM, the same approach as
   test_materials_ui.js; no browser or packages needed. Learning a style runs through the
   studio's one Send-to-Claude card (send-ui.js, loaded into the same sandbox; final review I3). */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/inspiration-ui.js'), 'utf8');
const sendSource = readFileSync(join(__dirname, 'dist/send-ui.js'), 'utf8');
const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));

function i18nStub() {
  return {
    lang: () => 'he',
    t(key, vars) {
      const value = he[key] ?? key;
      if (!vars) return value;
      return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value);
    },
  };
}

function makeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, dataset: {}, style: {}, attributes: {},
    _classes: new Set(), _listeners: {}, isConnected: true, disabled: false, hidden: false, checked: false,
    required: false, readOnly: false, value: '', textContent: '', open: false,
    get className() { return [...this._classes].join(' '); },
    set className(v) { this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); },
    get classList() {
      const self = this;
      return {add: (...c) => c.forEach(x => self._classes.add(x)), remove: (...c) => c.forEach(x => self._classes.delete(x)),
        contains: c => self._classes.has(c), toggle: (c, on) => { const want = on === undefined ? !self._classes.has(c) : !!on; if (want) self._classes.add(c); else self._classes.delete(c); }};
    },
    setAttribute(name, value) { this.attributes[name] = String(value); if (name === 'id') this.id = String(value); },
    getAttribute(name) { return this.attributes[name]; },
    removeAttribute(name) { delete this.attributes[name]; },
    append(...nodes) { nodes.forEach(n => { if (typeof n === 'string') { const t = makeNode('#text'); t.textContent = n; n = t; } n.parentNode = this; this.children.push(n); }); },
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); },
    remove() { if (this.parentNode) this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1); this.parentNode = null; },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    dispatch(type, evt = {}) { (this._listeners[type] || []).slice().forEach(fn => fn({preventDefault() {}, target: this, ...evt})); },
    click() { this.dispatch('click'); },
    focus() {}, select() {}, close() { this.open = false; this.dispatch('close'); },
    get text() { return this.textContent + this.children.map(c => c.text).join(''); },
  };
  return node;
}
function findAll(root, predicate) {
  const out = [];
  (function walk(n) { if (!n) return; if (predicate(n)) out.push(n); (n.children || []).forEach(walk); })(root);
  return out;
}
const find = (root, predicate) => findAll(root, predicate)[0] || null;
const byClass = cls => n => n._classes && n._classes.has(cls);
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 20; i++) await flush(); };
const reply = (status, data) => ({ok: status >= 200 && status < 300, status, headers: {get: () => 'application/json'}, json: async () => data});

const CARD_FIELDS = {id: 'file-abc', name_he: 'סגנון', name_en: 'Style', captions: 'מילה אחת בכל פעם', titles: 'כותרת גדולה',
  pace: 'מהיר', transitions: 'קאט חד', graphics: 'מסגרת דקה', music: 'ביט רגוע', sfx: 'וושש', hook: 'שאלה ישירה', avoid: 'לוגו של היוצר', extra: 'נשמר'};
const KEYS = ['captions', 'titles', 'pace', 'transitions', 'graphics', 'music', 'sfx', 'hook', 'avoid'];
const card = (over = {}) => ({reference: 'file-abc', exists: true, text: '...', fields: CARD_FIELDS, body: 'הערות', keys: KEYS,
  pinned: ['pace'], use: {}, valid: true, missing: [], revision: 'r1', ...over});

function harness(options = {}) {
  const nodes = new Map();
  const $ = sel => { if (!nodes.has(sel)) { const n = makeNode('div'); n.id = sel.slice(1); nodes.set(sel, n); } return nodes.get(sel); };
  $('#style-dialog').open = true;
  const calls = [], timers = [], copies = [], opened = [];
  let timerId = 0;
  const routes = options.routes || {};
  const fetch = async (url, init = {}) => {
    calls.push({url, init});
    const handler = routes[url.split('?')[0] + (init.method === 'POST' ? ':POST' : '')];
    if (!handler) throw new TypeError('no route ' + url);
    return handler(url, init);
  };
  const xhrs = [];
  class FakeXHR {
    constructor() { this.upload = {}; this.headers = {}; xhrs.push(this); }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(name, value) { this.headers[name] = value; }
    send(body) { this.body = body; }
  }
  const context = {
    window: {}, $, I18N: i18nStub(), fetch, URLSearchParams, XMLHttpRequest: FakeXHR, JSON, encodeURIComponent,
    document: {createElement: makeNode, addEventListener() {}, hidden: false},
    navigator: {clipboard: {writeText: async text => { if (options.clipboardFails) throw Error('no'); copies.push(text); }}},
    setTimeout: fn => { const id = ++timerId; timers.push({id, fn}); return id; },
    clearTimeout: id => { const i = timers.findIndex(t => t.id === id); if (i !== -1) timers.splice(i, 1); },
    Date, location: {hash: ''},
    closeStyle: () => { $('#style-dialog').open = false; opened.push('closeStyle'); },
    confirm: text => { opened.push(['confirm', text]); return options.confirm ?? true; },
  };
  context.window.NewVideo = {open: (button, opts) => opened.push(opts)};
  vm.createContext(context);
  context.window = Object.assign(context, context.window);
  if (!options.noSendUI) vm.runInContext(sendSource, context);
  vm.runInContext(source, context);
  const panel = $('#style-card-panel');
  return {
    context, $, panel, calls, timers, copies, opened, xhrs, Inspiration: context.window.Inspiration,
    async tick() { const due = timers.splice(0); due.forEach(t => t.fn()); await settle(); },
    button: key => find(panel, n => n.tagName === 'BUTTON' && n.textContent === he[key]),
    status: () => find(panel, byClass('style-card-status')).textContent,
    send: () => find(panel, byClass('send-section')),
    message: () => find(panel, byClass('send-message')).textContent,
    primary: () => find(panel, byClass('send-primary')),
  };
}

test('reference demo moments without a time show a dash instead of NaN:NaN', () => {
  const app = readFileSync(join(__dirname, 'dist/app.js'), 'utf8');
  const start = app.indexOf('const esc='), end = app.indexOf('\nlet removedIds');
  const context = {};
  vm.runInNewContext(app.slice(start, end), context);
  const html = vm.runInNewContext('momentsHtml', context)([{label: 'Hook'}, {time: 65, label: 'Reveal'}, {time: null, label: 'Cut'}]);
  assert.doesNotMatch(html, /NaN/);
  assert.match(html, /<p class="moment moment-untimed"><span aria-hidden="true">—<\/span>Hook<\/p>/);
  assert.match(html, /<button class="moment" data-time="65"><span>1:05<\/span>Reveal<\/button>/);
  assert.equal((html.match(/data-time/g) || []).length, 1);
  assert.equal(vm.runInNewContext('stamp', context)(undefined), '—');
});

test('composeCard keeps identity, extra keys and body, one line per field', () => {
  const h = harness();
  const text = h.Inspiration.composeCard(card(), {...CARD_FIELDS, pace: 'מהיר\nמאוד  ', hook: ' שאלה '}, 'file-abc', 'כותרת');
  assert.equal(text, '---\nid: file-abc\nname_he: סגנון\nname_en: Style\ncaptions: מילה אחת בכל פעם\ntitles: כותרת גדולה\npace: מהיר מאוד\n' +
    'transitions: קאט חד\ngraphics: מסגרת דקה\nmusic: ביט רגוע\nsfx: וושש\nhook: שאלה\navoid: לוגו של היוצר\nextra: נשמר\n---\nהערות\n');
  const fresh = h.Inspiration.composeCard(card({fields: {}, body: ''}), {captions: 'x'}, 'file-abc', 'כותרת: שנייה');
  assert.match(fresh, /^---\nid: file-abc\nname_he: כותרת: שנייה\nname_en: כותרת: שנייה\ncaptions: x\ntitles: \n/);
});

const NO_CARD = () => reply(200, card({exists: false, fields: {}, pinned: [], revision: null}));

test('no card yet: the rule, then the one Send-to-Claude card runs learn-style with steps', async () => {
  const states = [{state: 'running', steps: [{key: 'watch', state: 'done'}, {key: 'analyze', state: 'running'}, {key: 'card', state: 'todo'}]},
    {state: 'done', steps: []}];
  let cardCalls = 0;
  const h = harness({routes: {
    '/style-card': () => (++cardCalls === 1 ? NO_CARD() : reply(200, card())),
    '/claude-job:POST': () => reply(202, {job: 'a'.repeat(32)}),
    '/claude-job': url => url.includes('reference=') ? reply(200, {job: null}) : reply(200, states.shift()),
  }});
  h.Inspiration.mount({id: 'file-abc', title: 'כותרת', collection: 'reference'});
  await settle();
  assert.equal(h.panel.hidden, false);
  assert.match(h.panel.text, /לומדים את הטכניקה, לא מעתיקים את התוכן — קלוד לא ישתמש בצילומים, במילים או בלוגו של היוצר\./);
  assert.equal(find(h.panel, n => n.tagName === 'FORM'), null);
  assert.ok(h.send(), 'the shared send-ui card is mounted in the style panel');
  assert.equal(h.primary().textContent, he['inspiration.learn.button']);
  h.primary().click();
  await settle();
  const post = h.calls.find(c => c.url === '/claude-job' && c.init.method === 'POST');
  assert.deepEqual(JSON.parse(post.init.body), {reference: 'file-abc', task: 'learn-style'});
  assert.equal(post.init.headers['X-Studio-Action'], 'claude-job');
  assert.equal(h.primary().textContent, he['claude.cancel'], 'a running learn-style job can be stopped');
  await h.tick();
  assert.equal(h.message(), he['claude.state.running'].replace('{step}', he['claude.step.analyze']));
  await h.tick();
  assert.equal(cardCalls, 2, 'done reloads the card');
  const rows = findAll(h.panel, byClass('style-card-row'));
  assert.equal(rows.length, 9);
  assert.deepEqual(rows.map(r => find(r, n => n.tagName === 'LABEL' && n.attributes.for).textContent),
    ['כתוביות', 'כותרות', 'קצב', 'מעברים', 'גרפיקה', 'מוזיקה', 'אפקטי סאונד', 'פתיחה', 'להימנע']);
  assert.equal(find(rows[2], n => n.type === 'checkbox').checked, true);
  assert.equal(find(rows[0], n => n.type === 'checkbox').checked, false);
  assert.equal(find(rows[0], n => n.tagName === 'TEXTAREA').value, 'מילה אחת בכל פעם');
  assert.equal(h.primary().textContent, he['inspiration.learn.again']);
});

test('a failed job shows the translated message and the "copy details for support" link', async () => {
  const h = harness({routes: {
    '/style-card': NO_CARD,
    '/claude-job:POST': () => reply(202, {job: 'b'.repeat(32)}),
    '/claude-job': url => url.includes('reference=') ? reply(200, {job: null}) : reply(200, {job: 'b'.repeat(32), state: 'failed', steps: [], message_key: 'claude.not-logged-in'}),
    '/claude-job-log': () => reply(200, {log: 'line one\nline two'}),
  }});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await settle();
  h.primary().click();
  await settle(); await h.tick();
  assert.equal(h.message(), he['claude.not-logged-in']);
  const support = find(h.panel, byClass('send-support'));
  assert.equal(support.hidden, false);
  support.click();
  await settle();
  assert.match(h.copies[0], /line one\nline two$/);
});

test('cancel stops a learn-style run', async () => {
  const job = 'f'.repeat(32);
  let cancelled = null;
  const h = harness({routes: {
    '/style-card': NO_CARD,
    '/claude-job:POST': () => reply(202, {job}),
    '/claude-job-cancel:POST': (url, init) => { cancelled = JSON.parse(init.body); return reply(200, {job, state: 'stopped', steps: []}); },
    '/claude-job': url => url.includes('reference=') ? reply(200, {job: null}) : reply(200, {state: 'running', steps: []}),
  }});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await settle();
  h.primary().click();
  await settle();
  h.primary().click();
  await settle();
  assert.deepEqual(cancelled, {job});
  assert.equal(h.message(), he['claude.stopped']);
});

test('claude missing: copy-to-chat becomes the main action and copies the learn-style request', async () => {
  const h = harness({routes: {
    '/style-card': NO_CARD,
    '/claude-job:POST': () => reply(409, {error: 'claude-missing'}),
    '/claude-job': () => reply(200, {job: null}),
  }});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await settle();
  h.primary().click();
  await settle();
  assert.equal(h.message(), he['claude-missing']);
  h.primary().click();
  await settle();
  assert.deepEqual(h.copies, [he['claude.copy.learnStyle'].replace('{folder}', 'references/file-abc')]);
});

test('the old duplicate learn-style client is gone (one progress component)', () => {
  for (const name of ['startLearning', 'stepLine', 'POLL_MS', "fetch('/claude-job'", 'inspiration.learn.running']) {
    assert.equal(source.includes(name), false, name);
  }
  for (const key of ['inspiration.learn.running', 'inspiration.learn.missing', 'inspiration.step.watch']) {
    assert.equal(key in he, false, key);
  }
});

test('saving sends the edited card with pins; a 400 names the missing fields in Hebrew', async () => {
  const saves = [];
  const h = harness({routes: {
    '/style-card': () => reply(200, card()),
    '/style-card:POST': (url, init) => { saves.push(JSON.parse(init.body)); return saves.length === 1 ? reply(200, card({pinned: ['captions', 'pace'], revision: 'r2'})) : reply(400, {error: 'inspiration.error.invalidCard', missing: ['music', 'sfx']}); },
  }});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await flush(); await flush();
  const rows = findAll(h.panel, byClass('style-card-row'));
  find(rows[0], n => n.type === 'checkbox').checked = true;
  find(rows[1], n => n.tagName === 'TEXTAREA').value = 'כותרת קטנה';
  const form = find(h.panel, n => n.tagName === 'FORM');
  form.dispatch('submit');
  await flush(); await flush();
  assert.equal(saves[0].reference, 'file-abc');
  assert.equal(saves[0].revision, 'r1');
  assert.deepEqual(saves[0].pinned, ['captions', 'pace']);
  assert.match(saves[0].text, /\ntitles: כותרת קטנה\n/);
  assert.equal(h.status(), he['inspiration.card.saved']);
  form.dispatch('submit');
  await flush(); await flush();
  assert.equal(saves[1].revision, 'r2');
  assert.equal(find(h.panel, byClass('style-card-error')).textContent,
    he['inspiration.error.invalidCard'].replace('{keys}', 'מוזיקה, אפקטי סאונד'));
});

test('"use this style in a new video" closes the reference and opens the new-video dialog with it', async () => {
  const h = harness({routes: {'/style-card': () => reply(200, card())}});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await flush(); await flush();
  h.button('inspiration.card.useInNewVideo').click();
  assert.equal(JSON.stringify(h.opened), JSON.stringify(['closeStyle', {referenceId: 'file-abc'}]));
});

test('own work and techniques get no style card panel', async () => {
  const h = harness({routes: {}});
  h.Inspiration.mount({id: 'mine-1', title: 't', collection: 'mine'});
  assert.equal(h.panel.hidden, true);
  assert.equal(h.calls.length, 0);
});

test('upload streams the file with its details and reports progress', async () => {
  const h = harness();
  const progress = [];
  const file = {name: 'רילס.mp4', size: 10};
  const done = h.Inspiration.upload(file, {title: 'פתיחה', creator: '', note: 'x'}, p => progress.push(p));
  const xhr = h.xhrs[0];
  assert.equal(xhr.method, 'PUT');
  assert.equal(xhr.url, '/inspiration-file?' + new URLSearchParams({name: 'רילס.mp4', title: 'פתיחה', creator: '', note: 'x'}));
  assert.equal(xhr.headers['X-Studio-Action'], 'inspiration-file');
  assert.equal(xhr.body, file);
  xhr.upload.onprogress({lengthComputable: true, loaded: 5, total: 10});
  xhr.status = 201; xhr.responseText = JSON.stringify({id: 'file-x', duplicate: false, saved: true});
  xhr.onload();
  assert.equal(JSON.stringify(await done), JSON.stringify({id: 'file-x', duplicate: false, saved: true}));
  assert.deepEqual(progress, [50]);
  const failing = h.Inspiration.upload(file, {reference: 'link-1'});
  assert.equal(h.xhrs[1].url, '/inspiration-file?' + new URLSearchParams({name: 'רילס.mp4', reference: 'link-1'}));
  h.xhrs[1].status = 415; h.xhrs[1].responseText = JSON.stringify({error: 'inspiration.error.unsupportedType'});
  h.xhrs[1].onload();
  await assert.rejects(failing, {message: he['inspiration.error.unsupportedType']});
});

test('drop zone: a video makes the link optional; other files are refused', () => {
  const h = harness();
  h.$('#reference-url').required = true;
  h.Inspiration.resetDrop(false);
  assert.equal(h.Inspiration.pendingFile(), null);
  h.$('#inspiration-file').files = [{name: 'notes.pdf', size: 3}];
  h.$('#inspiration-file').dispatch('change');
  assert.equal(h.Inspiration.pendingFile(), null);
  assert.equal(h.$('#reference-error').textContent, he['inspiration.error.unsupportedType']);
  assert.equal(h.$('#reference-url').required, true);
  h.$('#inspiration-drop').dispatch('drop', {dataTransfer: {files: [{name: 'Clip.MOV', size: 3}]}});
  assert.equal(h.Inspiration.pendingFile().name, 'Clip.MOV');
  assert.equal(h.$('#reference-url').required, false);
  assert.equal(h.$('#inspiration-file-chosen').hidden, false);
  assert.equal(h.$('#inspiration-file-name').textContent, 'Clip.MOV');
  h.$('#inspiration-file-clear').click();
  assert.equal(h.Inspiration.pendingFile(), null);
  assert.equal(h.$('#reference-url').required, true);
  h.Inspiration.resetDrop(true);
  assert.equal(h.$('#inspiration-drop').hidden, true);
});

test('fix round 1: "learn again" asks first, since unpinned rows will change', async () => {
  for (const answer of [false, true]) {
    const h = harness({confirm: answer, routes: {
      '/style-card': () => reply(200, card()),
      '/claude-job:POST': () => reply(202, {job: 'e'.repeat(32)}),
      '/claude-job': url => url.includes('reference=') ? reply(200, {job: null}) : reply(200, {state: 'running', steps: []}),
    }});
    h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
    await settle();
    assert.equal(h.primary().textContent, he['inspiration.learn.again']);
    h.primary().click();
    await settle();
    assert.equal(JSON.stringify(h.opened[0]), JSON.stringify(['confirm', he['inspiration.learn.confirmAgain']]));
    assert.equal(h.calls.some(c => c.init.method === 'POST'), answer);
  }
  assert.match(he['inspiration.learn.confirmAgain'], /השורות שסימנתם 'לשמור' יישארו; השאר יתעדכנו/);
});

test('fix round 1: reopening a reference re-attaches to a learn-style job that is still running', async () => {
  const job = 'c'.repeat(32);
  const h = harness({routes: {
    '/style-card': NO_CARD,
    '/claude-job': url => url.includes('reference=file-abc') ? reply(200, {job, state: 'running', steps: [], started: Date.now() / 1000})
      : reply(200, {state: 'running', steps: [{key: 'watch', state: 'running'}, {key: 'analyze', state: 'todo'}, {key: 'card', state: 'todo'}]}),
  }});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await settle(); await h.tick();
  assert.ok(h.calls.some(c => c.url === '/claude-job?id=' + job));
  assert.equal(h.message(), he['claude.state.running'].replace('{step}', he['claude.step.watch']));
  assert.equal(h.primary().textContent, he['claude.cancel']);
});

test('fix round 1: a busy reply re-attaches to the job that is already running', async () => {
  const job = 'd'.repeat(32);
  let lookups = 0;
  const h = harness({routes: {
    '/style-card': NO_CARD,
    '/claude-job:POST': () => reply(409, {error: 'busy', job}),
    '/claude-job': url => url.includes('reference=') ? reply(200, ++lookups === 1 ? {job: null} : {job, state: 'running', steps: [], started: Date.now() / 1000})
      : reply(200, {state: 'running', steps: [{key: 'card', state: 'running'}]}),
  }});
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await settle();
  h.primary().click();
  await settle(); await h.tick();
  assert.ok(h.calls.some(c => c.url === '/claude-job?id=' + job));
  assert.equal(h.message(), he['claude.state.running'].replace('{step}', he['claude.step.card']));
});

test('closing the reference hands the page back to the card that was active before', async () => {
  const h = harness({routes: {'/style-card': NO_CARD, '/claude-job': () => reply(200, {job: null})}});
  const released = [];
  const real = h.context.SendUI.release;
  h.context.SendUI.release = token => { released.push(token); return real(token); };
  h.Inspiration.mount({id: 'file-abc', title: 't', collection: 'reference'});
  await settle();
  h.Inspiration.unmount();
  assert.equal(released.length, 1);
});

test('fix round 1: a body that still holds a broken front-matter block is not written twice', () => {
  const h = harness();
  const text = h.Inspiration.composeCard(card({fields: {}, body: '---\nid: x\nbroken line\n---\nהערות'}), {captions: 'x'}, 'file-abc', 'כותרת');
  assert.equal((text.match(/^---$/gm) || []).length, 2);
  assert.match(text, /\n---\nהערות\n$/);
});
