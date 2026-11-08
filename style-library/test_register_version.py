"""Task 17: scripts/register_version.py registers a skill's storyboard or video version in the
studio through Matt's register.py: it keeps the draft record's own fields (kind, video
language, created date -- the next "Send to Claude" needs kind), keeps every earlier version,
and never approves anything."""
import importlib.util
import json
import tempfile
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

import library
import project_index as index
import review_actions as storage

REPO_ROOT = Path(__file__).resolve().parents[1]
_reg_spec = importlib.util.spec_from_file_location('studio_register', REPO_ROOT / 'scripts/register.py')
register = importlib.util.module_from_spec(_reg_spec)
_reg_spec.loader.exec_module(register)
_spec = importlib.util.spec_from_file_location('studio_register_version', REPO_ROOT / 'scripts/register_version.py')
rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rv)


class RegisterVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        self.registry = self.base / 'projects.json'
        self.draft = {'id': 'demo', 'title': 'איך להתחיל עם AI', 'kind': 'talking-head', 'video_language': 'he',
                      'state': 'draft', 'format': 'video', 'created_at': '2026-11-08T10:00:00+00:00',
                      'primary_artifact': None, 'artifacts': [], 'source_notes': []}
        self.registry.write_text(json.dumps({'schema_version': 1, 'projects': [self.draft]}), encoding='utf-8')
        self.patches = [patch.object(register, 'ROOT', self.root), patch.object(library, 'BASE', self.base),
                        patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry),
                        patch.object(storage, 'BASE', self.base), patch.object(storage, 'CATALOG', self.base / 'catalog.json'),
                        patch.object(storage, 'JOURNALS', self.base / 'runtime/review-actions'),
                        patch.object(rv, 'register', register)]
        for p in self.patches:
            p.start()
        self.project = self.root / 'projects/demo'
        board = self.project / 'versions/v01/storyboard'
        board.mkdir(parents=True)
        for n in (1, 2):
            (board / f'{n:02}.jpg').write_bytes(b'jpeg')
        (board / 'frames.json').write_text(json.dumps([
            {'path': 'versions/v01/storyboard/01.jpg', 'title': 'פתיחה', 'note': 'הכותרת נכנסת עם המילה הראשונה'},
            {'path': 'versions/v01/storyboard/02.jpg', 'title': 'סיום', 'note': 'קריאה לפעולה'}], ensure_ascii=False),
            encoding='utf-8')
        (self.project / 'versions/v01/renders').mkdir()
        (self.project / 'versions/v01/renders/draft.mp4').write_bytes(b'mp4')
        (self.project / 'versions/v01/cut.mp4').write_bytes(b'mp4')
        (self.project / 'brief.md').write_text('# brief', encoding='utf-8')
        (self.project / 'STATUS.md').write_text('# status', encoding='utf-8')

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def record(self):
        return json.loads(self.registry.read_text(encoding='utf-8'))['projects'][0]

    def storyboard(self):
        return rv.register_version(self.project, 'V01', 'storyboard', frames='versions/v01/storyboard/frames.json',
                                   preview='versions/v01/renders/draft.mp4', cut='versions/v01/cut.mp4',
                                   summary='סטוריבורד ראשון מוכן', next_step='לעבור על התמונות ולהשאיר הערות', lang='he')

    def test_storyboard_registration_keeps_the_draft_fields(self):
        result = self.storyboard()
        record = self.record()
        self.assertEqual(result['primary'], 'storyboard-v01')
        for key in ('kind', 'video_language', 'created_at', 'title'):
            self.assertEqual(record[key], self.draft[key])
        self.assertEqual((record['state'], record['stage'], record['primary_artifact']),
                         ('review', 'storyboard', 'storyboard-v01'))
        artifacts = {a['id']: a for a in record['artifacts']}
        self.assertEqual(artifacts['storyboard-v01']['type'], 'board')
        self.assertEqual(artifacts['storyboard-v01']['stage'], 'storyboard')
        self.assertEqual(artifacts['storyboard-v01']['frames'][0]['title'], 'פתיחה')
        self.assertEqual(artifacts['preview-v01']['stage'], 'storyboard')
        self.assertEqual(artifacts['cut-v01']['stage'], 'spoken')
        self.assertEqual(record['cover_path'], 'versions/v01/storyboard/01.jpg')
        self.assertEqual({n['path'] for n in record['source_notes']}, {'STATUS.md', 'review-notes.md', 'brief.md'})
        self.assertTrue((self.project / 'review-notes.md').exists())
        self.assertNotIn('review_decision', record)

    def test_next_version_keeps_history(self):
        self.storyboard()
        (self.project / 'versions/v02/renders').mkdir(parents=True)
        (self.project / 'versions/v02/renders/final.mp4').write_bytes(b'mp4')
        (self.project / 'versions/v02/renders/poster.jpg').write_bytes(b'jpeg')
        result = rv.register_version(self.project, 'V02', 'final', video='versions/v02/renders/final.mp4',
                                     poster='versions/v02/renders/poster.jpg', summary='גרסה 2 מוכנה',
                                     next_step='לצפות ולאשר', lang='he')
        record = self.record()
        artifacts = {a['id']: a for a in record['artifacts']}
        self.assertEqual(result['primary'], 'video-v02')
        self.assertEqual(artifacts['video-v02']['approval_kind'], 'final')
        self.assertEqual(artifacts['video-v02']['stage'], 'edit')
        self.assertEqual(artifacts['storyboard-v01']['role'], 'storyboard')  # earlier versions stay as they were
        self.assertEqual(record['stage'], 'edit')
        self.assertEqual(record['kind'], 'talking-head')

    def test_never_overwrites_a_registered_version(self):
        self.storyboard()
        with self.assertRaises(rv.RegisterError) as caught:
            self.storyboard()
        self.assertEqual(caught.exception.code, 'register.exists')

    def approve_current(self):
        project = next(p for p in index.public_index()['projects'] if p['id'] == 'demo')
        self.assertTrue(project['review']['enabled'])
        storage.apply_decision({'project_id': 'demo', 'artifact_id': project['primary_artifact'], 'action': 'approve',
                                'revision': project['review']['revision'], 'request_id': str(uuid.uuid4())})

    def final_files(self, version='v02'):
        (self.project / f'versions/{version}/renders').mkdir(parents=True, exist_ok=True)
        (self.project / f'versions/{version}/renders/final.mp4').write_bytes(b'mp4 ' + version.encode())
        (self.project / f'versions/{version}/renders/poster.jpg').write_bytes(b'jpeg ' + version.encode())
        return f'versions/{version}/renders/final.mp4'

    def test_final_after_an_approved_storyboard_keeps_every_decision(self):
        self.storyboard()
        self.approve_current()
        before = self.record()
        state_file = (self.project / 'approval-state.json').read_bytes()
        self.assertEqual((before['state'], before['stage'], before['review_decision']['kind']),
                         ('in_progress', 'edit', 'storyboard'))
        result = rv.register_version(self.project, 'V02', 'final', video=self.final_files(),
                                     poster='versions/v02/renders/poster.jpg', summary='גרסה סופית',
                                     next_step='לצפות ולאשר', lang='he')
        after = self.record()
        self.assertEqual(result['primary'], 'video-v02')
        for key in ('review_decision', 'approval', 'baseline', 'review_action', 'kind', 'video_language', 'created_at'):
            self.assertEqual(json.dumps(after.get(key), ensure_ascii=False), json.dumps(before.get(key), ensure_ascii=False))
        old = {a['id']: a for a in before['artifacts']}
        for artifact in after['artifacts']:
            if artifact['id'] in old:
                self.assertEqual(artifact, old[artifact['id']])  # the approved storyboard, untouched
        self.assertEqual((after['state'], after['primary_artifact']), ('review', 'video-v02'))
        self.assertEqual((self.project / 'approval-state.json').read_bytes(), state_file)
        project = next(p for p in index.public_index()['projects'] if p['id'] == 'demo')
        self.assertEqual((project['review']['kind'], project['review']['action']), ('final', 'approve'))
        self.assertTrue(project['review']['enabled'])  # the creator can now approve the final in the studio
        self.assertEqual(after['reference_entry']['media_path'], 'projects/demo/versions/v02/renders/final.mp4')
        # ... and that approval goes through (library entry made from the prepared seed).
        (self.base / 'catalog.json').write_text(json.dumps({'schema_version': 4, 'entries': [], 'techniques': []}),
                                                encoding='utf-8')
        self.approve_current()
        final = self.record()
        self.assertEqual((final['state'], final['review_decision']['kind']), ('final', 'final'))
        catalog = json.loads((self.base / 'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['entries'][0]['media_path'], 'projects/demo/versions/v02/renders/final.mp4')
        self.assertEqual(len(json.loads((self.project / 'approval-state.json').read_text(encoding='utf-8'))['events']), 2)

    def decide(self, action):
        project = next(p for p in index.public_index()['projects'] if p['id'] == 'demo')
        self.assertTrue(project['review']['enabled'])
        self.assertEqual(project['review']['action'], action)
        storage.apply_decision({'project_id': 'demo', 'artifact_id': project['primary_artifact'], 'action': action,
                                'revision': project['review']['revision'], 'request_id': str(uuid.uuid4())})

    def register_final(self, version):
        return rv.register_version(self.project, version.upper(), 'final', video=self.final_files(version),
                                   poster=f'versions/{version}/renders/poster.jpg', summary='גרסה סופית',
                                   next_step='לצפות ולאשר', lang='he')

    def test_first_final_approval_works_without_a_catalog(self):
        # Fresh install: nothing ever created style-library/catalog.json.
        self.storyboard()
        self.decide('approve')
        self.register_final('v02')
        self.assertFalse((self.base / 'catalog.json').exists())
        self.decide('approve')
        self.assertEqual(self.record()['state'], 'final')
        catalog = json.loads((self.base / 'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['schema_version'], 4)
        self.assertEqual(catalog['entries'][0]['media_path'], 'projects/demo/versions/v02/renders/final.mp4')

    def test_append_refuses_a_final_project_until_it_is_reopened(self):
        self.storyboard()
        self.decide('approve')
        self.register_final('v02')
        self.decide('approve')
        before = self.registry.read_bytes()
        state_file = (self.project / 'approval-state.json').read_bytes()
        with self.assertRaises(rv.RegisterError) as caught:
            self.register_final('v03')
        self.assertEqual(caught.exception.code, 'register.final')
        self.assertIn('פתיחה מחדש', caught.exception.message)
        self.assertIn('Reopen', caught.exception.message)
        with self.assertRaisesRegex(ValueError, 'register.final'):  # register.py itself refuses too
            self.append(primary_artifact='video-v03', artifacts=[
                {'id': 'video-v03', 'label': 'V03', 'type': 'video', 'version': 'V03', 'role': 'current',
                 'path': self.final_files('v03')}])
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertEqual((self.project / 'approval-state.json').read_bytes(), state_file)
        # After the creator presses "Reopen" in the studio, the next round can be appended.
        self.decide('reopen')
        result = self.register_final('v03')
        record = self.record()
        self.assertEqual((result['primary'], record['state']), ('video-v03', 'review'))
        self.assertEqual(record['review_decision']['action'], 'reopen')

    def test_register_cli_exits_non_zero_for_a_final_project(self):
        self.storyboard()
        self.decide('approve')
        self.register_final('v02')
        self.decide('approve')
        before = self.registry.read_bytes()
        entry = self.project / 'cli.json'
        entry.write_text(json.dumps({'id': 'demo', 'title': 't', 'format': 'video', 'state': 'review', 'stage': 'edit',
                                     'summary': 's', 'next_step': 'n', 'primary_artifact': 'video-v03',
                                     'source_notes': [], 'artifacts': [
                                         {'id': 'video-v03', 'label': 'V03', 'type': 'video', 'version': 'V03',
                                          'role': 'current', 'path': self.final_files('v03')}]}), encoding='utf-8')
        with patch('sys.argv', ['register.py', 'project', str(entry), '--append-version']), \
                patch('sys.stderr') as stderr, self.assertRaises(SystemExit) as caught:
            register.main()
        self.assertNotEqual(caught.exception.code, 0)
        self.assertIn('register.final', ''.join(str(c.args[0]) for c in stderr.write.call_args_list))
        self.assertEqual(self.registry.read_bytes(), before)

    def test_final_needs_a_poster(self):
        self.storyboard()
        with self.assertRaises(rv.RegisterError) as caught:
            rv.register_version(self.project, 'V02', 'final', video=self.final_files(), summary='s', next_step='n')
        self.assertIn('poster', caught.exception.message)

    def append(self, **changes):
        item = {'id': 'demo', 'title': 't', 'format': 'video', 'state': 'review', 'stage': 'edit', 'summary': 's',
                'next_step': 'n', 'primary_artifact': 'video-v02', 'source_notes': [],
                'artifacts': [{'id': 'video-v02', 'label': 'V02', 'type': 'video', 'version': 'V02', 'role': 'current',
                               'path': self.final_files()}]}
        item.update(changes)
        entry = self.project / 'append.json'
        entry.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
        return register.register('project', entry, append=True)

    def test_append_refuses_to_overwrite_an_approved_artifact(self):
        self.storyboard()
        self.approve_current()
        before = self.registry.read_bytes()
        approved = next(a for a in self.record()['artifacts'] if a['id'] == 'storyboard-v01')
        changed = dict(approved, frames=approved['frames'][:1])
        with self.assertRaisesRegex(ValueError, 'cannot be changed'):
            self.append(artifacts=[changed])
        with self.assertRaisesRegex(ValueError, 'saved decisions'):
            self.append(review_decision={'action': 'approve', 'artifact_id': 'video-v02'})
        with self.assertRaisesRegex(ValueError, 'in_progress or review'):
            self.append(state='final')
        self.assertEqual(self.registry.read_bytes(), before)

    def test_append_needs_a_registered_project_and_something_new(self):
        with self.assertRaisesRegex(ValueError, 'No registered project'):
            self.append(id='other')
        self.storyboard()
        record = self.record()
        entry = self.project / 'same.json'
        entry.write_text(json.dumps(dict(record, state='review')), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Nothing new'):
            register.register('project', entry, append=True)
        with self.assertRaisesRegex(ValueError, 'either'):
            register.register('project', entry, replace=True, append=True)

    def test_replace_still_refuses_a_record_with_decisions(self):
        self.storyboard()
        self.approve_current()
        entry = self.project / 'replace.json'
        entry.write_text(json.dumps(self.record(), ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'saved approvals'):
            register.register('project', entry, replace=True)

    def test_unknown_project_and_missing_files(self):
        with self.assertRaises(rv.RegisterError) as caught:
            rv.register_version(self.root / 'projects/other', 'V01', 'final', video='x.mp4', summary='s', next_step='n')
        self.assertEqual(caught.exception.code, 'register.unknown-project')
        with self.assertRaises(rv.RegisterError) as caught:
            rv.register_version(self.project, 'V01', 'final', video='versions/v01/missing.mp4', summary='s',
                                next_step='n')
        self.assertEqual(caught.exception.code, 'register.failed')
        self.assertEqual(self.record()['state'], 'draft')


if __name__ == '__main__':
    unittest.main()
