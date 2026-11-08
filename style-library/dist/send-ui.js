/* Task 15: "שליחה לקלוד" (Send to Claude) with live progress, and the quiet
   "או העתקה לצ׳אט" (copy to chat) fallback. Mounted on the project page right below the
   choices card (studio.js projectPage); Task 13's "ללמוד את הסגנון" button mounts the same
   card with {task: 'learn-style'} for one reference.

   Server side (claude_runner.py, Task 14 + 15):
     POST /claude-job {project|reference, task}   -> 202 {job} | 409 {error: claude-missing|busy|...}
     GET  /claude-job?id=<job>                     -> {job, state, steps, message_key, started}
     GET  /claude-job?project=<id>|reference=<id>  -> the newest job for it, or {job: null}
     POST /claude-job-cancel {job}
     GET  /claude-job-log?id=<job>&lines=<n>       -> {log}: last n lines of logs/claude-<job>.log
     GET  /claude-request?project=<id>             -> {text}: the copy-to-chat request

   view(status) is a pure mapping from a runner status to what the card shows (title,
   message, steps, primary/secondary actions, support link, progress, elapsed time); mount()
   only turns that into DOM nodes and wires the actions. A running job survives a page reload:
   mount() asks the server for the project's newest job and resumes polling it. Polling runs
   every 2 s while a job runs, pauses while the tab is hidden and stops as soon as the job is
   done / failed / stopped or the card leaves the page. Step nodes are updated in place (keyed
   by step key), so the running step's CSS spinner never restarts between polls; the spinner
   is a plain CSS animation that the Motion setting (html[data-motion], motion-setting.js) and
   prefers-reduced-motion turn off -- a step's state is also always written out as text. */
