"""Registration order: new projects list first, replacements stay put, references still append."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from datetime import datetime
from unittest.mock import patch
import library
import project_index as index
import review_actions as storage

path = Path(__file__).resolve().parents[1] / 'scripts/register.py'
spec = importlib.util.spec_from_file_location('studio_register', path)
register = importlib.util.module_from_spec(spec)
spec.loader.exec_module(register)


class RegisterOrderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        self.registry = self.base / 'projects.json'
        self.registry.write_text(json.dumps({'schema_version': 1, 'projects': [
            {'id': 'recent', 'title': 'Recent'}, {'id': 'middle', 'title': 'Middle'}, {'id': 'oldest', 'title': 'Oldest'}]}), encoding='utf-8')
        self.patches = [patch.object(register, 'ROOT', self.root), patch.object(library, 'BASE', self.base),
                        patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry),
                        patch.object(storage, 'BASE', self.base), patch.object(storage, 'CATALOG', self.base/'catalog.json'),
                        patch.object(storage, 'JOURNALS', self.base/'runtime/review-actions')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def descriptor(self, slug, title):
        project = self.root / 'projects' / slug
        project.mkdir(parents=True, exist_ok=True)
        (project / 'STATUS.md').write_text('Review V01.', encoding='utf-8')
        (project / 'review.mp4').write_bytes(b'synthetic fixture')
        manifest = project / 'studio-entry.json'
        manifest.write_text(json.dumps({
            'id': slug, 'title': title, 'format': 'video', 'summary': 'Synthetic fixture.', 'next_step': 'Review V01.',
            'state': 'review', 'stage': 'edit', 'primary_artifact': 'review',
            'source_notes': [{'label': 'Status', 'path': 'STATUS.md'}],
            'artifacts': [{'id': 'review', 'label': 'Review', 'type': 'video', 'version': 'v01',
                           'path': 'review.mp4', 'role': 'current'}]}), encoding='utf-8')
        return manifest

    def projects(self):
        return json.loads(self.registry.read_text(encoding='utf-8'))['projects']

    def reference(self, **fields):
        poster = self.base/'dist/assets/fixture.png'
        poster.parent.mkdir(parents=True, exist_ok=True)
        poster.write_bytes(b'synthetic poster')
        item = {'id': 'demo-reference', 'title': 'Demo reference', 'subtitle': 'Fixture', 'version': 'v01',
                'collection': 'mine', 'project_id': 'demo', 'media_path': 'projects/demo/review.mp4',
                'creator': 'Owner', 'creator_id': 'owner', 'summary': 'Synthetic fixture', 'tags': [],
                'palette': [], 'traits': {}, 'keep': [], 'avoid': [], 'moments': [], 'notes': [],
                'poster': 'assets/fixture.png', 'evidence': 'Synthetic fixture', **fields}
        manifest = self.root/'reference.json'
        manifest.write_text(json.dumps(item), encoding='utf-8')
        return manifest

    def catalog(self):
        return json.loads((self.base/'catalog.json').read_text(encoding='utf-8'))

    def test_reference_registration_dates_and_links_both_arrival_orders(self):
        for project_first in [True, False]:
            with self.subTest(project_first=project_first):
                self.registry.write_text('{"projects":[]}', encoding='utf-8')
                (self.base/'catalog.json').write_text('{"entries":[],"techniques":[]}', encoding='utf-8')
                project = self.descriptor('demo', 'Demo')
                reference = self.reference()
                order = [('project', project), ('reference', reference)]
                if not project_first:order.reverse()
                for kind, manifest in order:register.register(kind, manifest)
                self.assertEqual(self.projects()[0]['reference_id'], 'demo-reference')
                self.assertIsNotNone(datetime.fromisoformat(self.catalog()['entries'][0]['created_at']).tzinfo)

    def test_replacements_keep_original_date_and_link_and_undated_records_stay_unknown(self):
        register.register('project', self.descriptor('demo', 'Demo'))
        manifest = self.reference(created_at='2026-10-01T10:00:00Z')
        register.register('reference', manifest)
        register.register('reference', self.reference(created_at='2026-11-05T10:00:00Z'), replace=True)
        self.assertEqual(self.catalog()['entries'][0]['created_at'], '2026-10-01T10:00:00Z')
        register.register('project', self.descriptor('demo', 'Updated'), replace=True)
        self.assertEqual(self.projects()[0]['reference_id'], 'demo-reference')
        data = self.catalog();data['entries'][0].pop('created_at')
        (self.base/'catalog.json').write_text(json.dumps(data), encoding='utf-8')
        register.register('reference', self.reference(), replace=True)
        self.assertNotIn('created_at', self.catalog()['entries'][0])
        data = self.catalog();data['entries'][0]['added_on']='2026-09-01'
        (self.base/'catalog.json').write_text(json.dumps(data), encoding='utf-8')
        register.register('reference', self.reference(created_at='2026-11-05'), replace=True)
        self.assertNotIn('created_at', self.catalog()['entries'][0])
        self.assertEqual(self.catalog()['entries'][0]['added_on'], '2026-09-01')

    def test_registration_does_not_guess_a_project_link(self):
        for extra in [{'version': 'another'}, {'project_id': 'other'}, {'media_path': 'projects/demo/other.mp4'}, {'collection':'reference'}]:
            with self.subTest(extra=extra):
                self.registry.write_text('{"projects":[]}', encoding='utf-8')
                (self.base/'catalog.json').write_text('{"entries":[],"techniques":[]}', encoding='utf-8')
                self.descriptor('demo', 'Demo');(self.root/'projects/demo/other.mp4').write_bytes(b'other')
                register.register('reference', self.reference(**extra))
                register.register('project', self.descriptor('demo', 'Demo'))
                self.assertNotIn('reference_id', self.projects()[0])

    def test_two_file_registration_rolls_back_and_preserves_concurrent_writes(self):
        register.register('project', self.descriptor('demo', 'Demo'))
        (self.base/'catalog.json').write_text('{"entries":[],"techniques":[]}', encoding='utf-8')
        manifest = self.reference();before_index=self.registry.read_bytes();before_catalog=(self.base/'catalog.json').read_bytes()
        original=storage.atomic_write;failed=False
        def failure(path, value):
            nonlocal failed
            if path==self.registry.resolve() and not failed:failed=True;raise OSError('fixture failure')
            return original(path, value)
        with patch.object(storage, 'atomic_write', side_effect=failure), self.assertRaises(storage.ReviewError):
            register.register('reference', manifest)
        self.assertEqual(self.registry.read_bytes(), before_index)
        self.assertEqual((self.base/'catalog.json').read_bytes(), before_catalog)
        commit=storage.commit
        def changed(*args):
            (self.base/'catalog.json').write_text('{"entries":[],"techniques":[],"owner_change":true}', encoding='utf-8')
            return commit(*args)
        with patch.object(storage, 'commit', side_effect=changed), self.assertRaises(storage.ReviewError):
            register.register('reference', manifest)
        self.assertEqual(self.registry.read_bytes(), before_index)
        self.assertTrue(self.catalog()['owner_change'])

    def test_ambiguous_links_and_invalid_new_dates_leave_registration_unchanged(self):
        project=self.descriptor('demo','Demo');manifest=self.reference(created_at='not-a-date')
        before=self.registry.read_bytes()
        with self.assertRaisesRegex(ValueError,'ISO date'):register.register('reference',manifest)
        self.assertEqual(self.registry.read_bytes(),before)
        self.assertFalse((self.base/'catalog.json').exists())
        register.register('reference',self.reference())
        data=self.catalog();data['entries'].append({**data['entries'][0],'id':'second-match'})
        (self.base/'catalog.json').write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'More than one'):register.register('project',project)
        self.assertEqual(self.registry.read_bytes(),before)

    def test_new_projects_are_listed_first(self):
        register.register('project', self.descriptor('newer', 'Newer'))
        register.register('project', self.descriptor('newest', 'Newest'))
        self.assertEqual([p['id'] for p in self.projects()], ['newest', 'newer', 'recent', 'middle', 'oldest'])

    def test_replacement_keeps_its_position(self):
        register.register('project', self.descriptor('middle', 'Middle, revised'), replace=True)
        projects = self.projects()
        self.assertEqual([p['id'] for p in projects], ['recent', 'middle', 'oldest'])
        self.assertEqual(projects[1]['title'], 'Middle, revised')

    def test_existing_id_without_replace_changes_nothing(self):
        before = self.registry.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            register.register('project', self.descriptor('middle', 'Middle, revised'))
        self.assertEqual(self.registry.read_bytes(), before)

    def test_one_script_request_can_only_be_registered_to_one_project(self):
        request_id = str(uuid.uuid4())
        first = self.descriptor('draft-one', 'First draft')
        first.write_text(json.dumps({**json.loads(first.read_text()), 'starter_request_id': request_id}), encoding='utf-8')
        register.register('project', first)
        other = self.descriptor('draft-two', 'Other draft')
        other.write_text(json.dumps({**json.loads(other.read_text()), 'starter_request_id': request_id}), encoding='utf-8')
        before = self.registry.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already has a project'):
            register.register('project', other)
        self.assertEqual(self.registry.read_bytes(), before)
        register.register('project', self.descriptor('draft-one', 'Updated draft'), replace=True)
        self.assertEqual(self.projects()[0]['starter_request_id'], request_id)

    def test_new_references_still_append(self):
        catalog = self.base / 'catalog.json'
        catalog.write_text(json.dumps({'schema_version': 4, 'entries': [{'id': 'saved-earlier'}], 'techniques': []}), encoding='utf-8')
        poster = self.base / 'dist' / 'assets' / 'fixture.png'
        poster.parent.mkdir(parents=True)
        poster.write_bytes(b'synthetic poster')
        manifest = self.root / 'reference.json'
        manifest.write_text(json.dumps({
            'id': 'saved-later', 'title': 'Saved later', 'subtitle': 'Fixture', 'version': 'v1', 'collection': 'reference',
            'creator': 'Fixture creator', 'creator_id': 'fixture-creator', 'summary': 'Synthetic fixture.', 'tags': [],
            'palette': [], 'traits': [], 'keep': [], 'avoid': [], 'moments': [], 'notes': [],
            'poster': 'assets/fixture.png', 'evidence': 'Synthetic fixture.'}), encoding='utf-8')
        register.register('reference', manifest)
        self.assertEqual([e['id'] for e in json.loads(catalog.read_text(encoding='utf-8'))['entries']], ['saved-earlier', 'saved-later'])


if __name__ == '__main__':
    unittest.main()
