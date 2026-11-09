/* Task 21: a vm-sandbox unit test for addons-ui.js, the same style test_new_video_ui.js
   and test_motion_setting.js already use. Covers: loading current state into the form
   on open, the combined POST body (key omitted unless typed), applying the response and
   closing on a successful save, the per-add-on "Clear key" button, and that any failure
   shows one generic translated message rather than the server's raw error text. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));
const flush = () => new Promise(resolve => setImmediate(resolve));

function i18nStub() {
  return {t: key => he[key] ?? key};
}

function makeNode(extra = {}) {
  return Object.assign({
    value: '', checked: false, disabled: false, hidden: false, textContent: '',
    listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
    classList: {names: new Set(), toggle(name, on) { on ? this.names.add(name) : this.names.delete(name); }},
  }, extra);
}

function openButton() {
  const button = {isConnected: true, focus() {}};
  button.closest = selector => selector === '[data-addons]' ? button : null;
  return button;
}

const DEFAULT_STATE = {
  voice: {enabled: false, provider: null, has_key: false},
  image: {enabled: false, provider: null, has_key: false},
};

function harness({state = DEFAULT_STATE, failGet = false, failPost = false, postResult} = {}) {
  const nodes = {
    '#addons-error': makeNode(),
    '#addons-voice-enabled': makeNode(), '#addons-voice-key': makeNode(), '#addons-voice-status': makeNode(), '#addons-voice-clear': makeNode({hidden: true}),
    '#addons-image-enabled': makeNode(), '#addons-image-provider': makeNode({value: 'openai-images'}), '#addons-image-key': makeNode(), '#addons-image-status': makeNode(), '#addons-image-clear': makeNode({hidden: true}),
  };
  const allFields = ['#addons-voice-enabled', '#addons-voice-key', '#addons-voice-clear',
    '#addons-image-enabled', '#addons-image-provider', '#addons-image-key', '#addons-image-clear'].map(key => nodes[key]);
  const formListeners = {};
  const form = Object.assign(makeNode(), {
    addEventListener(type, fn) { formListeners[type] = fn; },
    querySelectorAll() { return allFields; },
  });
  const dialogListeners = {};
  const dialog = Object.assign(makeNode(), {
    open: false,
    showModal() { this.open = true; },
    close() { this.open = false; },
    addEventListener(type, fn) { dialogListeners[type] = fn; },
  });
  nodes['#addons-form'] = form;
  nodes['#addons-dialog'] = dialog;

  const documentHandlers = {};
  const document = {activeElement: makeNode(), addEventListener(type, fn) { documentHandlers[type] = fn; }};
  const $ = selector => nodes[selector];

  const requests = [];
  const fetch = async (url, init = {}) => {
    requests.push({url, init});
    if (init.method === 'POST') {
      if (failPost) return {ok: false, json: async () => ({error: 'boom, do not show this'})};
      return {ok: true, json: async () => postResult || state};
    }
    if (failGet) return {ok: false, json: async () => ({})};
    return {ok: true, json: async () => state};
  };

  const context = {window: {}, document, $, I18N: i18nStub(), fetch};
  vm.runInContext(readFileSync(join(__dirname, 'dist/addons-ui.js'), 'utf8'), vm.createContext(context));

  return {
    nodes, requests, form, dialog,
    async openDialog() { documentHandlers.click({target: openButton(), preventDefault() {}}); await flush(); },
    async submit() {
      let prevented = false;
      await formListeners.submit({preventDefault() { prevented = true; }});
      return prevented;
    },
    async clickClear(kind) { await nodes[`#addons-${kind}-clear`].listeners.click(); },
  };
}

test('opening the dialog loads the current state into the form', async () => {
  const h = harness({state: {voice: {enabled: true, provider: 'elevenlabs', has_key: true}, image: {enabled: false, provider: null, has_key: false}}});
  await h.openDialog();
  assert.equal(h.dialog.open, true);
  assert.equal(h.requests[0].url, '/addons');
  assert.equal(h.nodes['#addons-voice-enabled'].checked, true);
  assert.equal(h.nodes['#addons-voice-key'].value, '', 'the key field is never prefilled');
  assert.equal(h.nodes['#addons-voice-status'].textContent, he['dialog.addons.connected']);
  assert.equal(h.nodes['#addons-voice-clear'].hidden, false);
  assert.equal(h.nodes['#addons-image-enabled'].checked, false);
  assert.equal(h.nodes['#addons-image-clear'].hidden, true);
});

test('submitting sends one POST with both add-ons; a typed key is included, an empty one is not', async () => {
  const h = harness();
  await h.openDialog();
  h.nodes['#addons-voice-enabled'].checked = true;
  h.nodes['#addons-voice-key'].value = 'sk-voice-secret';
  h.nodes['#addons-image-enabled'].checked = true;
  h.nodes['#addons-image-provider'].value = 'openai-images';
  await h.submit();
  const post = h.requests.find(r => r.init.method === 'POST');
  assert.equal(post.url, '/addons');
  assert.equal(post.init.headers['X-Studio-Action'], 'addons');
  assert.equal(post.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(post.init.body), {
    voice: {enabled: true, provider: 'elevenlabs', key: 'sk-voice-secret'},
    image: {enabled: true, provider: 'openai-images'},
  });
});

test('RULING R50: Foundry is not offered in the dialog, but a Foundry choice made elsewhere is kept', async () => {
  const html = require('node:fs').readFileSync(require('node:path').join(__dirname, 'dist/index.html'), 'utf8');
  assert.doesNotMatch(html, /value="foundry"/);
  const h = harness({state: {voice: {enabled: false, provider: null, has_key: false},
    image: {enabled: true, provider: 'foundry', has_key: true}}});
  await h.openDialog();
  await h.submit();
  const post = h.requests.find(r => r.init.method === 'POST');
  assert.deepEqual(JSON.parse(post.init.body).image, {enabled: true, provider: 'foundry'});
});

test('a successful save applies the returned state and closes the dialog', async () => {
  const h = harness({postResult: {voice: {enabled: true, provider: 'elevenlabs', has_key: true}, image: {enabled: false, provider: null, has_key: false}}});
  await h.openDialog();
  h.nodes['#addons-voice-enabled'].checked = true;
  h.nodes['#addons-voice-key'].value = 'sk-voice-secret';
  const prevented = await h.submit();
  assert.equal(prevented, true);
  assert.equal(h.dialog.open, false);
  assert.equal(h.nodes['#addons-voice-status'].textContent, he['dialog.addons.connected']);
  assert.equal(h.nodes['#addons-voice-status'].classList.names.has('connected'), true);
  assert.equal(h.nodes['#addons-voice-clear'].hidden, false);
  assert.equal(h.form.querySelectorAll()[0].disabled, false, 're-enabled once the save settles');
});

test('a failed save shows one generic translated message, never the server\'s raw error text', async () => {
  const h = harness({failPost: true});
  await h.openDialog();
  h.nodes['#addons-voice-enabled'].checked = true;
  await h.submit();
  assert.equal(h.nodes['#addons-error'].textContent, he['dialog.addons.error']);
  assert.doesNotMatch(h.nodes['#addons-error'].textContent, /boom/);
  assert.equal(h.dialog.open, true, 'a failed save keeps the dialog open');
});

test('the per-add-on Clear key button posts only that add-on with key:"" and keeps the dialog open', async () => {
  const h = harness({
    state: {voice: {enabled: true, provider: 'elevenlabs', has_key: true}, image: {enabled: false, provider: null, has_key: false}},
    postResult: {voice: {enabled: true, provider: 'elevenlabs', has_key: false}, image: {enabled: false, provider: null, has_key: false}},
  });
  await h.openDialog();
  assert.equal(h.nodes['#addons-voice-clear'].hidden, false);
  await h.clickClear('voice');
  const post = h.requests.find(r => r.init.method === 'POST');
  assert.deepEqual(JSON.parse(post.init.body), {voice: {enabled: true, provider: 'elevenlabs', key: ''}});
  assert.equal(h.dialog.open, true);
  assert.equal(h.nodes['#addons-voice-clear'].hidden, true);
  assert.equal(h.nodes['#addons-voice-status'].textContent, '');
});

test('a failed load (GET not ok) leaves the defaults on screen rather than crashing', async () => {
  const h = harness({failGet: true});
  await h.openDialog();
  assert.equal(h.dialog.open, true, 'the dialog still opens even if the load failed');
  assert.equal(h.nodes['#addons-voice-enabled'].checked, false);
  assert.equal(h.nodes['#addons-image-enabled'].checked, false);
  assert.equal(h.nodes['#addons-error'].textContent, '');
});
