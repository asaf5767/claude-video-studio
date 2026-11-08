"""Task 17: scripts/check_card.py, the learn-style skill's last check on the style card it
wrote: every card key present on one line, and every row the creator pinned unchanged."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_check_card', REPO_ROOT / 'scripts/check_card.py')
check_card = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_card)

KEYS = ('id', 'name_he', 'name_en', 'captions', 'titles', 'pace', 'transitions', 'graphics', 'music', 'sfx',
        'hook', 'avoid')


def card(**override):
    fields = {k: f'value of {k}' for k in KEYS}
    fields.update(override)
    return '---\n' + ''.join(f'{k}: {v}\n' for k, v in fields.items() if v is not None) + '---\n\nNotes.\n'


class CheckCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text, pins=None):
        (self.folder / 'style-card.md').write_text(text, encoding='utf-8')
        if pins is not None:
            (self.folder / 'style-card.json').write_text(json.dumps(pins, ensure_ascii=False), encoding='utf-8')

    def test_complete_card_without_pins(self):
        self.write(card())
        self.assertEqual(check_card.check(self.folder), {'ok': True, 'missing': [], 'changed_pins': []})

    def test_missing_or_empty_keys(self):
        self.write(card(music=None, hook=''))
        result = check_card.check(self.folder)
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing'], ['music', 'hook'])

    def test_pinned_rows_must_be_unchanged(self):
        self.write(card(captions='שורה אחת, מילה מודגשת'), {'pinned': {'captions': 'שורה אחת, מילה מודגשת',
                                                                       'pace': 'לאט'}})
        result = check_card.check(self.folder)
        self.assertEqual(result['changed_pins'], ['pace'])
        self.assertFalse(result['ok'])

    def test_legacy_pin_list_only_needs_the_key(self):
        self.write(card(), {'pinned': ['captions']})
        self.assertTrue(check_card.check(self.folder)['ok'])

    def test_missing_card_and_malformed_front_matter(self):
        self.assertEqual(check_card.check(self.folder)['missing'], list(KEYS))
        self.write('no front matter here')
        self.assertFalse(check_card.check(self.folder)['ok'])

    def test_cli_exit_codes(self):
        self.write(card())
        ok = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/check_card.py'), str(self.folder)],
                            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.write(card(avoid=''))
        bad = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/check_card.py'), str(self.folder)],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)['missing'], ['avoid'])


if __name__ == '__main__':
    unittest.main()
