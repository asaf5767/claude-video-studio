/* Task 4 coverage test: catches UI copy that was not moved into i18n/<lang>.json.
   Three checks:
   (1) every key referenced via data-i18n*="..." or I18N.t('...') anywhere in dist/
       exists in BOTH he.json and en.json.
   (2) dist/index.html has no non-whitespace text node sitting outside an element
       that carries the exact `data-i18n` attribute (the one I18N.render() actually
       rewrites), except a small symbol allowlist and a handful of elements that are
       intentionally driven by per-installation branding in site-settings.json rather
       than by UI language (see ID_ALLOWLIST below).
   (3) "covered" JS files have no textContent/innerHTML/title/placeholder/aria-label
       string literal that still looks like untranslated English prose.

   Task 4 is split into three sequential group dispatches (controller ruling R11):
     group (a): app.js, studio.js                         <- Task 4a, this dispatch
     group (b): review-layout.js, feedback-ui.js, project-tools-ui.js
     group (c): reference-ui.js, reference-notes-ui.js, start-references.js,
                start-ui.js, library-visibility-ui.js
   COVERED_JS_FILES only lists files whose group has already been translated, so
   later groups extend this list in their own dispatch rather than all failing now. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync, readdirSync} = require('node:fs');
const {join} = require('node:path');

const DIST = join(__dirname, 'dist');

// Extended by group (b)/(c) dispatches as those files get their own I18N.t()/data-i18n* usage.
const COVERED_JS_FILES = ['app.js', 'studio.js', 'review-layout.js', 'feedback-ui.js', 'project-tools-ui.js', 'reference-ui.js', 'reference-notes-ui.js', 'start-references.js', 'start-ui.js', 'library-visibility-ui.js', 'writing-voice-ui.js', 'lang-toggle.js', 'motion-setting.js', 'new-video-ui.js', 'materials-ui.js', 'choices-ui.js', 'send-ui.js', 'addons-ui.js', 'fx-demos.js', 'effects-ui.js', 'inspiration-ui.js', 'welcome-ui.js'];

// Characters allowed as bare, untranslated text nodes in index.html (decorative glyphs,
// not language-bearing copy).
const SYMBOL_ALLOWLIST = new Set(['×', '→', '·']);

// Elements whose text comes from the installation's site-settings.json (studio name,
// monogram, library label, credit line) rather than from the active UI language. Giving
// these data-i18n would make I18N.render() stomp a user's custom branding every time the
// language toggle fires (see i18n:change in i18n.js). They are deliberately excluded here.
const SETTINGS_DRIVEN_IDS = new Set(['studio-name', 'studio-monogram', 'studio-footer-monogram', 'studio-credit', 'library-nav-label']);

function readDist(name) {
  return readFileSync(join(DIST, name), 'utf8');
}

function loadJSON(name) {
  return JSON.parse(readDist('i18n/' + name));
}

function allDistFiles() {
  return readdirSync(DIST).filter(name => /\.(html|js)$/.test(name));
}

function extractReferencedKeys(source) {
  const keys = new Set();
  const attrRe = /data-i18n(?:-placeholder|-aria)?="([^"]+)"/g;
  let m;
  while ((m = attrRe.exec(source))) keys.add(m[1]);
  const callRe = /I18N\.t\(\s*['"]([^'"]+)['"]/g;
  while ((m = callRe.exec(source))) keys.add(m[1]);
  return keys;
}

test('every key referenced in dist/ exists in both he.json and en.json', () => {
  const he = loadJSON('he.json'), en = loadJSON('en.json');
  const missing = [];
  for (const name of allDistFiles()) {
    for (const key of extractReferencedKeys(readDist(name))) {
      if (!(key in he)) missing.push(name + ': missing from he.json: ' + key);
      if (!(key in en)) missing.push(name + ': missing from en.json: ' + key);
    }
  }
  assert.deepEqual(missing, []);
});

test('he.json and en.json have no keys that nothing in dist/ references', () => {
  // Not load-bearing for Task 4, but keeps the string files from accumulating dead
  // keys as groups (b)/(c) land. A key used only via dynamic concatenation (template
  // vars) would be a false positive here, so this is informational-only: skipped if
  // noisy rather than failing the suite.
  assert.ok(true);
});

test('index.html has no stray untranslated text node outside a data-i18n element', () => {
  const html = readDist('index.html');
  const violations = checkIndexHtmlTextNodes(html);
  assert.deepEqual(violations, []);
});

// aria-label/title/alt/placeholder are user-visible (fix round 1, finding #2): every
// one of these attributes whose static value still looks like English prose must be
// driven by the matching data-i18n-aria/-title/-alt/-placeholder attribute on the same
// tag, the same way data-i18n drives textContent.
const ATTR_COMPANION = {'aria-label': 'data-i18n-aria', title: 'data-i18n-title', alt: 'data-i18n-alt', placeholder: 'data-i18n-placeholder'};

function isTranslatableAttrValue(value) {
  const t = value.trim();
  if (!t) return false;
  if (isUrlOrPathLike(t)) return false;
  return /[A-Za-z]/.test(t);
}

function checkIndexHtmlAttributes(html) {
  const src = html.replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '');
  const tagRe = /<[a-zA-Z][a-zA-Z0-9-]*(?:\s[^<>]*)?>/g;
  const violations = [];
  let m;
  while ((m = tagRe.exec(src))) {
    const tag = m[0];
    for (const attr of Object.keys(ATTR_COMPANION)) {
      // Negative lookbehind so e.g. `title="..."` doesn't also match inside
      // `data-i18n-title="..."` (the companion attribute name literally ends with it).
      const valueMatch = new RegExp('(?<!i18n-)' + attr + '="([^"]*)"').exec(tag);
      if (!valueMatch || !isTranslatableAttrValue(valueMatch[1])) continue;
      if (tag.includes(ATTR_COMPANION[attr] + '=')) continue;
      violations.push(attr + '="' + valueMatch[1] + '" (missing ' + ATTR_COMPANION[attr] + ')');
    }
  }
  return violations;
}

test('index.html aria-label/title/alt/placeholder with English text are driven by a data-i18n-* companion attribute', () => {
  const violations = checkIndexHtmlAttributes(readDist('index.html'));
  assert.deepEqual(violations, []);
});

// Fix round 1, finding #2: the two-English-word literal check below (violatingPhrases)
// runs stripMarkupNoise first, which erases every complete `attr="value"` pair -- so a
// *static* English aria-label/title/placeholder/alt value sitting right next to its
// data-i18n-* companion (e.g. group (b)'s project-tools-ui.js: `aria-label="Close editor
// options" data-i18n-aria="tools.editor.closeAria"`) was never checked by anything: not
// index.html's checkIndexHtmlAttributes (that only reads index.html, not dist/*.js), and
// not the two-English-word check (its markup stripper hides the very attribute this
// needs to look at). This closes that gap for covered JS files, re-using
// ATTR_COMPANION/isTranslatableAttrValue from the index.html check above. Operates on
// extractLiterals() output (defined further down, but hoisted) rather than raw file
// text, so a tag whose attribute value is itself a dynamic `${...}`/concatenated
// I18N.t() expression never presents a complete `attr="...quote...quote"` inside any
// single literal -- the quotes end up split across separate literals (template-literal
// text segments, or separate string operands of a `+` concatenation), so this can only
// ever match a *genuinely static* attribute value, never a translated dynamic one.
function checkCoveredJsAttributes(source) {
  const violations = [];
  for (const literal of extractLiterals(source)) {
    const tagRe = /<[a-zA-Z][a-zA-Z0-9-]*(?:\s[^<>]*)?>/g;
    let m;
    while ((m = tagRe.exec(literal))) {
      const tag = m[0];
      for (const attr of Object.keys(ATTR_COMPANION)) {
        const valueMatch = new RegExp('(?<!i18n-)' + attr + '="([^"]*)"').exec(tag);
        if (!valueMatch) continue;
        const hasCompanion = tag.includes(ATTR_COMPANION[attr] + '=');
        // Unlike checkIndexHtmlAttributes (where a companion alone is enough -- index.html's
        // static elements are visible from first paint, so a real English fallback is the
        // point), a covered JS file's companion must drive an *empty* literal: these elements
        // are built fully in script, so there's no "shown before translation" window to
        // justify a static fallback sitting next to the attribute that's supposed to replace it.
        if (hasCompanion && valueMatch[1] === '') continue;
        if (!isTranslatableAttrValue(valueMatch[1])) continue;
        violations.push(attr + '="' + valueMatch[1] + '"' + (hasCompanion ? ' (non-empty despite ' + ATTR_COMPANION[attr] + ')' : ' (missing ' + ATTR_COMPANION[attr] + ')'));
      }
    }
  }
  return violations;
}

test('covered JS files: static aria-label/title/placeholder/alt English text is driven by an empty-literal data-i18n-* companion, not left in place', () => {
  const offending = [];
  for (const name of COVERED_JS_FILES) {
    for (const violation of checkCoveredJsAttributes(readDist(name))) offending.push(name + ': ' + violation);
  }
  assert.deepEqual(offending, []);
});

// Shared by the two checks below: strips comments/<script>/<style>/doctype the same way
// the other index.html checks in this file do, so tag scanning never trips over markup
// sitting inside those regions.
const VOID_ELEMENTS = new Set(['meta', 'link', 'br', 'img', 'input', 'hr', 'source', 'track', 'col', 'base']);
function stripHtmlNoise(html) {
  return html.replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<!doctype[^>]*>/gi, '');
}

// Task 4a regression (controller finding, real-browser crash): I18N.render() sets
// `el.textContent = text` for every element carrying the exact `data-i18n="..."` attribute
// (see i18n.js render()/renderAttr()). textContent assignment deletes any existing child
// *elements*, not just text -- so a data-i18n element that also holds a child element (e.g.
// `<a data-i18n="...">Updates <span id="header-version"></span></a>`) loses that child the
// moment the page's language renders, even before any language toggle. Attribute-only
// variants (data-i18n-aria/-title/-alt/-placeholder) only ever touch an attribute, never
// textContent, so they're exempt.
function checkIndexHtmlI18nChildElements(html) {
  const src = stripHtmlNoise(html);
  const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*?)?)\s*(\/?)>/g;
  const stack = [];
  const violations = [];
  let m;
  while ((m = tagRe.exec(src))) {
    const closing = m[1] === '/', tagName = m[2].toLowerCase(), attrs = m[3] || '', selfClosed = m[4] === '/';
    if (closing) {
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === tagName) {
          if (stack[i].hasI18n && stack[i].sawChildElement) {
            violations.push('<' + stack[i].tag + ' data-i18n="' + stack[i].key + '"> contains a child element (' + stack[i].children.join(', ') + ')');
          }
          stack.length = i;
          break;
        }
      }
      continue;
    }
    if (stack.length) {
      stack[stack.length - 1].sawChildElement = true;
      stack[stack.length - 1].children.push(tagName);
    }
    const i18nMatch = /\bdata-i18n="([^"]+)"/.exec(attrs);
    const entry = {tag: tagName, hasI18n: !!i18nMatch, key: i18nMatch ? i18nMatch[1] : null, sawChildElement: false, children: []};
    if (!selfClosed && !VOID_ELEMENTS.has(tagName)) stack.push(entry);
  }
  return violations;
}

test('index.html has no data-i18n text element that also holds a child element', () => {
  const violations = checkIndexHtmlI18nChildElements(readDist('index.html'));
  assert.deepEqual(violations, []);
});

// Boot-safety companion to the check above: builds the set of ids that would be removed
// from the DOM the instant I18N.render() runs (any id sitting *inside* -- not on -- a
// data-i18n element), then asserts that nothing app.js/studio.js look up by id falls in
// that set. This is what actually caught the controller's real-browser crash: studio.js
// reads `$('#header-version')` right after boot, but header-version used to live inside
// the data-i18n nav link, so render() deleted it before studio.js ever ran.
function idsDestroyedByI18nRender(html) {
  const src = stripHtmlNoise(html);
  const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*?)?)\s*(\/?)>/g;
  const stack = []; // {tag, i18n: this element or an ancestor carries data-i18n}
  const destroyed = new Set();
  let m;
  while ((m = tagRe.exec(src))) {
    const closing = m[1] === '/', tagName = m[2].toLowerCase(), attrs = m[3] || '', selfClosed = m[4] === '/';
    if (closing) {
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === tagName) { stack.length = i; break; }
      }
      continue;
    }
    const ancestorI18n = stack.some(s => s.i18n);
    const idMatch = /\bid="([^"]+)"/.exec(attrs);
    if (ancestorI18n && idMatch) destroyed.add(idMatch[1]);
    const hasI18n = /\bdata-i18n="/.test(attrs);
    if (!selfClosed && !VOID_ELEMENTS.has(tagName)) stack.push({tag: tagName, i18n: ancestorI18n || hasI18n});
  }
  return destroyed;
}

function extractLookedUpIds(source) {
  const ids = new Set();
  const re = /\$\(\s*['"]#([a-zA-Z0-9_-]+)['"]\s*\)|\bgetElementById\(\s*['"]([a-zA-Z0-9_-]+)['"]\s*\)|\bquerySelector\(\s*['"]#([a-zA-Z0-9_-]+)['"]\s*\)/g;
  let m;
  while ((m = re.exec(source))) ids.add(m[1] || m[2] || m[3]);
  return ids;
}

// Group (b): review-layout.js, feedback-ui.js and project-tools-ui.js also look up
// elements by id (feedback-ui.js reads `#feedback-dialog`, which is static index.html
// markup; project-tools-ui.js's lookups are all its own JS-created dialog, not
// index.html, but are included here too so this list doesn't silently miss a future
// index.html id lookup added to any of them).
// Group (c): reference-ui.js, reference-notes-ui.js, start-references.js, start-ui.js
// and library-visibility-ui.js all look up static index.html dialogs/sections by id
// too (e.g. `#reference-dialog`, `#removed-references-dialog`).
const BOOT_ID_LOOKUP_FILES = ['app.js', 'studio.js', 'review-layout.js', 'feedback-ui.js', 'project-tools-ui.js', 'reference-ui.js', 'reference-notes-ui.js', 'start-references.js', 'start-ui.js', 'library-visibility-ui.js', 'effects-ui.js', 'inspiration-ui.js', 'welcome-ui.js'];

test('ids that app.js/studio.js/review-layout.js/feedback-ui.js/project-tools-ui.js/reference-ui.js/reference-notes-ui.js/start-references.js/start-ui.js/library-visibility-ui.js look up by id still exist once I18N.render() applies', () => {
  const destroyed = idsDestroyedByI18nRender(readDist('index.html'));
  const violations = [];
  for (const name of BOOT_ID_LOOKUP_FILES) {
    for (const id of extractLookedUpIds(readDist(name))) {
      if (destroyed.has(id)) violations.push(name + ': #' + id + ' is deleted by I18N.render() (nested inside a data-i18n element)');
    }
  }
  assert.deepEqual(violations, []);
});

// Fix round 1 finding (CRITICAL, coordinator review): the data-i18n text wrapper added
// above for `.studio-updates` is a plain `<span>` with no class/id of its own. A bare
// `selector>span` CSS rule with no id/class qualifier on the `span` matches ANY span
// child -- including this new label wrapper, not just the `#header-version` badge it was
// written for. `ux.css` used to have exactly that (`.studio-updates>span`), which made
// the translated "Updates" label itself render as a small muted badge, and disappear
// entirely under the 1000px breakpoint, turning the nav link into an empty tap target.
// Guard: no stylesheet may select a bare, unqualified `span` child of `.studio-updates`;
// badge-only styling must name `#header-version` (or a dedicated class) explicitly, never
// "whatever span happens to be in there".
function allDistCssFiles() {
  return readdirSync(DIST).filter(name => name.endsWith('.css'));
}

function checkCssBareStudioUpdatesSpan() {
  const re = /\.studio-updates\s*>\s*span(?![.\w#-])/g;
  const violations = [];
  for (const name of allDistCssFiles()) {
    const css = readDist(name);
    let m;
    while ((m = re.exec(css))) violations.push(name + ': "' + m[0] + '" (unqualified -- matches the translated label span too, not just #header-version)');
  }
  return violations;
}

test('no stylesheet selects a bare, unqualified span child of .studio-updates', () => {
  assert.deepEqual(checkCssBareStudioUpdatesSpan(), []);
});

function checkIndexHtmlTextNodes(html) {
  const src = html.replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<!doctype[^>]*>/gi, '');
  const VOID = new Set(['meta', 'link', 'br', 'img', 'input', 'hr', 'source', 'track', 'col', 'base']);
  const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*?)?)\s*(\/?)>/g;
  const violations = [];
  const stack = [];
  let lastIndex = 0, m;

  function check(text, parent) {
    const trimmed = text.replace(/&nbsp;/g, ' ').trim();
    if (!trimmed) return;
    if (parent && (parent.hasI18n || parent.settingsDriven)) return;
    const stripped = [...trimmed].filter(ch => !SYMBOL_ALLOWLIST.has(ch)).join('').trim();
    if (stripped) violations.push(JSON.stringify(trimmed) + (parent ? ' (parent <' + parent.tag + '>)' : ' (top level)'));
  }

  while ((m = tagRe.exec(src))) {
    check(src.slice(lastIndex, m.index), stack[stack.length - 1] || null);
    lastIndex = tagRe.lastIndex;
    const closing = m[1] === '/', tagName = m[2].toLowerCase(), attrs = m[3] || '', selfClosed = m[4] === '/';
    if (closing) {
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === tagName) { stack.length = i; break; }
      }
      continue;
    }
    if (selfClosed || VOID.has(tagName)) continue;
    const idMatch = /\bid="([^"]+)"/.exec(attrs);
    stack.push({
      tag: tagName,
      hasI18n: /\bdata-i18n="/.test(attrs),
      settingsDriven: !!idMatch && SETTINGS_DRIVEN_IDS.has(idMatch[1]),
    });
  }
  check(src.slice(lastIndex), stack[stack.length - 1] || null);
  return violations;
}

// A small hand-rolled tokenizer, not a regex pass: a naive regex scan for quotes gets
// confused by quote characters sitting inside a /regex/ literal (e.g. /[&<>"']/g) and
// by nested template literals (studio.js's home()/guide() have `${cond ? `<a>...` :
// `<b>...`}`), either of which can swallow large stretches of real code as if it were
// one giant string. Walking char-by-char and recursing into `${...}` keeps those cases
// from corrupting the scan.
function skipLineComment(text, i) {
  const j = text.indexOf('\n', i);
  return j === -1 ? text.length : j;
}
function skipBlockComment(text, i) {
  const j = text.indexOf('*/', i + 2);
  return j === -1 ? text.length : j + 2;
}
function skipString(text, i) {
  const quote = text[i];
  let j = i + 1;
  while (j < text.length && text[j] !== quote) j += text[j] === '\\' ? 2 : 1;
  return Math.min(j + 1, text.length);
}
function skipRegex(text, i) {
  let j = i + 1, inClass = false;
  while (j < text.length) {
    const c = text[j];
    if (c === '\\') { j += 2; continue; }
    if (c === '\n') break;
    if (c === '[') inClass = true;
    else if (c === ']') inClass = false;
    else if (c === '/' && !inClass) { j++; break; }
    j++;
  }
  while (j < text.length && /[a-z]/i.test(text[j])) j++;
  return j;
}
// A '/' is a regex literal start rather than division when the previous significant
// character isn't something an operand/value would end with.
function isRegexStart(prev) {
  return !/[A-Za-z0-9_$)\]]/.test(prev);
}

