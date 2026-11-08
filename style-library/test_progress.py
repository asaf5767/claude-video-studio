"""Task 17: scripts/progress.py, the tiny helper the project skills use to write
progress.json ([{"key","state","detail"?}]) without hand-writing JSON."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_progress', REPO_ROOT / 'scripts/progress.py')
progress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(progress)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / 'progress.json'

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        return json.loads(self.file.read_text(encoding='utf-8'))

    def test_fixed_step_lists(self):
        self.assertEqual(progress.STEPS['talking-head'],
                         ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard'])
        self.assertEqual(progress.STEPS['faceless-reel'],
                         ['voice', 'transcribe', 'scenes', 'captions', 'sound', 'storyboard'])
        self.assertEqual(progress.STEPS['learn-style'], ['watch', 'analyze', 'card'])

    def test_start_writes_every_step_as_todo(self):
        progress.start(self.file, 'faceless-reel')
        self.assertEqual(self.read(), [{'key': k, 'state': 'todo'} for k in progress.STEPS['faceless-reel']])

    def test_start_with_matte_inserts_it_after_cut(self):
        progress.start(self.file, 'talking-head', extra=['matte'])
        self.assertEqual([s['key'] for s in self.read()],
                         ['ingest', 'transcribe', 'cut', 'matte', 'captions', 'graphics', 'sound', 'storyboard'])

    def test_start_rejects_unknown_skill_or_extra(self):
        with self.assertRaises(progress.ProgressError):
            progress.start(self.file, 'cooking')
        with self.assertRaises(progress.ProgressError):
            progress.start(self.file, 'learn-style', extra=['matte'])

    def test_start_replaces_an_earlier_run(self):
        progress.start(self.file, 'learn-style')
        progress.update(self.file, 'watch', 'done', 'ok')
        progress.start(self.file, 'learn-style')
        self.assertEqual(self.read()[0], {'key': 'watch', 'state': 'todo'})

    def test_update_keeps_other_steps_and_order(self):
        progress.start(self.file, 'learn-style')
        progress.update(self.file, 'analyze', 'running', 'מנתחים את הקצב · 40%')
        steps = self.read()
        self.assertEqual([s['key'] for s in steps], ['watch', 'analyze', 'card'])
        self.assertEqual(steps[1], {'key': 'analyze', 'state': 'running', 'detail': 'מנתחים את הקצב · 40%'})
        self.assertIn('מנתחים', self.file.read_text(encoding='utf-8'))  # real Hebrew, not \u escapes

    def test_update_without_detail_drops_the_old_detail(self):
        progress.start(self.file, 'learn-style')
        progress.update(self.file, 'watch', 'running', 'half way')
        progress.update(self.file, 'watch', 'done')
        self.assertEqual(self.read()[0], {'key': 'watch', 'state': 'done'})

    def test_update_rejects_bad_state_and_unknown_key(self):
        progress.start(self.file, 'learn-style')
        with self.assertRaises(progress.ProgressError):
            progress.update(self.file, 'watch', 'finished')
        with self.assertRaises(progress.ProgressError):
            progress.update(self.file, 'dance', 'done')
        self.assertEqual(self.read(), [{'key': k, 'state': 'todo'} for k in ['watch', 'analyze', 'card']])

    def test_detail_is_one_short_line(self):
        progress.start(self.file, 'learn-style')
        progress.update(self.file, 'watch', 'running', 'line one\nline two\t' + 'x' * 500)
        detail = self.read()[0]['detail']
        self.assertNotIn('\n', detail)
        self.assertLessEqual(len(detail), progress.MAX_DETAIL)
        self.assertTrue(detail.startswith('line one line two'))

    def test_missing_step_is_inserted_in_its_canonical_place(self):
        progress.start(self.file, 'talking-head')
        progress.update(self.file, 'matte', 'running', '10%')
        self.assertEqual([s['key'] for s in self.read()][2:5], ['cut', 'matte', 'captions'])

    def test_missing_or_corrupt_file_is_rebuilt(self):
        self.file.write_text('{not json', encoding='utf-8')
        progress.update(self.file, 'card', 'running')
        self.assertEqual(self.read(), [{'key': 'card', 'state': 'running'}])

    def test_write_is_atomic_and_leaves_no_temp_files(self):
        progress.start(self.file, 'learn-style')
        real_replace = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 1:  # the studio is reading the file on Windows: retried, not lost
                raise PermissionError('in use')
            return real_replace(src, dst)

        with patch.object(progress.os, 'replace', flaky), patch.object(progress.time, 'sleep'):
            progress.update(self.file, 'watch', 'done')
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.read()[0]['state'], 'done')
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ['progress.json'])

    def test_failed_write_keeps_the_previous_file(self):
        progress.start(self.file, 'learn-style')
        before = self.file.read_bytes()
        with patch.object(progress.os, 'replace', side_effect=PermissionError('locked')), \
                patch.object(progress.time, 'sleep'):
            with self.assertRaises(progress.ProgressError):
                progress.update(self.file, 'watch', 'done')
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ['progress.json'])

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/progress.py'), str(self.file), *args],
                              capture_output=True, text=True, encoding='utf-8')

    def test_cli(self):
        self.assertEqual(self.run_cli('--start', 'talking-head', '--with', 'matte').returncode, 0)
        result = self.run_cli('ingest', 'running', 'מכינים את הסרטונים')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read()[0], {'key': 'ingest', 'state': 'running', 'detail': 'מכינים את הסרטונים'})
        bad = self.run_cli('ingest', 'maybe')
        self.assertNotEqual(bad.returncode, 0)
        self.assertNotIn('Traceback', bad.stderr)


if __name__ == '__main__':
    unittest.main()
