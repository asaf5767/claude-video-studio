#!/usr/bin/env node
// Runs `node --test` over every test_*.js(/.mjs) file in a directory (default:
// style-library). Cross-platform replacement for `node --test style-library/test_*.js`,
// since PowerShell (the default shell on Windows GitHub Actions runners) does not
// expand that glob the way bash does.
import {readdirSync} from 'node:fs';
import {join, dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..');

export function listTestFiles(dir) {
  // readdirSync is non-recursive on purpose: parity with the old shell glob
  // (style-library/test_*.js), which only matched that one directory too.
  return readdirSync(dir)
    .filter((name) => /^test_.*\.m?js$/.test(name))
    .sort()
    .map((name) => join(dir, name));
}

export function runTests(files, {stdio = 'inherit'} = {}) {
  if (files.length === 0) return true;
  // Strip NODE_TEST_CONTEXT/NODE_TEST_WORKER_ID: when this function itself runs
  // inside a `node --test` process (as it does in this script's own tests), Node
  // sets those on the environment, and a spawned `node --test` child inherits them
  // and reports back as a worker instead of exiting with its own real status code.
  const env = {...process.env};
  delete env.NODE_TEST_CONTEXT;
  delete env.NODE_TEST_WORKER_ID;
  const result = spawnSync(process.execPath, ['--test', ...files], {stdio, env});
  return result.status === 0;
}

function main() {
  const target = process.argv[2] || 'style-library';
  const dir = resolve(REPO_ROOT, target);
  const files = listTestFiles(dir);
  if (files.length === 0) {
    console.error(`No test_*.js files found in ${dir}`);
    process.exit(1);
  }
  process.exit(runTests(files) ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
