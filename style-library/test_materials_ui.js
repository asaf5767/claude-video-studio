/* Task 9: a vm-sandbox unit test for materials-ui.js (the same style test_new_video_ui.js
   and test_feedback_ui.js already use). Run with: node --test style-library/test_materials_ui.js
   (no browser or packages needed).

   materials-ui.js builds its tile grid with document.createElement rather than innerHTML
   strings, so the fake DOM below is a small, generic node graph (append/insertBefore/
   remove/classList/addEventListener/dispatch) rather than an HTML parser -- the same
   "fake it, don't parse it" approach test_feedback_ui.js takes for its one <textarea>. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/materials-ui.js'), 'utf8');
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

// --- a tiny, generic fake DOM: only what materials-ui.js actually calls ---

function makeNode(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null,
    dataset: {}, style: {}, attributes: {}, _classes: new Set(), _listeners: {},
    isConnected: true, disabled: false, hidden: false, checked: false, value: '', textContent: '',
    get className() { return this._className || ''; },
    set className(v) { this._className = v; this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); },
    get classList() {
      const self = this;
      return {
        add: c => self._classes.add(c), remove: c => self._classes.delete(c), contains: c => self._classes.has(c),
        toggle: c => { if (self._classes.has(c)) self._classes.delete(c); else self._classes.add(c); },
      };
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name]; },
    append(...nodes) { nodes.forEach(n => { n.parentNode = this; this.children.push(n); }); },
    appendChild(n) { n.parentNode = this; this.children.push(n); return n; },
    insertBefore(newNode, ref) {
      const i = this.children.indexOf(ref);
      newNode.parentNode = this;
      if (i === -1) this.children.push(newNode); else this.children.splice(i, 0, newNode);
      return newNode;
    },
    remove() {
      if (!this.parentNode) return;
      const i = this.parentNode.children.indexOf(this);
      if (i !== -1) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    dispatch(type, evt = {}) { (this._listeners[type] || []).slice().forEach(fn => fn(evt)); },
    click() { this.dispatch('click', {}); },
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

function harness(options = {}) {
  const xhrInstances = [];
  class FakeXHR {
    constructor() { this.upload = {}; this.headers = {}; xhrInstances.push(this); }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(name, value) { this.headers[name] = value; }
    send(body) { this.body = body; }
  }

  const fetchCalls = [];
  const defaultFetch = async (url, init = {}) => {
    fetchCalls.push({url, init});
    if (typeof url === 'string' && url.startsWith('/materials?')) return {ok: true, json: async () => ({items: options.initialItems || []})};
    if (url === '/material-library') return {ok: true, json: async () => ({items: options.libraryItems || []})};
    if (url === '/material-update') return options.updateImpl ? options.updateImpl(init) : {ok: true, json: async () => ({...JSON.parse(init.body)})};
    if (url === '/material-from-library') return options.fromLibraryImpl ? options.fromLibraryImpl(init) : {ok: true, json: async () => ({id: 'added-1', file: 'materials/images/added.png', tag: 'image', note: '', owned: false, size: 1, added_at: 't'})};
    return {ok: true, json: async () => ({})};
  };

  // A controllable timer queue so a debounced note save can be driven deterministically
  // (including the "typing twice only saves once" cancellation case) without real delays.
  let nextTimerId = 0;
  const pendingTimers = new Map();
  const fakeSetTimeout = (fn, ms) => { const id = ++nextTimerId; pendingTimers.set(id, {fn, ms}); return id; };
  const fakeClearTimeout = id => pendingTimers.delete(id);
  const flushTimers = () => { const due = [...pendingTimers.values()]; pendingTimers.clear(); due.forEach(({fn}) => fn()); };

  const document = {createElement: tag => makeNode(tag)};
  const context = {
    document, window: {}, I18N: options.i18n || i18nStub(),
    URLSearchParams, XMLHttpRequest: FakeXHR,
    setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout,
    fetch: options.fetchImpl || defaultFetch,
  };
  vm.createContext(context);
  vm.runInContext(source, context);

  return {
    MaterialsUI: context.window.MaterialsUI, xhrInstances, fetchCalls, flushTimers, pendingTimers,
    ContextTypeError: vm.runInContext('TypeError', context),
    mountEl() { return makeNode('div'); },
  };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

// --- tagFor: pure helper, mirrors materials.py's _auto_tag() ---

test('tagFor mirrors the server auto-tag rule', () => {
  const {MaterialsUI} = harness();
  assert.equal(MaterialsUI.tagFor('a.MOV', false), 'raw');
  assert.equal(MaterialsUI.tagFor('b.mp4', true), 'broll');
  assert.equal(MaterialsUI.tagFor('logo.png', true), 'image');
  assert.equal(MaterialsUI.tagFor('beat.mp3', true), 'music');
});

test('tagFor: a first video is raw even with a mixed-case/unknown extension ordering', () => {
  const {MaterialsUI} = harness();
  assert.equal(MaterialsUI.tagFor('clip.webm', false), 'raw');
  assert.equal(MaterialsUI.tagFor('clip.m4v', true), 'broll');
  assert.equal(MaterialsUI.tagFor('shot.JPG', false), 'image');
  assert.equal(MaterialsUI.tagFor('voice.wav', false), 'music');
});

// --- mount(): loads existing items and renders a tile per item plus the drop tile ---

test('mount() loads /materials?project=<id> and renders one tile per item, plus the drop tile', async () => {
  const items = [
    {id: 'a1', file: 'materials/raw/clip.mp4', tag: 'raw', note: '', owned: false, size: 10, added_at: 't'},
    {id: 'a2', file: 'materials/images/logo.png', tag: 'logo', note: '', owned: true, size: 5, added_at: 't'},
  ];
  const h = harness({initialItems: items});
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  assert.equal(h.fetchCalls[0].url, '/materials?' + new URLSearchParams({project: 'demo'}));
  const tiles = findAll(el, hasClass('material-tile')).filter(n => !hasClass('material-drop')(n));
  assert.equal(tiles.length, 2);
  const dropTiles = findAll(el, hasClass('material-drop'));
  assert.equal(dropTiles.length, 1);
  const count = find(el, hasClass('materials-count'));
  assert.equal(count.textContent, he['materials.count.many'].replace('{n}', '2'));
});

// --- T9b: video tiles use a server-generated poster <img>, not <video preload=metadata> ---

test('a video item\'s thumb is a poster image wrapped in a link that opens the actual video', async () => {
  const items = [{id: 'v1', file: 'materials/raw/clip.mov', tag: 'raw', note: '', owned: false, size: 10, added_at: 't'}];
  const h = harness({initialItems: items});
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const link = find(el, hasClass('material-thumb-link'));
  assert.ok(link, 'the video tile is a clickable link');
  assert.equal(link.tagName, 'A');
  const expectedUrl = '/project-materials/' + encodeURIComponent('demo') + '/' + encodeURIComponent('v1');
  assert.equal(link.href, expectedUrl);
  const img = find(link, n => n.tagName === 'IMG');
  assert.ok(img, 'the poster is an <img>, not a <video>');
  assert.equal(img.src, expectedUrl + '?poster=1');
  assert.equal(findAll(el, n => n.tagName === 'VIDEO').length, 0, 'no <video preload=metadata> element is created');
});

test('a video thumb falls back to a plain placeholder when its poster image fails to load', async () => {
  const items = [{id: 'v1', file: 'materials/raw/clip.mov', tag: 'raw', note: '', owned: false, size: 10, added_at: 't'}];
  const h = harness({initialItems: items});
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const link = find(el, hasClass('material-thumb-link'));
  const img = find(link, n => n.tagName === 'IMG');
  img.dispatch('error', {});
  assert.equal(findAll(link, n => n.tagName === 'IMG').length, 0, 'the broken poster image is removed');
  const placeholder = find(link, hasClass('material-thumb-video-pending'));
  assert.ok(placeholder, 'a placeholder icon takes its place');
  assert.equal(placeholder.getAttribute('aria-hidden'), 'true');
});

test('mount() shows a translated load error on a network failure', async () => {
  const h = harness({fetchImpl: async () => { throw new h.ContextTypeError('Failed to fetch'); }});
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const status = find(el, hasClass('materials-status'));
  assert.equal(status.textContent, he['materials.loadError']);
});

// --- upload flow: one XHR per file, with progress and per-tile errors ---

test('dropping/picking a file sends one PUT per file with the right URL, header and body', async () => {
  const h = harness();
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const fileInput = find(el, n => n.tagName === 'INPUT' && n.attributes.type !== 'checkbox' && 'accept' in n);
  fileInput.files = [{name: 'צילום 1.mov'}];
  fileInput.dispatch('change', {});
  assert.equal(h.xhrInstances.length, 1);
  const xhr = h.xhrInstances[0];
  assert.equal(xhr.method, 'PUT');
  assert.equal(xhr.url, '/materials?' + new URLSearchParams({project: 'demo', name: 'צילום 1.mov'}));
  assert.equal(xhr.headers['X-Studio-Action'], 'materials');
  assert.equal(xhr.body.name, 'צילום 1.mov');
});

test('an uploading tile shows progress and becomes a settled tile on success (201)', async () => {
  const h = harness();
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const fileInput = find(el, n => n.tagName === 'INPUT' && 'accept' in n);
  fileInput.files = [{name: 'clip.mp4'}];
  fileInput.dispatch('change', {});
  const xhr = h.xhrInstances[0];
  const uploadingTile = find(el, hasClass('material-tile-uploading'));
  assert.ok(uploadingTile, 'an uploading tile is shown immediately');
  const bar = find(uploadingTile, hasClass('material-progress-bar'));
  xhr.upload.onprogress({lengthComputable: true, loaded: 50, total: 100});
  assert.equal(bar.style.width, '50%');
  const item = {id: 'new-1', file: 'materials/raw/clip.mp4', tag: 'raw', note: '', owned: false, size: 3, added_at: 't'};
  xhr.status = 201;
  xhr.responseText = JSON.stringify(item);
  xhr.onload();
  await flush();
  assert.equal(findAll(el, hasClass('material-tile-uploading')).length, 0);
  const settled = findAll(el, hasClass('material-tile')).filter(n => !hasClass('material-drop')(n));
  assert.equal(settled.length, 1);
  assert.equal(settled[0].dataset.itemId, 'new-1');
});

test('an upload error shows the translated server message on that tile and does not touch a second, still-running upload', async () => {
  const h = harness();
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const fileInput = find(el, n => n.tagName === 'INPUT' && 'accept' in n);
  fileInput.files = [{name: 'virus.exe'}, {name: 'ok.mp4'}];
  fileInput.dispatch('change', {});
  assert.equal(h.xhrInstances.length, 2);
  const [badXhr, goodXhr] = h.xhrInstances;
  badXhr.status = 415;
  badXhr.responseText = JSON.stringify({error: 'materials.error.unsupportedType'});
  badXhr.onload();
  const statuses = findAll(el, hasClass('material-tile-status'));
  assert.ok(statuses.some(s => s.textContent === he['materials.error.unsupportedType']), 'the failed tile shows the translated message');
  assert.ok(statuses.some(s => s.textContent === ''), 'the still-running upload is untouched by the first one failing');
  // the still-running upload completes normally afterwards
  const item = {id: 'ok-1', file: 'materials/raw/ok.mp4', tag: 'raw', note: '', owned: false, size: 1, added_at: 't'};
  goodXhr.status = 201; goodXhr.responseText = JSON.stringify(item); goodXhr.onload();
  await flush();
  const settled = findAll(el, hasClass('material-tile')).filter(n => !hasClass('material-drop')(n) && !hasClass('material-tile-uploading')(n));
  assert.equal(settled.length, 1, 'the second file settled into a normal tile once it succeeded');
  assert.equal(settled[0].dataset.itemId, 'ok-1');
});

// --- per-tile controls: tag dropdown, debounced note, owned checkbox ---

function mountedWithOneItem(h) {
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  return el;
}

test('changing the tag select PATCHes /material-update with the new tag', async () => {
  const items = [{id: 'a1', file: 'materials/raw/clip.mp4', tag: 'raw', note: '', owned: false, size: 1, added_at: 't'}];
  const h = harness({initialItems: items});
  const el = mountedWithOneItem(h);
  await flush();
  const select = find(el, n => n.tagName === 'SELECT');
  select.value = 'music';
  select.dispatch('change', {});
  await flush();
  const call = h.fetchCalls.find(c => c.url === '/material-update');
  assert.deepEqual(JSON.parse(call.init.body), {project: 'demo', item: 'a1', tag: 'music'});
  assert.equal(call.init.headers['X-Studio-Action'], 'material-update');
});

test('the tag menu offers voice-over ("קריינות") and saves it; new audio still starts as music', async () => {
  const items = [{id: 'a1', file: 'materials/audio/voice.m4a', tag: 'music', note: '', owned: false, size: 1, added_at: 't'}];
  const h = harness({initialItems: items});
  const el = mountedWithOneItem(h);
  await flush();
  const select = find(el, n => n.tagName === 'SELECT');
  const voice = select.children.find(o => o.value === 'voice');
  assert.ok(voice);
  assert.equal(voice.textContent, 'קריינות');
  assert.equal(h.MaterialsUI.tagFor('voice.m4a', true), 'music');
  select.value = 'voice';
  select.dispatch('change', {});
  await flush();
  const call = h.fetchCalls.find(c => c.url === '/material-update');
  assert.deepEqual(JSON.parse(call.init.body), {project: 'demo', item: 'a1', tag: 'voice'});
});

test('a failed tag change shows the translated error on that tile', async () => {
  const items = [{id: 'a1', file: 'materials/raw/clip.mp4', tag: 'raw', note: '', owned: false, size: 1, added_at: 't'}];
  const h = harness({initialItems: items, updateImpl: () => ({ok: false, json: async () => ({error: 'materials.error.invalidTag'})})});
  const el = mountedWithOneItem(h);
  await flush();
  const select = find(el, n => n.tagName === 'SELECT');
  select.dispatch('change', {});
  await flush();
  const tileStatus = find(el, hasClass('material-tile-status'));
  assert.equal(tileStatus.textContent, he['materials.error.invalidTag']);
});

test('toggling the owned checkbox PATCHes /material-update with owned:true', async () => {
  const items = [{id: 'a1', file: 'materials/raw/clip.mp4', tag: 'raw', note: '', owned: false, size: 1, added_at: 't'}];
  const h = harness({initialItems: items});
  const el = mountedWithOneItem(h);
  await flush();
  // The owned checkbox is the only <input type="checkbox">; the upload input is type="file".
  const ownedCheckbox = find(el, n => n.tagName === 'INPUT' && n.type === 'checkbox');
  ownedCheckbox.checked = true;
  ownedCheckbox.dispatch('change', {});
  await flush();
  const call = h.fetchCalls.find(c => c.url === '/material-update');
  assert.deepEqual(JSON.parse(call.init.body), {project: 'demo', item: 'a1', owned: true});
});

test('typing a note twice quickly only saves once (debounced), with the latest text', async () => {
  const items = [{id: 'a1', file: 'materials/raw/clip.mp4', tag: 'raw', note: '', owned: false, size: 1, added_at: 't'}];
  const h = harness({initialItems: items});
  const el = mountedWithOneItem(h);
  await flush();
  const note = find(el, n => n.tagName === 'TEXTAREA');
  note.value = 'בפתיח';
  note.dispatch('input', {});
  note.value = 'בפתיחה';
  note.dispatch('input', {});
  assert.equal(h.pendingTimers.size, 1, 'the first debounce timer was cancelled, not left pending');
  h.flushTimers();
  await flush();
  const updateCalls = h.fetchCalls.filter(c => c.url === '/material-update');
  assert.equal(updateCalls.length, 1);
  assert.deepEqual(JSON.parse(updateCalls[0].init.body), {project: 'demo', item: 'a1', note: 'בפתיחה'});
});

// --- "add from library" ---

test('opening the library picker lists GET /material-library items; adding one appends a settled tile', async () => {
  const libraryItems = [{id: 'lib-1', file: 'images/brand-logo.png', tag: 'logo', note: '', owned: true, size: 1, added_at: 't'}];
  const h = harness({libraryItems});
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const libraryButton = find(el, hasClass('materials-library-button'));
  libraryButton.dispatch('click', {});
  await flush();
  const row = find(el, hasClass('materials-library-item'));
  assert.ok(row, 'the library item is listed');
  const addButton = find(row, n => n.tagName === 'BUTTON');
  addButton.dispatch('click', {});
  await flush();
  const call = h.fetchCalls.find(c => c.url === '/material-from-library');
  assert.deepEqual(JSON.parse(call.init.body), {project: 'demo', item: 'lib-1'});
  const settled = findAll(el, hasClass('material-tile')).filter(n => !hasClass('material-drop')(n));
  assert.equal(settled.length, 1);
  assert.equal(settled[0].dataset.itemId, 'added-1');
});

test('an empty personal library shows the translated empty message', async () => {
  const h = harness({libraryItems: []});
  const el = h.mountEl();
  h.MaterialsUI.mount(el, 'demo');
  await flush();
  const libraryButton = find(el, hasClass('materials-library-button'));
  libraryButton.dispatch('click', {});
  await flush();
  const panel = find(el, hasClass('materials-library-panel'));
  const text = findAll(panel, n => n.textContent === he['materials.library.empty']);
  assert.equal(text.length, 1);
});
