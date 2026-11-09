"""Task 7: create a draft video project directly from the studio UI."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import project_index as index
import new_project


class NewProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.registry = self.root / 'projects.json'
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def registry_projects(self):
        return json.loads(self.registry.read_text(encoding='utf-8'))['projects']

    def test_hebrew_title_gets_timestamp_id(self):
        record = new_project.create({'title': 'איך להתחיל עם AI', 'kind': 'talking-head', 'video_language': 'he'})
        self.assertRegex(record['id'], r'^video-\d{8}-\d{6}$')
        self.assertEqual(record['title'], 'איך להתחיל עם AI')
        self.assertEqual(record['state'], 'draft')
        self.assertEqual(record['primary_artifact'], None)
        self.assertEqual(record['artifacts'], [])
        self.assertEqual(record['source_notes'], [])

    def test_english_title_slug(self):
        record = new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})
        self.assertEqual(record['id'], 'my-first-reel')

    def test_collision_suffix(self):
        ids = [new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})['id']
               for _ in range(3)]
        self.assertEqual(ids, ['my-first-reel', 'my-first-reel-2', 'my-first-reel-3'])

    def test_creates_folders_and_files(self):
        record = new_project.create({'title': 'My First Reel', 'kind': 'talking-head', 'video_language': 'he'})
        root = self.root / 'projects' / record['id']
        for sub in ('raw', 'broll', 'images', 'audio'):
            self.assertTrue((root / 'materials' / sub).is_dir(), sub)
        brief = (root / 'brief.md').read_text(encoding='utf-8')
        self.assertIn('<!-- choices -->', brief)
        self.assertIn('<!-- /choices -->', brief)
        self.assertIn('My First Reel', brief)
        self.assertNotIn('lang:', brief)  # only this project's language section was copied
        self.assertTrue((root / 'STATUS.md').is_file())
        self.assertEqual(json.loads((root / 'materials.json').read_text(encoding='utf-8')), {'items': []})
        self.assertEqual(json.loads((root / 'choices.json').read_text(encoding='utf-8')), {})
        self.assertEqual(self.registry_projects()[0]['id'], record['id'])

    def test_a_title_cannot_fake_or_end_the_choices_block(self):
        # Final review M14: the title is written into brief.md with comment markers neutralized.
        record = new_project.create({'title': 'Reel <!-- choices --> x --> y', 'kind': 'faceless', 'video_language': 'en'})
        root = self.root / 'projects' / record['id']
        brief = (root / 'brief.md').read_text(encoding='utf-8')
        self.assertEqual(brief.count('<!-- choices -->'), 1)
        self.assertEqual(brief.count('-->'), 2)  # only the real block's two markers
        self.assertEqual(self.registry_projects()[0]['title'], 'Reel <!-- choices --> x --> y')  # stored exactly

    def test_rejects_bad_kind(self):
        with self.assertRaises(new_project.NewProjectError) as ctx:
            new_project.create({'title': 'Valid title', 'kind': 'cinematic', 'video_language': 'en'})
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.message_key, 'newVideo.error.kind')
        self.assertFalse(self.registry.exists())

    def test_rejects_bad_title(self):
        for title in ['', ' ', 'x' * 81]:
            with self.subTest(title=title), self.assertRaises(new_project.NewProjectError) as ctx:
                new_project.create({'title': title, 'kind': 'faceless', 'video_language': 'en'})
            self.assertEqual(ctx.exception.status, 400)

    def test_rejects_bad_language(self):
        with self.assertRaises(new_project.NewProjectError) as ctx:
            new_project.create({'title': 'Valid title', 'kind': 'faceless', 'video_language': 'fr'})
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.message_key, 'newVideo.error.language')

    def test_registry_write_is_atomic(self):
        """A crash mid-write (os.replace failing) must never corrupt projects.json."""
        new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})
        before = self.registry.read_text(encoding='utf-8')
        with patch('atomic.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(new_project.NewProjectError) as ctx:
                new_project.create({'title': 'Second Reel', 'kind': 'faceless', 'video_language': 'en'})
            self.assertEqual(ctx.exception.status, 503)
        after = self.registry.read_text(encoding='utf-8')
        self.assertEqual(before, after)
        self.assertEqual(json.loads(after)['projects'], [{
            **json.loads(before)['projects'][0],
        }])
        self.assertEqual(len(json.loads(after)['projects']), 1)
        self.assertEqual(json.loads(after)['projects'][0]['id'], 'my-first-reel')

    # --- Fix round 1 ---

    def test_registry_write_failure_removes_the_orphaned_project_folder(self):
        with patch('atomic.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(new_project.NewProjectError) as ctx:
                new_project.create({'title': 'Orphan Reel', 'kind': 'faceless', 'video_language': 'en'})
        self.assertEqual(ctx.exception.status, 503)
        self.assertFalse((self.root / 'projects' / 'orphan-reel').exists())
        self.assertFalse(self.registry.exists())

    def test_file_write_failure_removes_the_orphaned_project_folder(self):
        with patch('new_project.Path.write_text', side_effect=OSError('disk full')):
            with self.assertRaises(new_project.NewProjectError) as ctx:
                new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})
        self.assertEqual(ctx.exception.status, 503)
        self.assertFalse((self.root / 'projects' / 'my-first-reel').exists())

    def test_a_folder_that_existed_before_the_call_is_never_deleted_on_failure(self):
        stray = self.root / 'projects' / 'my-first-reel'
        stray.mkdir(parents=True)
        (stray / 'keep-me.txt').write_text('precious', encoding='utf-8')
        with patch('atomic.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(new_project.NewProjectError):
                new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})
        self.assertTrue((stray / 'keep-me.txt').is_file())

    def test_windows_reserved_device_name_gets_a_timestamp_id(self):
        for title in ['CON', 'com1', 'LPT9', 'Nul', 'prn']:
            with self.subTest(title=title):
                record = new_project.create({'title': title, 'kind': 'faceless', 'video_language': 'en'})
                # A same-second collision would get a numeric suffix; still never the bare device name.
                self.assertRegex(record['id'], r'^video-\d{8}-\d{6}(-\d+)?$')

    def test_reference_id_is_recorded_in_choices_as_a_look_reference(self):
        record = new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en',
                                      'reference_id': 'cool-reference'})
        choices = json.loads((self.root / 'projects' / record['id'] / 'choices.json').read_text(encoding='utf-8'))
        self.assertEqual(choices, {'look': 'ref:cool-reference'})

    # --- Fix round 1, finding 5: brief.md must already agree with choices.json at creation ---

    def test_brief_choices_block_reflects_the_reference_look_at_creation(self):
        record = new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en',
                                      'reference_id': 'cool-reference'})
        brief = (self.root / 'projects' / record['id'] / 'brief.md').read_text(encoding='utf-8')
        self.assertIn('<!-- choices -->\n- Look: Style from inspiration\n<!-- /choices -->', brief)

    def test_brief_choices_block_reflects_the_reference_look_at_creation_in_hebrew(self):
        record = new_project.create({'title': 'הסרטון הראשון שלי', 'kind': 'faceless', 'video_language': 'he',
                                      'reference_id': 'cool-reference'})
        brief = (self.root / 'projects' / record['id'] / 'brief.md').read_text(encoding='utf-8')
        self.assertIn('<!-- choices -->\n- מראה: סגנון מהשראה\n<!-- /choices -->', brief)

    def test_brief_choices_block_stays_empty_without_a_reference(self):
        record = new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})
        brief = (self.root / 'projects' / record['id'] / 'brief.md').read_text(encoding='utf-8')
        self.assertIn('<!-- choices -->\n<!-- /choices -->', brief)

    def test_missing_reference_id_still_writes_empty_choices(self):
        record = new_project.create({'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'})
        choices = json.loads((self.root / 'projects' / record['id'] / 'choices.json').read_text(encoding='utf-8'))
        self.assertEqual(choices, {})

    def test_invalid_reference_id_is_rejected(self):
        with self.assertRaises(new_project.NewProjectError) as ctx:
            new_project.create({'title': 'Valid title', 'kind': 'faceless', 'video_language': 'en',
                                 'reference_id': 'Not Valid!'})
        self.assertEqual(ctx.exception.status, 400)
        self.assertFalse(self.registry.exists())

    def test_brief_section_strips_lang_markers_for_both_languages(self):
        for language in ('he', 'en'):
            with self.subTest(language=language):
                text = new_project.brief_section(language)
                self.assertNotIn('<!-- lang:', text)
                self.assertNotIn('<!-- /lang:', text)
                self.assertIn('<!-- choices -->', text)
                self.assertIn('<!-- /choices -->', text)


if __name__ == '__main__':
    unittest.main()
