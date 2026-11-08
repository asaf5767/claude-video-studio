/* Task 5: Assaf's identity in the shipped UI: website theme tokens, ember-dot logo instead of Matt's "ai." mark,
   upstream credit in the footer, the עב / EN toggle, the slot headline script, and <bdi> around user titles. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync, existsSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const DIST = join(__dirname, 'dist');
const read = name => readFileSync(join(DIST, name), 'utf8');
const json = name => JSON.parse(read('i18n/' + name));

test("root CSS defines the website's theme tokens", () => {
  const css = read('styles.css');
  const root = /:root\s*\{([^}]*)\}/.exec(css);
  assert.ok(root, 'styles.css has a :root block');
  const tokens = {'--ink': '#07070a', '--text': '#f5ede5', '--muted': '#a89e95', '--dim': '#948a81', '--ember': '#ff6b2c', '--gold': '#ffc77d',
    '--glow': 'rgba(255,107,44,.35)', '--line': 'rgba(255,226,204,.10)', '--panel': 'rgba(10,9,13,.86)', '--r-lg': '24px', '--r-md': '14px', '--r-pill': '999px', '--ease': 'cubic-bezier(.2,.8,.2,1)'};
  for (const [name, value] of Object.entries(tokens)) assert.match(root[1], new RegExp(name + '\\s*:\\s*' + value.replace(/[()|.]/g, '\\$&') + '\\s*(;|$)'), name);
  assert.match(css, /color-scheme\s*:\s*dark/);
});

test("header and footer carry the ember-dot logo, not Matt's ai. mark", () => {
  const html = read('index.html');
  assert.doesNotMatch(html, />ai\.</);
  assert.doesNotMatch(html, /Built by Matt Paige/);
  assert.match(html, /class="monogram[^"]*"[^>]*id="studio-monogram"/);
  assert.match(html, /data-i18n="brand\.tagline"/);
  assert.match(html, /<meta name="theme-color" content="#07070a">/);
  assert.match(html, /<link rel="icon" href="assets\/brand\/ember-dot\.svg" type="image\/svg\+xml">/);
  assert.ok(existsSync(join(DIST, 'assets/brand/ember-dot.svg')));
  const svg = read('assets/brand/ember-dot.svg');
  for (const stop of ['#ffb27d', '#ff6b2c', '#c2410c']) assert.match(svg, new RegExp(stop, 'i'));
  for (const lang of ['he', 'en']) {
    const strings = json(lang + '.json');
    assert.ok(strings['brand.name'] && strings['brand.tagline'], lang + ' brand strings');
  }
  assert.equal(json('he.json')['brand.name'], 'הסטודיו של אסף');
  assert.equal(json('he.json')['brand.tagline'], 'עריכת וידאו עם Claude');
  assert.equal(json('en.json')['brand.name'], 'Assaf’s Studio');
  assert.equal(json('en.json')['brand.tagline'], 'Video editing with Claude');
  // The settings-driven name falls back to brand.name, so a fresh install shows Assaf's studio in either language.
  assert.match(read('app.js'), /settings\.studio_name\|\|I18N\.t\('brand\.name'\)/);
});

test('footer credits the upstream open-source project', () => {
  const html = read('index.html');
  const footer = /<footer>[\s\S]*<\/footer>/.exec(html)[0];
  assert.match(footer, /<a [^>]*href="https:\/\/github\.com\/mattp68\/ai-video-studio"[^>]*data-i18n="footer\.basedOn"[^>]*>[^<]*<\/a>/);
  assert.equal(json('he.json')['footer.basedOn'], 'מבוסס על AI Video Studio של Matt Paige (קוד פתוח, MIT)');
  assert.match(json('en.json')['footer.basedOn'], /^Based on Matt Paige’s AI Video Studio \(open source, MIT\)/);
});

test('header has the עב / EN language toggle and loads the new scripts', () => {
  const html = read('index.html');
  assert.match(html, /<button type="button" data-lang="he" lang="he" aria-pressed="true" data-i18n="app.lang.he">/);
  assert.match(html, /<button type="button" data-lang="en" lang="en" aria-pressed="false" data-i18n="app.lang.en">/);
  assert.match(html, /<script src="lang-toggle\.js" defer><\/script>/);
  assert.match(html, /<script src="slot-headline\.js" defer><\/script>/);
  assert.equal(json('he.json')['app.lang.he'], 'עב');
  assert.equal(json('en.json')['app.lang.en'], 'EN');
});

test('footer has the תנועה / Motion control (auto, always, off) and loads its script', () => {
  const html = read('index.html');
  const footer = /<footer>[\s\S]*<\/footer>/.exec(html)[0];
  assert.match(footer, /<label class="motion-control"><span data-i18n="motion.label">[^<]*<\/span><select id="motion-setting">/);
  for (const value of ['auto', 'always', 'off']) assert.match(footer, new RegExp('<option value="' + value + '" data-i18n="motion.' + value + '">'));
  assert.doesNotMatch(/<header[\s\S]*<\/header>/.exec(html)[0], /motion-setting/, 'not in the header');
  assert.match(html, /<script src="motion-setting\.js" defer><\/script>/);
  assert.equal(json('he.json')['motion.label'], 'תנועה');
  assert.equal(json('en.json')['motion.label'], 'Motion');
});

test('user project titles are wrapped in <bdi> so mixed Hebrew, English and numbers keep their order', () => {
  const studio = read('studio.js');
  const start = studio.indexOf(' function card(p){'), end = studio.indexOf('\n function renderCards(', start);
  assert.ok(start >= 0 && end > start);
  const en = json('en.json');
  const context = {h: s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])), projectHash: () => '#p', stateLabel: () => 'Ready',
    I18N: {t: (key, vars) => Object.keys(vars || {}).reduce((s, k) => s.split('{' + k + '}').join(vars[k]), en[key] ?? key)}};
  runInNewContext(studio.slice(start, end), context);
  const html = context.card({title: 'AI חוסך 38 שניות', subtitle: '', summary: '', artifacts: [], format: 'video', state: 'review'});
  assert.match(html, /<h2><bdi>AI חוסך 38 שניות<\/bdi><\/h2>/);
  assert.match(studio, /<h1><bdi>\$\{h\(p\.title\)\}<\/bdi><\/h1>/, 'project page heading');
  assert.match(studio, /<h2><bdi>\$\{h\(resume\.title\)\}<\/bdi><\/h2>/, 'resume card heading');
});

test('no old brand name left in the UI strings, and the quickstart page shares the theme', () => {
  for (const lang of ['he', 'en']) {
    const strings = json(lang + '.json');
    const old = Object.entries(strings).filter(([key, value]) => /AI Video Studio/.test(value) && key !== 'footer.basedOn').map(([key]) => key);
    assert.deepEqual(old, [], lang + '.json');
  }
  assert.match(json('he.json')['quickstart.docTitle'], /הסטודיו של אסף/);
  assert.match(json('en.json')['quickstart.docTitle'], /Assaf’s Studio/);
  const quick = read('quickstart.html');
  assert.doesNotMatch(quick, /AI Video Studio/);
  assert.match(quick, /<link rel="stylesheet" href="theme\.css">/);
  // The header name is translated text (settings can still override it after load).
  assert.match(read('index.html'), /<span id="studio-name" data-i18n="brand\.name">[^<]*<\/span>/);
});
