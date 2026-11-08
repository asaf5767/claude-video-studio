/* Minimal i18n core: loads /ui-language and the matching i18n/<lang>.json strings, exposes I18N.t/lang/set/ready,
   and keeps <html lang dir> and [data-i18n*] elements in sync. Task 4 moves the real UI copy into the string files. */
window.I18N = (() => {
  const SUPPORTED = ['he', 'en'];
  const RTL = {he: true, en: false};
  const warned = new Set();
  let lang = 'he'; // Hebrew-first default; never trust a stale static <html lang> before the saved setting loads.
  let strings = {};

  function direction(l) { return RTL[l] ? 'rtl' : 'ltr'; }

  function t(key, vars) {
    const value = strings[key];
    if (value === undefined) {
      if (!warned.has(key)) {
        warned.add(key);
        if (typeof console !== 'undefined') console.warn('Missing i18n key: ' + key);
      }
      return key;
    }
    if (!vars) return value;
    return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value);
  }

  // The Python modules raise English sentences; show the known ones in the UI language (unknown ones pass through).
  const SERVER_MESSAGES = {
    'The project folder needs a safe local path before saving feedback.': 'server.feedbackUnsafePath',
    'Reference notes need a safe local path before saving.': 'server.notesUnsafePath',
    'The reference source needs a safe local path.': 'server.referenceSourceUnsafePath',
    'The studio decision files need safe local paths before saving.': 'server.decisionUnsafePath',
    'Writing files need safe local paths. Existing files are preserved.': 'server.writingUnsafePath',
  };

  function server(message) {
    const key = typeof message === 'string' ? SERVER_MESSAGES[message.trim()] : undefined;
    return key && strings[key] !== undefined ? strings[key] : message;
  }

  function renderAttr(scope, attr, apply) {
    scope.querySelectorAll('[' + attr + ']').forEach(el => apply(el, t(el.getAttribute(attr))));
  }

  function render(scope) {
    const root = scope || document;
    renderAttr(root, 'data-i18n', (el, text) => { el.textContent = text; });
    renderAttr(root, 'data-i18n-placeholder', (el, text) => { el.setAttribute('placeholder', text); });
    renderAttr(root, 'data-i18n-aria', (el, text) => { el.setAttribute('aria-label', text); });
    renderAttr(root, 'data-i18n-title', (el, text) => { el.setAttribute('title', text); });
    renderAttr(root, 'data-i18n-alt', (el, text) => { el.setAttribute('alt', text); });
  }

  function applyDocument(l) {
    document.documentElement.lang = l;
    document.documentElement.dir = direction(l);
  }

  async function loadStrings(l) {
    const response = await fetch('i18n/' + l + '.json', {cache: 'no-store'});
    if (!response.ok) throw Error('Could not load studio language strings.');
    strings = await response.json();
  }

  async function init() {
    let next = lang;
    try {
      const response = await fetch('/ui-language', {cache: 'no-store'});
      if (response.ok) {
        const data = await response.json();
        if (data && SUPPORTED.includes(data.language)) next = data.language;
      }
    } catch (error) { /* keep the Hebrew default if the saved setting is unavailable */ }
    try {
      await loadStrings(next);
    } catch (error) {
      strings = {}; // Missing keys fall back to returning the key itself; see t().
      if (typeof console !== 'undefined') console.warn('Could not load i18n strings for ' + next + '.', error);
    }
    lang = next;
    applyDocument(lang);
    render();
  }

  const ready = init().catch(error => {
    // init() already recovers from a failed language lookup or strings fetch above;
    // this is only a last-resort guard so I18N.ready never produces an unhandled rejection.
    if (typeof console !== 'undefined') console.warn('i18n initialization failed.', error);
  });

  async function set(next) {
    if (!SUPPORTED.includes(next)) throw Error('Use he or en.');
    const response = await fetch('/ui-language', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'ui-language'},
      body: JSON.stringify({language: next}),
    });
    if (!response.ok) throw Error('Could not change the studio language.');
    await loadStrings(next);
    lang = next;
    applyDocument(lang);
    render();
    document.dispatchEvent(new CustomEvent('i18n:change', {detail: {lang}}));
  }

  return {t, server, lang: () => lang, set, ready};
})();
