#!/usr/bin/env node
// Checks every style-library/dist/*.js file with `node --check`.
//
// Cross-platform replacement for the shell loop
//   for file in style-library/dist/*.js; do node --check "$file"; done
// which does not work on Windows GitHub Actions runners: their default
// shell is PowerShell, which does not expand that glob the same way.
import {readdirSync} from 'node:fs';
import {join, dirname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));

export function listDistFiles(distDir) {
  // readdirSync is non-recursive on purpose: parity with the old shell glob
  // (style-library/dist/*.js), which only matched that one directory too.
  return readdirSync(distDir)
    .filter((name) => name.endsWith('.js'))
    .sort()
    .map((name) => join(distDir, name));
}

export function checkFiles(files, {stdio = 'inherit'} = {}) {
  // Strip NODE_TEST_CONTEXT/NODE_TEST_WORKER_ID in case this runs inside a
  // `node --test` process (as it does in this script's own tests); `node --check`
  // ignores them, but stripping keeps this consistent with run_node_tests.mjs.
  const env = {...process.env};
  delete env.NODE_TEST_CONTEXT;
  delete env.NODE_TEST_WORKER_ID;
  let ok = true;
  for (const file of files) {
    const result = spawnSync(process.execPath, ['--check', file], {stdio, env});
    if (result.status !== 0) ok = false;
  }
  return ok;
}

function main() {
  const distDir = join(__dirname, '..', 'style-library', 'dist');
  const files = listDistFiles(distDir);
  if (files.length === 0) {
    console.error(`No .js files found in ${distDir}`);
    process.exit(1);
  }
  process.exit(checkFiles(files) ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
