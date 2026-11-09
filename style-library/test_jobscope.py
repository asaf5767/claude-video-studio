"""RULING R51: in a studio run (STUDIO_JOB_DIR set) every helper refuses a path outside the job
folder (scripts/jobscope.py). Each helper runs as a real subprocess from a throwaway studio
with dummy files only; the refused file must stay untouched."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'
_spec = importlib.util.spec_from_file_location('studio_jobscope', SCRIPTS / 'jobscope.py')
jobscope = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jobscope)


class ConfineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.job = self.root / 'projects' / 'demo'
        (self.job / 'work').mkdir(parents=True)
        (self.job / 'work' / 'a.mp4').write_bytes(b'x')
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.env = {**os.environ}
        os.environ[jobscope.ENV] = str(self.job)

    def tearDown(self):
        os.chdir(self.cwd)
        os.environ.clear()
        os.environ.update(self.env)
        self.tmp.cleanup()

    def refused(self, path, **options):
        with self.assertRaises(jobscope.JobScopeError, msg=path):
            jobscope.confine(path, **options)

    def test_inside_paths_pass(self):
        for path in ('projects/demo/work/a.mp4', 'projects/demo/versions/v01/out.mp4', str(self.job / 'x.json'),
                     'projects/demo/work/תמונה שלי.jpg', 'PROJECTS/DEMO/work/a.mp4' if jobscope.CASELESS else 'projects/demo/b'):
            with self.subTest(path=path):
                self.assertEqual(jobscope.confine(path), path)

    def test_outside_and_tricky_paths_are_refused(self):
        for path in ('CLAUDE.md', 'scripts/json.py', '.claude/settings.local.json', 'projects/other/x.mp4',
                     'projects/demo/../other/x', 'projects/demo/work/../../../CLAUDE.md', 'C:/Windows/x',
                     '//server/share/x', '/etc/passwd', 'projects/demo/.env', 'projects/demo/.ENV',
                     'projects/demo/.Env.local', 'projects/demo/.env ', 'projects/demo/a.mp4.', 'projects/demo/x:stream',
                     'projects/demo/.env::$DATA', 'projects/demo/NUL', 'projects/demo/con.txt', 'projects/demo/COM1.mp4'):
            with self.subTest(path=path):
                self.refused(path)

    def test_a_link_out_of_the_folder_is_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            os.symlink(outside, self.job / 'link', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('this account cannot create symlinks')
        self.refused('projects/demo/link/x.mp4')

    def test_read_only_asset_folders_only_for_reads(self):
        self.assertEqual(jobscope.confine(str(REPO / 'looks'), read=True), str(REPO / 'looks'))
        self.refused(str(REPO / 'looks' / 'x.mp4'))

    def test_new_and_exists(self):
        self.refused('projects/demo/work/a.mp4', new=True)
        self.refused('projects/demo/work/missing.mp4', exists=True)

    def test_no_job_folder_means_no_check(self):
        del os.environ[jobscope.ENV]
        self.assertEqual(jobscope.confine('CLAUDE.md'), 'CLAUDE.md')


class HelperTests(unittest.TestCase):
    """Every helper the runner allows refuses an outside path before doing anything."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.job = self.root / 'projects' / 'demo'
        (self.job / 'versions' / 'v01').mkdir(parents=True)
        (self.job / 'work').mkdir()
        (self.job / 'work' / 'words.json').write_text('[]', encoding='utf-8')
        (self.job / 'work' / 'take.mp4').write_bytes(b'not a video')
        (self.root / 'CLAUDE.md').write_text('original\n', encoding='utf-8')
        (self.root / 'outside.txt').write_text('text\n', encoding='utf-8')
        self.env = {**os.environ, jobscope.ENV: str(self.job), 'PYTHONUTF8': '1'}

    def tearDown(self):
        self.tmp.cleanup()

    def run_helper(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, encoding='utf-8', timeout=120)

    def assert_refused(self, script, *args):
        done = self.run_helper(script, *args)
        self.assertEqual(done.returncode, 2, (script, args, done.stdout, done.stderr))
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1])['code'], 'job.outside-folder', done.stdout)
        self.assertEqual((self.root / 'CLAUDE.md').read_text(encoding='utf-8'), 'original\n')
        self.assertFalse((self.root / 'scripts').exists())

    def test_progress(self):
        self.assert_refused('progress.py', 'CLAUDE.md', '--start', 'talking-head')
        self.assert_refused('progress.py', 'scripts/json.py', 'cut', 'running')
        self.assertEqual(self.run_helper('progress.py', 'projects/demo/progress.json', '--start', 'talking-head').returncode, 0)

    def test_transcribe(self):
        self.assert_refused('transcribe.py', 'projects/demo/work/take.mp4', 'CLAUDE.md', '--language', 'he', '--force')
        self.assert_refused('transcribe.py', 'outside.txt', 'projects/demo/work/w.json', '--language', 'he')

    def test_captions(self):
        self.assert_refused('captions.py', 'projects/demo/work/words.json', 'CLAUDE.md')
        self.assert_refused('captions.py', '../words.json', 'projects/demo/c.json')

    def test_cut(self):
        self.assert_refused('cut.py', 'projects/demo', 'projects/demo/work/words.json', 'scripts')
        self.assert_refused('cut.py', '.', 'projects/demo/work/words.json', 'projects/demo/versions/v01')

    def test_matte(self):
        self.assert_refused('matte.py', 'projects/demo/work/take.mp4', 'scripts')
        self.assert_refused('matte.py', 'projects/demo/work/take.mp4', 'projects/demo/m', '--progress', 'CLAUDE.md')
        self.assert_refused('matte.py', 'projects/demo/work/take.mp4', 'projects/demo/m', '--reuse-from', 'projects/other')

    def test_project_helpers(self):
        self.assert_refused('new_version.py', '.')
        self.assert_refused('new_version.py', 'projects/demo', '--copy', '../../CLAUDE.md')
        self.assert_refused('prepare_media.py', 'projects')
        self.assert_refused('register_version.py', 'projects/demo', '--version', 'V01', '--kind', 'storyboard',
                            '--poster', '../../CLAUDE.md', '--summary', 's', '--next-step', 'n')
        self.assert_refused('check_card.py', '.')

    def test_addons(self):
        for script, flag in (('addons_voice.py', '--text-file'), ('addons_image.py', '--prompt-file')):
            with self.subTest(script=script):
                self.assert_refused(script, flag, 'outside.txt', '--out', 'projects/demo/a.mp3')
                self.assert_refused(script, flag, 'projects/demo/work/words.json', '--out', 'CLAUDE.md')
                self.assert_refused(script, '--check', '--project', '.')

    def test_round3_studio_records_cannot_be_overwritten(self):
        # G8: helper outputs may never replace the studio's own records in the job folder.
        (self.job / 'approval-state.json').write_text('{"approved": true}', encoding='utf-8')
        self.assert_refused('progress.py', 'projects/demo/approval-state.json', '--start', 'talking-head')
        self.assert_refused('captions.py', 'projects/demo/work/words.json', 'projects/demo/choices.json')
        self.assert_refused('transcribe.py', 'projects/demo/work/take.mp4', 'projects/demo/style-card.json',
                            '--language', 'he')
        self.assertEqual((self.job / 'approval-state.json').read_text(encoding='utf-8'), '{"approved": true}')
        self.assert_refused('captions.py', 'projects/demo/work/words.json', 'projects/demo/look.json')  # round 4

    def test_round3_hf_output_is_a_new_video(self):
        (self.job / 'versions' / 'v01' / 'old.mp4').write_bytes(b'x')
        for output in ('projects/demo/versions/v01/old.mp4', 'projects/demo/versions/v01/notes.md',
                       'projects/demo/approval-state.json'):
            with self.subTest(output=output):
                self.assert_refused('hf.py', 'render', 'projects/demo/versions/v01', '--output', output)

    def test_round3_addons_keep_their_spending_guard(self):
        # G10: a studio run never lifts the cost guard or asks for several images at once.
        self.assert_refused('addons_voice.py', '--text-file', 'projects/demo/work/words.json',
                            '--out', 'projects/demo/a.mp3', '--allow-cost')
        self.assert_refused('addons_image.py', '--prompt-file', 'projects/demo/work/words.json',
                            '--out', 'projects/demo/a.png', '--n', '3')

    def test_round3_register_version_files_stay_in_the_project(self):
        # G9: a registered file is resolved and must be inside the project.
        sys.path.insert(0, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location('studio_register_version', SCRIPTS / 'register_version.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        (self.root / 'projects' / 'other.jpg').write_bytes(b'x')
        with self.assertRaises(module.RegisterError):
            module._file(self.job, '../other.jpg')
        (self.job / 'p.jpg').write_bytes(b'x')
        self.assertEqual(module._file(self.job, 'p.jpg'), 'p.jpg')

    def test_hf_only_check_and_render_inside_the_job(self):
        for args in (('render', 'projects/demo/versions/v01', '--output', 'CLAUDE.md'),
                     ('render', 'projects/demo/versions/v01', '--output', 'projects/demo/a.mp4', '--browser-path', 'x'),
                     ('render', 'projects/demo/versions/v01', '--output', 'projects/demo/a.mp4', '--docker', '1'),
                     ('render', 'projects/demo/versions/v01', '--config', 'x', '--output', 'projects/demo/a.mp4'),
                     ('check', '.'), ('publish', 'projects/demo/versions/v01'), ('init', 'projects/demo/x'),
                     ('render', 'projects/demo/versions/v01')):
            with self.subTest(args=args):
                self.assert_refused('hf.py', *args)
        spec = importlib.util.spec_from_file_location('studio_hf', SCRIPTS / 'hf.py')
        hf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hf)
        old, cwd = os.environ.get(jobscope.ENV), os.getcwd()
        os.environ[jobscope.ENV] = str(self.job)
        os.chdir(self.root)
        try:
            argv = ['render', 'projects/demo/versions/v01', '--workers', '1', '--fps', '30', '--crf', '18',
                    '--output', 'projects/demo/versions/v01/renders/video-only.mp4']
            self.assertEqual(hf.allowed(argv), argv)
            self.assertEqual(hf.allowed(['check', 'projects/demo/versions/v01']), ['check', 'projects/demo/versions/v01'])
        finally:
            os.chdir(cwd)
            if old is None:
                os.environ.pop(jobscope.ENV, None)
            else:
                os.environ[jobscope.ENV] = old


if __name__ == '__main__':
    unittest.main()
