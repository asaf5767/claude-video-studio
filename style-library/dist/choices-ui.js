/* Task 10: "tap to choose" project choices -- the four steps (cut / look / sound /
   finish) that write the <!-- choices --> block of the project's brief.md instead of a
   typed prompt. Mounted right below MaterialsUI on the project page.

   GET /choices returns both this project's saved choices AND the shared config (step and
   option ids, each with an i18n key naming its label) in one response -- see choices.py's
   module docstring for why the label *text* lives only in dist/i18n/<lang>.json, not
   duplicated into this file or into choices.config.json. Every tap/toggle/textarea edit
   saves immediately (optimistic UI): the control updates right away, a POST /choices
   patch follows, and a failure reverts the control and shows the translated error --
   the same pattern materials-ui.js uses for its tag/note/owned fields. A patch only ever
   carries the field(s) that changed, so the server's read-modify-write merge in
   choices.save() never touches "effects" (Task 12's own save path) just because this UI
   saved an unrelated step.

   Fix round 1 (coordinator review):
   - finding 1: the sfx/captions toggles are a real <input type="checkbox"> made visually
     invisible with the existing `.sr-only` utility (clip, not `hidden`/display:none), so
     it stays focusable and in the tab order; CSS shows a focus ring on its sibling
     `.choice-switch` track via `input:focus-visible + .choice-switch`. See
     test_choices_ui.js's "switch is keyboard operable" tests.
   - finding 3: a look card's sample image that 404s (e.g. a release zip missing
     look-files) is swapped for a tasteful gradient placeholder with the look's name,
     never a broken-image icon.
   - finding 4: the four single-select groups (cut/look/sound length) are proper
     role="radiogroup"/"radio" controls with roving tabindex and Arrow/Home/End
     navigation, the same pattern start-references.js's example picker already uses.

   Fix round 1, finding 2 (same-field rapid taps) first tried a per-field `seq` sent to
   the server. Fix round 2, controller ruling R33, replaced that with a client-only fix:
   `fieldSeq` lived only in this closure and reset on reload (or simply never existed in a
   second tab) while the server's half of the guard lived in choices.json -- after a
   reload, a brand-new tap could be sent with a seq the server already considered old, get
   silently dropped, and the UI would show a 200 response that quietly reverted the tap
   with no visible error. choices.py no longer does any seq bookkeeping at all (see its
   module docstring); the fix lives entirely here instead: per field, never more than one
   /choices request in flight. A tap that arrives while one is already in flight does not
   go out immediately -- it replaces whatever was queued (only the latest value survives)
   and is sent the instant the in-flight one settles; that in-flight request's own
   response (success *or* failure) is discarded unapplied the moment something newer gets
   queued, so it can never apply stale data or revert a newer tap. Because there is never
   more than one outstanding request per field, responses cannot arrive out of order --
   not "guarded against", but impossible by construction, with no seq, no server
   bookkeeping, and nothing that can go stale across a reload or a second tab (see
   `queueFieldSave`/`runFieldSave` below). */
