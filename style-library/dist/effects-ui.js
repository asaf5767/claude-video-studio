/* Task 12: the "אפקטים ומראה" screen (#effects, or #effects?project=<id> from a project page's
   "+ אפקט" link; &tab=look opens the presenter-looks tab). Two tabs read from GET /effects: After-Effects-style motion graphics
   (effects/effects.json) and presenter looks, "איך אתם נראים" (looks/presenter.json). Every
   card plays a live demo from dist/fx-demos.js.

   "הוספה לסרטון" needs a target project. With one, add/remove saves through POST /choices
   (Task 10's server-side merge): effects as the project's whole "effects" list
   [{effect, when}] -- when = the optional "כשאני אומר…" word -- and a presenter look as the
   single "presenter" id (or null). Without one, a picker asks "לאיזה סרטון להוסיף?" first and
   the hash becomes #effects?project=<id>. The tray at the bottom shows that project's picks.

   Performance: only cards on screen animate (IntersectionObserver), everything pauses while
   the tab is hidden or the screen is left, and the footer Motion setting is respected (auto
   follows prefers-reduced-motion; off / reduced draws each demo's still end frame). */
window.EffectsBoard = (() => {
  const MAX_EFFECTS = 20, MAX_WHEN = 80, WHEN_SAVE_DELAY = 600, LOOP_GAP = 450, MAX_START_DELAY = 700;
  const MOTIONS = ['auto', 'always', 'off'];

  // ---- pure helpers (unit-tested) ----
  const clip = text => String(text || '').trim().slice(0, MAX_WHEN); // otherwise saved verbatim (ruling R35)
  const logic = {
    animate: (pref, reduced) => pref === 'always' || (pref !== 'off' && !reduced),
    withEffect: (list, id, when) => (list.some(e => e.effect === id)
      ? list.map(e => (e.effect === id ? {effect: id, when: clip(when)} : e))
      : [...list, {effect: id, when: clip(when)}]),
    withoutEffect: (list, id) => list.filter(e => e.effect !== id),
    // Saved choices may hold ids the catalog no longer has, or legacy items without "when";
    // re-sending them would make every later save fail, so keep only known, well-formed ones.
    clean(saved, data) {
      const known = data ? new Set(data.effects.map(e => e.id)) : null;
      const looks = data ? new Set(data.looks.map(l => l.id)) : null;
      const effects = [];
      for (const item of Array.isArray(saved.effects) ? saved.effects : []) {
        if (!item || typeof item.effect !== 'string' || (known && !known.has(item.effect))) continue;
        if (effects.some(e => e.effect === item.effect)) continue;
        effects.push({effect: item.effect, when: typeof item.when === 'string' ? clip(item.when) : ''});
      }
      const presenter = typeof saved.presenter === 'string' && (!looks || looks.has(saved.presenter)) ? saved.presenter : null;
      return {effects, presenter};
    },
  };

  let root = null, active = false, token = 0;
  let catalog = null, projectsCache = null;
  let tab = 'fx', filter = 'all';
  let project = null; // {id, title}
  let chosen = {effects: [], presenter: null};
  let motionPref = 'auto';
  let observer = null, saveQueue = Promise.resolve(), pendingAdd = null;
  const cards = new Map(); // id -> {item, kind, stage, button, input, ctx, visible}
  const whenTimers = new Set(); // pending debounced "when" saves
  const TABS = ['fx', 'look'];
  const ui = {};
  let picker = null;

  function mk(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }
  const items = kind => (catalog ? (kind === 'fx' ? catalog.effects : catalog.looks) : []);
  const find = id => (catalog ? [...catalog.effects, ...catalog.looks].find(item => item.id === id) : null);
  const nameOf = id => { const item = find(id); return item ? I18N.t(item.name_key) : id; };
  const catLabel = category => I18N.t(['fx', 'cat', category].join('.'));
  const isChosen = (item, kind) => (kind === 'fx' ? chosen.effects.some(e => e.effect === item.id) : chosen.presenter === item.id);
  function reducedMotion() {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch { return false; }
  }
  const animating = () => logic.animate(motionPref, reducedMotion());
  function showStatus(text) { if (ui.status) ui.status.textContent = text || ''; }

  // ---- data ----
  async function getJSON(url) {
    const response = await fetch(url, {cache: 'no-store'});
    if (!response.ok) throw Error(String(response.status));
    return response.json();
  }
  async function loadCatalog() {
    if (!catalog) catalog = await getJSON('/effects');
  }
  async function loadProjects(force) {
    if (!projectsCache || force) projectsCache = (await getJSON('/projects.json')).projects || [];
    return projectsCache;
  }
  async function loadProject(id) {
    const [data, list] = await Promise.all([getJSON('/choices?' + new URLSearchParams({project: id})), loadProjects(false).catch(() => [])]);
    chosen = logic.clean(data.choices || {}, catalog);
    const entry = list.find(p => p.id === id);
    project = {id, title: entry ? entry.title : id};
  }

  // ---- saving ----
  function save(patch) {
    if (!project) return Promise.resolve();
    const previous = {effects: chosen.effects, presenter: chosen.presenter};
    chosen = {...chosen, ...patch};
    refreshChoices();
    const projectId = project.id;
    const job = saveQueue.then(async () => {
      const response = await fetch('/choices', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'choices'},
        body: JSON.stringify({project: projectId, ...patch}),
      });
      let result = null;
      try { result = await response.json(); } catch { /* the generic message below covers it */ }
      if (!response.ok) throw Error(result && result.error ? I18N.t(result.error) : I18N.t('effects.saveError'));
      if (project && project.id === projectId) {
        for (const field of Object.keys(patch)) if (field in result) chosen[field] = result[field];
        showStatus('');
        refreshChoices();
      }
    }).catch(error => {
      if (project && project.id === projectId) {
        for (const field of Object.keys(patch)) chosen[field] = previous[field];
        refreshChoices();
        showStatus(error instanceof TypeError ? I18N.t('effects.saveError') : error.message);
      }
    });
    saveQueue = job;
    return job;
  }

  function add(item, kind) {
    if (isChosen(item, kind)) return;
    if (kind === 'look') { save({presenter: item.id}); return; }
    if (chosen.effects.length >= MAX_EFFECTS) { showStatus(I18N.t('effects.limit')); return; }
    const card = cards.get(item.id);
    save({effects: logic.withEffect(chosen.effects, item.id, card && card.input ? card.input.value : '')});
  }
  function remove(id, kind) {
    if (kind === 'look') save({presenter: null});
    else save({effects: logic.withoutEffect(chosen.effects, id)});
  }
  function toggle(item, kind) {
    if (!project) { openPicker(() => add(item, kind)); return; }
    if (isChosen(item, kind)) remove(item.id, kind); else add(item, kind);
  }

  // ---- rendering ----
  function buildShell() {
    root.innerHTML = '';
    const board = mk('section', 'effects-board');
    const heading = mk('div', 'effects-heading');
    const titleBox = mk('div');
    titleBox.append(mk('p', 'eyebrow', I18N.t('effects.eyebrow')), mk('h1', null, I18N.t('effects.title')), mk('p', 'lede', I18N.t('effects.lede')));
    heading.append(titleBox);
    ui.target = mk('div', 'effects-target');
    ui.tabs = mk('div', 'effects-tabs');
    ui.tabs.setAttribute('role', 'tablist');
    ui.tabs.setAttribute('aria-label', I18N.t('effects.tabsAria'));
    ui.filters = mk('div', 'effects-filters');
    ui.filters.setAttribute('role', 'group');
    ui.filters.setAttribute('aria-label', I18N.t('effects.filtersAria'));
    ui.note = mk('p', 'effects-note');
    ui.status = mk('p', 'effects-status');
    ui.status.setAttribute('role', 'status');
    ui.grid = mk('div', 'effects-grid');
    ui.grid.id = 'effects-panel';
    ui.grid.setAttribute('role', 'tabpanel');
    ui.tray = mk('aside', 'effects-tray');
    ui.tray.setAttribute('aria-live', 'polite');
    board.append(heading, ui.target, ui.tabs, ui.filters, ui.note, ui.status, ui.grid, ui.tray);
    root.append(board);
  }

  function renderTarget() {
    const box = ui.target;
    box.innerHTML = '';
    if (project) {
      const label = mk('span', 'effects-target-label', I18N.t('effects.target.label'));
      const title = mk('strong', 'effects-target-title');
      title.append(mk('bdi', null, project.title || project.id));
      const open = mk('a', 'plain-link', I18N.t('effects.target.open'));
      open.href = '#' + new URLSearchParams({project: project.id});
      const change = mk('button', 'text-button', I18N.t('effects.target.change'));
      change.type = 'button';
      change.addEventListener('click', () => openPicker(null));
      box.append(label, title, open, change);
    } else {
      const none = mk('span', 'effects-target-label', I18N.t('effects.target.none'));
      const choose = mk('button', 'secondary', I18N.t('effects.target.choose'));
      choose.type = 'button';
      choose.addEventListener('click', () => openPicker(null));
      box.append(none, choose);
    }
  }

  function selectTab(id, focus) {
    if (tab !== id) { tab = id; filter = 'all'; renderBoard(); }
    if (focus) { const button = [...ui.tabs.children].find(b => b.dataset.tab === id); if (button) button.focus(); }
  }

  // Arrow keys move between the two tabs (reading direction aware), Home/End jump to the ends.
  function tabKey(event, id) {
    const rtl = document.documentElement && document.documentElement.dir === 'rtl';
    let next = null;
    if (event.key === 'Home') next = TABS[0];
    else if (event.key === 'End') next = TABS[TABS.length - 1];
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      const forward = (event.key === 'ArrowLeft') === rtl;
      next = TABS[(TABS.indexOf(id) + (forward ? 1 : -1) + TABS.length) % TABS.length];
    }
    if (!next) return;
    event.preventDefault();
    selectTab(next, true);
  }

  function renderTabs() {
    ui.tabs.innerHTML = '';
    for (const [id, key] of [['fx', 'effects.tab.fx'], ['look', 'effects.tab.looks']]) {
      const button = mk('button', 'effects-tab', I18N.t(key));
      button.type = 'button';
      button.id = 'effects-tab-' + id;
      button.dataset.tab = id;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', String(tab === id));
      button.setAttribute('aria-controls', ui.grid.id);
      button.tabIndex = tab === id ? 0 : -1;
      button.addEventListener('click', () => selectTab(id, false));
      button.addEventListener('keydown', event => tabKey(event, id));
      ui.tabs.append(button);
    }
    ui.grid.setAttribute('aria-labelledby', 'effects-tab-' + tab);
  }

  function renderFilters() {
    ui.filters.innerHTML = '';
    const categories = ['all', ...new Set(items(tab).map(item => item.category))];
    for (const category of categories) {
      const button = mk('button', 'effects-filter', category === 'all' ? I18N.t('effects.filter.all') : catLabel(category));
      button.type = 'button';
      button.dataset.cat = category;
      button.setAttribute('aria-pressed', String(filter === category));
      button.addEventListener('click', () => { if (filter === category) return; filter = category; renderBoard(); });
      ui.filters.append(button);
    }
  }

  function renderNote() {
    const parts = [];
    if (tab === 'look') parts.push(I18N.t('effects.looksNote'));
    if (!animating()) parts.push(I18N.t('effects.motionOff'));
    ui.note.textContent = parts.join(' ');
    ui.note.hidden = !parts.length;
  }

  function buildCard(item, kind) {
    const name = I18N.t(item.name_key);
    const card = mk('article', 'fx-card');
    card.dataset.fxId = item.id;
    const stage = mk('div', 'fx-stage');
    stage.setAttribute('role', 'img');
    stage.setAttribute('aria-label', I18N.t('effects.demoAria', {name}));
    const meta = mk('div', 'fx-meta');
    meta.append(mk('span', 'fx-cat', catLabel(item.category)), mk('h3', 'fx-name', name), mk('p', 'fx-desc', I18N.t(item.desc_key)));
    const actions = mk('div', 'fx-actions');
    let input = null;
    if (kind === 'fx') {
      input = mk('input', 'fx-when');
      input.type = 'text';
      input.maxLength = MAX_WHEN;
      input.setAttribute('placeholder', I18N.t('effects.when.placeholder'));
      input.setAttribute('aria-label', I18N.t('effects.when.aria') + ' · ' + name);
      const saved = chosen.effects.find(e => e.effect === item.id);
      input.value = saved ? saved.when : '';
      let timer = null;
      input.addEventListener('input', () => {
        clearTimeout(timer);
        whenTimers.delete(timer);
        timer = setTimeout(() => {
          whenTimers.delete(timer);
          const current = chosen.effects.find(e => e.effect === item.id);
          if (current && current.when !== clip(input.value)) save({effects: logic.withEffect(chosen.effects, item.id, input.value)});
        }, WHEN_SAVE_DELAY);
        whenTimers.add(timer);
      });
      actions.append(input);
    }
    const button = mk('button', 'fx-add');
    button.type = 'button';
    button.addEventListener('click', () => toggle(item, kind));
    actions.append(button);
    meta.append(actions);
    card.append(stage, meta);
    const entry = {item, kind, stage, button, input, ctx: null, visible: false};
    cards.set(item.id, entry);
    updateCard(entry);
    return card;
  }

  function updateCard(entry) {
    const on = isChosen(entry.item, entry.kind);
    entry.button.textContent = on ? I18N.t(entry.kind === 'fx' ? 'effects.added' : 'effects.lookChosen') : I18N.t('effects.add');
    entry.button.classList.toggle('on', on); // the label says the state; no aria-pressed on top of it
    if (entry.input && on && document.activeElement !== entry.input) {
      const saved = chosen.effects.find(e => e.effect === entry.item.id);
      if (saved) entry.input.value = saved.when;
    }
  }

  function renderGrid() {
    stopDemos();
    cards.clear();
    ui.grid.innerHTML = '';
    if (!catalog) return;
    for (const item of items(tab)) {
      if (filter === 'all' || item.category === filter) ui.grid.append(buildCard(item, tab));
    }
    startDemos();
  }

  function chip(text, onRemove, removeLabel) {
    const box = mk('span', 'fx-chip');
    box.append(mk('bdi', null, text));
    const x = mk('button', 'fx-chip-remove', '×');
    x.type = 'button';
    x.setAttribute('aria-label', removeLabel);
    x.addEventListener('click', onRemove);
    box.append(x);
    return box;
  }

  function renderTray() {
    const tray = ui.tray;
    tray.innerHTML = '';
    tray.append(mk('strong', 'fx-tray-title', I18N.t('effects.tray.title')));
    if (!project) {
      tray.append(mk('span', 'fx-tray-empty', I18N.t('effects.tray.noProject')));
      const choose = mk('button', 'text-button', I18N.t('effects.target.choose'));
      choose.type = 'button';
      choose.addEventListener('click', () => openPicker(null));
      tray.append(choose);
      return;
    }
    const list = mk('div', 'fx-tray-items');
    for (const e of chosen.effects) {
      const name = nameOf(e.effect);
      const text = e.when ? name + ' · ' + I18N.t('choices.brief.when', {when: e.when}) : name;
      list.append(chip(text, () => remove(e.effect, 'fx'), I18N.t('effects.tray.remove', {name})));
    }
    if (chosen.presenter) {
      const name = nameOf(chosen.presenter);
      list.append(chip(name, () => remove(chosen.presenter, 'look'), I18N.t('effects.tray.remove', {name})));
    }
    if (!list.children.length) tray.append(mk('span', 'fx-tray-empty', I18N.t('effects.tray.empty')));
    else tray.append(list);
  }

  function refreshChoices() {
    cards.forEach(updateCard);
    if (ui.tray) renderTray();
  }

  function renderBoard() {
    if (!root || !ui.grid) return;
    renderTarget();
    renderTabs();
    renderFilters();
    renderNote();
    renderGrid();
    renderTray();
  }

  // ---- live demos ----
  function clearStage(stage) {
    if (stage.getAnimations) stage.getAnimations({subtree: true}).forEach(a => a.cancel());
    stage.innerHTML = '';
  }
  function stopDemo(entry) {
    if (!entry.ctx) return;
    entry.ctx.cancel();
    entry.ctx = null;
    if (entry.stage.getAnimations) entry.stage.getAnimations({subtree: true}).forEach(a => a.pause());
  }
  function playDemo(entry) {
    const demos = window.FxDemos, play = demos && demos[entry.item.demo];
    if (!play || entry.ctx || !active || document.hidden || !animating()) return;
    const ctx = entry.ctx = demos.context();
    (async () => {
      await demos.presenterReady; // the presenter photo decodes once; never start a demo before that
      await ctx.wait(Math.random() * MAX_START_DELAY);
      while (!ctx.cancelled) {
        clearStage(entry.stage);
        await play(entry.stage, ctx);
        await ctx.wait(LOOP_GAP);
      }
    })().catch(error => {
      if (error === demos.CANCELLED) return;
      if (entry.ctx === ctx) entry.ctx = null;
      if (window.console) console.error('effects-ui:', entry.item.id, error);
    });
  }
  function drawStill(entry) {
    const demos = window.FxDemos, play = demos && demos[entry.item.demo];
    stopDemo(entry);
    if (!play) return;
    (async () => {
      await demos.presenterReady; // same decode-before-first-paint rule as the live loop
      clearStage(entry.stage);
      await play(entry.stage, demos.context({still: true}));
    })().catch(() => { /* a still frame is best effort */ });
  }
  function stopDemos() {
    if (observer) { observer.disconnect(); observer = null; }
    cards.forEach(stopDemo);
  }
  function startDemos() {
    stopDemos();
    if (!window.FxDemos || !active) return;
    if (!animating()) { cards.forEach(drawStill); return; }
    if (typeof IntersectionObserver === 'function') {
      const byStage = new Map([...cards.values()].map(entry => [entry.stage, entry]));
      observer = new IntersectionObserver(entries => {
        for (const change of entries) {
          const entry = byStage.get(change.target);
          if (!entry) continue;
          entry.visible = change.isIntersecting;
          if (entry.visible) playDemo(entry); else stopDemo(entry);
        }
      }, {rootMargin: '80px 0px'});
      byStage.forEach((_entry, stage) => observer.observe(stage));
    } else {
      cards.forEach(entry => { entry.visible = true; playDemo(entry); });
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) cards.forEach(stopDemo);
    else if (active && animating()) cards.forEach(entry => { if (entry.visible) playDemo(entry); });
  });

  // ---- "לאיזה סרטון להוסיף?" picker ----
  function buildPicker() {
    const dialog = mk('dialog', 'fx-picker');
    dialog.id = 'effects-picker';
    dialog.setAttribute('aria-labelledby', 'effects-picker-title');
    const head = mk('div', 'fx-picker-head');
    const title = mk('h2');
    title.id = 'effects-picker-title';
    const close = mk('button', 'close-button', '×');
    close.type = 'button';
    close.addEventListener('click', () => dialog.close());
    head.append(title, close);
    const body = mk('p', 'fx-picker-body');
    const list = mk('div', 'fx-picker-list');
    dialog.append(head, body, list);
    dialog.addEventListener('close', () => { pendingAdd = null; });
    document.body.append(dialog);
    return {dialog, title, close, body, list};
  }

  async function openPicker(then) {
    picker = picker || buildPicker();
    const {dialog, title, close, body, list} = picker;
    title.textContent = I18N.t('effects.picker.title');
    close.setAttribute('aria-label', I18N.t('effects.picker.closeAria'));
    body.textContent = I18N.t('effects.picker.body');
    list.innerHTML = '';
    list.append(mk('p', 'fx-picker-note', I18N.t('effects.picker.loading')));
    if (!dialog.open) dialog.showModal();
    pendingAdd = then;
    let projects;
    try { projects = await loadProjects(true); } catch {
      list.innerHTML = '';
      list.append(mk('p', 'fx-picker-note', I18N.t('effects.picker.loadError')));
      return;
    }
    list.innerHTML = '';
    if (!projects.length) {
      list.append(mk('p', 'fx-picker-note', I18N.t('effects.picker.empty')));
      const start = mk('button', 'primary', I18N.t('projects.home.newVideo'));
      start.type = 'button';
      start.setAttribute('data-new-video', '');
      start.addEventListener('click', () => dialog.close());
      list.append(start);
      return;
    }
    for (const p of projects) {
      const option = mk('button', 'fx-picker-item');
      option.type = 'button';
      option.dataset.project = p.id;
      option.append(mk('bdi', null, p.title || p.id));
      if (project && project.id === p.id) option.setAttribute('aria-current', 'true');
      option.addEventListener('click', () => chooseProject(p.id));
      list.append(option);
    }
  }

  function dropPendingWhen() {
    whenTimers.forEach(timer => clearTimeout(timer));
    whenTimers.clear();
  }

  async function chooseProject(id) {
    dropPendingWhen();
    const then = pendingAdd;
    pendingAdd = null;
    if (picker && picker.dialog.open) picker.dialog.close();
    history.replaceState(null, '', '#effects?' + new URLSearchParams({project: id}));
    try {
      await loadProject(id);
    } catch {
      showStatus(I18N.t('effects.loadError'));
      return;
    }
    renderTarget();
    refreshChoices();
    if (then) then();
  }

  // ---- public ----
  function mount(el, projectId, wantedTab) {
    const my = ++token;
    if (wantedTab === 'fx' || wantedTab === 'look') { tab = wantedTab; filter = 'all'; }
    root = el;
    active = true;
    if (window.SlotHeadline && typeof window.SlotHeadline.motion === 'function') motionPref = window.SlotHeadline.motion();
    if (!project || project.id !== projectId) {
      dropPendingWhen();
      project = projectId ? {id: projectId, title: ''} : null;
      chosen = {effects: [], presenter: null};
    }
    buildShell();
    renderBoard();
    showStatus(catalog ? '' : I18N.t('effects.loading'));
    (async () => {
      try {
        await loadCatalog();
        if (projectId) await loadProject(projectId);
        if (my !== token) return;
        showStatus('');
        renderBoard();
      } catch {
        if (my === token) showStatus(I18N.t('effects.loadError'));
      }
    })();
  }

  function leave() {
    dropPendingWhen();
    active = false;
    token++;
    stopDemos();
    if (picker && picker.dialog.open) picker.dialog.close();
  }

  function setMotion(value) {
    if (!MOTIONS.includes(value) || value === motionPref) return motionPref;
    motionPref = value;
    if (active && ui.grid) { renderNote(); startDemos(); }
    return motionPref;
  }

  // The system reduced-motion setting can change while the board is open (auto follows it).
  try {
    const query = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
    if (query && query.addEventListener) query.addEventListener('change', () => { if (active && ui.grid) { renderNote(); startDemos(); } });
  } catch { /* no matchMedia: auto simply animates */ }

  document.addEventListener('i18n:change', () => {
    if (!active || !root) return;
    buildShell();
    renderBoard();
  });

  return {mount, leave, setMotion, logic, get project() { return project && project.id; }};
})();
