"""Fix round 1 (Task 7, R23 follow-up): scripts/studio.py's legacy `new` scaffold must not
leak templates/brief.md's <!-- lang: --> markers into a project's brief.md after Task 7
wrapped the template's Hebrew/English sections in those markers."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_path = REPO_ROOT / 'scripts/studio.py'
_spec = importlib.util.spec_from_file_location('studio_cli', _path)
studio_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(studio_cli)


class LegacyScaffoldBriefTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / 'templates').mkdir(parents=True)
        for name in ['STATUS.md', 'STORYBOARD.md', 'selects.csv', 'sound-cues.csv', 'asset-ledger.csv', 'edit-plan.json']:
            shutil.copy2(REPO_ROOT / 'templates' / name, self.root / 'templates' / name)
        # `run()` would otherwise shell out to the real scripts/register.py with a
        # project path that doesn't exist under this temp ROOT; this test only cares
        # about the scaffolded brief.md, so stub it out rather than register anything.
        self.patches = [patch.object(studio_cli, 'ROOT', self.root), patch.object(studio_cli, 'run')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def test_scaffolded_brief_has_no_lang_markers(self):
        studio_cli.new_project(SimpleNamespace(slug='demo-project'))
        brief = (self.root / 'projects' / 'demo-project' / 'brief.md').read_text(encoding='utf-8')
        self.assertNotIn('<!-- lang:', brief)
        self.assertNotIn('<!-- /lang:', brief)
        self.assertIn('<!-- choices -->', brief)
        self.assertIn('<!-- /choices -->', brief)
        self.assertIn('Video brief', brief)  # the English section's own heading
        self.assertTrue((self.root / 'projects' / 'demo-project' / 'STATUS.md').is_file())


if __name__ == '__main__':
    unittest.main()
