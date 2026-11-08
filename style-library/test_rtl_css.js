/* Task 5: RTL-safe CSS and Assaf's bundled fonts.
   (1) No physical-direction declaration (margin-left, padding-right, left:, text-align:right, ...)
       outside a rule that is explicitly marked with a /* physical-ok *\/ comment.
   (2) Every font-family (and the family part of every `font:` shorthand) starts with a bundled
       family: one of the role variables (--display/--body/--head/--aside/--mono/--serif) or a
       name that has an @font-face in dist CSS. The role variables themselves start with one.
   (3) No italics under html[lang="he"]: no font-style:italic / `font:italic` at all, and em/i
       are reset to normal.
   (4) Matt's fonts (Archivo Black, Instrument Serif, Inter) are gone from dist. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync, readdirSync, existsSync} = require('node:fs');
const {join} = require('node:path');

const DIST = join(__dirname, 'dist');
const cssFiles = readdirSync(DIST).filter(name => name.endsWith('.css'));
const read = name => readFileSync(join(DIST, name), 'utf8');

// Innermost `selector{body}` blocks; nested @media wrappers fall away because the selector
// part cannot contain a brace. Comments are kept so /* physical-ok */ can be seen.
function rules(css) {
  const out = [];
  const re = /([^{}]*)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(css))) out.push({selector: m[1].trim(), body: m[2]});
  return out;
}

function declarations(body) {
  return body.replace(/\/\*[\s\S]*?\*\//g, '').split(';').map(d => d.trim()).filter(Boolean).map(d => {
    const i = d.indexOf(':');
    return {prop: d.slice(0, i).trim().toLowerCase(), value: d.slice(i + 1).trim()};
  });
}

const PHYSICAL_PROP = /^(margin-left|margin-right|padding-left|padding-right|border-left(-[a-z]+)?|border-right(-[a-z]+)?|left|right)$/;

