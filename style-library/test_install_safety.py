"""Update safety: served-file validation and installed-vs-release comparison, on disposable fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import library

spec = importlib.util.spec_from_file_location('check_install', Path(__file__).resolve().parents[1] / 'scripts/check_install.py')
check_install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_install)

def entry(path, data):
    return {'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

class ServedFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for name in ['references/demo/clip.mp4', 'references/demo/note.md', 'style-library/references/old/clip.mp4', 'projects/demo/.hidden.mp4']:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
        self.patch = patch.object(library, 'STUDIO', self.root); self.patch.start()
    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()
    def test_servable_entry_passes(self):
        library.check_served({'media_path': 'references/demo/clip.mp4', 'notes': ['references/demo/note.md']})
    def test_existing_but_unservable_files_fail_validation(self):
        for e in [{'media_path': 'style-library/references/old/clip.mp4', 'notes': []},
                  {'media_path': 'projects/demo/.hidden.mp4', 'notes': []},
                  {'notes': ['references/demo/clip.mp4']},
                  {'notes': [], 'slides': [{'path': 'references/demo/note.md'}]},
                  {'notes': [], 'archive_path': 'references/demo/clip.mp4'}]:
            with self.subTest(entry=e), self.assertRaisesRegex(AssertionError, 'would not be served'):
                library.check_served(e)

class InstallComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / 'same.txt').write_bytes(b'same'); (self.root / 'custom.txt').write_bytes(b'changed locally')
        self.manifest = {'candidate': 'ai-video-studio-9.9.9', 'files': [entry('same.txt', b'same'), entry('custom.txt', b'original'), entry('new.txt', b'new in release')]}
    def tearDown(self):
        self.tmp.cleanup()
    def test_identical_modified_and_missing(self):
        self.assertEqual(check_install.compare(self.root, self.manifest), {'identical': ['same.txt'], 'modified': ['custom.txt'], 'missing': ['new.txt']})
    def test_symlinked_file_is_not_trusted(self):
        (self.root / 'alias.txt').symlink_to(self.root / 'same.txt')
        self.assertEqual(check_install.compare(self.root, {'files': [entry('alias.txt', b'same')]})['missing'], ['alias.txt'])
    def test_unsafe_or_malformed_manifest_is_rejected(self):
        # An absolute path outside the studio is unsafe on any OS; build one for
        # whichever platform the suite runs on instead of hard-coding a POSIX path.
        absolute_path = str(Path(self.tmp.name) / 'outside.txt')
        for files in [[entry('../outside.txt', b'x')], [entry(absolute_path, b'x')], [{'path': 'same.txt', 'sha256': 'not-a-hash'}], []]:
            path = self.root / 'manifest.json'; path.write_text(json.dumps({'files': files}), encoding='utf-8')
            with self.subTest(files=files), self.assertRaises(ValueError):
                check_install.load_manifest(str(path))
    def test_only_official_release_manifests_are_fetched(self):
        self.assertEqual(check_install.manifest_url('v0.1.0-beta.4'), check_install.RELEASES + 'v0.1.0-beta.4/ai-video-studio-0.1.0-beta.4.manifest.json')
        for tag in ['0.1.0', 'v1', 'vmain', 'v0.1.0/../../x']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                check_install.manifest_url(tag)
        with patch.object(check_install.urllib.request, 'urlopen') as urlopen, self.assertRaises(ValueError):
            check_install.load_manifest('https://example.invalid/ai-video-studio.manifest.json')
        urlopen.assert_not_called()
    def test_local_label_suffix_maps_to_its_published_release(self):
        self.assertEqual(check_install.default_tag('0.1.0-beta.3+local'), 'v0.1.0-beta.3')
        self.assertEqual(check_install.default_tag('0.1.0-beta.4'), 'v0.1.0-beta.4')

if __name__ == '__main__':
    unittest.main()
