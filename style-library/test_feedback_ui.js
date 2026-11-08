// Run with: node --test style-library/test_feedback_ui.js (no browser or packages needed).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = readFileSync(join(__dirname, 'dist/feedback-ui.js'), 'utf8');
// Task 4: feedback-ui.js now calls I18N.t(key, vars) for UI copy. This sandboxed context
// doesn't load the real i18n.js, so it gets a stub that looks up the same strings a
// Hebrew-first page would show in English (en.json), with the same `{name}`
// interpolation i18n.js itself implements (same approach as test_studio_ui.js's own
// i18nStub()).
function i18nStub() {
  const en = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));
  return {ready: Promise.resolve(), lang: () => 'en', server: message => message, t(key, vars) { const value = en[key] ?? key; if (!vars) return value; return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value); }};
}
const project = {id: 'demo', title: 'Demo project'};
const edit = {id: 'edit-v02', label: 'Full edit', version: 'V02', type: 'video'};
const board = {id: 'board-v01', label: 'Storyboard', version: 'V01', type: 'board', frames: [{}, {}]};
const notes = [
  {id: 'current-a', artifact_id: edit.id, label: 'Full edit', version: 'V02', status: 'open', time: 0, frame: null, text: 'Current first note'},
  {id: 'current-b', artifact_id: edit.id, label: 'Full edit', version: 'V02', status: 'open', time: null, frame: null, text: 'Current second note'},
  {id: 'older', artifact_id: 'edit-v01', label: 'First edit', version: 'V01', status: 'open', time: 2, frame: null, text: 'Older note'},
  {id: 'applied', artifact_id: edit.id, label: 'Full edit', version: 'V02', status: 'applied', time: null, frame: null, text: 'Already applied'}
];
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness({clipboardFails = false, saveFails = false, linkFails = false, changeFails = false} = {}) {
  const elements = new Map();
  const node = selector => {
    if (!elements.has(selector)) elements.set(selector, {value: '', textContent: '', isConnected: true, dataset: {},
      classList: {add() {}}, focus() {}, select() {}, append() {}, showModal() { this.open = true; }, close() { this.open = false; }, querySelector: node});
    return elements.get(selector);
  };
  let html = '', click;
  Object.defineProperty(node('#feedback-panel'), 'innerHTML', {get: () => html, set(value) {
    html = value;
    const text = /<textarea[^>]*>([\s\S]*?)<\/textarea>/.exec(value)?.[1] || '';
    node('#feedback-text').value = text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
  }});
  const video = node('#project-artifact video'); video.currentTime = 0; video.pause = () => { video.paused = true; };
  const state = {notes: structuredClone(notes).map(n => ({...n, revision: n.id + '-revision', content_revision: n.id + '-content'})), copies: [], requests: [], links: new Map(), node, get html() { return html; }};
  const context = {window: {}, URL, URLSearchParams, crypto: webcrypto, esc: escape, notify() {}, I18N: i18nStub(),
    location: {href: 'http://127.0.0.1:4870/#project=demo', hash: '#project=demo'},
    document: {querySelector: node, createElement: () => node(Symbol()), addEventListener: (type, listener) => { if (type === 'click') click = listener; }},
    navigator: {clipboard: {writeText: async text => { if (clipboardFails) throw Error('Unavailable'); state.copies.push(text); }}},
    fetch: async (url, options = {}) => {
      if (url === '/feedback-link') {
        if (linkFails) return {ok: false, status: 409, json: async () => ({error: 'The saved notes changed. Reopen and review them.'})};
        const body = JSON.parse(options.body), id = String(state.links.size + 1).padStart(24, '0');
        const record = {...body, id, artifact_ids: [...new Set(state.notes.filter(n => body.note_ids.includes(n.id)).map(n => n.artifact_id))]};
        state.links.set(id, record); return {ok: true, json: async () => record};
      }
      if (url === '/feedback-note') {
        const body = JSON.parse(options.body); state.requests.push(body);
        if (changeFails) return {ok: false, status: 409, json: async () => ({error: 'This note changed in another window. Your draft is preserved.'})};
        const n = state.notes.find(n => n.id === body.note_id);
        n.history = [...(n.history || []), {action: body.action, at: '2026-10-31T12:00:00Z', before: {...n, history: undefined}}];
        if (body.action === 'edit') { n.text = body.text; n.updated_at = '2026-10-31T12:00:00Z'; }
        if (body.action === 'delete') n.deleted_at = '2026-10-31T12:00:00Z';
        if (body.action === 'restore') delete n.deleted_at;
        n.revision += '-changed';
      } else if (options.method === 'POST') {
        const body = JSON.parse(options.body); state.requests.push(body);
        if (saveFails) return {ok: false, status: 409, json: async () => ({error: 'This version changed. Refresh before saving.'})};
        state.notes.push({id: body.request_id, artifact_id: body.artifact_id, version: 'V02', label: 'Full edit', status: 'open', time: body.time, frame: body.frame, text: body.text});
      }
      return {ok: true, json: async () => ({project_id: project.id, contexts: {[edit.id]: 'revision', [board.id]: 'board-revision'}, notes: state.notes})};
    }};
  runInNewContext(source, context);
  state.api = context.window.ProjectFeedback;
  state.click = async (selector, dataset = {}) => { click({target: {closest: candidate => candidate === selector ? {...node(selector), dataset} : null}}); await flush(); };
  state.selection = text => state.links.get(new URL((text || state.copies.at(-1)).split('\n').at(-1)).hash.split('feedback=')[1]);
  return state;
}