window.SendUI = (() => {
  const POLL_MS = 2000;
  const LOG_PREVIEW_LINES = 8;
  const RECENT_SECONDS = 12 * 3600; // a failed/stopped job newer than this is shown again after a reload
  const SUPPORT_LINES = 40;
  const STEP_STATES = ['done', 'running', 'todo'];
  const STATE_KEY = {done: 'claude.stepState.done', running: 'claude.stepState.running', todo: 'claude.stepState.todo'};
  const STEP_KEYS = ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard', 'voice', 'scenes',
    'watch', 'analyze', 'card', 'matte'];
  const MESSAGE_KEYS = ['claude.not-logged-in', 'claude.limit', 'claude.failed', 'claude-missing', 'busy',
    'claude.invalid-request', 'claude.unknown-project', 'claude.unknown-reference', 'claude.unknown-job', 'claude.unknown-kind'];
  // Retrying cannot help with these: the copy-to-chat request becomes the main action.
  const COPY_FIRST = new Set(['claude-missing', 'claude.unknown-kind']);
  const finished = new Map(); // target key -> last finished status, re-shown when the page re-renders
  let active = null;          // the one mounted card's controller
  let run = 0;

  // ------------------------------------------------------------ pure helpers

  function stepLabel(key) {
    const name = 'claude.step.' + key;
    const text = STEP_KEYS.includes(key) ? I18N.t(name) : name;
    return text === name ? String(key) : text;
  }

  function elapsed(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    if (total < 60) return I18N.t('claude.elapsed.under');
    if (total < 120) return I18N.t('claude.elapsed.oneMinute');
    if (total < 3600) return I18N.t('claude.elapsed.minutes', {n: String(Math.floor(total / 60))});
    const minutes = Math.floor(total / 60) % 60;
    return I18N.t('claude.elapsed.hours', {h: String(Math.floor(total / 3600)), mm: String(minutes).padStart(2, '0')});
  }

  function view(status, options = {}) {
    const s = status && typeof status === 'object' ? status : {state: 'idle'};
    const style = options.task === 'learn-style';
    const state = s.state || 'idle';
    let steps = (Array.isArray(s.steps) ? s.steps : []).filter(step => step && typeof step.key === 'string').map((step, i) => ({
      key: step.key, label: stepLabel(step.key), number: i + 1,
      state: STEP_STATES.includes(step.state) ? step.state : 'todo',
      detail: typeof step.detail === 'string' ? step.detail : '',
    }));
    if (state === 'done') steps = steps.map(step => ({...step, state: 'done'}));
    const done = steps.filter(step => step.state === 'done').length;
    const current = steps.find(step => step.state === 'running');
    const progress = state === 'done' ? 1 : steps.length ? (done + (current ? 0.5 : 0)) / steps.length : null;
    const send = {action: 'send', label: I18N.t('claude.send')};
    const quietCopy = {action: 'copy', label: I18N.t('claude.copy')};
    const copy = {action: 'copy', label: I18N.t('claude.copyPrimary')};
    const retry = {action: 'retry', label: I18N.t('claude.retry')};
    const base = {state, steps, progress, primary: send, secondary: quietCopy, support: null, running: false,
      title: I18N.t('claude.title.idle'), label: '', elapsed: '', panel: false};
    const time = typeof s.started === 'number' && typeof options.now === 'number' ? elapsed(options.now - s.started) : '';
    switch (state) {
      case 'starting':
        return {...base, primary: {...send, disabled: true}, secondary: null, label: I18N.t('claude.state.starting')};
      case 'running':
      case 'stopping':
        return {...base, running: true, panel: true, secondary: null, elapsed: time ? I18N.t('claude.elapsed', {time}) : '',
          title: I18N.t(style ? 'claude.title.runningStyle' : 'claude.title.running'),
          primary: {action: 'cancel', label: I18N.t('claude.cancel'), disabled: state === 'stopping'},
          label: state === 'stopping' ? I18N.t('claude.state.stopping')
            : current ? I18N.t('claude.state.running', {step: current.label}) : I18N.t('claude.state.gettingStarted')};
      case 'done':
        return {...base, panel: steps.length > 0, secondary: null, title: I18N.t('claude.title.done'),
          primary: style ? null : {action: 'review', label: I18N.t('claude.review')},
          label: I18N.t(style ? 'claude.state.doneStyle' : 'claude.state.done')};
      case 'failed': {
        const key = s.message_key || 'claude.failed';
        const copyFirst = COPY_FIRST.has(key);
        return {...base, panel: steps.length > 0, title: I18N.t('claude.title.failed'), label: I18N.t(key),
          primary: copyFirst ? copy : retry, secondary: copyFirst ? null : copy,
          support: !copyFirst && s.job ? {action: 'support', label: I18N.t('claude.support')} : null};
      }
      case 'stopped':
        return {...base, panel: steps.length > 0, title: I18N.t('claude.title.stopped'), label: I18N.t('claude.stopped'),
          primary: retry, secondary: copy};
      default:
        return base;
    }
  }

  // stream-json from `claude -p --output-format stream-json` -> a few short plain lines.
  function readableLog(text, max = 4) {
    const out = [];
    const clip = value => String(value).trim().split('\n')[0].slice(0, 140);
    for (const line of String(text || '').split('\n')) {
      const raw = line.trim();
      if (!raw) continue;
      let event;
      try { event = JSON.parse(raw); } catch { out.push(clip(raw)); continue; }
      const content = event && event.type === 'assistant' && event.message && Array.isArray(event.message.content) ? event.message.content : [];
      for (const part of content) {
        if (part && part.type === 'text' && typeof part.text === 'string' && part.text.trim()) out.push(clip(part.text));
        else if (part && part.type === 'tool_use' && typeof part.name === 'string') {
          const input = part.input && typeof part.input === 'object' ? part.input : {};
          const detail = [input.command, input.file_path, input.pattern, input.path].find(v => typeof v === 'string' && v.trim());
          out.push(clip(part.name + (detail ? ' · ' + detail : '')));
        }
      }
    }
    return out.slice(-max);
  }

  // ------------------------------------------------------------ DOM

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = [].concat(className).join(' ');
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function build(ctl) {
    const style = ctl.task === 'learn-style';
    const section = node('section', 'send-section');
    section.setAttribute('aria-label', I18N.t('claude.sectionAria'));
    const head = node('div', 'send-head');
    const eyebrow = node('p', ['eyebrow', 'send-eyebrow']);
    const title = node('h2', 'send-title');
    const intro = node('p', 'send-intro', I18N.t(style ? 'claude.introStyle' : 'claude.intro'));
    head.append(eyebrow, title, intro);

    const actions = node('div', 'send-actions');
    const primary = node('button', ['primary', 'send-primary']);
    primary.type = 'button';
    const quiet = node('button', ['send-quiet', 'send-copy']);
    quiet.type = 'button';
    actions.append(primary, quiet);

    const message = node('p', 'send-message');
    message.setAttribute('role', 'status');
    message.setAttribute('aria-live', 'polite');

    const progress = node('div', 'send-progress');
    const stepsCol = node('div', 'send-steps-col');
    const list = node('ol', 'send-steps');
    list.setAttribute('aria-label', I18N.t('claude.stepsAria'));
    const bar = node('div', 'send-bar');
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-label', I18N.t('claude.progressAria'));
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    const fill = node('span', 'send-bar-fill');
    bar.append(fill);
    stepsCol.append(list, bar);
    const side = node('div', 'send-side');
    const elapsedLine = node('p', 'send-elapsed');
    const note = node('p', 'send-note', I18N.t('claude.closeNote'));
    const log = node('pre', 'send-log');
    log.setAttribute('dir', 'ltr');
    log.setAttribute('aria-label', I18N.t('claude.logAria'));
    side.append(elapsedLine, note, log);
    progress.append(stepsCol, side);

    const support = node('button', ['send-quiet', 'send-support']);
    support.type = 'button';
    const status = node('p', 'send-status');
    status.setAttribute('role', 'status');
    const fallback = node('div', 'send-fallback');
    const fallbackLabel = node('label', 'send-fallback-label', I18N.t('claude.copyLabel'));
    const area = node('textarea', 'send-fallback-text');
    area.setAttribute('readonly', '');
    area.setAttribute('rows', '12');
    area.setAttribute('spellcheck', 'false');
    area.setAttribute('dir', 'auto');
    area.id = 'send-fallback-' + ctl.token;
    fallbackLabel.setAttribute('for', area.id);
    fallback.append(fallbackLabel, area);
    fallback.hidden = true;

    section.append(head, actions, message, progress, support, status, fallback);
    ctl.el.replaceChildren(section);
    ctl.nodes = {section, eyebrow, title, intro, primary, quiet, message, progress, list, bar, fill, elapsedLine, note, log, support, status, fallback, area};
    ctl.stepNodes = new Map();
    primary.addEventListener('click', () => act(ctl, ctl.view && ctl.view.primary));
    quiet.addEventListener('click', () => act(ctl, ctl.view && ctl.view.secondary));
    support.addEventListener('click', () => act(ctl, ctl.view && ctl.view.support));
  }

  function setButton(button, action) {
    button.hidden = !action;
    if (!action) return;
    if (button.textContent !== action.label) button.textContent = action.label;
    button.disabled = !!action.disabled;
    button.dataset.action = action.action;
  }

  function renderSteps(ctl, steps) {
    const {list} = ctl.nodes;
    const keep = [];
    for (const step of steps) {
      let item = ctl.stepNodes.get(step.key);
      if (!item) {
        const li = node('li', 'send-step');
        const icon = node('span', 'send-step-icon');
        icon.setAttribute('aria-hidden', 'true');
        const label = node('span', 'send-step-label');
        const state = node('span', ['sr-only', 'send-step-state']);
        const detail = node('small', 'send-step-detail');
        li.append(icon, label, state, detail);
        item = {li, icon, label, state, detail};
        ctl.stepNodes.set(step.key, item);
      }
      if (item.li.dataset.state !== step.state) {
        item.li.dataset.state = step.state;
        STEP_STATES.forEach(name => item.li.classList.toggle('is-' + name, name === step.state));
        item.state.textContent = I18N.t(STATE_KEY[step.state]);
      }
      const glyph = step.state === 'done' ? '✓' : step.state === 'todo' ? String(step.number) : '';
      if (item.icon.textContent !== glyph) item.icon.textContent = glyph;
      if (item.label.textContent !== step.label) item.label.textContent = step.label;
      if (item.detail.textContent !== step.detail) item.detail.textContent = step.detail;
      keep.push(item.li);
    }
    for (const [key, item] of ctl.stepNodes) if (!steps.some(step => step.key === key)) ctl.stepNodes.delete(key);
    const same = keep.length === list.children.length && keep.every((li, i) => list.children[i] === li);
    if (!same) list.replaceChildren(...keep);
  }

  function render(ctl, status) {
    if (!ctl.nodes) return;
    ctl.status = status;
    const v = view(status, {task: ctl.task, now: Date.now() / 1000});
    ctl.view = v;
    const n = ctl.nodes;
    n.section.dataset.state = v.state;
    n.eyebrow.textContent = I18N.t(v.running ? 'claude.eyebrowRunning' : 'claude.eyebrow');
    n.title.textContent = v.title;
    n.intro.hidden = v.state !== 'idle';
    setButton(n.primary, v.primary);
    setButton(n.quiet, v.secondary);
    n.quiet.classList.toggle('is-quiet', !!v.secondary && v.secondary.label === I18N.t('claude.copy'));
    setButton(n.support, v.support);
    n.message.textContent = v.label;
    n.message.hidden = !v.label;
    n.progress.hidden = !v.panel;
    renderSteps(ctl, v.steps);
    n.bar.hidden = v.progress === null && !v.running;
    if (v.progress === null) {
      n.bar.removeAttribute('aria-valuenow');
      n.bar.classList.add('is-waiting');
      n.fill.style.inlineSize = '';
    } else {
      const percent = Math.round(v.progress * 100);
      n.bar.setAttribute('aria-valuenow', String(percent));
      n.bar.classList.remove('is-waiting');
      n.fill.style.inlineSize = percent + '%';
    }
    n.elapsedLine.textContent = v.elapsed;
    n.elapsedLine.hidden = !v.elapsed;
    n.note.hidden = !v.running;
    n.log.hidden = !n.log.textContent || !(v.running || v.state === 'failed');
  }

  // ------------------------------------------------------------ job lifecycle

  const alive = ctl => active === ctl && ctl.el.isConnected;
  const targetQuery = ctl => (ctl.task === 'learn-style' ? 'reference=' : 'project=') + encodeURIComponent(ctl.id);

  function schedule(ctl) {
    clearTimeout(ctl.timer);
    ctl.timer = null;
    if (!alive(ctl) || document.hidden || !ctl.job) return;
    ctl.timer = setTimeout(() => { ctl.timer = null; poll(ctl); }, POLL_MS);
  }

  async function readJson(response) {
    try { return await response.json(); } catch { return null; }
  }

  async function poll(ctl) {
    if (!alive(ctl) || !ctl.job || ctl.polling) return;
    ctl.polling = true;
    let status = null;
    try {
      const response = await fetch('/claude-job?id=' + encodeURIComponent(ctl.job), {cache: 'no-store'});
      const data = await readJson(response);
      if (response.ok && data) status = data;
      else if (response.status === 404) status = {state: 'failed', message_key: (data && data.error) || 'claude.unknown-job'};
    } catch { /* a missed poll: try again in 2 s */ }
    ctl.polling = false;
    if (!alive(ctl)) return;
    if (status) apply(ctl, status);
    else schedule(ctl);
  }

  async function refreshLog(ctl) {
    if (!ctl.job) return;
    try {
      const response = await fetch(`/claude-job-log?id=${encodeURIComponent(ctl.job)}&lines=${LOG_PREVIEW_LINES}`, {cache: 'no-store'});
      const data = response.ok ? await readJson(response) : null;
      const lines = data ? readableLog(data.log) : [];
      if (!alive(ctl) || !lines.length) return;
      ctl.nodes.log.textContent = lines.join('\n');
      ctl.nodes.log.hidden = !(ctl.view && (ctl.view.running || ctl.view.state === 'failed'));
    } catch { /* the log preview is decorative */ }
  }

  function apply(ctl, status) {
    if (!alive(ctl)) return;
    if (status.job) ctl.job = status.job;
    const shown = ctl.cancelling && status.state === 'running' ? {...status, state: 'stopping'} : status;
    render(ctl, shown);
    if (status.state === 'running') {
      finished.delete(ctl.key);
      if (ctl.logTick++ % 2 === 1) refreshLog(ctl); // the log preview is decorative: every other poll
      schedule(ctl);
      return;
    }
    clearTimeout(ctl.timer);
    ctl.timer = null;
    ctl.cancelling = false;
    if (['done', 'failed', 'stopped'].includes(status.state)) finished.set(ctl.key, status);
    if (status.state === 'done') {
      if (ctl.onDone) ctl.onDone(status);
      else if (ctl.task === 'edit' && window.Studio && window.Studio.refresh) window.Studio.refresh(true);
    }
  }

  async function resume(ctl) {
    let data = null;
    try {
      const response = await fetch('/claude-job?' + targetQuery(ctl), {cache: 'no-store'});
      data = response.ok ? await readJson(response) : null;
    } catch { return false; }
    if (!alive(ctl) || !data || !data.job) return false;
    // A running job resumes. A job that failed or stopped while the window was closed is
    // shown once more (with try again / copy to chat) if it is recent; done jobs never are.
    const recent = typeof data.started === 'number' && Date.now() / 1000 - data.started < RECENT_SECONDS;
    if (data.state !== 'running' && !(recent && ['failed', 'stopped'].includes(data.state))) return false;
    ctl.job = data.job;
    apply(ctl, data);
    return true;
  }

  async function send(ctl) {
    finished.delete(ctl.key);
    ctl.job = null;
    ctl.cancelling = false;
    ctl.nodes.log.textContent = '';
    ctl.nodes.fallback.hidden = true;
    ctl.nodes.status.textContent = '';
    render(ctl, {state: 'starting'});
    let response, data;
    try {
      const body = ctl.task === 'learn-style' ? {reference: ctl.id, task: 'learn-style'} : {project: ctl.id, task: 'edit'};
      response = await fetch('/claude-job', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'claude-job'}, body: JSON.stringify(body)});
      data = (await readJson(response)) || {};
    } catch {
      return apply(ctl, {state: 'failed', message_key: 'claude.failed'});
    }
    if (!alive(ctl)) return;
    if (response.status === 409 && data.error === 'busy') {
      if (await resume(ctl)) return;
      return apply(ctl, {state: 'failed', message_key: 'busy'});
    }
    if (!response.ok || typeof data.job !== 'string') return apply(ctl, {state: 'failed', message_key: data.error || 'claude.failed'});
    apply(ctl, {job: data.job, state: 'running', steps: [], message_key: null, started: Date.now() / 1000});
  }

  async function cancel(ctl) {
    if (!ctl.job || ctl.cancelling) return;
    ctl.cancelling = true;
    render(ctl, {...ctl.status, state: 'stopping'});
    try {
      const response = await fetch('/claude-job-cancel', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'claude-job-cancel'}, body: JSON.stringify({job: ctl.job})});
      const data = await readJson(response);
      if (response.ok && data) return apply(ctl, data);
    } catch { /* fall through: keep polling, the next poll shows the real state */ }
    ctl.cancelling = false;
    if (alive(ctl)) apply(ctl, ctl.status && ctl.status.state === 'stopping' ? {...ctl.status, state: 'running'} : ctl.status);
  }

  async function clip(ctl, text, done) {
    const n = ctl.nodes;
    try {
      await navigator.clipboard.writeText(text);
      n.fallback.hidden = true;
      n.status.textContent = done;
    } catch {
      n.area.value = text;
      n.fallback.hidden = false;
      n.status.textContent = I18N.t('claude.copyManual');
      n.area.focus();
      n.area.select();
      n.area.scrollTop = 0;
    }
  }

  async function copyRequest(ctl) {
    let text = null;
    if (ctl.task === 'learn-style') text = I18N.t('claude.copy.learnStyle', {folder: 'references/' + ctl.id});
    else {
      try {
        const response = await fetch('/claude-request?project=' + encodeURIComponent(ctl.id), {cache: 'no-store'});
        const data = response.ok ? await readJson(response) : null;
        if (data && typeof data.text === 'string') text = data.text;
      } catch { /* shown below */ }
    }
    if (!alive(ctl)) return;
    if (text === null) { ctl.nodes.status.textContent = I18N.t('claude.copyFailed'); return; }
    await clip(ctl, text, I18N.t('claude.copied'));
  }

  async function copySupport(ctl) {
    const job = ctl.job || (ctl.status && ctl.status.job);
    if (!job) return;
    let text = null;
    try {
      const response = await fetch(`/claude-job-log?id=${encodeURIComponent(job)}&lines=${SUPPORT_LINES}`, {cache: 'no-store'});
      const data = response.ok ? await readJson(response) : null;
      if (data && typeof data.log === 'string') text = data.log;
    } catch { /* shown below */ }
    if (!alive(ctl)) return;
    if (text === null) { ctl.nodes.status.textContent = I18N.t('claude.copyFailed'); return; }
    if (!text.trim()) { ctl.nodes.status.textContent = I18N.t('claude.supportEmpty'); return; }
    await clip(ctl, I18N.t('claude.supportNote') + '\n\n' + text, I18N.t('claude.supportCopied'));
  }

  function review(ctl) {
    finished.delete(ctl.key);
    const hash = '#project=' + encodeURIComponent(ctl.id);
    if (location.hash === hash) { if (window.Studio && window.Studio.route) window.Studio.route(); }
    else location.hash = hash;
  }

  function act(ctl, action) {
    if (!action || action.disabled || !alive(ctl)) return;
    if (action.action === 'send' || action.action === 'retry') return send(ctl);
    if (action.action === 'cancel') return cancel(ctl);
    if (action.action === 'copy') return copyRequest(ctl);
    if (action.action === 'support') return copySupport(ctl);
    if (action.action === 'review') return review(ctl);
  }

  // ------------------------------------------------------------ public

  // mount(el, id, {task: 'edit' | 'learn-style', onDone}) -- id is a project id (edit) or a
  // reference id (learn-style). One card is active at a time; mounting again (a language
  // switch or page refresh re-renders the project page) takes over any job still running.
  function mount(el, id, options = {}) {
    const task = options.task === 'learn-style' ? 'learn-style' : 'edit';
    const key = (task === 'learn-style' ? 'reference:' : 'project:') + id;
    const previous = active;
    if (previous) { clearTimeout(previous.timer); previous.timer = null; }
    const ctl = {el, id, task, key, token: ++run, job: null, status: null, view: null, timer: null,
      polling: false, cancelling: false, logTick: 0, onDone: typeof options.onDone === 'function' ? options.onDone : null};
    active = ctl;
    build(ctl);
    const carried = previous && previous.key === key && previous.status && ['running', 'stopping'].includes(previous.status.state) ? previous : null;
    if (carried) {
      // Take over the job and poll it straight away: the old card's in-flight poll (which may
      // carry the job's end) is dropped with the old card, so nothing else would notice.
      ctl.job = carried.job;
      ctl.cancelling = carried.cancelling;
      ctl.nodes.log.textContent = carried.nodes ? carried.nodes.log.textContent : '';
      render(ctl, carried.status);
      poll(ctl);
      return ctl.token;
    }
    const ended = finished.get(key);
    if (ended && ended.state === 'done') {
      // The page was re-rendered after a finished job (Studio.refresh showing the new
      // version): back to "send", with a one-time note. The next render is plain.
      finished.delete(key);
      render(ctl, {state: 'idle'});
      ctl.nodes.status.textContent = I18N.t(ctl.task === 'learn-style' ? 'claude.state.doneStyle' : 'claude.state.done');
      return ctl.token;
    }
    if (ended) { ctl.job = ended.job || null; render(ctl, ended); return ctl.token; }
    render(ctl, {state: 'idle'});
    resume(ctl);
    return ctl.token;
  }

  document.addEventListener('visibilitychange', () => {
    const ctl = active;
    if (!ctl) return;
    if (document.hidden) { clearTimeout(ctl.timer); ctl.timer = null; return; }
    if (ctl.job && ctl.status && ['running', 'stopping'].includes(ctl.status.state)) poll(ctl);
  });

  return {mount, view, elapsed, readableLog, STEP_KEYS, MESSAGE_KEYS};
})();
