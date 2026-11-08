/* Task 19: the first-run welcome card (dist/welcome-ui.js) shows once on the videos home page, under the
   home heading, and its dismissal is saved through the guarded /ui-welcome request. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const source = readFileSync(join(__dirname, 'dist/welcome-ui.js'), 'utf8');
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise(resolve => setImmediate(resolve)); };

// A tiny DOM: just enough element behaviour for the card (append/after/remove/querySelector by class).
class Node {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.parent = null; this.attributes = {}; this.listeners = {};
    this.className = ''; this.textContent = ''; this.id = ''; this.type = ''; this.focused = false; this.dataset = {};
    const self = this;
    this.classList = {add(name) { self.className = (self.className + ' ' + name).trim(); }, contains(name) { return self.className.split(' ').includes(name); }};
  }
  append(...nodes) { nodes.forEach(n => { n.parent = this; this.children.push(n); }); }
  after(node) { const list = this.parent.children; node.parent = this.parent; list.splice(list.indexOf(this) + 1, 0, node); }
  remove() { if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  focus() { this.focused = true; }
  all() { return this.children.flatMap(c => [c, ...c.all()]); }
  querySelector(selector) {
    if (selector === '.home-heading [data-new-video]') return this.all().find(n => n.dataset.newVideo !== undefined && n.parent && n.parent.className === 'home-heading') || null;
    const cls = selector.replace(/^\./, '');
    return this.all().find(n => n.className.split(' ').includes(cls)) || null;
  }
}

function harness({seen = false, failGet = false, failPost = false, heading = true} = {}) {
  const requests = [];
  const page = new Node('section');
  if (heading) {
    const head = new Node('section'); head.className = 'home-heading';
    const start = new Node('button'); start.dataset.newVideo = '';
    head.append(start); page.append(head);
  }
  page.append(Object.assign(new Node('section'), {className: 'project-list'}));
  const toast = {textContent: '', hidden: true};
  const document = {
    querySelector: sel => sel === '#projects-page' ? page : sel === '#toast' ? toast : null,
    createElement: tag => new Node(tag),
  };
  const fetch = async (url, init = {}) => {
    requests.push({url, init});
    if (init.method === 'POST') return failPost ? {ok: false, json: async () => ({})} : {ok: true, json: async () => JSON.parse(init.body)};
    if (failGet) throw new TypeError('offline');
    return {ok: true, json: async () => ({welcome_seen: seen})};
  };
  const window = {};
  runInNewContext(source, {window, document, fetch, I18N: {t: key => key, ready: Promise.resolve()}, setTimeout: () => 0, JSON, String, Error});
  const card = () => page.querySelector('.first-run-welcome');
  return {window, page, toast, requests, card};
}

test('shows the 3-step welcome under the home heading when it has not been seen', async () => {
  const h = harness();
  await h.window.WelcomeCard.ready;
  const card = h.card();
  assert.ok(card, 'the card is shown');
  assert.equal(h.page.children.indexOf(card), 1, 'right after .home-heading');
  assert.equal(card.tagName, 'ASIDE');
  const title = card.children.find(n => n.tagName === 'H2');
  assert.equal(title.textContent, 'welcome.title');
  assert.equal(card.attributes['aria-labelledby'], title.id);
  const steps = card.children.find(n => n.tagName === 'OL').children;
  assert.equal(steps.length, 3);
  assert.deepEqual(steps.map(li => li.children[1].textContent), ['welcome.step1.title', 'welcome.step2.title', 'welcome.step3.title']);
  assert.deepEqual(steps.map(li => li.children[2].textContent), ['welcome.step1.body', 'welcome.step2.body', 'welcome.step3.body']);
  const button = card.children.find(n => n.tagName === 'BUTTON');
  assert.equal(button.textContent, 'welcome.dismiss');
  assert.equal(button.type, 'button');
  assert.equal(h.requests[0].url, '/ui-welcome');
});

test('stays hidden once seen, and when the setting cannot be read', async () => {
  for (const options of [{seen: true}, {failGet: true}]) {
    const h = harness(options);
    await h.window.WelcomeCard.ready;
    h.window.WelcomeCard.render();
    assert.equal(h.card(), null, JSON.stringify(options));
  }
});

test('waits for the home heading and never shows twice', async () => {
  const h = harness({heading: false});
  await h.window.WelcomeCard.ready;
  assert.equal(h.card(), null, 'no heading yet (projects still loading)');
  const head = new Node('section'); head.className = 'home-heading'; h.page.children.unshift(head); head.parent = h.page;
  h.window.WelcomeCard.render();
  h.window.WelcomeCard.render();
  assert.equal(h.page.all().filter(n => n.className.includes('first-run-welcome')).length, 1);
});

test('the entrance animation class is only on the first render of the page', async () => {
  const h = harness();
  await h.window.WelcomeCard.ready;
  assert.ok(h.card().classList.contains('is-entering'));
  h.card().remove();
  h.window.WelcomeCard.render(); // home() redraws on refresh / language change
  assert.ok(h.card());
  assert.ok(!h.card().classList.contains('is-entering'));
});

test('dismissing removes the card, saves welcome_seen with the guarded request and focuses New video', async () => {
  const h = harness();
  await h.window.WelcomeCard.ready;
  const button = h.card().children.find(n => n.tagName === 'BUTTON');
  await button.listeners.click();
  assert.equal(h.card(), null);
  const post = h.requests.find(r => r.init.method === 'POST');
  assert.equal(post.url, '/ui-welcome');
  assert.equal(post.init.headers['X-Studio-Action'], 'ui-welcome');
  assert.equal(post.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(post.init.body), {welcome_seen: true});
  assert.ok(h.page.querySelector('.home-heading [data-new-video]').focused);
  h.window.WelcomeCard.render();
  assert.equal(h.card(), null, 'a later home() redraw does not bring it back');
  assert.equal(h.toast.hidden, true);
});

test('a failed save still hides it for this visit and says so', async () => {
  const h = harness({failPost: true});
  await h.window.WelcomeCard.ready;
  await h.window.WelcomeCard.dismiss();
  await flush();
  assert.equal(h.card(), null);
  assert.equal(h.toast.textContent, 'welcome.error');
  assert.equal(h.toast.hidden, false);
});

test('home() asks for the card on every redraw and index.html loads the module', () => {
  const studio = readFileSync(join(__dirname, 'dist/studio.js'), 'utf8');
  assert.match(studio, /function home\(\)\{[\s\S]*?window\.WelcomeCard\?\.render\?\.\(\);[\s\S]*?\n \}/);
  const html = readFileSync(join(__dirname, 'dist/index.html'), 'utf8');
  assert.match(html, /<script src="welcome-ui\.js" defer><\/script>/);
});

test('the card copy exists in both languages with the agreed wording', () => {
  const he = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/he.json'), 'utf8'));
  const en = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));
  assert.equal(he['welcome.title'], 'סרטון ראשון ב-3 צעדים');
  assert.equal(en['welcome.title'], 'Your first video in 3 steps');
  assert.equal(he['welcome.dismiss'], 'יאללה, מתחילים');
  assert.equal(en['welcome.dismiss'], 'Let’s go');
  assert.equal(he['welcome.step3.title'], 'שליחה לקלוד');
});

test('the card CSS respects the Motion setting', () => {
  const css = readFileSync(join(__dirname, 'dist/theme.css'), 'utf8');
  assert.match(css, /html\[data-motion="off"\] \.first-run-welcome\.is-entering\{animation:none\}/);
  assert.match(css, /prefers-reduced-motion:reduce\)\{html:not\(\[data-motion="always"\]\) \.first-run-welcome\.is-entering\{animation:none\}/);
});
