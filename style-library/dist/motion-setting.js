/* Footer "תנועה / Motion" control: auto (follow the system's reduced-motion setting), always, or off.
   Saved in settings.json through /ui-motion (same guards as /ui-language) and applied to the slot headlines
   and to the effects board's live demos (effects-ui.js). */
(() => {
  const select = document.querySelector('#motion-setting');
  if (!select) return;
  let current = 'auto';

  function apply(value) {
    select.value = value;
    // CSS reads this too: html[data-motion=off|always] stops / keeps the Send-to-Claude spinner (Task 15).
    if (document.documentElement) document.documentElement.dataset.motion = value;
    if (value === current) return; // same setting: don't restart the headlines
    current = value;
    if (window.SlotHeadline) window.SlotHeadline.setMotion(value);
    if (window.EffectsBoard) window.EffectsBoard.setMotion(value); // the effects board's live demos
  }

  function notify(message) {
    const toast = document.querySelector('#toast');
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 3200);
  }

  fetch('/ui-motion', {cache: 'no-store'})
    .then(response => (response.ok ? response.json() : null))
    .then(data => { if (data && data.motion) apply(data.motion); })
    .catch(() => { /* keep auto when the setting can't be read */ });

  select.addEventListener('change', async () => {
    const next = select.value, previous = current;
    select.disabled = true;
    try {
      const response = await fetch('/ui-motion', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'ui-motion'},
        body: JSON.stringify({motion: next}),
      });
      if (!response.ok) throw Error();
      apply(next);
    } catch {
      apply(previous);
      notify(I18N.t('motion.error'));
    } finally {
      select.disabled = false;
    }
  });
})();
