/* Task 12: dist/fx-demos.js -- the registry of live demos behind every effects-board card.
   Run with: node --test style-library/test_fx_demos.js (vm sandbox, tiny fake DOM). */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/fx-demos.js'), 'utf8');
const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));
const catalogIds = [
  ...JSON.parse(readFileSync(join(__dirname, '..', 'effects', 'effects.json'), 'utf8')),
  ...JSON.parse(readFileSync(join(__dirname, '..', 'looks', 'presenter.json'), 'utf8')),
].map(item => item.demo);

function node(tag) {
  return {
    tagName: String(tag).toUpperCase(), children: [], style: {}, attributes: {}, textContent: '', animations: [],
    classList: {add() {}, remove() {}, toggle() {}},
    appendChild(child) { this.children.push(child); return child; },
    append(...nodes) { nodes.forEach(n => this.children.push(n)); },
    setAttribute(name, value) { this.attributes[name] = value; },
    animate(keyframes, timing) {
      const animation = {keyframes, timing, finished: false, finish() { this.finished = true; }, pause() {}, cancel() {}};
      this.animations.push(animation);
      return animation;
    },
  };
}

// A fake `Image` constructor: fx-demos.js preloads exactly one at module load (`new Image()`)
// and clones it (`.cloneNode()`) for every presenter element, instead of constructing a fresh
// Image (and so re-fetching) on every demo/loop pass. `Image.instances` records every `new
// Image()` call so a test can assert only one was ever made; each instance's decode() only
// resolves when `_resolveDecode()` is called, or immediately if `load()`'s `autoDecode` (the
// default) is left on.
function makeImage() {
  const instances = [];
  function Image() {
    const el = node('img');
    el.src = '';
    el.alt = '';
    let resolveDecode;
    const decoded = new Promise(resolve => { resolveDecode = resolve; });
    el.decode = () => decoded;
    el._resolveDecode = resolveDecode;
    el.cloneNode = () => {
      const clone = node('img');
      clone.src = el.src;
      clone.alt = el.alt;
      return clone;
    };
    instances.push(el);
    return el;
  }
  Image.instances = instances;
  return Image;
}

function load({timers, autoDecode = true} = {}) {
  const missingKeys = [];
  const Image = makeImage();
  const context = {
    window: {},
    document: {
      createElement: node, createElementNS: (_ns, tag) => node(tag), createTextNode: text => ({text}),
      documentElement: {dir: 'rtl'},
    },
    I18N: {t: key => { if (!(key in he)) missingKeys.push(key); return he[key] ?? key; }},
    setTimeout: timers ? timers.set : (fn => { fn(); return 0; }),
    Image, Math, Promise, Object, Array, String,
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  if (autoDecode) Image.instances.forEach(img => img._resolveDecode());
  return {FxDemos: context.window.FxDemos, missingKeys, Image};
}

function count(root) { return 1 + root.children.reduce((n, c) => n + (c.children ? count(c) : 0), 0); }

test('the registry holds exactly the demos the two catalogs name, each a function', () => {
  const {FxDemos} = load();
  assert.deepEqual([...Object.keys(FxDemos)].sort(), [...catalogIds].sort());
  for (const id of catalogIds) assert.equal(typeof FxDemos[id], 'function', id);
  assert.equal(typeof FxDemos.context, 'function');
});

test('every demo draws its end frame in still mode without timers, using only known i18n keys', async () => {
  const {FxDemos, missingKeys} = load({timers: {set: () => { throw new Error('still mode must not wait'); }}});
  for (const id of catalogIds) {
    const stage = node('div');
    await FxDemos[id](stage, FxDemos.context({still: true}));
    assert.ok(count(stage) > 2, id + ' drew nothing');
    const all = [];
    (function walk(n) { all.push(...(n.animations || [])); (n.children || []).forEach(c => c.children && walk(c)); })(stage);
    assert.ok(all.every(a => a.finished), id + ': an animation was left running in still mode');
    assert.ok(all.every(a => a.timing.fill === 'both'), id + ': animations hold their end state');
  }
  assert.deepEqual(missingKeys, []);
});

test('a live demo waits on timers (duration + delay) and stops when its ctx is cancelled', async () => {
  const pending = [];
  const {FxDemos} = load({timers: {set: (fn, ms) => { pending.push({fn, ms}); return pending.length; }}});
  const ctx = FxDemos.context();
  const stage = node('div');
  const run = FxDemos.mask(stage, ctx);
  assert.equal(pending.length, 1);
  assert.equal(pending[0].ms, 300);
  pending.shift().fn();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(pending[0].ms, 450, 'the line animation is awaited by a 450 ms timer');
  ctx.cancel();
  pending.shift().fn();
  await assert.rejects(run, err => err === FxDemos.CANCELLED);
});

test('the presenter photo is an <img> pointing at the shipped cutout, hidden from the accessibility tree', async () => {
  const {FxDemos} = load();
  const stage = node('div');
  await FxDemos.portrait(stage, FxDemos.context({still: true}));
  const images = [];
  (function walk(n) { if (n.tagName === 'IMG') images.push(n); (n.children || []).forEach(walk); })(stage);
  assert.equal(images.length, 1, 'exactly one presenter image in this demo');
  assert.equal(images[0].src, 'assets/brand/presenter-cutout.png');
  assert.equal(images[0].alt, '');
  assert.equal(images[0].attributes['aria-hidden'], 'true');
});

test('the presenter image is preloaded once and FxDemos.presenterReady waits for its decode', async () => {
  const {FxDemos, Image} = load({autoDecode: false});
  assert.equal(Image.instances.length, 1, 'exactly one Image() is constructed at module load');
  assert.equal(Image.instances[0].src, 'assets/brand/presenter-cutout.png');
  let settled = false;
  FxDemos.presenterReady.then(() => { settled = true; });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(settled, false, 'presenterReady must not resolve before the image finishes decoding');
  Image.instances[0]._resolveDecode();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(settled, true, 'presenterReady resolves once decode() does');
});

test('replaying presenter demos never constructs a new Image (no repeat network request per loop pass)', async () => {
  const {FxDemos, Image} = load();
  for (let i = 0; i < 3; i++) await FxDemos.portrait(node('div'), FxDemos.context({still: true}));
  await FxDemos.green(node('div'), FxDemos.context({still: true}));
  await FxDemos.sticker(node('div'), FxDemos.context({still: true}));
  assert.equal(Image.instances.length, 1, 'only the one preloaded Image is ever constructed; every presenter element is a clone of it');
});

test('cancelling a demo leaves no unhandled rejection from its un-awaited animations', async () => {
  const unhandled = [];
  const onUnhandled = reason => unhandled.push(reason);
  process.on('unhandledRejection', onUnhandled);
  try {
    const pending = [];
    const {FxDemos} = load({timers: {set: (fn, ms) => { pending.push({fn, ms}); return pending.length; }}});
    for (const id of ['zoomthru', 'kinetic', 'particles', 'counter', 'dotwave']) {
      const ctx = FxDemos.context();
      const run = FxDemos[id](node('div'), ctx);
      run.catch(() => {}); // the board's loop handles the awaited chain
      for (let i = 0; i < 3 && pending.length; i++) { pending.shift().fn(); await new Promise(r => setImmediate(r)); }
      ctx.cancel();
      while (pending.length) pending.shift().fn();
      for (let i = 0; i < 5; i++) await new Promise(r => setImmediate(r));
    }
    await new Promise(r => setTimeout(r, 20));
    assert.deepEqual(unhandled, []);
  } finally {
    process.off('unhandledRejection', onUnhandled);
  }
});