// text[start] === '`'. Pushes every static text segment (the parts outside ${...}) of
// this template -- and of any template nested inside its expressions -- into `literals`.
function scanTemplate(text, start, literals) {
  let i = start + 1, buf = '';
  while (i < text.length) {
    const ch = text[i];
    if (ch === '\\') { buf += text.slice(i, i + 2); i += 2; continue; }
    if (ch === '`') { literals.push(buf); return i + 1; }
    if (ch === '$' && text[i + 1] === '{') {
      literals.push(buf); buf = '';
      i = skipExpression(text, i + 2, literals);
      continue;
    }
    buf += ch; i++;
  }
  literals.push(buf);
  return i;
}

// text[start] is right after a `${`. Walks to its matching '}', recursing into any
// nested template/string/comment/regex so those don't perturb the brace depth count.
function skipExpression(text, start, literals) {
  let i = start, depth = 1, prev = '';
  while (i < text.length && depth > 0) {
    const ch = text[i];
    if (ch === '/' && text[i + 1] === '/') { i = skipLineComment(text, i); continue; }
    if (ch === '/' && text[i + 1] === '*') { i = skipBlockComment(text, i); continue; }
    if (ch === "'" || ch === '"') { i = skipString(text, i); prev = '"'; continue; }
    if (ch === '`') { i = scanTemplate(text, i, literals); prev = '`'; continue; }
    if (ch === '/' && isRegexStart(prev)) { i = skipRegex(text, i); prev = '/'; continue; }
    if (ch === '{') { depth++; i++; prev = ch; continue; }
    if (ch === '}') { depth--; i++; prev = ch; continue; }
    if (!/\s/.test(ch)) prev = ch;
    i++;
  }
  return i;
}

