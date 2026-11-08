/* Task 5 fix round 1: English that leaked into Hebrew mode is translated client-side.
   - Backend error sentences (Python raises English) are mapped to i18n keys by I18N.server().
   - The review decision button uses i18n keys by kind/action instead of the server's English label. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');

const read = name => readFileSync(join(__dirname, name), 'utf8');
const he = JSON.parse(read('dist/i18n/he.json')), en = JSON.parse(read('dist/i18n/en.json'));

function loadI18N(lang) {
  const files = {he, en};
  const document = {documentElement: {}, querySelectorAll: () => [], dispatchEvent() {}};
  const fetch = async url => url === '/ui-language' ? {ok: true, json: async () => ({language: lang})} : {ok: true, json: async () => files[url.match(/i18n\/(\w+)\.json/)[1]]};
  const context = {document, fetch, console: {warn() {}}, CustomEvent: class {}};
  context.window = context;
  runInNewContext(read('dist/i18n.js'), context);
  return context.window.I18N;
}

// Every backend sentence about unsafe local paths, exactly as the Python modules raise it.
const BACKEND = [
  ['feedback.py', 'The project folder needs a safe local path before saving feedback.'],
  ['reference_notes.py', 'Reference notes need a safe local path before saving.'],
  ['reference_notes.py', 'The reference source needs a safe local path.'],
  ['review_actions.py', 'The studio decision files need safe local paths before saving.'],
  ['scripting.py', 'Writing files need safe local paths. Existing files are preserved.'],
];

test('the backend sentences still exist verbatim in the Python modules', () => {
  for (const [file, sentence] of BACKEND) assert.ok(read(file).includes(sentence), file + ': ' + sentence);
});

test('I18N.server translates known backend sentences and passes anything else through', async () => {
  const i18n = loadI18N('he');
  await i18n.ready;
  for (const [, sentence] of BACKEND) {
    const text = i18n.server(sentence);
    assert.notEqual(text, sentence);
    assert.match(text, /[֐-׿]/, 'Hebrew for: ' + sentence);
  }
  assert.equal(i18n.server('Something new from the server.'), 'Something new from the server.');
  assert.equal(i18n.server(undefined), undefined);
  const english = loadI18N('en');
  await english.ready;
  assert.equal(english.server(BACKEND[0][1]), en['server.feedbackUnsafePath']);
});

test('error paths that show server messages go through I18N.server', () => {
  assert.match(read('dist/feedback-ui.js'), /Error\(I18N\.server\(result\.error\) \|\| I18N\.t\('feedback\.error\.notesCouldNotLoad'\)\)/);
  assert.match(read('dist/feedback-ui.js'), /Error\(I18N\.server\(result\.error\) \|\| I18N\.t\('feedback\.save\.failedDefault'\)\)/);
  assert.match(read('dist/feedback-ui.js'), /Error\(I18N\.server\(result\.error\) \|\| I18N\.t\('feedback\.note\.changeFailedDefault'\)\)/);
  assert.match(read('dist/reference-notes-ui.js'), /Error\(I18N\.server\(value\.error\)\|\|I18N\.t\('referenceNotes\.error\.unavailable'\)\)/);
  assert.match(read('dist/studio.js'), /Error\(I18N\.server\(result\.error\)\|\|I18N\.t\('project\.decisionSaveFailed'\)\)/);
});

test('the review decision button is labelled from i18n keys, not the server English', () => {
  const studio = read('dist/studio.js');
  assert.doesNotMatch(studio, /:decision\.label\)/);
  const start = studio.indexOf(' const decisionLabel='), end = studio.indexOf('\n', start);
  assert.ok(start >= 0, 'studio.js defines decisionLabel');
  const context = {I18N: {t: key => he[key] ?? key}};
  runInNewContext(studio.slice(start, end).replace('const decisionLabel', 'globalThis.decisionLabel'), context);
  const label = (kind, action = 'approve', format = 'video') => context.decisionLabel({kind, action}, {format});
  assert.equal(label('storyboard'), he['review.decision.approveStoryboard']);
  assert.equal(label('spoken_cut'), he['review.decision.approveSpokenCut']);
  assert.equal(label('final'), he['review.decision.approveFinal']);
  assert.equal(label('final', 'approve', 'presentation'), he['review.decision.approveSectionFinal']);
  assert.equal(label('storyboard', 'reopen'), he['review.decision.reopen']);
  assert.equal(label('mystery'), he['review.decision.approveCheckpoint']);
  for (const key of ['approveStoryboard', 'approveSpokenCut', 'approveFinal', 'approveSectionFinal', 'reopen', 'approveCheckpoint'])
    assert.match(he['review.decision.' + key], /[֐-׿]/);
});
