/* Task 5 fix round 1: the footer "תנועה / Motion" control (dist/motion-setting.js) loads and saves the motion
   setting through /ui-motion and hands it to SlotHeadline. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/motion-setting.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function harness({saved = 'auto', failPost = false} = {}) {
  const requests = [], applied = [];
  const select = {value: 'auto', disabled: false, listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; }};
  const toast = {textContent: '', hidden: true};
  const document = {querySelector: sel => sel === '#motion-setting' ? select : sel === '#toast' ? toast : null};
  const fetch = async (url, init = {}) => {
    requests.push({url, init});
    if (init.method === 'POST') return failPost ? {ok: false, json: async () => ({})} : {ok: true, json: async () => JSON.parse(init.body)};
    return {ok: true, json: async () => ({motion: saved})};
  };
  const window = {SlotHeadline: {setMotion: value => { applied.push(value); return value; }}};
  runInNewContext(source, {window, document, fetch, I18N: {t: key => key}, setTimeout: () => 0, JSON});
  return {select, toast, requests, applied, window};
}

test('loads the saved motion setting into the control and the headline', async () => {
  const h = harness({saved: 'always'});
  await flush();
  assert.equal(h.requests[0].url, '/ui-motion');
  assert.equal(h.select.value, 'always');
  assert.deepEqual(h.applied, ['always']);
});

test('changing the control saves it with the guarded request and applies it', async () => {
  const h = harness();
  await flush();
  h.select.value = 'off';
  await h.select.listeners.change();
  const post = h.requests.find(r => r.init.method === 'POST');
  assert.equal(post.url, '/ui-motion');
  assert.equal(post.init.headers['X-Studio-Action'], 'ui-motion');
  assert.equal(post.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(post.init.body), {motion: 'off'});
  assert.equal(h.applied.at(-1), 'off');
  assert.equal(h.select.disabled, false);
});

test('a failed save puts the previous value back and tells the user', async () => {
  const h = harness({failPost: true});
  await flush();
  h.select.value = 'always';
  await h.select.listeners.change();
  assert.equal(h.select.value, 'auto');
  assert.deepEqual(h.applied, []);
  assert.equal(h.toast.textContent, 'motion.error');
  assert.equal(h.toast.hidden, false);
});

test('the effects board gets the motion setting too (Task 12: live demos respect it)', async () => {
  const h = harness({saved: 'off'});
  const board = [];
  h.window.EffectsBoard = {setMotion: value => board.push(value)};
  await flush();
  assert.deepEqual(board, ['off'], 'the saved setting reaches the board on load');
  h.select.value = 'always';
  await h.select.listeners.change();
  assert.deepEqual(board, ['off', 'always']);
});

test('the headline is not re-mounted when the value did not change (initial auto load, failed save)', async () => {
  const h = harness({saved: 'auto', failPost: true});
  await flush();
  assert.deepEqual(h.applied, [], 'loading auto over the default auto does nothing');
  h.select.value = 'off';
  await h.select.listeners.change();
  assert.deepEqual(h.applied, [], 'reverting a failed save to the same value does not re-mount');
  assert.equal(h.select.value, 'auto');
});