test('current-version copy contains exact open-note IDs; all-project scope requires its own action', async () => {
  const h = harness(); await h.api.render(project, edit);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'});
  assert.deepEqual(h.selection(), {project_id: 'demo', artifact_id: edit.id, artifact_ids: [edit.id], note_ids: ['current-a', 'current-b'], note_revisions: {'current-a': 'current-a-content', 'current-b': 'current-b-content'}, id: '000000000000000000000001'});
  assert.match(h.copies[0], /artifact=edit-v02/);
  assert.match(h.copies[0], /^Please use my 2 saved feedback notes/);
  assert.doesNotMatch(h.copies[0], /Apply only|Saved notes:|Feedback selection:|review-feedback\.json/);
  assert.doesNotMatch(h.copies[0], /Current first note|Older note|Already applied/);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'all'});
  assert.deepEqual(h.selection().note_ids, ['current-a', 'current-b', 'older']);
  assert.match(h.copies[1], /across project versions/);
});

test('a storyboard copy stays scoped to its version, including notes on other scenes', async () => {
  const h = harness(); h.notes.push({id: 'scene-b', artifact_id: board.id, status: 'open', frame: 2, time: null, text: 'Scene two note'});
  await h.api.render(project, board, 0);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'});
  assert.deepEqual(h.selection().note_ids, ['scene-b']);
  assert.deepEqual(h.selection().artifact_ids, [board.id]);
});

test('capturing zero seconds shows an attachment and survives navigation; removal keeps the draft', async () => {
  const h = harness(); await h.api.render(project, edit);
  h.node('#feedback-text').value = 'Keep this draft'; h.api.moment();
  assert.match(h.html, /Note time: <strong>0:00\.00/);
  assert.equal(h.node('#project-artifact video').paused, true);
  assert.equal(h.node('#feedback-text').value, 'Keep this draft');
  await h.api.render(project, board, 1); await h.api.render(project, edit);
  assert.match(h.html, /Note time: <strong>0:00\.00/);
  await h.click('[data-feedback-remove-moment]');
  assert.doesNotMatch(h.html, /Note time: <strong>/);
  assert.equal(h.node('#feedback-text').value, 'Keep this draft');
});

test('saving sends the attached time and reveals a copy action for the saved note', async () => {
  const h = harness(); h.notes.length = 0; await h.api.render(project, edit);
  h.node('#project-artifact video').currentTime = 1.25; h.api.moment();
  h.node('#feedback-text').value = 'New note'; await h.click('[data-feedback-save]');
  assert.equal(h.requests[0].time, 1.25); assert.equal(h.requests[0].artifact_id, edit.id);
  assert.match(h.node('#feedback-status').textContent, /Feedback saved/);
  assert.match(h.html, /1 open note · V02/);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'});
  assert.deepEqual(h.selection().note_ids, [h.requests[0].request_id]);
});

test('a stale-save rejection retains the draft and attached moment', async () => {
  const h = harness({saveFails: true}); await h.api.render(project, edit);
  h.node('#project-artifact video').currentTime = 3.5; h.api.moment();
  h.node('#feedback-text').value = 'Preserve me'; await h.click('[data-feedback-save]');
  assert.equal(h.node('#feedback-text').value, 'Preserve me');
  assert.match(h.html, /Note time: <strong>0:03\.50/);
  assert.equal(h.node('[data-feedback-save]').disabled, true);
});

test('unavailable clipboard exposes the same exact-note request for manual copying', async () => {
  const h = harness({clipboardFails: true}); await h.api.render(project, edit);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'});
  assert.equal(h.node('#feedback-copy-dialog').open, true);
  const selection = h.selection(h.node('#feedback-copy-text').value);
  assert.deepEqual(selection.note_ids, ['current-a', 'current-b']);
});


test('Add timestamp replaces the time without a separate Change action and preserves the note text', async () => {
  const h = harness(); await h.api.render(project, edit);
  h.node('#feedback-text').value = 'Keep this note'; h.node('#project-artifact video').currentTime = 1; h.api.moment();
  h.node('#project-artifact video').currentTime = 2.5; h.api.moment();
  assert.match(h.html, /Note time: <strong>0:02\.50/);
  assert.match(h.html, />Add timestamp<\/button>/);
  assert.doesNotMatch(h.html, />Change<|Moment attached|Attach current moment/);
  assert.equal(h.node('#feedback-text').value, 'Keep this note');
});

