// Quick tests for scripts/run_node_tests.mjs: the cross-platform (Windows-PowerShell-safe)
// replacement for `node --test style-library/test_*.js`.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {listTestFiles, runTests} from './run_node_tests.mjs';

function withTempDir(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'run-node-tests-'));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
}

test('listTestFiles matches test_*.js and test_*.mjs, sorted, ignoring others', () => {
  withTempDir((dir) => {
    writeFileSync(join(dir, 'test_b.js'), '');
    writeFileSync(join(dir, 'test_a.mjs'), '');
    writeFileSync(join(dir, 'helper.js'), '');
    writeFileSync(join(dir, 'other_test_c.js'), '');
    const names = listTestFiles(dir).map((f) => f.split(/[\\/]/).pop());
    assert.deepEqual(names, ['test_a.mjs', 'test_b.js']);
  });
});

test('runTests returns true for a passing suite', () => {
  withTempDir((dir) => {
    const file = join(dir, 'test_pass.js');
    writeFileSync(file, "const {test} = require('node:test'); test('ok', () => {});\n");
    assert.equal(runTests([file], {stdio: 'pipe'}), true);
  });
});

test('runTests returns false for a failing suite', () => {
  withTempDir((dir) => {
    const file = join(dir, 'test_fail.js');
    writeFileSync(
      file,
      "const {test} = require('node:test'); const assert = require('node:assert'); test('bad', () => { assert.ok(false); });\n",
    );
    assert.equal(runTests([file], {stdio: 'pipe'}), false);
  });
});

test('runTests with no files is a no-op success', () => {
  assert.equal(runTests([]), true);
});