window.ChoicesUI = (() => {
  const EXTRA_SAVE_DELAY = 600;
  const CHECK = '✓';
  const ARROW_DIRECTION = {ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1};
  let run = 0;

  function mount(el, projectId) {
    const token = ++run;
    let config = null;
    let state = {};
    let looksList = [];
    // `confirmed[field]` is the last value this tab actually knows the server holds (set
    // from the initial load, and again every time a save for that field finally applies).
    // It is the revert target on a failed save -- not just "one tap back" -- because a
    // chain of queued taps (see runFieldSave) can fail after several superseded taps that
    // were never individually confirmed or reverted; rolling back to the last *known-good*
    // value is the only one that's safe to show.
    let confirmed = {};
    const fieldInFlight = {}; // field -> true while exactly one /choices request for it is in flight
    const fieldQueued = {};   // field -> the single latest pending {body, onApply, onRevert}, or undefined

    const section = document.createElement('section');
    section.className = 'choices-section';
    section.setAttribute('aria-label', I18N.t('choices.sectionAria'));

    const heading = document.createElement('h2');
    heading.textContent = I18N.t('choices.title');

    const status = document.createElement('p');
    status.className = 'choices-status';
    status.setAttribute('role', 'status');

    const grid = document.createElement('div');
    grid.className = 'choices-grid';

    const extraWrap = document.createElement('div');
    extraWrap.className = 'choices-extra';

    // Task 12: "+ אפקט" opens the effects board aimed at this project (#effects?project=<id>).
    const head = document.createElement('div');
    head.className = 'choices-head';
    const addEffect = document.createElement('a');
    addEffect.className = 'choices-add-effect';
    addEffect.href = '#effects?' + new URLSearchParams({project: projectId});
    addEffect.textContent = I18N.t('choices.addEffect');
    addEffect.setAttribute('title', I18N.t('choices.addEffectAria'));
    head.append(heading, addEffect);

    section.append(head, status, grid, extraWrap);
    el.innerHTML = '';
    el.append(section);

    function showStatus(message) { status.textContent = message || ''; }

    // The raw network call only -- no field/queueing awareness here; that lives in
    // queueFieldSave/runFieldSave below. Throws (with an already-translated message) on
    // any non-ok response or network failure; resolves with the parsed JSON result
    // otherwise.
    async function postChoices(body) {
      const response = await fetch('/choices', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'choices'},
        body: JSON.stringify({project: projectId, ...body}),
      });
      let result = null;
      try { result = await response.json(); } catch { /* fall through to the generic message below */ }
      if (!response.ok) throw Error(I18N.t(result?.error || 'choices.saveError'));
      return result;
    }

    // Public entry point for a field save (fix round 2, module header): if this field has
    // no request in flight, send immediately; otherwise replace whatever was queued for it
    // (only the latest tap survives) and let the in-flight request's own completion start
    // this one.
    function queueFieldSave(field, body, onApply, onRevert) {
      if (fieldInFlight[field]) { fieldQueued[field] = {body, onApply, onRevert}; return; }
      runFieldSave(field, body, onApply, onRevert);
    }

    // Always exactly one request for `field` in flight while this runs (never entered
    // while fieldInFlight[field] is already true from outside queueFieldSave). On
    // settling, if something newer has been queued in the meantime, this response is
    // dropped entirely -- no apply, no revert, no status message -- and the queued
    // request is sent immediately, still under the same "in flight" window. Only the
    // request that settles with nothing queued behind it actually applies or reverts.
    async function runFieldSave(field, body, onApply, onRevert) {
      fieldInFlight[field] = true;
      let result, failed = false, error = null;
      try {
        result = await postChoices(body);
      } catch (e) {
        failed = true; error = e;
      }
      const queued = fieldQueued[field];
      if (queued) {
        fieldQueued[field] = undefined;
        return runFieldSave(field, queued.body, queued.onApply, queued.onRevert);
      }
      fieldInFlight[field] = false;
      if (!failed) {
        showStatus('');
        onApply(result);
      } else {
        showStatus(error instanceof TypeError ? I18N.t('choices.saveError') : error.message);
        onRevert();
      }
    }

    function buildOption(value, labelText) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'choice-option';
      button.setAttribute('role', 'radio');
      button.dataset.value = value;
      const text = document.createElement('span');
      text.textContent = labelText;
      const check = document.createElement('span');
      check.className = 'choice-check';
      check.setAttribute('aria-hidden', 'true');
      check.textContent = CHECK;
      button.append(text, check);
      return button;
    }

    // Roving tabindex (fix round 1, finding 4): the selected radio is the only one with
    // tabindex 0 (so Tab enters/leaves the group in one stop); if nothing is selected yet,
    // the first option is the entry point instead.
    function markSelected(buttons, value) {
      const hasSelection = buttons.some(b => b.dataset.value === value);
      buttons.forEach((button, i) => {
        const on = button.dataset.value === value;
        button.classList.toggle('on', on);
        button.setAttribute('aria-checked', String(on));
        button.tabIndex = on ? 0 : (hasSelection ? -1 : (i === 0 ? 0 : -1));
      });
    }

    // A tap-to-choose single-select group shared by cut/sound/length/look: optimistic
    // selection, a queued/serialized save (see queueFieldSave), and a revert to the last
    // server-confirmed value (never re-rendering the whole grid) if the save that ends up
    // actually settling fails.
    function buildOptionGroup(field, stepLabel, options, buildButton) {
      const group = document.createElement('div');
      group.className = 'choice-options';
      group.setAttribute('role', 'radiogroup');
      group.setAttribute('aria-label', stepLabel);
      const buttons = options.map(buildButton);
      markSelected(buttons, state[field]);
      buttons.forEach(button => group.append(button));
      buttons.forEach(button => {
        button.addEventListener('click', () => {
          const value = button.dataset.value;
          if (state[field] === value) return;
          markSelected(buttons, value);
          state[field] = value;
          queueFieldSave(field, {[field]: value},
            result => { if (result) state[field] = result[field]; confirmed[field] = state[field]; markSelected(buttons, state[field]); },
            () => { state[field] = confirmed[field]; markSelected(buttons, state[field]); });
        });
      });
      return group;
    }

    function buildSwitch(field, labelText) {
      const row = document.createElement('label');
      row.className = 'choice-switch-row';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'sr-only'; // visually hidden, NOT display:none -- stays focusable/tabbable (fix round 1, finding 1)
      input.checked = state[field] === true;
      const track = document.createElement('span');
      track.className = 'choice-switch';
      track.classList.toggle('on', state[field] === true);
      const knob = document.createElement('i');
      track.append(knob);
      const text = document.createElement('span');
      text.textContent = labelText;
      row.append(input, track, text);
      input.addEventListener('change', () => {
        const value = input.checked;
        track.classList.toggle('on', value);
        state[field] = value;
        queueFieldSave(field, {[field]: value},
          result => {
            if (result) state[field] = result[field];
            confirmed[field] = state[field];
            input.checked = state[field] === true; track.classList.toggle('on', state[field] === true);
          },
          () => {
            // confirmed[field] is `undefined` (not `false`) for a switch nothing has ever
            // saved yet -- the `=== true` coercion keeps that showing as off, same as the
            // initial unset display, instead of literally setting `checked = undefined`.
            state[field] = confirmed[field];
            input.checked = state[field] === true; track.classList.toggle('on', state[field] === true);
          });
      });
      return row;
    }

    function buildCutStep() {
      const step = document.createElement('div');
      step.className = 'choice-step';
      const label = document.createElement('div');
      label.className = 'choice-step-label';
      const stepLabel = I18N.t(config.cut.label_key);
      label.textContent = stepLabel;
      const group = buildOptionGroup('cut', stepLabel, config.cut.options,
        opt => buildOption(opt.id, I18N.t(opt.label_key)));
      step.append(label, group);
      return step;
    }

    // A tasteful fallback for a missing sample.jpg (fix round 1, finding 3): no broken-
    // image icon, just the look's own name sitting on a gradient card.
    function attachThumbFallback(card, img) {
      img.addEventListener('error', () => {
        img.remove();
        card.classList.add('choice-look-placeholder');
      }, {once: true});
    }

    function buildLookStep() {
      const step = document.createElement('div');
      step.className = 'choice-step';
      const label = document.createElement('div');
      label.className = 'choice-step-label';
      const stepLabel = I18N.t(config.look.label_key);
      label.textContent = stepLabel;
      const he = I18N.lang() === 'he';
      const entries = looksList.map(item => ({id: item.id, name: he ? item.name_he : item.name_en, sample: item.sample}));
      if (typeof state.look === 'string' && state.look.startsWith('ref:')) {
        entries.push({id: state.look, name: I18N.t(config.look.ref_label_key), sample: null});
      }
      const group = buildOptionGroup('look', stepLabel, entries, entry => {
        const card = buildOption(entry.id, entry.name);
        card.classList.add('choice-look-card');
        if (entry.sample) {
          const img = document.createElement('img');
          img.className = 'choice-look-thumb';
          img.loading = 'lazy';
          img.alt = '';
          attachThumbFallback(card, img);
          img.src = entry.sample;
          card.prepend(img);
        }
        return card;
      });
      group.className = 'choice-look-grid';
      // Task 12: presenter looks ("איך אתם נראים") live on the effects board's second tab.
      const addLook = document.createElement('a');
      addLook.className = 'choices-add-look';
      addLook.href = '#effects?' + new URLSearchParams({project: projectId, tab: 'look'});
      addLook.textContent = I18N.t('choices.addLook');
      step.append(label, group, addLook);
      return step;
    }

    function buildSoundStep() {
      const step = document.createElement('div');
      step.className = 'choice-step';
      const label = document.createElement('div');
      label.className = 'choice-step-label';
      const stepLabel = I18N.t(config.sound.label_key);
      label.textContent = stepLabel;
      const group = buildOptionGroup('sound', stepLabel, config.sound.options,
        opt => buildOption(opt.id, I18N.t(opt.label_key)));
      const switchRow = buildSwitch('sfx', I18N.t(config.sound.sfx_label_key));
      step.append(label, group, switchRow);
      return step;
    }

    function buildFinishStep() {
      const step = document.createElement('div');
      step.className = 'choice-step';
      const label = document.createElement('div');
      label.className = 'choice-step-label';
      const stepLabel = I18N.t(config.finish.label_key);
      label.textContent = stepLabel;
      const switchRow = buildSwitch('captions', I18N.t(config.finish.captions_label_key));
      const group = buildOptionGroup('length', stepLabel, config.finish.length_options,
        opt => buildOption(opt.id, I18N.t(opt.label_key)));
      step.append(label, switchRow, group);
      return step;
    }

    function buildExtra() {
      extraWrap.innerHTML = '';
      const label = document.createElement('label');
      label.className = 'choices-extra-label';
      const labelText = document.createElement('span');
      labelText.textContent = I18N.t(config.extra.ui_label_key);
      const textarea = document.createElement('textarea');
      textarea.className = 'choices-extra-input';
      textarea.maxLength = 1000;
      textarea.setAttribute('placeholder', I18N.t('choices.extra.placeholder'));
      textarea.value = state.extra || '';
      const hint = document.createElement('p');
      hint.className = 'choices-extra-hint';
      hint.setAttribute('role', 'status');
      hint.hidden = true;
      label.append(labelText, textarea);
      extraWrap.append(label, hint);
      let timer = null;
      textarea.addEventListener('input', () => {
        clearTimeout(timer);
        // The note is written into one line of brief.md; the server rejects control
        // characters (Task 12 fix round 1), so line breaks/tabs become spaces as you type.
        if (/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(textarea.value)) {
          textarea.value = textarea.value.replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/g, ' ');
          if (hint.hidden) { hint.textContent = I18N.t('choices.extra.newlineHint'); hint.hidden = false; } // shown once
        }
        const value = textarea.value;
        timer = setTimeout(() => {
          state.extra = value;
          // Task 10 fix round 2: one request in flight per field (queueFieldSave). Task 12
          // ruling R35: on a failure the textarea goes back to the last confirmed note so the
          // UI and the saved state stay in sync (the status line shows the server's message),
          // but only if nothing was typed since this save -- newer typing is never erased.
          queueFieldSave('extra', {extra: value},
            result => { if (result) state.extra = result.extra; confirmed.extra = state.extra; },
            () => {
              state.extra = confirmed.extra;
              if (textarea.value === value) textarea.value = confirmed.extra || '';
            });
        }, EXTRA_SAVE_DELAY);
      });
    }

    // Delegated Arrow/Home/End roving-tabindex navigation shared by every radiogroup
    // (fix round 1, finding 4) -- scoped to the pressed button's own group, since the
    // four steps are four separate radiogroups, not one.
    section.addEventListener('keydown', event => {
      const button = event.target.closest('[role="radio"]');
      if (!button) return;
      const group = button.closest('[role="radiogroup"]');
      if (!group) return;
      const buttons = [...group.querySelectorAll('[role="radio"]')];
      const direction = ARROW_DIRECTION[event.key];
      if (direction || event.key === 'Home' || event.key === 'End') {
        event.preventDefault();
        const index = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
          (buttons.indexOf(button) + direction + buttons.length) % buttons.length;
        buttons[index].focus();
        buttons[index].click();
      }
    });

    function render() {
      grid.innerHTML = '';
      grid.append(buildCutStep(), buildLookStep(), buildSoundStep(), buildFinishStep());
      buildExtra();
    }

    async function load() {
      try {
        const [choicesResponse, looksResponse] = await Promise.all([
          fetch('/choices?' + new URLSearchParams({project: projectId}), {cache: 'no-store'}),
          fetch('/looks', {cache: 'no-store'}),
        ]);
        if (token !== run || !el.isConnected) return;
        if (!choicesResponse.ok) throw Error(I18N.t('choices.loadError'));
        const choicesData = await choicesResponse.json();
        config = choicesData.config;
        state = {...choicesData.choices};
        confirmed = {...choicesData.choices};
        looksList = looksResponse.ok ? (await looksResponse.json()).items : [];
        if (token !== run || !el.isConnected) return;
        render();
      } catch {
        if (token === run && el.isConnected) showStatus(I18N.t('choices.loadError'));
      }
    }

    load();
    return {refresh: load};
  }

  return {mount};
})();
