"""Task 17: scripts/new_version.py gives each edit round its own versions/vNN/ folder (so an
approved version is never overwritten) with the studio's bundled Hebrew fonts and copies of
the media the composition needs."""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_new_version', REPO_ROOT / 'scripts/new_version.py')
new_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(new_version)


class NewVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / 'projects' / 'demo'
        (self.project / 'work/media').mkdir(parents=True)
        (self.project / 'work/media/a-1.mp4').write_bytes(b'video')
        (self.project / 'work/media/logo-2.png').write_bytes(b'png')

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_version_gets_fonts_and_font_css(self):
        result = new_version.create(self.project)
        folder = self.project / 'versions/v01'
        self.assertEqual(result['version'], 'V01')
        self.assertEqual(Path(result['folder']), folder)
        for family in ('Secular One', 'Heebo', 'Suez One', 'Karantina', 'Bellefair'):
            self.assertIn(family, result['fonts'])
        css = (folder / 'fonts/fonts.css').read_text(encoding='utf-8')
        self.assertIn("font-family: 'Secular One'", css)
        for url in __import__('re').findall(r"url\('([^']+)'\)", css):
            self.assertTrue((folder / 'fonts' / url).is_file(), url)
        self.assertTrue(any((folder / 'fonts').glob('*LICENSE*')))
        for empty in ('renders', 'storyboard', 'sfx'):
            self.assertTrue((folder / empty).is_dir())

    def test_versions_count_up_and_never_reuse_a_folder(self):
        new_version.create(self.project)
        (self.project / 'versions/v01/index.html').write_text('approved', encoding='utf-8')
        self.assertEqual(new_version.create(self.project)['version'], 'V02')
        self.assertEqual((self.project / 'versions/v01/index.html').read_text(encoding='utf-8'), 'approved')
        (self.project / 'versions/v07').mkdir()
        self.assertEqual(new_version.create(self.project)['version'], 'V08')

    def test_copy_media_into_the_version(self):
        result = new_version.create(self.project, copy=['work/media/a-1.mp4', 'work/media/logo-2.png'])
        self.assertEqual(result['media'], ['media/a-1.mp4', 'media/logo-2.png'])
        self.assertEqual((self.project / 'versions/v01/media/a-1.mp4').read_bytes(), b'video')

    def test_copy_refuses_files_outside_the_project(self):
        outside = Path(self.tmp.name) / 'secret.txt'
        outside.write_text('x', encoding='utf-8')
        with self.assertRaises(new_version.VersionError):
            new_version.create(self.project, copy=['../../secret.txt'])
        self.assertFalse((self.project / 'versions').exists())

    def test_from_copies_only_the_composition_sources(self):
        new_version.create(self.project)
        first = self.project / 'versions/v01'
        (first / 'index.html').write_text('<html>v1</html>', encoding='utf-8')
        (first / 'scenes.json').write_text('[]', encoding='utf-8')
        (first / 'media').mkdir()
        (first / 'media/voice.wav').write_bytes(b'w')
        (first / 'media/shots').mkdir()
        (first / 'media/shots/a.png').write_bytes(b'p')
        derived = ['cut.mp4', 'cut.words.json', 'cut.map.json', 'captions.json', 'mix.wav', 'base.mp4',
                   'cut-request.json', 'sound-plan.json', 'words.fixed.json', 'README.md']
        for name in derived:
            (first / name).write_bytes(b'x')
        for folder in ('matte', 'renders', 'storyboard', 'sfx'):
            (first / folder).mkdir(exist_ok=True)
            (first / folder / 'f.bin').write_bytes(b'x')
        result = new_version.create(self.project, source='v01')
        second = Path(result['folder'])
        self.assertEqual((second / 'index.html').read_text(encoding='utf-8'), '<html>v1</html>')
        self.assertEqual((second / 'scenes.json').read_text(encoding='utf-8'), '[]')
        self.assertEqual((second / 'media/voice.wav').read_bytes(), b'w')
        self.assertEqual((second / 'media/shots/a.png').read_bytes(), b'p')
        for name in derived:
            self.assertFalse((second / name).exists(), name)
        self.assertFalse((second / 'matte').exists())
        for folder in ('renders', 'storyboard', 'sfx'):
            self.assertEqual(list((second / folder).iterdir()), [], folder)
        self.assertEqual(sorted(p.name for p in second.iterdir()),
                         sorted(['index.html', 'scenes.json', 'media', 'fonts', 'renders', 'storyboard', 'sfx'] +
                                (['gsap.min.js'] if result['gsap'] else [])))

    def test_a_final_project_gets_no_new_version_until_it_is_reopened(self):
        new_version.create(self.project)
        registry = Path(self.tmp.name) / 'projects.json'
        final = {'id': 'demo', 'state': 'final', 'review_decision': {'action': 'approve', 'kind': 'final'},
                 'artifacts': []}
        registry.write_text(json.dumps({'projects': [final]}), encoding='utf-8')
        with patch.object(new_version, 'REGISTRY', registry):
            with self.assertRaises(new_version.VersionError) as caught:
                new_version.create(self.project, source='v01')
            self.assertEqual(caught.exception.code, 'register.final')
            self.assertIn('פתיחה מחדש', str(caught.exception))
            self.assertIn('Reopen', str(caught.exception))
            self.assertEqual(sorted(p.name for p in (self.project / 'versions').iterdir()), ['v01'])
            with patch('sys.stderr', new_callable=io.StringIO) as err:
                self.assertEqual(new_version.main([str(self.project)]), 2)
            self.assertTrue(err.getvalue().startswith('register.final: '))
            registry.write_text(json.dumps({'projects': [dict(final, state='review',
                                                              review_decision={'action': 'reopen'})]}), encoding='utf-8')
            self.assertEqual(new_version.create(self.project, source='v01')['version'], 'V02')
        # One message for both refusals.
        _reg = importlib.util.spec_from_file_location('studio_register_msg', REPO_ROOT / 'scripts/register.py')
        register = importlib.util.module_from_spec(_reg)
        _reg.loader.exec_module(register)
        self.assertEqual(register.FINAL_MESSAGE, new_version.FINAL_MESSAGE)

    def test_registered_tells_whether_the_studio_points_into_a_version(self):
        registry = Path(self.tmp.name) / 'projects.json'
        new_version.create(self.project)
        new_version.create(self.project)
        self.assertFalse(new_version.registered(self.project / 'versions/v01', registry))  # no registry yet
        registry.write_text(json.dumps({'projects': [{'id': 'demo', 'artifacts': [
            {'id': 'storyboard-v01', 'type': 'board', 'frames': [{'path': 'versions/v01/storyboard/01.jpg'}]},
            {'id': 'other', 'type': 'video', 'path': 'versions/v010/x.mp4'}]}]}), encoding='utf-8')
        self.assertTrue(new_version.registered(self.project / 'versions/v01', registry))
        self.assertFalse(new_version.registered(self.project / 'versions/v02', registry))
        registry.write_text(json.dumps({'projects': [{'id': 'demo', 'artifacts': [
            {'id': 'video-v02', 'type': 'video', 'path': 'versions/v02/renders/final.mp4',
             'poster_path': 'versions/v02/storyboard/poster.jpg'}]}]}), encoding='utf-8')
        self.assertTrue(new_version.registered(self.project / 'versions/v02', registry))
        self.assertFalse(new_version.registered(Path(self.tmp.name) / 'elsewhere', registry))

    def test_cli(self):
        done = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/new_version.py'), str(self.project),
                               '--copy', 'work/media/a-1.mp4'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['version'], 'V01')
        bad = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/new_version.py'), str(self.project),
                              '--from', 'v09'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn('Traceback', bad.stderr)


if __name__ == '__main__':
    unittest.main()
