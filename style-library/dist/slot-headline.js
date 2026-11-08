/* Slot headline: the top h1 of each studio screen spins word by word through Assaf's five display fonts like a
   slot machine, 10 spins (one every 3 s), then settles on Secular One and stops.
   - Uses the Web Animations API (element.animate); CSS transitions did not run reliably in the target browser.
   - The real text stays in the h1's aria-label; the reels are aria-hidden copies.
   - Motion setting (footer, persisted in settings.json): auto follows prefers-reduced-motion (no spinning, the
     headline simply shows in Secular One); always spins regardless; off never spins.
   - Pauses while the tab is hidden or the headline's screen is hidden; re-mounts when the text changes
     (language toggle, re-render). Fonts and per-font scale live in CSS (.slot-f0 ... .slot-f4). */
window.SlotHeadline = (() => {
  // Order matters: index 0 is where every headline starts and finally settles.
  const FONTS = ['Secular One', 'Bellefair', 'Karantina 700', 'Heebo 800', 'Suez One'];
  const N = FONTS.length, REPS = 8, ROW_EM = 1.3, SPINS = 10, PERIOD = 3000, FIRST_SPIN = 600;
  const SPIN_MS = 1150, STAGGER = 120, SPIN_EASE = 'cubic-bezier(.12,.62,.22,1.12)';
  const WIDTH_MS = 450, WIDTH_DELAY = 700, WIDTH_EASE = 'cubic-bezier(.3,1.4,.4,1)';
  const TARGETS = '#projects-page h1, #library-page .intro h1, #guide-page h1, #updates-page h1, #effects-page h1';
  const MOTIONS = ['auto', 'always', 'off'];
  const states = new WeakMap();
  const live = new Set(); // mounted headlines, so a motion change can re-mount them
  let motionPref = 'auto';

  const ty = p => 'translateY(' + (-ROW_EM * p) + 'em)';
  const blurFrames = (from, to) => [
    {transform: ty(from), filter: 'blur(0px)', offset: 0},
    {filter: 'blur(3px)', offset: 0.15},
    {filter: 'blur(1.5px)', offset: 0.7},
    {transform: ty(to), filter: 'blur(0px)', offset: 1},
  ];

  function reducedMotion() {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch { return false; }
  }

  function staticHeadline(options) {
    const motion = options.motion || motionPref;
    if (motion === 'off') return true;
    if (motion === 'always') return false;
    return options.reducedMotion !== undefined ? options.reducedMotion : reducedMotion();
  }

  // Headline -> lines of words. <br> starts a new line; words inside <em>/<strong> keep an accent colour.
  function readLines(el) {
    const lines = [[]];
    const push = (text, accent) => text.split(/\s+/).filter(Boolean).forEach(word => lines[lines.length - 1].push({word, accent}));
    for (const node of Array.from(el.childNodes || [])) {
      if (node.nodeType === 3) push(node.nodeValue || '', false);
      else if (node.nodeType === 1) {
        const tag = String(node.tagName || '').toUpperCase();
        if (tag === 'BR') lines.push([]);
        else push(node.textContent || '', tag === 'EM' || tag === 'STRONG' || tag === 'B');
      }
    }
    return lines.filter(line => line.length);
  }

  function span(doc, className) {
    const node = doc.createElement('span');
    node.className = className;
    return node;
  }

  function widthOf(reel, row) {
    const text = reel.rows[row] && reel.rows[row].firstChild;
    const box = text && text.getBoundingClientRect ? text.getBoundingClientRect() : null;
    return box && box.width ? Math.ceil(box.width) + 2 : 0;
  }

  function setWidths(state) {
    for (const reel of state.reels) {
      const width = widthOf(reel, reel.pos);
      if (width) reel.win.style.width = width + 'px';
    }
  }

  function rendered(el) {
    return !el.getClientRects || el.getClientRects().length > 0;
  }

  function stop(el) {
    const state = states.get(el);
    if (!state) return;
    clearTimeout(state.first);
    clearInterval(state.timer);
    state.first = state.timer = null;
  }

  function spin(state) {
    const el = state.el;
    if (!el.isConnected) { stop(el); states.delete(el); live.delete(el); return; }
    if (state.spins >= SPINS) { stop(el); return; }
    const doc = el.ownerDocument || document;
    if (doc.hidden || !rendered(el)) return; // paused: don't count a spin nobody sees
    state.spins++;
    const next = state.spins === SPINS ? 0 : (state.cur + 1) % N;
    state.reels.forEach((reel, k) => {
      let from = reel.pos;
      if (from + N * 3 >= N * REPS) { from %= N; reel.reel.style.transform = ty(from); }
      const target = (from - (from % N)) + N * 2 + next;
      const motion = reel.reel.animate(blurFrames(from, target), {duration: SPIN_MS, delay: k * STAGGER, easing: SPIN_EASE, fill: 'both'});
      motion.onfinish = () => { reel.reel.style.transform = ty(target); motion.cancel(); };
      reel.pos = target;
      const fromWidth = reel.win.style.width || (widthOf(reel, from) ? widthOf(reel, from) + 'px' : null);
      const toWidth = widthOf(reel, target);
      if (fromWidth && toWidth) {
        const grow = reel.win.animate([{width: fromWidth}, {width: toWidth + 'px'}], {duration: WIDTH_MS, delay: k * STAGGER + WIDTH_DELAY, easing: WIDTH_EASE, fill: 'forwards'});
        grow.onfinish = () => { reel.win.style.width = toWidth + 'px'; grow.cancel(); };
      }
    });
    state.cur = next;
    if (state.spins >= SPINS) stop(el);
  }

  function mount(el, options = {}) {
    if (!el) return null;
    stop(el);
    const previous = states.get(el);
    const doc = el.ownerDocument || document;
    const lines = previous && previous.inner.parentNode === el ? previous.lines : readLines(el);
    const reduce = staticHeadline(options);
    const label = lines.map(line => line.map(w => w.word).join(' ')).join(' ');
    const inner = span(doc, 'slot-inner');
    inner.setAttribute('aria-hidden', 'true');
    const reels = [];
    for (const line of lines) {
      const row = span(doc, 'slot-line');
      for (const {word, accent} of line) {
        const win = span(doc, 'slot-win' + (accent ? ' slot-accent' : ''));
        const reel = span(doc, 'slot-reel');
        const rows = [];
        const copies = reduce ? 1 : REPS;
        for (let r = 0; r < copies; r++) {
          FONTS.slice(0, reduce ? 1 : N).forEach((_, f) => {
            const cell = span(doc, 'slot-row');
            const text = span(doc, 'slot-f' + f);
            text.textContent = word;
            cell.appendChild(text);
            reel.appendChild(cell);
            rows.push(cell);
          });
        }
        win.appendChild(reel);
        row.appendChild(win);
        reels.push({win, reel, rows, pos: 0});
      }
      inner.appendChild(row);
    }
    el.textContent = '';
    el.appendChild(inner);
    el.setAttribute('aria-label', label);
    if (el.classList) el.classList.add('slot-headline');
    const state = {el, lines, inner, reels, spins: 0, cur: 0, reduce, first: null, timer: null};
    states.set(el, state);
    live.add(el);
    if (reduce) return state;
    setWidths(state);
    if (doc.fonts && doc.fonts.ready && doc.fonts.ready.then) doc.fonts.ready.then(() => { if (states.get(el) === state) setWidths(state); });
    state.first = setTimeout(() => {
      state.first = null;
      spin(state);
      if (state.spins < SPINS) state.timer = setInterval(() => spin(state), PERIOD);
    }, FIRST_SPIN);
    return state;
  }

  // Apply the saved motion setting (auto/always/off) and re-mount every live headline with it.
  function setMotion(value) {
    if (!MOTIONS.includes(value)) return motionPref;
    motionPref = value;
    for (const el of [...live]) {
      if (el.isConnected) mount(el);
      else { stop(el); states.delete(el); live.delete(el); }
    }
    return motionPref;
  }

  function inspect(el) {
    const state = states.get(el);
    if (!state) return null;
    return {spins: state.spins, running: !!(state.timer || state.first), reduce: state.reduce, landed: state.reels.map(r => FONTS[r.pos % N]), label: el.getAttribute('aria-label')};
  }

  function needsMount(el) {
    const state = states.get(el);
    return !state || state.inner.parentNode !== el;
  }

  // Mount every visible screen headline that is new or whose text was replaced.
  function refresh(root) {
    const scope = root || document;
    scope.querySelectorAll(TARGETS).forEach(el => {
      if (rendered(el) && needsMount(el)) mount(el);
    });
  }

  function auto() {
    let queued = false;
    const later = () => { if (queued) return; queued = true; setTimeout(() => { queued = false; refresh(); }, 0); };
    new MutationObserver(later).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['hidden']});
    document.addEventListener('i18n:change', later);
    later();
  }

  if (typeof MutationObserver === 'function' && typeof document !== 'undefined' && document.addEventListener) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auto, {once: true});
    else auto();
  }

  return {mount, refresh, inspect, setMotion, motion: () => motionPref, FONTS, SPINS, PERIOD};
})();
