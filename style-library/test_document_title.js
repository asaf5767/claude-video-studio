/* Integration fix: toggling he<->en used to reset <title> to the "Projects" label on every
   page, because app.js's i18n:change handler (applySiteSettings) unconditionally overwrote
   document.title with the projects-section title, racing studio.js's own section-aware
   title update (studio.js's i18n:change listener, which runs after app.js's). This slices
   applySiteSettings() out of app.js (same technique test_studio_ui.js uses for studio.js)
   and checks it only sets the "Projects" title when there is no section router yet (the
   very first load) or the router says the current section really is Projects. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/app.js'), 'utf8');
const start = source.indexOf("async function applySiteSettings(){");
const end = source.indexOf("\ndocument.addEventListener('i18n:change',applySiteSettings);", start);
if (start < 0 || end < start) throw new Error('applySiteSettings() moved or was renamed in app.js');
const slice = source.slice(start, end + 1);

function harness({studio} = {}) {
  const nodes = new Map();
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, {textContent: '', hidden: false, href: ''});
    return nodes.get(key);
  };
  const settings = {
    studio_name: 'הסטודיו של אסף',
    library_label: 'ספרייה',
    monogram: 'א',
    credit: {name: '', url: ''},
  };
  const document = {title: 'stale title'};
  const context = {
    $: node,
    document,
    window: studio === undefined ? {} : {Studio: {currentSection: studio}},
    I18N: {t: key => key},
    fetch: async () => ({ok: true, json: async () => settings}),
  };
  runInNewContext(slice, context);
  return {context, document};
}

test('before the section router exists (first page load), the title is set', async () => {
  const {context, document} = harness();
  await context.applySiteSettings();
  assert.equal(document.title, 'הסטודיו של אסף · app.nav.projects');
});

test('on the projects section, the title still follows i18n', async () => {
  const {context, document} = harness({studio: 'projects'});
  await context.applySiteSettings();
  assert.equal(document.title, 'הסטודיו של אסף · app.nav.projects');
});

test('on any other section, applySiteSettings leaves the title to the section router', async () => {
  for (const section of ['library', 'project', 'guide', 'updates', 'effects']) {
    const {context, document} = harness({studio: section});
    document.title = 'set by the section router';
    await context.applySiteSettings();
    assert.equal(document.title, 'set by the section router', `section=${section}`);
  }
});
