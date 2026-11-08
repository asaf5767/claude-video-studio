/* Header language toggle (עב / EN): switches the studio language through I18N.set and keeps aria-pressed in sync.
   The labels themselves come from i18n (app.lang.he / app.lang.en) and read the same in both languages. */
(() => {
  const buttons = () => Array.from(document.querySelectorAll('[data-lang]'));

  function sync() {
    const active = I18N.lang();
    for (const button of buttons()) button.setAttribute('aria-pressed', String(button.dataset.lang === active));
  }

  function notify(message) {
    const toast = document.querySelector('#toast');
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 3200);
  }

  async function choose(button) {
    const next = button.dataset.lang;
    if (next === I18N.lang()) return;
    const all = buttons();
    all.forEach(b => { b.disabled = true; });
    try {
      await I18N.set(next);
    } catch {
      notify(I18N.t('app.lang.error'));
    } finally {
      all.forEach(b => { b.disabled = false; });
      sync();
    }
  }

  for (const button of buttons()) button.addEventListener('click', () => choose(button));
  document.addEventListener('i18n:change', sync);
  I18N.ready.then(sync);
})();