test('a stale compact-link request does not copy or broaden the selection', async () => {
  const h = harness({linkFails: true}); await h.api.render(project, edit);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'});
  assert.equal(h.copies.length, 0);
  assert.equal(h.links.size, 0);
  assert.match(h.node('.feedback-copy-status').textContent, /saved notes changed/);
});


test('applied historical feedback remains visible, but copies contain only open notes', async () => {
  const h = harness(); h.notes.find(n => n.id === 'applied').applied_in = {version: 'V03'};
  await h.api.render(project, edit);
  assert.match(h.html, /Already applied/); assert.match(h.html, /Applied in V03/);
  assert.match(h.html, /Saved on this version \(3\)/);
  await h.click('[data-feedback-list]');
  assert.match(h.node('.saved-feedback-list').innerHTML, /Older note/);
  assert.match(h.node('.saved-feedback-list').innerHTML, /Already applied/);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'});
  assert.deepEqual(h.selection().note_ids, ['current-a', 'current-b']);
});

test('notes sort by newest save without changing stored order', async () => {
  const h = harness(); h.notes[0].created_at = '2026-10-30T10:00:00Z'; h.notes[1].created_at = '2026-10-31T10:00:00Z';
  await h.api.render(project, edit);
  assert.ok(h.html.indexOf('Current second note') < h.html.indexOf('Current first note'));
  assert.equal(h.notes[0].id, 'current-a');
});

test('inline editing keeps note identity and application, and cancel does not write', async () => {
  const h = harness(); await h.api.render(project, edit);
  await h.click('[data-feedback-edit]', {feedbackEdit: 'applied', noteScope: 'version'});
  h.node('[data-feedback-edit-text]').value = 'Clearer historical note';
  await h.click('[data-feedback-change]', {feedbackChange: 'edit', noteId: 'applied'});
  assert.equal(h.requests[0].revision, 'applied-revision');
  assert.equal(h.notes.find(n => n.id === 'applied').status, 'applied');
  assert.match(h.html, /Clearer historical note/); assert.match(h.html, /Before editing/); assert.match(h.html, /Already applied/);
  await h.click('[data-feedback-edit]', {feedbackEdit: 'current-a', noteScope: 'version'});
  await h.click('[data-feedback-cancel]'); assert.equal(h.requests.length, 1);
});

test('deletion hides notes from copy, Undo restores, and deleted notes remain recoverable', async () => {
  const h = harness(); await h.api.render(project, edit);
  await h.click('[data-feedback-change]', {feedbackChange: 'delete', noteId: 'current-a'});
  assert.doesNotMatch(h.html, /Current first note/); assert.match(h.html, />Undo</);
  await h.click('[data-feedback-copy]', {feedbackCopy: 'version'}); assert.deepEqual(h.selection().note_ids, ['current-b']);
  await h.click('[data-feedback-list]'); assert.match(h.node('.saved-feedback-list').innerHTML, /Deleted notes \(1\)/);
  await h.click('[data-feedback-change]', {feedbackChange: 'restore', noteId: 'current-a'});
  assert.match(h.html, /Current first note/); assert.equal(h.notes[0].deleted_at, undefined);
});

test('a stale edit preserves its text and never silently rebases or applies it', async () => {
  const h = harness({changeFails: true}); await h.api.render(project, edit);
  await h.click('[data-feedback-edit]', {feedbackEdit: 'current-a', noteScope: 'version'});
  h.node('[data-feedback-edit-text]').value = 'My unsaved correction';
  await h.click('[data-feedback-change]', {feedbackChange: 'edit', noteId: 'current-a'});
  assert.match(h.html, /My unsaved correction/); assert.match(h.html, /another window/);
  assert.equal(h.notes[0].text, 'Current first note');
});


test('unsaved corrections survive switching notes and cancel removes only that correction', async () => {
  const h = harness(); await h.api.render(project, edit);
  await h.click('[data-feedback-edit]', {feedbackEdit: 'current-a', noteScope: 'version'});
  h.node('[data-feedback-edit-text]').value = 'My first unsaved correction';
  await h.click('[data-feedback-edit]', {feedbackEdit: 'current-b', noteScope: 'version'});
  h.node('[data-feedback-edit-text]').value = 'My second unsaved correction';
  await h.click('[data-feedback-cancel]');
  await h.click('[data-feedback-edit]', {feedbackEdit: 'current-a', noteScope: 'version'});
  assert.match(h.html, /My first unsaved correction/); assert.equal(h.requests.length, 0);
});

test('reading position is retained per version and a newly saved note is revealed at the top', async () => {
  const h = harness(); await h.api.render(project, edit);
  h.node('.feedback-note-list').scrollTop = 180;
  await h.api.render(project, board, 1);
  assert.equal(h.node('.feedback-note-list').scrollTop, 0);
  await h.api.render(project, edit);
  assert.equal(h.node('.feedback-note-list').scrollTop, 180);
  h.node('#feedback-text').value = 'The newest saved feedback';
  await h.click('[data-feedback-save]');
  assert.equal(h.node('.feedback-note-list').scrollTop, 0);
});
