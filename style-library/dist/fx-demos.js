/* Task 12: live demos for the effects board ("אפקטים ומראה"). One small scene per effect
   (effects/effects.json) and per presenter look (looks/presenter.json), each registered with
   demo('<id>', async (stage, ctx) => ...) -- the catalog's "demo" field names one of these
   (test_effects.py parses this file for the ids).

   window.FxDemos is the registry: FxDemos[id](stage[, ctx]) plays one pass of the demo into
   `stage` (an empty, position:relative box with the .fx-stage container) and resolves when it
   is done. FxDemos.context({still}) (not enumerable, so Object.keys(FxDemos) is just the ids)
   makes the ctx a caller passes in to stop a demo early (ctx.cancel()) or to draw only its
   end frame (still: true -- every animation jumps to its end and every wait resolves at once).

   - Web Animations API only (element.animate): CSS transitions did not run in the target
     browser. Timing is awaited with timers (duration + delay), never with animation.finished,
     which hung in some environments (controller ruling R19/R20).
   - The demo subject is the studio owner's AI-generated presenter photo (supplied and cleared
     by the owner for distribution; see THIRD_PARTY_NOTICES.md) -- the same cutout used in the
     built-in look previews (looks/_presenter/presenter-cutout.png), served here from
     assets/brand/presenter-cutout.png. Never a real person's likeness.
   - Sizes are written in px for a 240px-wide card and converted to container units (cqw), so
     a demo scales with its card. All sample words come from I18N (fx.demo.*). */
