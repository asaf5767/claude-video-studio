// Quick tests for scripts/check_js.mjs: the cross-platform (Windows-PowerShell-safe)
// replacement for `for f in style-library/dist/*.js; do node --check "$f"; done`.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {listDistFiles, checkFiles} from './check_js.mjs';

function withTempDir(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'check-js-'));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
}

test('listDistFiles finds .js files, sorted, ignoring other extensions', () => {
  withTempDir((dir) => {
    writeFileSync(join(dir, 'b.js'), '');
    writeFileSync(join(dir, 'a.js'), '');
    writeFileSync(join(dir, 'notes.txt'), '');
    const names = listDistFiles(dir).map((f) => f.split(/[\\/]/).pop());
    assert.deepEqual(names, ['a.js', 'b.js']);
  });
});

test('checkFiles returns true when every file is syntactically valid', () => {
  withTempDir((dir) => {
    const file = join(dir, 'ok.js');
    writeFileSync(file, 'const x = 1;\n');
    assert.equal(checkFiles([file], {stdio: 'pipe'}), true);
  });
});

test('checkFiles returns false when a file has a syntax error', () => {
  withTempDir((dir) => {
    const good = join(dir, 'ok.js');
    const bad = join(dir, 'bad.js');
    writeFileSync(good, 'const x = 1;\n');
    writeFileSync(bad, 'const x = ;\n');
    assert.equal(checkFiles([good, bad], {stdio: 'pipe'}), false);
  });
});

test('checkFiles with no files is a no-op success', () => {
  assert.equal(checkFiles([], {stdio: 'pipe'}), true);
});
