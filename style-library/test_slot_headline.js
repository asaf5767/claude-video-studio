/* Task 5: slot headline (dist/slot-headline.js). Runs the real file in a vm sandbox with a tiny fake DOM,
   a recording element.animate and fake timers; no browser packages needed. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/slot-headline.js'), 'utf8');

function fakeDom() {
  const calls = [];
  const doc = {hidden: false, fonts: null};
  function element(tagName) {
    const el = {
      nodeType: 1, tagName: tagName.toUpperCase(), childNodes: [], attributes: {}, style: {}, className: '', parentNode: null, ownerDocument: doc,
      get isConnected() { return true; },
      get firstChild() { return this.childNodes[0] || null; },
      classList: {add(name) { el.className = (el.className + ' ' + name).trim(); }},
      appendChild(child) { child.parentNode = el; el.childNodes.push(child); return child; },
      setAttribute(name, value) { el.attributes[name] = String(value); },
      getAttribute(name) { return name in el.attributes ? el.attributes[name] : null; },
      get textContent() { return el.childNodes.map(c => c.nodeType === 3 ? c.nodeValue : c.textContent).join(''); },
      set textContent(value) { el.childNodes.forEach(c => { c.parentNode = null; }); el.childNodes = value ? [{nodeType: 3, nodeValue: String(value), parentNode: el}] : []; },
      getBoundingClientRect() { return {width: 40 + el.textContent.length * 10}; },
      getClientRects() { return [{}]; },
      animate(frames, options) { const a = {frames, options, cancel() {}, onfinish: null}; calls.push({el, frames, options, anim: a}); return a; },
    };
    return el;
  }
  doc.createElement = element;
  return {doc, element, calls};
}

function harness({text = 'הסרטון הבא שלכם', reduce = false, build, motion} = {}) {
  const dom = fakeDom();
  const timers = new Map();
  let nextId = 1;
  const add = (fn, ms, repeat) => { const id = nextId++; timers.set(id, {fn, ms, repeat}); return id; };
  const context = {
    window: {matchMedia: query => ({matches: reduce && /reduce/.test(query)})},
    document: dom.doc,
    setTimeout: (fn, ms) => add(fn, ms, false), setInterval: (fn, ms) => add(fn, ms, true),
    clearTimeout: id => timers.delete(id), clearInterval: id => timers.delete(id),
  };
  runInNewContext(source, context);
  const api = context.window.SlotHeadline;
  if (motion) api.setMotion(motion);
  const h1 = dom.element('h1');
  if (build) build(h1, dom); else h1.textContent = text;
  api.mount(h1);
  const runTimeouts = () => { for (const [id, t] of [...timers]) if (!t.repeat) { timers.delete(id); t.fn(); } };
  const tickInterval = () => { for (const t of [...timers.values()]) if (t.repeat) t.fn(); };
  const intervals = () => [...timers.values()].filter(t => t.repeat);
  return {api, h1, dom, timers, runTimeouts, tickInterval, intervals};
}

const reels = h1 => {
  const out = [];
  const walk = node => { if (node.className && /\bslot-reel\b/.test(node.className)) out.push(node); (node.childNodes || []).forEach(walk); };
  walk(h1);
  return out;
};

test('mount splits the headline into one reel per word and keeps the text accessible', () => {
  const h = harness();
  assert.equal(h.h1.getAttribute('aria-label'), 'הסרטון הבא שלכם');
  const inner = h.h1.childNodes[0];
  assert.equal(inner.getAttribute('aria-hidden'), 'true', 'reel copies are hidden from assistive tech');
  assert.equal(h.h1.childNodes.length, 1);
  const words = reels(h.h1);
  assert.equal(words.length, 3);
  assert.equal(words[0].childNodes.length, 5 * 8, 'each reel holds several rotations of the five fonts');
  assert.deepEqual(words[0].childNodes.slice(0, 5).map(row => row.childNodes[0].className), ['slot-f0', 'slot-f1', 'slot-f2', 'slot-f3', 'slot-f4']);
  assert.equal(words[1].childNodes[0].textContent, 'הבא');
  assert.deepEqual(Array.from(h.api.FONTS), ['Secular One', 'Bellefair', 'Karantina 700', 'Heebo 800', 'Suez One']);
});

test('each spin animates every word with the blur keyframes, the slot easing and a 120 ms stagger', () => {
  const h = harness();
  assert.equal(h.dom.calls.length, 0, 'nothing moves before the first spin');
  h.runTimeouts(); // first spin
  const spins = h.dom.calls.filter(c => c.options.duration === 1150);
  assert.equal(spins.length, 3);
  assert.deepEqual(spins.map(c => c.options.delay), [0, 120, 240]);
  for (const c of spins) {
    assert.equal(c.options.easing, 'cubic-bezier(.12,.62,.22,1.12)');
    assert.deepEqual(JSON.parse(JSON.stringify(c.frames.map(f => [f.offset, f.filter]))), [[0, 'blur(0px)'], [0.15, 'blur(3px)'], [0.7, 'blur(1.5px)'], [1, 'blur(0px)']]);
    assert.match(c.frames[3].transform, /^translateY\(-\d+(\.\d+)?em\)$/);
  }
  const widths = h.dom.calls.filter(c => c.options.duration === 450);
  assert.equal(widths.length, 3, 'each word window animates to the landed font width');
  assert.deepEqual(widths.map(c => c.options.delay), [700, 820, 940]);
  assert.equal(widths[0].options.easing, 'cubic-bezier(.3,1.4,.4,1)');
  assert.deepEqual(Array.from(h.api.inspect(h.h1).landed), ['Bellefair', 'Bellefair', 'Bellefair']);
  assert.equal(h.intervals().length, 1);
  assert.equal(h.intervals()[0].ms, 3000);
});

test('after 10 spins every word lands on Secular One and the timer stops', () => {
  const h = harness();
  h.runTimeouts();
  for (let i = 0; i < 20 && h.intervals().length; i++) h.tickInterval();
  const state = h.api.inspect(h.h1);
  assert.equal(state.spins, 10);
  assert.deepEqual(Array.from(state.landed), ['Secular One', 'Secular One', 'Secular One']);
  assert.equal(h.intervals().length, 0, 'interval cleared');
  assert.equal(state.running, false);
  assert.equal(h.dom.calls.filter(c => c.options.duration === 1150).length, 30);
});

test('a hidden tab pauses the spins without using them up', () => {
  const h = harness();
  h.dom.doc.hidden = true;
  h.runTimeouts();
  h.tickInterval();
  assert.equal(h.dom.calls.length, 0);
  assert.equal(h.api.inspect(h.h1).spins, 0);
  h.dom.doc.hidden = false;
  h.tickInterval();
  assert.equal(h.api.inspect(h.h1).spins, 1);
});

test('reduced motion shows the headline in Secular One and never animates', () => {
  const h = harness({reduce: true});
  h.runTimeouts();
  h.tickInterval();
  assert.equal(h.dom.calls.length, 0);
  assert.equal(h.timers.size, 0);
  const words = reels(h.h1);
  assert.equal(words.length, 3);
  for (const reel of words) {
    assert.equal(reel.childNodes.length, 1);
    assert.equal(reel.childNodes[0].childNodes[0].className, 'slot-f0');
  }
  assert.deepEqual(Array.from(h.api.inspect(h.h1).landed), ['Secular One', 'Secular One', 'Secular One']);
  assert.equal(h.h1.getAttribute('aria-label'), 'הסרטון הבא שלכם');
});

test('a <br> starts a new line and <em> words keep an accent', () => {
  const h = harness({build(h1, dom) {
    h1.appendChild({nodeType: 3, nodeValue: 'Bring your material.'});
    h1.appendChild(dom.element('br'));
    const em = dom.element('em'); em.textContent = 'Make it yours.'; h1.appendChild(em);
  }});
  const lines = h.h1.childNodes[0].childNodes;
  assert.equal(lines.length, 2);
  assert.equal(lines[0].childNodes.length, 3);
  assert.match(lines[1].childNodes[0].className, /slot-accent/);
  assert.equal(h.h1.getAttribute('aria-label'), 'Bring your material. Make it yours.');
});

test('re-mounting a live headline keeps its words instead of reading the reel copies', () => {
  const h = harness();
  h.api.mount(h.h1);
  assert.equal(reels(h.h1).length, 3);
  assert.equal(h.h1.getAttribute('aria-label'), 'הסרטון הבא שלכם');
  h.h1.textContent = 'Your next video';
  h.api.mount(h.h1);
  assert.equal(h.h1.getAttribute('aria-label'), 'Your next video');
});

test('motion setting "always" spins even when the system asks for reduced motion', () => {
  const h = harness({reduce: true, motion: 'always'});
  h.runTimeouts();
  assert.equal(h.dom.calls.filter(c => c.options.duration === 1150).length, 3);
  assert.equal(reels(h.h1)[0].childNodes.length, 40);
});

test('motion setting "off" keeps the headline static in Secular One even without reduced motion', () => {
  const h = harness({reduce: false, motion: 'off'});
  h.runTimeouts();
  h.tickInterval();
  assert.equal(h.dom.calls.length, 0);
  assert.equal(h.timers.size, 0);
  assert.deepEqual(Array.from(h.api.inspect(h.h1).landed), ['Secular One', 'Secular One', 'Secular One']);
});

test('changing the motion setting re-mounts live headlines; unknown values are ignored', () => {
  const h = harness({reduce: true});
  assert.equal(h.api.inspect(h.h1).reduce, true);
  h.api.setMotion('always');
  assert.equal(h.api.inspect(h.h1).reduce, false);
  assert.equal(h.api.inspect(h.h1).running, true);
  assert.equal(h.h1.getAttribute('aria-label'), 'הסרטון הבא שלכם', 'words survive the re-mount');
  h.api.setMotion('sideways');
  assert.equal(h.api.motion(), 'always');
  h.api.setMotion('off');
  assert.equal(h.api.inspect(h.h1).reduce, true);
  assert.equal(h.api.inspect(h.h1).running, false);
});
