const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

class CustomEvent {
  constructor(type, init) {
    this.type = type;
    this.detail = (init && init.detail) || null;
  }
}

function loadI18N(options = {}) {
  const code = readFileSync(join(__dirname, 'dist/i18n.js'), 'utf8');
  // Starts mismatched on purpose (stale pre-i18n "en"/ltr) so passing tests prove the
  // module resolves its own language/direction rather than coincidentally inheriting it.
  const docElement = {lang: 'en', dir: 'ltr'};
  const events = [];
  const requests = [];
  const files = {he: {hi: 'שלום {name}'}, en: {hi: 'Hello {name}'}, ...options.files};
  const languageState = {language: options.initialLanguage || 'he'};
  const warnings = [];
  const document = {
    documentElement: docElement,
    querySelectorAll: () => options.nodes || [],
    dispatchEvent: event => {
      // Real browsers throw a TypeError when dispatchEvent is given anything that
      // isn't an Event/CustomEvent instance; enforce the same here so a regression
      // back to a plain object ({type: ...}) fails this suite instead of only
      // failing silently in a real browser.
      if (!(event instanceof CustomEvent)) throw new TypeError('dispatchEvent requires a CustomEvent');
      events.push(event);
    },
  };
  const fetchImpl = async (url, init) => {
    requests.push({url, init});
    if (url === '/ui-language') {
      if (options.failLanguageLookup) throw new Error('network down');
      if (init && init.method === 'POST') {
        const body = JSON.parse(init.body);
        if (body.language !== 'he' && body.language !== 'en') return {ok: false, status: 400, json: async () => ({error: 'bad'})};
        languageState.language = body.language;
        return {ok: true, json: async () => languageState};
      }
      return {ok: true, json: async () => languageState};
    }
    const match = /^i18n\/(he|en)\.json$/.exec(url);
    if (match) {
      if (options.failStrings) return {ok: false, status: 500, json: async () => ({})};
      return {ok: true, json: async () => files[match[1]]};
    }
    return {ok: false, status: 404, json: async () => ({})};
  };
  const context = {document, fetch: fetchImpl, window: {}, CustomEvent, console: {warn: message => warnings.push(message)}};
  runInNewContext(code, context);
  return {I18N: context.window.I18N, document: docElement, events, requests, warnings};
}

test('t interpolates vars', async () => {
  const {I18N} = loadI18N();
  await I18N.ready;
  assert.equal(I18N.t('hi', {name: 'אסף'}), 'שלום אסף');
});

test('set(en) sets dir ltr and set(he) sets dir rtl', async () => {
  const {I18N, document} = loadI18N();
  await I18N.ready;
  await I18N.set('en');
  assert.equal(document.dir, 'ltr');
  assert.equal(document.lang, 'en');
  assert.equal(I18N.lang(), 'en');
  await I18N.set('he');
  assert.equal(document.dir, 'rtl');
  assert.equal(document.lang, 'he');
  assert.equal(I18N.lang(), 'he');
});

test('he.json and en.json have identical key sets', () => {
  const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));
  const en = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));
  assert.deepEqual(Object.keys(he).sort(), Object.keys(en).sort());
});

test('a missing key returns the key itself and logs only once', async () => {
  const {I18N, warnings} = loadI18N();
  await I18N.ready;
  assert.equal(I18N.t('does-not-exist'), 'does-not-exist');
  assert.equal(I18N.t('does-not-exist'), 'does-not-exist');
  assert.equal(warnings.length, 1);
});

test('set dispatches a real CustomEvent after strings are reloaded', async () => {
  const {I18N, events} = loadI18N();
  await I18N.ready;
  await I18N.set('en');
  assert.equal(events.length, 1);
  assert.ok(events[0] instanceof CustomEvent);
  assert.equal(events[0].type, 'i18n:change');
  assert.equal(events[0].detail.lang, 'en');
});

test('a failed language lookup falls back to Hebrew, not the stale document language', async () => {
  const {I18N, document} = loadI18N({failLanguageLookup: true, initialLanguage: 'en'});
  await I18N.ready;
  assert.equal(I18N.lang(), 'he');
  assert.equal(document.lang, 'he');
  assert.equal(document.dir, 'rtl');
});

test('a failed strings fetch still resolves ready without throwing, falling back to key lookup', async () => {
  const {I18N} = loadI18N({failStrings: true});
  await assert.doesNotReject(I18N.ready);
  assert.equal(I18N.t('hi', {name: 'אסף'}), 'hi');
});

test('data-i18n-title and data-i18n-alt set translated title/alt attributes (Task 4a fix round 1)', async () => {
  const attrs = {};
  const node = {
    getAttribute: name => ({'data-i18n-title': 'label', 'data-i18n-alt': 'picture'}[name] ?? null),
    setAttribute: (name, value) => { attrs[name] = value; },
  };
  const {I18N} = loadI18N({nodes: [node], files: {he: {label: 'תווית', picture: 'תמונה'}, en: {label: 'Label', picture: 'Picture'}}});
  await I18N.ready;
  assert.equal(attrs.title, 'תווית');
  assert.equal(attrs.alt, 'תמונה');
});
