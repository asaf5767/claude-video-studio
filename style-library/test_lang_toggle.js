/* Task 5: the עב / EN header toggle (dist/lang-toggle.js) switches I18N and reflects the active language. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/lang-toggle.js'), 'utf8');

function harness({fail = false} = {}) {
  let lang = 'he';
  const sets = [], docHandlers = {};
  const button = code => ({dataset: {lang: code}, attributes: {}, disabled: false, listeners: {},
    setAttribute(name, value) { this.attributes[name] = String(value); }, addEventListener(type, fn) { this.listeners[type] = fn; }});
  const buttons = [button('he'), button('en')];
  const toast = {textContent: '', hidden: true};
  const document = {querySelectorAll: sel => sel === '[data-lang]' ? buttons : [], querySelector: sel => sel === '#toast' ? toast : null,
    addEventListener: (type, fn) => { docHandlers[type] = fn; }};
  const I18N = {ready: Promise.resolve(), lang: () => lang, t: key => key,
    async set(next) { sets.push(next); if (fail) throw Error('nope'); lang = next; docHandlers['i18n:change']?.({detail: {lang}}); }};
  runInNewContext(source, {window: {}, document, I18N, setTimeout: () => 0});
  return {buttons, sets, toast, docHandlers};
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test('clicking EN switches the studio language and marks EN pressed', async () => {
  const h = harness();
  await flush();
  assert.equal(h.buttons[0].attributes['aria-pressed'], 'true');
  assert.equal(h.buttons[1].attributes['aria-pressed'], 'false');
  await h.buttons[1].listeners.click();
  await flush();
  assert.deepEqual(h.sets, ['en']);
  assert.equal(h.buttons[1].attributes['aria-pressed'], 'true');
  assert.equal(h.buttons[0].attributes['aria-pressed'], 'false');
});

test('clicking the active language does nothing', async () => {
  const h = harness();
  await flush();
  await h.buttons[0].listeners.click();
  assert.deepEqual(h.sets, []);
});

test('a failed switch keeps the current language and tells the user', async () => {
  const h = harness({fail: true});
  await flush();
  await h.buttons[1].listeners.click();
  await flush();
  assert.equal(h.buttons[0].attributes['aria-pressed'], 'true');
  assert.equal(h.toast.textContent, 'app.lang.error');
  assert.equal(h.toast.hidden, false);
  assert.equal(h.buttons[1].disabled, false);
});