window.FxDemos = (() => {
  const FxDemos = {};
  const EASE = 'cubic-bezier(.2,.8,.2,1)';
  const CANCELLED = 'fx-demo-cancelled';
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function demo(id, play) { FxDemos[id] = (stage, ctx) => play(stage, ctx || context()); }

  function context(options = {}) {
    const still = !!options.still;
    const ctx = {still, cancelled: false};
    ctx.cancel = () => { ctx.cancelled = true; };
    // Rejects with CANCELLED once the demo is cancelled. Demos fire some ctx.A() calls without
    // awaiting them, so the rejection is pre-handled here (no "Uncaught (in promise)"); an
    // awaiting caller still sees it and stops.
    ctx.wait = ms => {
      if (still) return Promise.resolve();
      const timer = new Promise((resolve, reject) => {
        setTimeout(() => (ctx.cancelled ? reject(CANCELLED) : resolve()), ms);
      });
      timer.catch(() => {});
      return timer;
    };
    // Start an animation; resolve after its duration + delay (a timer, not .finished).
    ctx.A = (el, keyframes, timing = {}) => {
      const animation = el.animate(keyframes, {fill: 'both', easing: EASE, ...timing});
      if (still) {
        try { animation.finish(); } catch { /* a zero-length or idle animation is already at its end */ }
        return Promise.resolve();
      }
      return ctx.wait((timing.duration || 0) + (timing.delay || 0));
    };
    // Step a value from 0 to 1 over `ms` (a count-up), in timer ticks.
    ctx.tween = async (ms, step) => {
      if (still) { step(1); return; }
      const ticks = Math.max(1, Math.round(ms / 33));
      for (let i = 1; i <= ticks; i++) { step(i / ticks); await ctx.wait(ms / ticks); }
    };
    return ctx;
  }
  Object.defineProperty(FxDemos, 'context', {value: context, enumerable: false});
  Object.defineProperty(FxDemos, 'CANCELLED', {value: CANCELLED, enumerable: false});

  // ---------- building blocks ----------
  const u = px => (px / 2.4).toFixed(2) + 'cqw'; // px on a 240px-wide card -> container units
  const FONTS = {head: 'font-family:var(--head);font-weight:700', display: 'font-family:var(--display);font-weight:400',
    serif: 'font-family:var(--serif);font-weight:400', body: 'font-family:var(--body)'};
  const font = (role, px) => FONTS[role] + ';font-size:' + u(px);

  function E(tag, css, text, parent) {
    const el = document.createElement(tag);
    if (css) el.style.cssText = css;
    if (text != null) el.textContent = text;
    if (parent) parent.appendChild(el);
    return el;
  }
  // a full-stage layer; centered=true lays its children out in the middle
  function layer(parent, css, centered) {
    const el = E('div', css, null, parent);
    el.classList.add(centered ? 'fx-c' : 'fx-l');
    return el;
  }
  function S(tag, attrs, parent) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, String(value));
    if (parent) parent.appendChild(el);
    return el;
  }
  const isRtl = () => (document.documentElement && document.documentElement.dir) === 'rtl';

  // ---------- the presenter (owner-supplied, owner-cleared photo cutout) ----------
  const PRESENTER_SRC = 'assets/brand/presenter-cutout.png';
  // Preloaded and decoded exactly once at module load. effects-ui.js's playDemo()/drawStill()
  // wipe and rebuild a card's whole stage every loop pass (clearStage() + play()), so every
  // presenter demo creates a fresh <img> element on every pass -- cloning this single, already-
  // decoded node (instead of each call setting its own `.src`) means that rebuild never re-fetches
  // or re-decodes the image, so there is no flash of an empty stage after the first paint.
  // `presenterReady` (exposed below, like `context`/`CANCELLED`) lets the caller await the first
  // decode before the very first play, so that one doesn't flash either.
  const presenterSource = new Image();
  presenterSource.src = PRESENTER_SRC;
  const presenterReady = Promise.resolve(presenterSource.decode ? presenterSource.decode() : null).catch(() => {});
  Object.defineProperty(FxDemos, 'presenterReady', {value: presenterReady, enumerable: false});
  function presenterImage(parent) {
    // Same meet/xMid/YMax semantics the old illustration used: fit entirely inside the box,
    // centered horizontally, anchored to the bottom.
    const img = presenterSource.cloneNode(true);
    img.style.cssText = 'width:100%;height:100%;display:block;object-fit:contain;object-position:bottom';
    img.alt = '';
    img.setAttribute('aria-hidden', 'true');
    if (parent) parent.appendChild(img);
    return img;
  }
  function person(parent, css) {
    const wrap = E('div', 'position:absolute;left:0;right:0;bottom:0;height:88%;' + (css || ''), null, parent);
    presenterImage(wrap);
    return wrap;
  }
  function room(parent) {
    const r = layer(parent, 'background:linear-gradient(180deg,#d8d2c6 0%,#cfc8bb 58%,#9c8f7c 58%,#8a7d6a 100%)');
    E('div', 'position:absolute;top:18%;right:8%;width:28%;height:26%;background:linear-gradient(#7d9bb5,#a9c3d6);border:' + u(5) + ' solid #efe9dd;border-radius:3px', null, r);
    E('div', 'position:absolute;top:20%;left:10%;width:16%;height:36%;background:#3f6b4a;border-radius:40% 40% 8px 8px', null, r);
    return r;
  }
  function scene(parent) { return {r: room(parent), p: person(parent)}; }

  // ============ EFFECTS: After-Effects-style motion graphics ============

  demo('zoomthru', async (s, c) => {
    const a = layer(s, 'background:#07070a', true);
    const t = E('div', font('head', 70) + ';color:var(--text)', I18N.t('fx.demo.zoomthru.word'), a);
    const b = layer(s, 'background:radial-gradient(circle at 50% 40%,#3a1a0c,#07070a);opacity:0', true);
    E('div', font('display', 28) + ';color:var(--ember)', I18N.t('fx.demo.zoomthru.next'), b);
    await c.wait(500);
    c.A(t, [{transform: 'scale(1)', filter: 'blur(0)'}, {transform: 'scale(14)', filter: 'blur(6px)'}], {duration: 700, easing: 'cubic-bezier(.6,0,.9,.4)'});
    await c.wait(420);
    await c.A(b, [{opacity: 0, transform: 'scale(.6)', filter: 'blur(8px)'}, {opacity: 1, transform: 'scale(1)', filter: 'blur(0)'}], {duration: 520, easing: 'cubic-bezier(.1,.6,.2,1)'});
    await c.wait(1200);
  });

  demo('kinetic', async (s, c) => {
    layer(s, 'background:#0f0b14');
    const w = layer(s, 'flex-direction:column;line-height:.95', true);
    const words = I18N.t('fx.demo.kinetic').split(/\s+/).filter(Boolean);
    const key = Math.min(2, words.length - 1);
    const from = isRtl() ? 140 : -140;
    for (const [i, word] of words.entries()) {
      const size = i === key ? 62 : i === words.length - 1 ? 50 : 44;
      const e = E('div', font('head', size) + ';color:' + (i === key ? 'var(--ember)' : 'var(--text)'), word, w);
      c.A(e, [{transform: 'translateX(' + u(from) + ') skewX(-20deg)', filter: 'blur(10px)', opacity: 0},
        {transform: 'translateX(' + u(-from / 17) + ') skewX(4deg)', filter: 'blur(0)', opacity: 1, offset: 0.7},
        {transform: 'none', opacity: 1}], {duration: 460});
      await c.wait(170);
    }
    await c.wait(1500);
  });

  demo('mask', async (s, c) => {
    layer(s, 'background:linear-gradient(160deg,#1a1410,#07070a)');
    const w = layer(s, 'flex-direction:column;gap:' + u(8), true);
    const line = E('div', 'height:3px;width:70%;background:var(--ember);transform:scaleX(0)', null, w);
    const clip = E('div', 'overflow:hidden', null, w);
    const title = E('div', font('display', 34) + ';color:var(--text)', I18N.t('fx.demo.mask.title'), clip);
    const clip2 = E('div', 'overflow:hidden', null, w);
    const sub = E('div', font('body', 15) + ';color:var(--dim)', I18N.t('fx.demo.mask.sub'), clip2);
    await c.wait(300);
    await c.A(line, [{transform: 'scaleX(0)'}, {transform: 'scaleX(1)'}], {duration: 450, easing: 'cubic-bezier(.7,0,.2,1)'});
    c.A(title, [{transform: 'translateY(110%)'}, {transform: 'none'}], {duration: 600, easing: 'cubic-bezier(.2,.9,.2,1)'});
    await c.wait(150);
    await c.A(sub, [{transform: 'translateY(-110%)'}, {transform: 'none'}], {duration: 500});
    await c.wait(1300);
  });

  demo('trim', async (s, c) => {
    layer(s, 'background:#0b0b10');
    const svg = S('svg', {viewBox: '0 0 200 290', width: '100%', height: '100%', style: 'position:absolute;inset:0', 'aria-hidden': 'true'}, s);
    const path = S('path', {d: 'M30 250 C40 190 160 200 150 140 C140 80 50 110 60 50', fill: 'none', stroke: '#ff6b2c', 'stroke-width': 4,
      'stroke-linecap': 'round', pathLength: 1, 'stroke-dasharray': 1, 'stroke-dashoffset': 1}, svg);
    const dot = (cx, cy, hidden) => S('circle', {cx, cy, r: 6, fill: '#ffc77d', opacity: hidden ? 0 : 1, style: 'transform-box:fill-box;transform-origin:center'}, svg);
    dot(30, 250, false);
    const d2 = dot(150, 140, true), d3 = dot(60, 50, true);
    const label = (text, x, y) => E('div', 'position:absolute;left:' + x + '%;top:' + y + '%;' + font('display', 16) + ';color:#fff;opacity:0', text, s);
    const l1 = label(I18N.t('fx.demo.trim.a'), 8, 88), l2 = label(I18N.t('fx.demo.trim.b'), 70, 44), l3 = label(I18N.t('fx.demo.trim.c'), 36, 9);
    const rise = [{opacity: 0, transform: 'translateY(6px)'}, {opacity: 1, transform: 'none'}];
    c.A(l1, [{opacity: 0}, {opacity: 1}], {duration: 300});
    await c.wait(200);
    c.A(path, [{strokeDashoffset: 1}, {strokeDashoffset: 0}], {duration: 1300, easing: 'ease-in-out'});
    await c.wait(650);
    c.A(d2, [{opacity: 0, transform: 'scale(0)'}, {opacity: 1, transform: 'scale(1)'}], {duration: 250});
    c.A(l2, rise, {duration: 300});
    await c.wait(650);
    c.A(d3, [{opacity: 0, transform: 'scale(0)'}, {opacity: 1, transform: 'scale(1)'}], {duration: 250});
    await c.A(l3, rise, {duration: 300});
    await c.wait(1200);
  });

  demo('morph', async (s, c) => {
    layer(s, 'background:#0b0b10');
    const w = layer(s, '', true);
    const shape = E('div', 'width:' + u(40) + ';height:' + u(40) + ';border-radius:999px;background:var(--ember);display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden;color:#07070a;white-space:nowrap;' + font('body', 15) + ';font-weight:800', null, w);
    await c.A(shape, [{transform: 'scale(0)'}, {transform: 'scale(1)'}], {duration: 350, easing: 'cubic-bezier(.2,1.6,.3,1)'});
    await c.A(shape, [{width: u(40)}, {width: u(150)}], {duration: 420, easing: 'cubic-bezier(.7,0,.2,1)'});
    shape.textContent = I18N.t('fx.demo.morph.button');
    await c.wait(600);
    shape.textContent = '';
    await c.A(shape, [{width: u(150), height: u(40), borderRadius: '999px', backgroundColor: '#ff6b2c'},
      {width: u(170), height: u(120), borderRadius: u(18), backgroundColor: '#f5ede5'}], {duration: 500, easing: 'cubic-bezier(.7,0,.2,1)'});
    E('b', 'font-size:' + u(26), '✓', shape);
    E('span', 'font-size:' + u(14), I18N.t('fx.demo.morph.done'), shape);
    await c.wait(1300);
  });

  demo('particles', async (s, c) => {
    layer(s, 'background:radial-gradient(circle at 50% 50%,#1d120c,#07070a)');
    const w = layer(s, '', true);
    const t = E('div', font('head', 64) + ';color:var(--text);opacity:0', I18N.t('fx.demo.particles'), w);
    await c.wait(300);
    c.A(t, [{opacity: 0, transform: 'scale(2)'}, {opacity: 1, transform: 'scale(1)'}], {duration: 300, easing: 'cubic-bezier(.5,0,.75,0)'});
    await c.wait(260);
    if (!c.still) {
      for (let i = 0; i < 34; i++) {
        const angle = Math.random() * Math.PI * 2, dist = 60 + Math.random() * 90, size = 3 + Math.random() * 5;
        const p = E('div', 'position:absolute;left:50%;top:50%;width:' + u(size) + ';height:' + u(size) + ';border-radius:50%;background:' + (i % 3 ? '#ff6b2c' : '#ffc77d'), null, s);
        c.A(p, [{transform: 'translate(-50%,-50%)', opacity: 1},
          {transform: 'translate(calc(-50% + ' + u(Math.cos(angle) * dist) + '),calc(-50% + ' + u(Math.sin(angle) * dist) + ')) scale(.3)', opacity: 0}],
        {duration: 800 + Math.random() * 400, easing: 'cubic-bezier(.1,.8,.3,1)'});
      }
    }
    c.A(t, [{transform: 'scale(1)'}, {transform: 'scale(1.08)'}, {transform: 'scale(1)'}], {duration: 240});
    await c.wait(1600);
  });

  demo('leak', async (s, c) => {
    const a = layer(s, 'background:#14100c', true);
    E('div', font('serif', 34) + ';color:var(--text)', I18N.t('fx.demo.leak'), a);
    const leak = E('div', 'position:absolute;inset:-30%;background:radial-gradient(ellipse at 30% 50%,rgba(255,170,90,.95),rgba(255,107,44,.6) 30%,transparent 60%);mix-blend-mode:screen;opacity:0', null, s);
    if (c.still) { leak.style.opacity = '.85'; return; } // the end frame shows the leak at its peak
    await c.wait(500);
    await c.A(leak, [{opacity: 0, transform: 'translateX(-40%)'}, {opacity: 1, transform: 'translateX(0)', offset: 0.5}, {opacity: 0, transform: 'translateX(40%)'}], {duration: 1100, easing: 'ease-in-out'});
    await c.wait(900);
  });

  demo('flare', async (s, c) => {
    layer(s, 'background:linear-gradient(160deg,#1c1410,#07070a)');
    const w = layer(s, '', true);
    const t = E('div', 'position:relative;overflow:hidden;' + font('display', 38) + ';color:var(--text);padding:0 ' + u(8), I18N.t('fx.demo.flare'), w);
    const shine = E('div', 'position:absolute;top:-30%;bottom:-30%;left:-60%;width:35%;background:linear-gradient(100deg,transparent,rgba(255,236,210,.95),transparent);transform:skewX(-20deg)', null, t);
    await c.A(t, [{opacity: 0, letterSpacing: '.3em'}, {opacity: 1, letterSpacing: '0em'}], {duration: 500});
    if (c.still) { shine.style.left = '40%'; return; }
    await c.A(shine, [{left: '-60%'}, {left: '130%'}], {duration: 650, easing: 'ease-in-out'});
    await c.wait(1200);
  });

  demo('glitch', async (s, c) => {
    const a = layer(s, 'background:#0d0d14', true);
    E('div', font('display', 30) + ';color:#fff', I18N.t('fx.demo.glitch.before'), a);
    const b = layer(s, 'background:#1b0d06;opacity:0', true);
    E('div', font('display', 30) + ';color:var(--ember)', I18N.t('fx.demo.glitch.after'), b);
    await c.wait(700);
    for (let i = 0; i < 8; i++) {
      const y = Math.random() * 80 | 0, h = 6 + Math.random() * 16 | 0, x = (Math.random() * 30 - 15) | 0;
      a.style.clipPath = 'inset(' + y + '% 0 ' + (100 - y - h) + '% 0)';
      a.style.transform = 'translateX(' + u(x) + ')';
      a.style.filter = 'hue-rotate(' + (Math.random() * 180 | 0) + 'deg)';
      b.style.opacity = i > 4 ? '1' : '0';
      await c.wait(60);
    }
    a.style.opacity = '0';
    b.style.opacity = '1';
    await c.wait(1300);
  });

  demo('liquid', async (s, c) => {
    scene(s);
    const blob = E('div', 'position:absolute;left:50%;top:60%;width:' + u(40) + ';height:' + u(40) + ';background:var(--ember);border-radius:46% 54% 60% 40%/50% 42% 58% 50%;transform:translate(-50%,-50%) scale(0)', null, s);
    const next = layer(s, 'opacity:0', true);
    E('div', font('head', 56) + ';color:#07070a', I18N.t('fx.demo.liquid'), next);
    await c.wait(600);
    await c.A(blob, [{transform: 'translate(-50%,-50%) scale(0) rotate(0)'}, {transform: 'translate(-50%,-50%) scale(18) rotate(120deg)'}], {duration: 800, easing: 'cubic-bezier(.6,0,.3,1)'});
    await c.A(next, [{opacity: 0, transform: 'scale(.7)'}, {opacity: 1, transform: 'none'}], {duration: 350, easing: 'cubic-bezier(.2,1.4,.3,1)'});
    await c.wait(1200);
  });

  demo('spinblur', async (s, c) => {
    const {r, p} = scene(s);
    const g = layer(s, 'opacity:0;background:radial-gradient(circle,#2a160c,#07070a)', true);
    E('div', font('display', 30) + ';color:var(--ember)', I18N.t('fx.demo.spinblur'), g);
    await c.wait(700);
    const out = [{transform: 'rotate(0) scale(1)', filter: 'blur(0)'}, {transform: 'rotate(180deg) scale(1.4)', filter: 'blur(10px)'}];
    c.A(r, out, {duration: 380, easing: 'cubic-bezier(.7,0,1,.5)'});
    await c.A(p, out, {duration: 380, easing: 'cubic-bezier(.7,0,1,.5)'});
    await c.A(g, [{opacity: 1, transform: 'rotate(-180deg) scale(1.4)', filter: 'blur(10px)'}, {opacity: 1, transform: 'none', filter: 'blur(0)'}], {duration: 420, easing: 'cubic-bezier(0,.5,.3,1)'});
    await c.wait(1200);
  });

  demo('cascade', async (s, c) => {
    layer(s, 'background:#100c0a');
    const w = layer(s, 'flex-wrap:wrap;gap:2px ' + u(8) + ';padding:0 ' + u(18), true);
    const words = I18N.t('fx.demo.cascade').split(/\s+/).filter(Boolean);
    let key = words.findIndex(word => word.includes('AI'));
    if (key < 0) key = Math.floor(words.length / 2);
    const els = words.map((word, i) => {
      const box = E('div', font('display', 30) + ';color:' + (i === key ? 'var(--ember)' : '#fff'), null, w);
      E('bdi', '', word, box);
      return box;
    });
    els.forEach((el, i) => c.A(el, [{transform: 'translateY(' + u(-60) + ')', opacity: 0}, {transform: 'translateY(' + u(4) + ')', opacity: 1, offset: 0.75}, {transform: 'none', opacity: 1}],
      {duration: 520, delay: i * 110, easing: 'cubic-bezier(.3,0,.2,1)'}));
    await c.wait(520 + (els.length - 1) * 110);
    await c.wait(1400);
  });

  demo('impact', async (s, c) => {
    const {p} = scene(s);
    const ghost = person(s, 'mix-blend-mode:screen;opacity:0;filter:sepia(1) saturate(9) hue-rotate(-50deg)');
    const flash = layer(s, 'background:#fff;opacity:0');
    if (c.still) { ghost.style.opacity = '.45'; ghost.style.transform = 'translateX(' + u(6) + ')'; return; } // end frame: the hit itself
    await c.wait(700);
    c.A(flash, [{opacity: 0.7}, {opacity: 0}], {duration: 200});
    c.A(ghost, [{opacity: 0.6, transform: 'translateX(' + u(6) + ')'}, {opacity: 0, transform: 'none'}], {duration: 350});
    await c.A(p, [{transform: 'translate(0,0) scale(1.08)'}, {transform: 'translate(' + u(-6) + ',' + u(4) + ') scale(1.08)'},
      {transform: 'translate(' + u(5) + ',' + u(-3) + ') scale(1.08)'}, {transform: 'translate(' + u(-2) + ',' + u(2) + ') scale(1.04)'}, {transform: 'none'}], {duration: 380});
    await c.wait(1300);
  });

  demo('pop', async (s, c) => {
    scene(s);
    const stickers = [['🔥', 12, 20], ['+38%', 60, 14], [I18N.t('fx.demo.pop.works'), 8, 58], ['AI', 70, 54]];
    for (const [text, x, y] of stickers) {
      const e = E('div', 'position:absolute;left:' + x + '%;top:' + y + '%;background:#fff;color:#07070a;border-radius:999px;padding:' + u(4) + ' ' + u(10) + ';' + font('body', 15) + ';font-weight:800;box-shadow:0 6px 14px rgba(0,0,0,.3)', null, s);
      E('bdi', '', text, e);
      c.A(e, [{transform: 'scale(0) rotate(-20deg)'}, {transform: 'scale(1.2) rotate(6deg)', offset: 0.6}, {transform: 'scale(1) rotate(0)'}], {duration: 420, easing: 'cubic-bezier(.2,1.4,.3,1)'});
      await c.wait(200);
    }
    await c.wait(1500);
  });

  demo('marker', async (s, c) => {
    layer(s, 'background:#100c0a');
    const w = layer(s, 'padding:0 ' + u(18) + ';' + font('body', 24) + ';font-weight:700;color:#fff;line-height:1.5', true);
    const sentence = E('div', '', null, w);
    sentence.append(document.createTextNode(I18N.t('fx.demo.marker.lead') + ' '));
    const mark = E('span', 'position:relative;display:inline-block', null, sentence);
    const bar = E('span', 'position:absolute;inset:8% ' + u(-4) + ';background:var(--ember);border-radius:4px;transform:scaleX(0);transform-origin:' + (isRtl() ? 'right' : 'left'), null, mark);
    E('span', 'position:relative', I18N.t('fx.demo.marker.word'), mark);
    await c.wait(600);
    await c.A(bar, [{transform: 'scaleX(0)'}, {transform: 'scaleX(1)'}], {duration: 550, easing: 'cubic-bezier(.7,0,.2,1)'});
    await c.wait(1400);
  });

  demo('explode', async (s, c) => {
    layer(s, 'background:#0b0b10');
    const w = layer(s, '', true);
    const letters = [...I18N.t('fx.demo.explode')].map(ch => E('span', 'display:inline-block;' + font('head', 70) + ';color:var(--text)', ch, w));
    if (c.still) return; // the end frame keeps the word whole
    await c.wait(900);
    letters.forEach(l => c.A(l, [{transform: 'none', opacity: 1},
      {transform: 'translate(' + u((Math.random() * 200 - 100) | 0) + ',' + u((Math.random() * 200 - 100) | 0) + ') rotate(' + ((Math.random() * 180 - 90) | 0) + 'deg)', opacity: 0}],
    {duration: 700, easing: 'cubic-bezier(.2,.6,.3,1)'}));
    await c.wait(700);
    await c.wait(500);
  });

  demo('counter', async (s, c) => {
    layer(s, 'background:#0b0b10');
    const chart = E('div', 'position:absolute;inset:16% 12% 14%;display:flex;align-items:flex-end;gap:' + u(10) + ';border-bottom:2px solid #33333a', null, s);
    const bars = [30, 45, 52, 88].map((h, i) => E('div', 'flex:1;height:' + h + '%;background:' + (i === 3 ? 'var(--ember)' : '#2c2c34') + ';border-radius:' + u(6) + ' ' + u(6) + ' 0 0;transform-origin:bottom;transform:scaleY(0)', null, chart));
    const n = E('div', 'position:absolute;top:6%;left:12%;' + font('head', 44) + ';color:var(--ember);direction:ltr', '×1.0', s);
    bars.forEach((b, i) => c.A(b, [{transform: 'scaleY(0)'}, {transform: 'scaleY(1)'}], {duration: 650, delay: i * 120, easing: 'cubic-bezier(.2,1.2,.3,1)'}));
    await c.tween(1100, p => { n.textContent = '×' + (1 + (1 - Math.pow(1 - p, 3)) * 2.9).toFixed(1); });
    await c.wait(1300);
  });

  demo('dotwave', async (s, c) => {
    layer(s, 'background:#07070a');
    const grid = E('div', 'position:absolute;inset:8%;display:grid;grid-template-columns:repeat(9,1fr);gap:' + u(8), null, s);
    const dots = [];
    for (let i = 0; i < 9 * 13; i++) dots.push(E('div', 'width:' + u(6) + ';height:' + u(6) + ';border-radius:50%;background:#3a2a22;justify-self:center', null, grid));
    const t = layer(s, '', true);
    E('div', font('display', 32) + ';color:var(--text);text-shadow:0 0 20px #07070a', I18N.t('fx.demo.dotwave'), t);
    if (c.still) return;
    dots.forEach((d, i) => {
      const x = i % 9, y = (i / 9) | 0;
      c.A(d, [{transform: 'scale(1)', backgroundColor: '#3a2a22'}, {transform: 'scale(1.9)', backgroundColor: '#ff6b2c'}, {transform: 'scale(1)', backgroundColor: '#3a2a22'}],
        {duration: 900, delay: (x + y) * 60, easing: 'ease-in-out'});
    });
    await c.wait(900 + (8 + 12) * 60);
    await c.wait(300);
  });

  // ============ PRESENTER LOOKS ("איך אתם נראים") ============

  demo('popout', async (s, c) => {
    layer(s, 'background:#0f0b0a');
    const win = E('div', 'position:absolute;left:10%;right:10%;top:44%;bottom:6%;border:' + u(3) + ' solid #ff6b2c;border-radius:' + u(14) + ';overflow:hidden', null, s);
    room(win);
    person(win, 'height:150%;bottom:-10%');
    const head = person(s, 'height:75%;bottom:1%;clip-path:inset(0 0 73.3% 0)');
    E('div', 'position:absolute;top:6%;right:0;left:0;text-align:center;' + font('head', 40) + ';color:var(--text)', I18N.t('fx.demo.zoomthru.next'), s);
    await c.A(head, [{transform: 'translateY(' + u(40) + ')', opacity: 0}, {transform: 'none', opacity: 1}], {duration: 550, easing: 'cubic-bezier(.2,1.3,.3,1)'});
    await c.wait(1600);
  });

  demo('green', async (s, c) => {
    room(s);
    const fresh = layer(s, 'background:linear-gradient(160deg,#ff6b2c,#7a1f0a);opacity:0');
    E('div', 'position:absolute;inset:0;background:repeating-linear-gradient(45deg,rgba(255,255,255,.06) 0 10px,transparent 10px 20px)', null, fresh);
    person(s);
    await c.wait(800);
    await c.A(fresh, [{clipPath: 'circle(0% at 50% 40%)', opacity: 1}, {clipPath: 'circle(90% at 50% 40%)', opacity: 1}], {duration: 700, easing: 'cubic-bezier(.7,0,.2,1)'});
    await c.wait(1500);
  });

  demo('behind', async (s, c) => {
    room(s);
    const t = E('div', 'position:absolute;top:10%;left:0;right:0;text-align:center;' + font('head', 110) + ';line-height:1;color:var(--ember)', 'AI', s);
    person(s);
    await c.A(t, [{transform: 'scale(.6)', opacity: 0}, {transform: 'scale(1)', opacity: 1}], {duration: 600, easing: 'cubic-bezier(.2,1.3,.3,1)'});
    await c.wait(1600);
  });

  demo('sticker', async (s, c) => {
    const bg = layer(s, 'background:#ffc77d');
    E('div', 'position:absolute;inset:0;background:radial-gradient(#e8a85a 1.5px,transparent 1.6px);background-size:16px 16px', null, bg);
    const o = u(4);
    const p = person(s, 'height:80%;filter:drop-shadow(0 0 0 #fff) drop-shadow(' + o + ' 0 0 #fff) drop-shadow(-' + o + ' 0 0 #fff) drop-shadow(0 ' + o + ' 0 #fff) drop-shadow(0 -' + o + ' 0 #fff) drop-shadow(0 10px 12px rgba(0,0,0,.35))');
    await c.A(p, [{transform: 'scale(.7) rotate(-14deg)', opacity: 0}, {transform: 'scale(1) rotate(-4deg)', opacity: 1}], {duration: 500, easing: 'cubic-bezier(.2,1.4,.3,1)'});
    await c.wait(1600);
  });

  demo('split', async (s, c) => {
    const top = E('div', 'position:absolute;left:0;right:0;top:0;height:50%;overflow:hidden;background:#f5f2eb', null, s);
    const ui = E('div', 'position:absolute;inset:' + u(10) + ';font-size:' + u(11) + ';color:#222;direction:ltr;text-align:start', null, top);
    E('b', '', 'Claude', ui);
    for (const [width, color] of [['80%', '#e5e1d8'], ['60%', '#e5e1d8'], ['70%', '#ffd9c7']]) {
      E('div', 'margin-top:' + u(7) + ';height:' + u(8) + ';background:' + color + ';border-radius:4px;width:' + width, null, ui);
    }
    const bottom = E('div', 'position:absolute;left:0;right:0;bottom:0;height:50%;overflow:hidden', null, s);
    room(bottom);
    person(bottom, 'height:150%;bottom:-55%');
    E('div', 'position:absolute;left:0;right:0;top:50%;height:' + u(3) + ';background:var(--ember)', null, s);
    await c.A(top, [{transform: 'translateY(-100%)'}, {transform: 'none'}], {duration: 500, easing: 'cubic-bezier(.2,1,.3,1)'});
    await c.wait(1600);
  });

  demo('bubble', async (s, c) => {
    const screen = E('div', 'position:absolute;inset:0;background:#f5f2eb;padding:' + u(14) + ';font-size:' + u(11) + ';color:#222', null, s);
    E('b', '', I18N.t('fx.demo.bubble'), screen);
    const tiles = E('div', 'margin-top:' + u(10) + ';display:grid;grid-template-columns:1fr 1fr;gap:' + u(6), null, screen);
    for (const color of ['#ffd9c7', '#e5e1d8', '#e5e1d8', '#ffd9c7']) E('div', 'height:' + u(50) + ';background:' + color + ';border-radius:' + u(6), null, tiles);
    const bubble = E('div', 'position:absolute;width:42%;aspect-ratio:1;bottom:6%;left:6%;border-radius:50%;overflow:hidden;border:' + u(4) + ' solid #ff6b2c;box-shadow:0 8px 20px rgba(0,0,0,.4)', null, s);
    room(bubble);
    person(bubble, 'height:140%;bottom:-30%');
    await c.A(bubble, [{transform: 'scale(0)'}, {transform: 'scale(1)'}], {duration: 450, easing: 'cubic-bezier(.2,1.4,.3,1)'});
    await c.wait(1600);
  });

  demo('portrait', async (s, c) => {
    const r = room(s);
    person(s);
    await c.wait(700);
    await c.A(r, [{filter: 'blur(0) brightness(1)'}, {filter: 'blur(' + u(7) + ') brightness(.85)'}], {duration: 700});
    if (c.still) return; // the end frame keeps the background blurred
    await c.wait(1300);
    await c.A(r, [{filter: 'blur(' + u(7) + ') brightness(.85)'}, {filter: 'blur(0) brightness(1)'}], {duration: 500});
  });

  demo('doc', async (s, c) => {
    layer(s, 'background:#efe9dd');
    const circle = E('div', 'position:absolute;width:76%;aspect-ratio:1;border-radius:50%;background:var(--ember);left:12%;top:20%', null, s);
    person(s, 'filter:grayscale(1) contrast(1.2)');
    const name = E('div', 'position:absolute;bottom:18%;right:6%;background:#07070a;color:#fff;' + font('display', 18) + ';padding:' + u(3) + ' ' + u(10) + ';transform:rotate(-3deg)', I18N.t('fx.demo.doc.name'), s);
    const role = E('div', 'position:absolute;bottom:10%;right:12%;background:var(--ember);color:#07070a;' + font('body', 13) + ';font-weight:800;padding:' + u(3) + ' ' + u(10) + ';transform:rotate(-3deg)', I18N.t('fx.demo.doc.role'), s);
    c.A(circle, [{transform: 'scale(0)'}, {transform: 'scale(1)'}], {duration: 450, easing: 'cubic-bezier(.2,1.3,.3,1)'});
    await c.wait(300);
    await c.A(name, [{transform: 'rotate(-3deg) translateX(-120%)'}, {transform: 'rotate(-3deg)'}], {duration: 400});
    await c.A(role, [{transform: 'rotate(-3deg) translateX(-140%)'}, {transform: 'rotate(-3deg)'}], {duration: 350});
    await c.wait(1400);
  });

  demo('spot', async (s, c) => {
    room(s);
    const dark = layer(s, 'background:radial-gradient(ellipse 45% 55% at 50% 60%,transparent 0%,rgba(0,0,0,.88) 70%);opacity:0');
    person(s);
    await c.wait(700);
    await c.A(dark, [{opacity: 0}, {opacity: 1}], {duration: 600});
    if (c.still) return; // the end frame keeps the spotlight on
    await c.wait(1500);
    await c.A(dark, [{opacity: 1}, {opacity: 0}], {duration: 400});
  });

  demo('clones', async (s, c) => {
    room(s);
    const spots = [['-30%', '.72', 'grayscale(.2)'], ['30%', '.72', 'hue-rotate(40deg)'], ['0%', '.88', 'none']];
    const people = spots.map(([x, scale, filter]) => person(s, 'transform:translateX(' + x + ') scale(' + scale + ');transform-origin:bottom;filter:' + filter + ';opacity:0'));
    for (const [i, p] of people.entries()) {
      const [x, scale] = spots[i];
      await c.A(p, [{opacity: 0, transform: 'translateX(' + x + ') scale(' + scale + ') translateY(' + u(20) + ')'}, {opacity: 1, transform: 'translateX(' + x + ') scale(' + scale + ')'}], {duration: 380, easing: 'cubic-bezier(.2,1.3,.3,1)'});
      p.style.opacity = '1';
    }
    await c.wait(1500);
  });

  return FxDemos;
})();