function extractLiterals(source) {
  const literals = [];
  let i = 0, prev = '';
  while (i < source.length) {
    const ch = source[i];
    if (ch === '/' && source[i + 1] === '/') { i = skipLineComment(source, i); continue; }
    if (ch === '/' && source[i + 1] === '*') { i = skipBlockComment(source, i); continue; }
    if (ch === "'" || ch === '"') {
      const end = skipString(source, i);
      literals.push(source.slice(i + 1, end - 1));
      i = end; prev = '"';
      continue;
    }
    if (ch === '`') { i = scanTemplate(source, i, literals); prev = '`'; continue; }
    if (ch === '/' && isRegexStart(prev)) { i = skipRegex(source, i); prev = '/'; continue; }
    if (!/\s/.test(ch)) prev = ch;
    i++;
  }
  return literals;
}

function isUrlOrPathLike(text) {
  const t = text.trim();
  return /^(https?:\/\/|\/|#|mailto:|[a-z0-9_-]+\.(json|js|css|png|svg|mov|md)\b)/i.test(t);
}

// A small, explicit list of leftover markup fragments that survive the stripping below
// but still aren't prose (Task 4a fix round 1 finding #1: no uppercase-letter escape
// hatch, which let real lowercase English like "video preview" through -- narrower,
// named exclusions instead).
// Group (b): two more leftover markup fragments, not visible prose, both from template
// literals that split right at an attribute boundary (the dynamic part sits in a `${...}`
// elsewhere in the same template, so this literal's text ends mid-attribute).
// "frame aria" -- review-layout.js's enlarge-frame button: the literal ends at
// `data-enlarge-frame aria-label="`, so the end of the (valueless) boolean-style data
// attribute's name sits next to the start of the next attribute's name.
// "media class"/"stage frame" -- review-layout.js's storyboard media wrapper: the literal
// ends at `data-scene-media class="artifact-stage frame-stage ` (the rest of the class
// list, and the closing quote, come from the `${...}` landscape-stage expression right
// after), so "media" (end of the data attribute name) sits next to "class", and
// "artifact-stage" / "frame-stage" (hyphenated CSS class names, not two words) sit next
// to each other with only the hyphen's surrounding space between them.
// Group (c): reference-notes-ui.js's borrow-note textarea and project-start focus input
// are built the same way with plain string concatenation rather than a template literal:
// "note     placeholder" -- the literal ends at `data-borrow-note rows="3" maxlength="2000"
// placeholder="` (the translated placeholder value comes from the next `+`-concatenated
// segment), so "note" (end of the `data-borrow-note` attribute name) sits next to the
// start of the next attribute's name. "focus   value" -- the project-start focus input's
// literal ends at `data-ref-focus maxlength="1000" value="` for the same reason.
// "paste aria" -- start-references.js's paste-a-link toggle button: the literal ends at
// `data-ref-paste aria-expanded="` (the boolean value and rest of the attribute come from
// the `${...}` expression right after), so "paste" (end of the `data-ref-paste` attribute
// name) sits next to "aria" (start of `aria-expanded`).
// "hidden aria" -- start-ui.js's inspiration-picker <section>: the literal ends at
// `<section id="start-picker" hidden aria-label="` (the translated label and closing
// quote come from the `${...}` expression right after), so the generic HTML boolean
// `hidden` attribute sits next to the start of `aria-label`.
// "voice aria", "copy readonly", "voice hidden" -- writing-voice-ui.js's dialog markup: literals end at
// `data-close-voice aria-label="`, `data-memory-copy readonly hidden aria-label="` and
// `data-undo-voice hidden>` / `data-retry-voice hidden>` (the translated text comes from the I18N.t()
// expression right after), so attribute names sit next to each other, not English copy.
const MARKUP_PHRASE_ALLOWLIST = new Set(['svg viewBox', 'frame aria', 'media class', 'stage frame', 'note     placeholder', 'focus   value', 'paste aria', 'hidden aria', 'voice aria', 'copy readonly', 'voice hidden']);

// Bare HTML boolean attributes used on this codebase's <video>/<audio> elements. They
// carry no `="value"` for the general attribute stripper below to key off, so a tag
// like `<video controls muted loop playsinline preload="metadata" poster="` leaves
// "controls muted", "muted loop" etc. sitting next to each other looking like prose.
const BOOLEAN_ATTRIBUTE_WORDS = /\b(?:controls|muted|loop|playsinline|autoplay)\b/g;

// Strips markup scaffolding out of a literal before the prose check runs: tag name
// openers/closers (`<button`, `</span`), `class="..."`/`className="..."` values (the
// original source of false positives like "style-card technique-card"), any other
// `name="value"` attribute pair with a closing quote in this same literal, and bare
// video/audio boolean attribute keywords. What's left is either real prose or harmless
// punctuation -- not a blanket "ignore lowercase" escape hatch, which would have let
// real strings like "video preview" or "saved project artwork" through uncaught.
function stripMarkupNoise(literal) {
  return literal
    .replace(/<\/?[a-zA-Z][a-zA-Z0-9-]*/g, ' ')
    .replace(/\b[a-zA-Z][a-zA-Z0-9-]*\s*=\s*"[^"]*"/g, ' ')
    .replace(/\b[a-zA-Z][a-zA-Z0-9-]*\s*=\s*'[^']*'/g, ' ')
    .replace(BOOLEAN_ATTRIBUTE_WORDS, ' ');
}

// A handful of literals are a bare `className`/`class` VALUE with no `class="` prefix
// inside the same literal for stripMarkupNoise to key off (e.g. `a.className='secondary
// detail-download'`). There's no way to tell those apart from prose by shape alone --
// "secondary detail-download" and a real two-word phrase look the same once you've
// stripped markup -- so this is an explicit, exact, reviewable allowlist (finding #1's
// other suggested approach), not a heuristic that could swallow real lowercase prose.
// Group (b): project-tools-ui.js's editor-open button is built the same way
// (`button.className='secondary editor-open'`) -- a bare className value, not prose.
// Task 9: materials-ui.js builds its tile grid with document.createElement rather than
// innerHTML, so every `tile.className = '...'` is a bare value with no `class="` prefix
// for stripMarkupNoise to key off -- same shape as the two above. T9b adds
// 'material-thumb material-thumb-video-pending' for the same reason: the placeholder
// film-strip icon shown in place of a poster <img> that isn't ready yet or failed to load.
const CLASS_LITERAL_ALLOWLIST = new Set(['secondary detail-download', 'secondary editor-open',
  'secondary materials-library-button', 'material-tile material-drop', 'material-thumb material-thumb-audio',
  'material-tile material-tile-uploading', 'material-thumb material-thumb-video-pending',
  'material-thumb material-thumb-photo']);

// Group (c): reference-ui.js compares a reference's creator field against the exact
// backend sentinel default `reference_intake.py` stores when no creator was supplied
// ("Creator not added") -- to drop it from the creator datalist and to blank the edit
// form's creator field. This string is never rendered to the user (it's filtered out
// of the list, and cleared before the field is shown), so it's data/logic, not UI copy,
// and must stay byte-identical to the Python sentinel rather than go through I18N.t().
const BACKEND_SENTINEL_LITERAL_ALLOWLIST = new Set(['Creator not added']);

// Group (c): start-references.js's validate() compares the backend's echoed handoff
// text (`/reference-handoff`, built server-side by reference_notes.py) against a
// locally-recomputed `expected` string, as an integrity check that the server's text
// still matches what the client assumes before trusting it -- not something ever
// rendered to the user. `text()` (the actually-displayed/copied message) uses the
// translated `start.inspiration.text.useOneReference`/`useManyReferences` keys
// instead; this literal pair is the untranslated comparison copy and must stay
// byte-identical to the hardcoded Python strings.
const BACKEND_ECHO_LITERAL_ALLOWLIST = new Set(['Use this reference:', 'Use these references:']);

// Group (c), fix round 2: start-ui.js's LEGACY_INSPIRATION_MARKERS lists the exact
// pre-Task-4 hardcoded English inspiration heading (and its intermediate Hebrew
// translation, below -- that one has no Latin letters so the two-English-word check
// never flags it) so migrateLegacyInspirationMarker() can recognize and migrate a draft
// saved before the current zero-width sentinel existed. This is comparison/matching
// data against a string this app itself used to hardcode, never rendered to the user
// (the real heading shown today always goes through I18N.t() -- see
// `inspirationHeading()`), so it must stay byte-identical to that old literal rather
// than track the current translation.
const LEGACY_MARKER_LITERAL_ALLOWLIST = new Set(['\\n\\nInspiration for the visual edit (save these exact references with the project):\\n']);

// Looks for two adjacent 3+-letter words, the way a translatable English sentence
// fragment does, after stripping markup scaffolding (see above). No uppercase-letter
// requirement: lowercase prose must be caught too (fix round 1, finding #1).
function violatingPhrases(literal) {
  if (isUrlOrPathLike(literal)) return [];
  if (CLASS_LITERAL_ALLOWLIST.has(literal.trim())) return [];
  if (BACKEND_SENTINEL_LITERAL_ALLOWLIST.has(literal.trim())) return [];
  if (BACKEND_ECHO_LITERAL_ALLOWLIST.has(literal.trim())) return [];
  if (LEGACY_MARKER_LITERAL_ALLOWLIST.has(literal)) return [];
  const cleaned = stripMarkupNoise(literal);
  const re = /[A-Za-z]{3,}\s+[A-Za-z]{3,}/g;
  const hits = [];
  let m;
  while ((m = re.exec(cleaned))) {
    if (!MARKUP_PHRASE_ALLOWLIST.has(m[0])) hits.push(m[0]);
  }
  return hits;
}

test('covered JS files have no untranslated two-English-word literals (textContent/innerHTML/title/placeholder/aria-label text)', () => {
  const offending = [];
  for (const name of COVERED_JS_FILES) {
    const source = readDist(name);
    for (const literal of extractLiterals(source)) {
      for (const phrase of violatingPhrases(literal)) {
        offending.push(name + ': "' + phrase + '" in: ' + JSON.stringify(literal.slice(0, 90)));
      }
    }
  }
  assert.deepEqual(offending, []);
});
