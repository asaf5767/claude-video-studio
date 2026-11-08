"""Task 10: choices.save()/current() -- tap-to-choose project choices written into
choices.json and into the <!-- choices --> block of brief.md, in the project's own
video language."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import project_index as index
import choices


class ChoicesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Path(self.temp.name).resolve()
        self.registry_path = self.studio / 'projects.json'
        self.catalog_path = self.studio / 'catalog.json'
        self.patches = [
            patch.object(index, 'STUDIO', self.studio),
            patch.object(index, 'REGISTRY', self.registry_path),
            patch.object(choices, 'CATALOG', self.catalog_path),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def make_project(self, project_id='demo', video_language='he', brief=None):
        root = self.studio / 'projects' / project_id
        root.mkdir(parents=True)
        (root / 'choices.json').write_text('{}', encoding='utf-8')
        default_brief = (
            '# תקציר הסרטון\n\n- כותרת: demo\n\n<!-- choices -->\n<!-- /choices -->\n'
            if video_language == 'he' else
            '# Video brief\n\n- Title: demo\n\n<!-- choices -->\n<!-- /choices -->\n'
        )
        (root / 'brief.md').write_text(brief if brief is not None else default_brief, encoding='utf-8')
        registry = json.loads(self.registry_path.read_text(encoding='utf-8')) if self.registry_path.exists() else {'schema_version': 1, 'projects': []}
        registry['projects'].append({'id': project_id, 'title': project_id, 'kind': 'faceless', 'video_language': video_language,
                                      'state': 'draft', 'format': 'video', 'created_at': '2026-01-01T00:00:00+00:00',
                                      'primary_artifact': None, 'artifacts': [], 'source_notes': []})
        self.registry_path.write_text(json.dumps(registry), encoding='utf-8')
        return root

    def add_reference(self, reference_id='cool-reference'):
        data = json.loads(self.catalog_path.read_text(encoding='utf-8')) if self.catalog_path.exists() else {'schema_version': 4, 'entries': []}
        data['entries'].append({'id': reference_id, 'title': 'Cool reference'})
        self.catalog_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def saved_choices(self, project_id='demo'):
        return json.loads((self.studio / 'projects' / project_id / 'choices.json').read_text(encoding='utf-8'))

    def brief_text(self, project_id='demo'):
        return (self.studio / 'projects' / project_id / 'brief.md').read_text(encoding='utf-8')

    # --- test_valid_choices_written_to_json_and_brief ---

    def test_valid_choices_written_to_json_and_brief(self):
        self.make_project(video_language='he')
        result = choices.save('demo', {'cut': 'tight', 'sound': 'music-energetic', 'sfx': True})
        self.assertEqual(result['cut'], 'tight')
        self.assertEqual(self.saved_choices(), {'cut': 'tight', 'sound': 'music-energetic', 'sfx': True})
        brief = self.brief_text()
        self.assertIn('- חיתוך: הדוק', brief)
        self.assertIn('- סאונד: מוזיקה אנרגטית, עם אפקטי סאונד', brief)
        self.assertEqual(brief.count('<!-- choices -->'), 1)

    def test_valid_choices_written_in_english_project(self):
        self.make_project(video_language='en')
        choices.save('demo', {'captions': True, 'length': '30-60'})
        brief = self.brief_text()
        self.assertIn('- Finish: Captions, 30–60 seconds', brief)

    # --- test_unknown_option_rejected ---

    def test_unknown_option_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'cut': 'bogus'})
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.message_key, 'choices.error.unknownOption')
        self.assertEqual(self.saved_choices(), {})

    def test_unknown_top_level_field_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'nonsense': 'x'})
        self.assertEqual(ctx.exception.status, 400)

    def test_bad_sound_and_length_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'sound': 'bogus'})
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'length': '1-2'})

    def test_non_boolean_sfx_and_captions_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'sfx': 'yes'})
        self.assertEqual(ctx.exception.message_key, 'choices.error.invalidRequest')
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'captions': 'yes'})

    def test_extra_too_long_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'extra': 'x' * 1001})
        self.assertEqual(ctx.exception.message_key, 'choices.error.extraTooLong')

    # --- test_effects_keep_order_and_when ---

    def test_effects_keep_order_and_when(self):
        self.make_project(video_language='he')
        effects = [{'effect': 'zoomthru', 'when': 'סוכנים'}, {'effect': 'marker', 'when': ''}]
        result = choices.save('demo', {'effects': effects})
        self.assertEqual(result['effects'], effects)
        self.assertEqual(self.saved_choices()['effects'], effects)
        brief = self.brief_text()
        self.assertIn('- אפקטים: זום דרך מילה [zoomthru] (כשאני אומר "סוכנים"); מרקר מדגיש [marker]', brief)

    def test_effects_rendered_in_english_project(self):
        self.make_project(video_language='en')
        choices.save('demo', {'effects': [{'effect': 'zoomthru', 'when': 'agents'}]})
        self.assertIn('- Effects: Zoom through a word [zoomthru] (when I say "agents")', self.brief_text())

    def test_malformed_effect_item_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'effects': [{'effect': 'zoomthru'}]})
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'effects': [{'effect': 'zoomthru', 'when': 'x' * 81}]})
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'effects': 'zoomthru'})

    def test_control_characters_rejected_in_when_and_extra(self):
        # Fix round 1: brief.md lines stay single lines -- real control characters are refused.
        self.make_project()
        for bad in ('line\nbreak', 'tab\there', 'cr\rhere', 'nul\x00', 'del\x7f', 'u2028\u2028x'):
            with self.assertRaises(choices.ChoicesError, msg=repr(bad)) as ctx:
                choices.save('demo', {'effects': [{'effect': 'marker', 'when': bad}]})
            self.assertEqual(ctx.exception.status, 400)
            with self.assertRaises(choices.ChoicesError, msg=repr(bad)):
                choices.save('demo', {'extra': bad})

    def test_comment_markers_kept_verbatim_but_neutralized_in_the_brief(self):
        # Ruling R35: any printable text is allowed. choices.json and the API keep it exactly;
        # only the brief.md block neutralizes <!-- / --> so the block markers can never break.
        self.make_project(video_language='he')
        extra = 'הערה --> עם <!-- סימנים -->'
        when = 'לפני --> אחרי'
        result = choices.save('demo', {'extra': extra, 'effects': [{'effect': 'marker', 'when': when}]})
        self.assertEqual(result['extra'], extra)
        self.assertEqual(result['effects'][0]['when'], when)
        self.assertEqual(self.saved_choices()['extra'], extra)
        self.assertEqual(choices.current('demo')['choices']['effects'][0]['when'], when)
        brief = self.brief_text()
        self.assertEqual(brief.count('<!--'), 2, 'only the two block markers')
        self.assertEqual(brief.count('-->'), 2, 'only the two block markers')
        self.assertIn('לפני → אחרי', brief)
        # round trip: a later save still finds and replaces the one block
        choices.save('demo', {'cut': 'tight'})
        brief = self.brief_text()
        self.assertEqual(brief.count('<!-- choices -->'), 1)
        self.assertEqual(brief.count('<!-- /choices -->'), 1)
        self.assertEqual(brief.count('<!--'), 2)
        self.assertEqual(brief.count('-->'), 2)
        self.assertIn('- חיתוך: הדוק', brief)
        self.assertIn('לפני → אחרי', brief)
        self.assertEqual(self.saved_choices()['extra'], extra)

    def test_when_with_an_arrow_saved_verbatim(self):
        self.make_project()
        result = choices.save('demo', {'effects': [{'effect': 'zoomthru', 'when': 'A → B'}]})
        self.assertEqual(result['effects'], [{'effect': 'zoomthru', 'when': 'A → B'}])

    def test_unknown_effect_id_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'effects': [{'effect': 'not-an-effect', 'when': ''}]})
        self.assertEqual(ctx.exception.message_key, 'choices.error.unknownOption')
        # a presenter look is not an effect
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'effects': [{'effect': 'popout', 'when': ''}]})

    def test_duplicate_effect_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'effects': [{'effect': 'marker', 'when': ''}, {'effect': 'marker', 'when': 'x'}]})

    # --- presenter look ("איך אתם נראים"), one per project ---

    def test_presenter_look_saved_and_rendered(self):
        self.make_project(video_language='he')
        result = choices.save('demo', {'presenter': 'popout'})
        self.assertEqual(result['presenter'], 'popout')
        self.assertEqual(self.saved_choices()['presenter'], 'popout')
        self.assertIn('- איך אתם נראים: יוצא מהמסגרת [popout]', self.brief_text())

    def test_presenter_look_rendered_in_english(self):
        self.make_project(video_language='en')
        choices.save('demo', {'presenter': 'green'})
        self.assertIn('- How you look: Green screen, new background [green]', self.brief_text())

    def test_presenter_null_clears_the_line(self):
        self.make_project(video_language='he')
        choices.save('demo', {'presenter': 'popout'})
        result = choices.save('demo', {'presenter': None})
        self.assertIsNone(result['presenter'])
        self.assertNotIn('איך אתם נראים', self.brief_text())

    def test_unknown_presenter_rejected(self):
        self.make_project()
        for bad in ('not-a-look', 'zoomthru', 'soft', 3, ['popout']):
            with self.assertRaises(choices.ChoicesError, msg=repr(bad)):
                choices.save('demo', {'presenter': bad})

    # --- test_brief_block_replaced_not_duplicated ---

    def test_brief_block_replaced_not_duplicated(self):
        self.make_project(video_language='he')
        choices.save('demo', {'cut': 'tight'})
        choices.save('demo', {'cut': 'natural'})
        brief = self.brief_text()
        self.assertEqual(brief.count('<!-- choices -->'), 1)
        self.assertEqual(brief.count('<!-- /choices -->'), 1)
        self.assertIn('- חיתוך: טבעי', brief)
        self.assertNotIn('הדוק', brief)

    def test_brief_block_appended_when_markers_missing(self):
        self.make_project(video_language='he', brief='# תקציר הסרטון\n\n- כותרת: demo\n')
        choices.save('demo', {'cut': 'tight'})
        brief = self.brief_text()
        self.assertEqual(brief.count('<!-- choices -->'), 1)
        self.assertIn('- חיתוך: הדוק', brief)
        self.assertIn('- כותרת: demo', brief)

    # --- test_ref_look_requires_existing_reference ---

    def test_ref_look_requires_existing_reference(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'look': 'ref:missing-reference'})
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.message_key, 'choices.error.unknownOption')
        self.add_reference('cool-reference')
        result = choices.save('demo', {'look': 'ref:cool-reference'})
        self.assertEqual(result['look'], 'ref:cool-reference')

    def test_builtin_look_accepted(self):
        self.make_project(video_language='he')
        result = choices.save('demo', {'look': 'soft'})
        self.assertEqual(result['look'], 'soft')
        self.assertIn('- מראה: ', self.brief_text())

    def test_unknown_builtin_look_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {'look': 'not-a-look'})

    # --- merge semantics: a later save never drops an earlier field it didn't mention ---

    def test_save_preserves_fields_not_in_the_patch(self):
        self.make_project()
        choices.save('demo', {'effects': [{'effect': 'zoomthru', 'when': ''}]})
        choices.save('demo', {'cut': 'tight'})
        saved = self.saved_choices()
        self.assertEqual(saved['cut'], 'tight')
        self.assertEqual(saved['effects'], [{'effect': 'zoomthru', 'when': ''}])

    # --- unknown / missing project ---

    def test_unknown_project_is_404(self):
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('missing', {'cut': 'tight'})
        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(ctx.exception.message_key, 'choices.error.unknownProject')

    def test_current_returns_choices_and_config(self):
        self.make_project()
        choices.save('demo', {'cut': 'tight'})
        result = choices.current('demo')
        self.assertEqual(result['choices']['cut'], 'tight')
        self.assertIn('cut', result['config'])
        self.assertIn('look', result['config'])

    def test_current_unknown_project_is_404(self):
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.current('missing')
        self.assertEqual(ctx.exception.status, 404)

    def test_empty_patch_rejected(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError):
            choices.save('demo', {})

    # --- Fix round 2, controller ruling R33: the server-side seq guard from fix round 1
    # is gone. save() is a plain last-request-wins merge; any leftover `_seq` key from an
    # old choices.json (written by that abandoned approach) must be silently absorbed and
    # never resurface, on every read, not just once. ---

    def test_save_no_longer_takes_a_seq_argument(self):
        self.make_project()
        with self.assertRaises(TypeError):
            choices.save('demo', {'cut': 'tight'}, seq={'cut': 1})

    def test_the_last_save_call_always_wins_plain_and_simple(self):
        self.make_project()
        choices.save('demo', {'cut': 'natural'})
        result = choices.save('demo', {'cut': 'tight'})
        self.assertEqual(result['cut'], 'tight')
        self.assertEqual(self.saved_choices()['cut'], 'tight')

    def test_legacy_seq_key_is_stripped_on_read_and_never_resurfaces(self):
        root = self.make_project(video_language='he')
        (root / 'choices.json').write_text(
            json.dumps({'cut': 'tight', '_seq': {'cut': 7}}, ensure_ascii=False), encoding='utf-8')
        current = choices.current('demo')
        self.assertNotIn('_seq', current['choices'])
        self.assertEqual(current['choices']['cut'], 'tight')
        result = choices.save('demo', {'sound': 'no-music'})
        self.assertNotIn('_seq', result)
        self.assertEqual(result, {'cut': 'tight', 'sound': 'no-music'})
        # The key is gone from disk too, the moment anything saves again.
        raw = json.loads((root / 'choices.json').read_text(encoding='utf-8'))
        self.assertNotIn('_seq', raw)
        self.assertNotIn('_seq', self.brief_text())

    def test_legacy_seq_key_never_reappears_even_across_repeated_reads(self):
        # Regression guard: an earlier draft of this fix only stripped `_seq` once
        # (inside save()'s merge) rather than in _read_choices() itself, so a bare
        # current() call right after a legacy file was written would still have leaked it.
        root = self.make_project()
        (root / 'choices.json').write_text(json.dumps({'_seq': {'cut': 3}}), encoding='utf-8')
        for _ in range(3):
            self.assertNotIn('_seq', choices.current('demo')['choices'])

    def test_a_seq_key_cannot_be_smuggled_in_through_a_normal_patch(self):
        self.make_project()
        with self.assertRaises(choices.ChoicesError) as ctx:
            choices.save('demo', {'_seq': {'cut': 1}})
        self.assertEqual(ctx.exception.status, 400)

    # --- Fix round 1, finding 5: a project created from an inspiration reference must
    # have brief.md agree with choices.json from the moment it is created ---

    def test_render_block_renders_a_ref_look_without_requiring_the_reference_to_exist(self):
        # render_block() is a pure renderer (new_project.py calls it before the project is
        # even registered) -- it must never depend on reference-existence validation,
        # which is choices.save()'s job once the project is real.
        block = choices.render_block('he', {'look': 'ref:does-not-exist-yet'})
        self.assertEqual(block, '<!-- choices -->\n- מראה: סגנון מהשראה\n<!-- /choices -->\n')

    def test_render_block_empty_choices_matches_the_template_default(self):
        self.assertEqual(choices.render_block('en', {}), '<!-- choices -->\n<!-- /choices -->\n')


if __name__ == '__main__':
    unittest.main()