test('dist CSS has no physical-direction declarations outside /* physical-ok */ rules', () => {
  const hits = [];
  for (const file of cssFiles) {
    for (const rule of rules(read(file))) {
      if (rule.selector.startsWith('@font-face')) continue;
      if (/\/\*\s*physical-ok\s*\*\//.test(rule.body) || /\/\*\s*physical-ok\s*\*\//.test(rule.selector)) continue;
      for (const {prop, value} of declarations(rule.body)) {
        if (PHYSICAL_PROP.test(prop) || ((prop === 'text-align' || prop === 'float' || prop === 'clear') && /^(left|right)\b/.test(value)))
          hits.push(file + ': ' + rule.selector.slice(-60) + ' { ' + prop + ':' + value + ' }');
      }
    }
  }
  assert.deepEqual(hits, []);
});

function fontFaceFamilies() {
  const names = new Set();
  for (const file of cssFiles) {
    const re = /@font-face\s*\{[^}]*font-family\s*:\s*["']?([^;"'}]+)["']?/g;
    let m;
    while ((m = re.exec(read(file)))) names.add(m[1].trim().toLowerCase());
  }
  return names;
}

const ROLE_VARS = ['--display', '--body', '--head', '--aside', '--mono', '--serif'];

function firstFamily(stack) {
  const first = stack.split(',')[0].trim();
  const v = /^var\(\s*(--[a-z-]+)/.exec(first);
  if (v) return {variable: v[1]};
  return {name: first.replace(/^["']|["']$/g, '').trim().toLowerCase()};
}

function shorthandFamily(value) {
  // `font: [style] [weight] size[/line-height] family, ...` -> the family list
  const m = /(?:^|\s)(?:[\d.]+(?:px|em|rem|%|vw|vh)|var\([^)]*\)|clamp\([^)]*\)|larger|smaller|medium|small|large)(?:\/[^\s]+)?\s+(.+)$/.exec(value);
  return m ? m[1] : null;
}

test('every font-family in dist CSS starts with a bundled family', () => {
  const bundled = fontFaceFamilies();
  const bad = [];
  const okFirst = (stack, where) => {
    const first = firstFamily(stack);
    if (first.variable ? !ROLE_VARS.includes(first.variable) : !bundled.has(first.name)) bad.push(where + ' -> ' + stack);
  };
  for (const file of cssFiles) {
    for (const rule of rules(read(file))) {
      if (rule.selector.startsWith('@font-face')) continue;
      for (const {prop, value} of declarations(rule.body)) {
        if (prop === 'font-family') { if (value !== 'inherit') okFirst(value, file + ' ' + rule.selector.slice(-50)); }
        else if (prop === 'font') {
          if (/^(inherit|initial|unset)$/.test(value)) continue;
          const family = shorthandFamily(value);
          if (!family) bad.push(file + ' ' + rule.selector.slice(-50) + ' -> unparsed font:' + value);
          else okFirst(family, file + ' ' + rule.selector.slice(-50));
        } else if (ROLE_VARS.includes(prop)) okFirst(value, file + ' ' + prop);
      }
    }
  }
  assert.deepEqual(bad, []);
  const root = read('styles.css');
  for (const role of ['--display', '--body', '--head', '--aside', '--mono']) assert.match(root, new RegExp(role + '\\s*:'), 'styles.css defines ' + role);
});

test('every @font-face file exists in dist/assets/fonts and has a licence next to it', () => {
  const missing = [];
  for (const file of cssFiles) {
    const re = /url\(["']?(assets\/fonts\/[^)"']+)["']?\)/g;
    let m;
    while ((m = re.exec(read(file)))) if (!existsSync(join(DIST, m[1]))) missing.push(m[1]);
  }
  assert.deepEqual(missing, []);
  const fonts = readdirSync(join(DIST, 'assets', 'fonts'));
  for (const font of fonts.filter(name => /\.(woff2?|ttf)$/.test(name))) {
    // Files are named <family>-<weight>-<subset>.woff2 and licences <family>-LICENSE.txt.
    const family = font.replace(/-\d.*$/, '');
    assert.ok(fonts.includes(family + '-LICENSE.txt'), 'licence for ' + font);
  }
});

test('no italics in the studio (Hebrew has no italic) and em/i are reset upright', () => {
  const hits = [];
  for (const file of cssFiles) {
    for (const rule of rules(read(file))) {
      for (const {prop, value} of declarations(rule.body)) {
        if ((prop === 'font-style' && /italic|oblique/.test(value)) || (prop === 'font' && /\b(italic|oblique)\b/.test(value))) hits.push(file + ' ' + rule.selector.slice(-60));
      }
    }
  }
  assert.deepEqual(hits, []);
  assert.match(read('styles.css'), /(^|[}\s,])em\s*,\s*i\s*\{[^}]*font-style\s*:\s*normal/);
});

test("Matt's fonts are gone: no Archivo, Instrument or Inter in dist", () => {
  const offenders = [];
  for (const name of readdirSync(DIST).filter(n => /\.(css|html|js)$/.test(n))) {
    if (/archivo|instrument|\binter\b|InterLocal/i.test(read(name))) offenders.push(name);
  }
  for (const font of readdirSync(join(DIST, 'assets', 'fonts'))) if (/archivo|instrument|inter/i.test(font)) offenders.push('assets/fonts/' + font);
  assert.deepEqual(offenders, []);
});

test('directional arrows mirror in RTL', () => {
  const css = cssFiles.map(read).join('\n');
  assert.match(css, /\[dir=["']?rtl["']?\][^{]*\.arrow[^{]*\{[^}]*scaleX\(-1\)/);
});

// Fix round 2: a physical background-position (a select's arrow, an icon) must have a [dir=rtl] counterpart,
// otherwise in Hebrew the arrow sits on top of the text.
function physicalBackgroundPosition(prop, value) {
  if (prop === 'background-position') return /\b(left|right)\b/.test(value);
  if (prop === 'background') return /\b(left|right)\b/.test(value.replace(/url\([^)]*\)/g, ''));
  return false;
}

test('a physical background-position (left/right) has a [dir=rtl] counterpart', () => {
  const all = cssFiles.flatMap(file => rules(read(file)).map(rule => ({...rule, file})));
  const missing = [];
  for (const rule of all) {
    if (/\[dir=["']?rtl["']?\]/.test(rule.selector)) continue;
    if (/\/\*\s*physical-ok\s*\*\//.test(rule.body)) continue;
    if (!declarations(rule.body).some(d => physicalBackgroundPosition(d.prop, d.value))) continue;
    const first = rule.selector.replace(/\/\*[\s\S]*?\*\//g, '').split(',')[0].trim();
    const counterpart = all.some(other => /\[dir=["']?rtl["']?\]/.test(other.selector) && other.selector.includes(first) &&
      declarations(other.body).some(d => d.prop === 'background-position'));
    if (!counterpart) missing.push(rule.file + ': ' + first);
  }
  assert.deepEqual(missing, []);
});

test("data-URI icons are drawn in theme colours, not Matt's olive", () => {
  const olive = [];
  for (const file of cssFiles) {
    for (const m of read(file).matchAll(/url\(["']?data:image\/svg\+xml[^)]*\)/g)) {
      for (const hex of m[0].matchAll(/%23([0-9a-fA-F]{6})/g)) {
        const [r, g, b] = [0, 2, 4].map(i => parseInt(hex[1].slice(i, i + 2), 16));
        if (g > r && g > b) olive.push(file + ': #' + hex[1]); // greenish = Matt's olive palette
      }
    }
  }
  assert.deepEqual(olive, []);
});

test('closed disclosure chevrons point the reading way in RTL and still turn down when open', () => {
  const css = cssFiles.map(read).join('\n');
  const rtlRules = rules(css).filter(rule => /\[dir=["']?rtl["']?\]/.test(rule.selector));
  for (const sel of ['.project-script', '.reference-note-composer']) {
    const closed = rtlRules.find(rule => rule.selector.split(',').some(s => s.trim().endsWith(sel + '>summary:before')));
    const open = rtlRules.find(rule => rule.selector.split(',').some(s => s.trim().endsWith(sel + '[open]>summary:before')));
    assert.ok(closed && /scaleX\(-1\)/.test(closed.body), sel + ' closed points the RTL way');
    assert.ok(open && /rotate\(90deg\)/.test(open.body), sel + ' open still turns down');
  }
});

test('UI arrows and check marks render in a bundled font; ⋯ (not in any bundled font) is not used', () => {
  // Heebo has no arrow/check glyphs, so a symbols subset of IBM Plex Mono (OFL) is registered as an extra
  // "Heebo" face limited to those code points; every font stack falls back to Heebo.
  const faces = [...read('styles.css').matchAll(/@font-face\{font-family:"Heebo"[^}]*\}/g)].map(m => m[0]);
  const symbols = faces.find(face => /plex-mono-400-symbols/.test(face));
  assert.ok(symbols, 'a Heebo face points at the Plex Mono symbols subset');
  for (const range of ['U+2190-2199', 'U+21BB', 'U+2713']) assert.ok(symbols.includes(range), 'symbols face covers ' + range);
  const ui = readdirSync(DIST).filter(n => /\.(html|js)$/.test(n)).map(read).join('') + read('i18n/he.json') + read('i18n/en.json');
  assert.doesNotMatch(ui, /\u22EF/);
});
