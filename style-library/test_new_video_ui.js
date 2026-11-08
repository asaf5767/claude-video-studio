/* Fix round 1 (Task 7): a vm-sandbox unit test for new-video-ui.js, the same style
   test_studio_ui.js already uses for review-layout.js/start-ui.js. Covers: empty-title
   validation, kind selection, the POST body shape (including reference_id passthrough),
   navigation on success, and a translated error on failure. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));

function i18nStub() {
  return {lang: () => 'he', t: key => he[key] ?? key};
}

// A fake [data-new-video] trigger button: `.closest('[data-new-video]')` resolves to
// itself, matching how `event.target.closest(selector)` works on a real DOM node.
function openButton(dataset = {}) {
  const button = {dataset};
  button.closest = selector => selector === '[data-new-video]' ? button : null;
  return button;
}

function clickEvent(target) {
  return {target, preventDefault() {}};
}

function radioGroup(attr, values) {
  return values.map(value => {
    const button = {dataset: {[attr]: value}, attributes: {}, setAttribute(name, v) { this.attributes[name] = v; }};
    button.closest = selector => selector === `[data-${attr === 'newVideoKind' ? 'new-video-kind' : 'new-video-language'}]` ? button : null;
    return button;
  });
}

function harness(options = {}) {
  const nodes = new Map();
  const documentHandlers = {};
  const kindButtons = radioGroup('newVideoKind', ['talking-head', 'faceless']);
  const languageButtons = radioGroup('newVideoLanguage', ['he', 'en']);

  const node = key => {
    if (!nodes.has(key)) {
      nodes.set(key, {
        value: '', textContent: '', disabled: false, focused: false, isConnected: true, listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; },
        focus() { this.focused = true; },
      });
    }
    return nodes.get(key);
  };

  const dialog = node('#new-video-dialog');
  dialog.open = false;
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => { dialog.open = false; };
  dialog.querySelectorAll = selector => selector === '[data-new-video-kind]' ? kindButtons
    : selector === '[data-new-video-language]' ? languageButtons
    : [node('#new-video-title-input'), node('#new-video-save')];

  const form = node('#new-video-form');
  form.reset = () => { node('#new-video-title-input').value = ''; };
  form.reportValidity = () => options.titleValid !== false;

  const requests = [];
  const defaultFetch = async (url, init) => {
    requests.push({url, init, body: JSON.parse(init.body)});
    return {ok: true, json: async () => ({id: 'my-first-reel', state: 'draft'})};
  };

  const document = {
    activeElement: node('body'),
    addEventListener(type, fn) { documentHandlers[type] = fn; },
  };

  const context = {
    document, window: {}, $: node, I18N: options.i18n || i18nStub(),
    location: {hash: '#projects'},
  };
  const sandbox = vm.createContext(context);
  vm.runInContext(readFileSync(join(__dirname, 'dist/new-video-ui.js'), 'utf8'), sandbox);
  // `instanceof TypeError` inside the sandboxed script only matches an error built from
  // *this context's own* TypeError constructor (a vm context is its own realm) -- a real
  // browser's fetch() throws a same-realm TypeError, so recreate that here (via a tiny
  // same-context eval) rather than throwing a cross-realm one from this outer process.
  if (options.networkFailure) {
    const ContextTypeError = vm.runInContext('TypeError', sandbox);
    context.fetch = async () => { throw new ContextTypeError('Failed to fetch'); };
  } else {
    context.fetch = options.fetchImpl || defaultFetch;
  }

  return {
    node, dialog, form, requests, location: context.location, kindButtons, languageButtons,
    openDialog(dataset) { documentHandlers.click(clickEvent(openButton(dataset))); },
    clickKind(value) { dialog.listeners.click(clickEvent(kindButtons.find(b => b.dataset.newVideoKind === value))); },
    clickLanguage(value) { dialog.listeners.click(clickEvent(languageButtons.find(b => b.dataset.newVideoLanguage === value))); },
    async submit() {
      let prevented = false;
      await form.listeners.submit({preventDefault() { prevented = true; }});
      return prevented;
    },
  };
}

test('opening via the shared [data-new-video] trigger focuses the title field and resets kind/language to defaults', () => {
  const h = harness();
  h.openDialog();
  assert.equal(h.node('#new-video-title-input').focused, true);
  assert.equal(h.dialog.open, true);
  assert.equal(h.kindButtons.find(b => b.dataset.newVideoKind === 'talking-head').attributes['aria-checked'], 'true');
  assert.equal(h.languageButtons.find(b => b.dataset.newVideoLanguage === 'he').attributes['aria-checked'], 'true');
});

test('an empty/invalid title never reaches the network (native form validation blocks submit)', async () => {
  const h = harness({titleValid: false});
  h.openDialog();
  await h.submit();
  assert.equal(h.requests.length, 0);
});

test('choosing a kind tap-card updates aria-checked and is sent in the POST body', async () => {
  const h = harness();
  h.openDialog();
  h.node('#new-video-title-input').value = 'My First Reel';
  h.clickKind('faceless');
  assert.equal(h.kindButtons.find(b => b.dataset.newVideoKind === 'faceless').attributes['aria-checked'], 'true');
  assert.equal(h.kindButtons.find(b => b.dataset.newVideoKind === 'talking-head').attributes['aria-checked'], 'false');
  await h.submit();
  assert.equal(h.requests[0].body.kind, 'faceless');
});

test('the POST body has exactly title/kind/video_language, with X-Studio-Action and JSON content type', async () => {
  const h = harness();
  h.openDialog();
  h.node('#new-video-title-input').value = 'My First Reel';
  h.clickLanguage('en');
  await h.submit();
  const {url, init, body} = h.requests[0];
  assert.equal(url, '/new-video');
  assert.equal(init.method, 'POST');
  assert.equal(init.headers['X-Studio-Action'], 'new-video');
  assert.equal(init.headers['Content-Type'], 'application/json');
  assert.deepEqual(body, {title: 'My First Reel', kind: 'talking-head', video_language: 'en'});
});

test('a reference id passed through the opening button is included as reference_id', async () => {
  const h = harness();
  h.openDialog({referenceId: 'cool-reference'});
  h.node('#new-video-title-input').value = 'My First Reel';
  await h.submit();
  assert.equal(h.requests[0].body.reference_id, 'cool-reference');
});

test('no reference id on the opening button means no reference_id key in the POST body', async () => {
  const h = harness();
  h.openDialog();
  h.node('#new-video-title-input').value = 'My First Reel';
  await h.submit();
  assert.equal('reference_id' in h.requests[0].body, false);
});

test('on success the dialog closes and the location hash navigates to the new project', async () => {
  const h = harness();
  h.openDialog();
  h.node('#new-video-title-input').value = 'My First Reel';
  const prevented = await h.submit();
  assert.equal(prevented, true);
  assert.equal(h.dialog.open, false);
  assert.equal(h.location.hash, '#project=my-first-reel');
});

test('a server error key is shown translated, not as the raw key', async () => {
  const h = harness({fetchImpl: async () => ({ok: false, json: async () => ({error: 'newVideo.error.kind'})})});
  h.openDialog();
  h.node('#new-video-title-input').value = 'My First Reel';
  await h.submit();
  assert.equal(h.node('#new-video-error').textContent, he['newVideo.error.kind']);
  assert.notEqual(h.node('#new-video-error').textContent, 'newVideo.error.kind');
  assert.equal(h.dialog.open, true); // a failed save keeps the dialog open with the error shown
});

test('a network failure (fetch throws TypeError) shows the translated network-error message', async () => {
  const h = harness({networkFailure: true});
  h.openDialog();
  h.node('#new-video-title-input').value = 'My First Reel';
  await h.submit();
  assert.equal(h.node('#new-video-error').textContent, he['dialog.reference.networkError']);
});
