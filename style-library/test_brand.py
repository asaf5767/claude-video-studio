"""Task 5: a fresh install shows Assaf's brand (empty settings defaults -> translated brand.name, ember-dot logo) and no Matt credit line."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import library


class BrandDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(library, 'BASE', Path(self.temp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_fresh_install_uses_the_built_in_brand(self):
        settings = library.site_settings()
        self.assertEqual(settings['studio_name'], '')
        self.assertEqual(settings['monogram'], '')
        self.assertEqual(settings['credit'], {'name': '', 'url': ''})

    def test_the_example_settings_do_not_bring_matt_branding_back(self):
        example = json.loads((Path(library.__file__).parent / 'settings.example.json').read_text(encoding='utf-8'))
        (Path(self.temp.name) / 'settings.json').write_text(json.dumps(example), encoding='utf-8')
        settings = library.site_settings()
        self.assertEqual(settings['studio_name'], '')
        self.assertEqual(settings['credit']['name'], '')

    def test_a_custom_studio_name_still_wins(self):
        (Path(self.temp.name) / 'settings.json').write_text(json.dumps({'studio_name': 'My Studio', 'monogram': 'ms'}), encoding='utf-8')
        settings = library.site_settings()
        self.assertEqual(settings['studio_name'], 'My Studio')
        self.assertEqual(settings['monogram'], 'ms')


if __name__ == '__main__':
    unittest.main()
