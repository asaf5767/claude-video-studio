"""User review writes run only against temporary fixtures, never the production projects."""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import project_index as index
import review_actions as reviews
import library
from serve import Handler


class QuietHandler(Handler):
    def log_message(self, *args): pass


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        self.project = self.root / 'projects' / 'demo'
        self.project.mkdir(parents=True)
        for name, text in [('STATUS.md', '# Demo\nReview V02; V01 accepted.\n'),
                           ('review-notes.md', '# Review decisions\nKeep the earlier edit.\n')]:
            (self.project / name).write_text(text, encoding='utf-8')
        (self.project / 'active-edit.json').write_text(json.dumps({'version': 2, 'review_file': 'review.mp4'}), encoding='utf-8')
        (self.project / 'review.mp4').write_bytes(b'current video fixture')
        (self.project / 'frame.png').write_bytes(b'png fixture')
        self.p = {'id': 'demo', 'title': 'Demo', 'format': 'video', 'state': 'review', 'stage': 'refine',
                  'summary': 'Review V02.', 'next_step': 'Watch V02.', 'primary_artifact': 'review',
                  'reference_id': 'demo-video', 'source_notes': [], 'artifacts': [
                      {'id': 'review', 'type': 'video', 'path': 'review.mp4', 'version': 'V02',
                       'label': 'Latest review', 'role': 'current', 'approval_kind': 'final'},
                      {'id': 'old-review', 'type': 'video', 'path': 'review.mp4', 'version': 'V01',
                       'label': 'Earlier review', 'role': 'history'}]}
        for name in ['STATUS.md', 'review-notes.md', 'active-edit.json']:
            self.p['source_notes'].append({'path': name, 'label': name,
                'sha256': hashlib.sha256((self.project / name).read_bytes()).hexdigest()})
        self.entry = {'id': 'demo-video', 'collection': 'mine', 'version': 'V02',
                      'media_path': 'projects/demo/review.mp4', 'review_status': 'review_pending',
                      'traits': {'Motion': 'Keep this analysis'}, 'moments': [{'time': 1, 'label': 'Keep this moment'}]}
        self.registry = self.base / 'projects.json'
        self.catalog = self.base / 'catalog.json'
        self.catalog.write_text(json.dumps({'entries': [self.entry], 'techniques': [{'id': 'unchanged', 'examples': []}]}), encoding='utf-8')
        self.save()
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry),
                        patch.object(reviews, 'BASE', self.base), patch.object(reviews, 'CATALOG', self.catalog),
                        patch.object(reviews, 'JOURNALS', self.base / 'runtime/review-actions')]
        for p in self.patches: p.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def save(self):
        self.registry.write_text(json.dumps({'projects': [self.p]}), encoding='utf-8')

    def body(self, action='approve'):
        p = index.public_index()['projects'][0]
        return {'project_id': 'demo', 'artifact_id': p['primary_artifact'], 'action': action,
                'revision': p['review']['revision'], 'request_id': str(uuid.uuid4())}

    def test_final_approval_is_persistent_exact_and_idempotent(self):
        before_video = (self.project / 'review.mp4').read_bytes()
        body = self.body()
        result = reviews.apply_decision(body)
        p = result['projects'][0]
        self.assertEqual(p['state'], 'final')
        self.assertFalse(p['stale'])
        self.assertEqual(p['review']['action'], 'reopen')
        status = (self.project / 'STATUS.md').read_text(encoding='utf-8')
        self.assertIn('Final approved: Latest review V02', status)
        self.assertIn('Review V02; V01 accepted.', status)
        events = json.loads((self.project / 'approval-state.json').read_text(encoding='utf-8'))['events']
        self.assertEqual(events[0]['version'], 'V02')
        self.assertEqual(events[0]['files'][0]['sha256'], hashlib.sha256(before_video).hexdigest())
        self.assertEqual(json.loads((self.project / 'active-edit.json').read_text(encoding='utf-8'))['studio_review']['version'], 'V02')
        entry = json.loads(self.catalog.read_text(encoding='utf-8'))['entries'][0]
        self.assertEqual(entry['delivery_status'], 'final')
        self.assertEqual(entry['traits'], self.entry['traits'])
        self.assertEqual(entry['moments'], self.entry['moments'])
        self.assertTrue(reviews.apply_decision(body)['duplicate'])
        self.assertEqual(len(json.loads((self.project / 'approval-state.json').read_text(encoding='utf-8'))['events']), 1)
        self.assertEqual((self.project / 'review.mp4').read_bytes(), before_video)
        index.validate()

    def test_final_approval_preserves_intentionally_removed_reference(self):
        data=json.loads(self.catalog.read_text(encoding='utf-8'));marker={'demo-video':{'removed_at':'2026-10-27T12:00:00+00:00'}}
        data['removed_references']=marker;self.catalog.write_text(json.dumps(data), encoding='utf-8')
        reviews.apply_decision(self.body())
        after=json.loads(self.catalog.read_text(encoding='utf-8'))
        self.assertEqual(after['removed_references'],marker)
        self.assertEqual(after['entries'][0]['delivery_status'],'final')
        self.assertEqual((self.project/'review.mp4').read_bytes(),b'current video fixture')

    def test_final_recovers_one_exact_project_reference_without_duplicate_or_date_reset(self):
        self.p.pop('reference_id');self.save()
        data=json.loads(self.catalog.read_text(encoding='utf-8'))
        data['entries'][0].update(project_id='demo',created_at='2026-10-01T10:00:00Z')
        self.catalog.write_text(json.dumps(data), encoding='utf-8');body=self.body()
        result=reviews.apply_decision(body)
        self.assertEqual(result['projects'][0]['reference_id'],'demo-video')
        self.assertEqual(result['projects'][0]['state'],'final')
        saved=json.loads(self.catalog.read_text(encoding='utf-8'))
        self.assertEqual(len(saved['entries']),1)
        self.assertEqual(saved['entries'][0]['created_at'],'2026-10-01T10:00:00Z')
        self.assertEqual(saved['entries'][0]['traits'],self.entry['traits'])
        self.assertEqual(saved['entries'][0]['moments'],self.entry['moments'])
        self.assertTrue(reviews.apply_decision(body)['duplicate'])

    def test_missing_reference_link_never_recovers_ambiguous_or_mismatched_sources(self):
        for extra in [{'project_id':'other'}, {'version':'V99'}, {'media_path':'projects/demo/old.mp4'}, {'asset_type':'carousel'},
                      {'source_sha256':'0'*64}, {'archived_from':'other'}, {'removed':True}, {'ambiguous':True}, {'explicit':True}]:
            with self.subTest(extra=extra):
                self.p.pop('reference_id',None)
                if extra.get('explicit'):self.p['reference_id']='missing-explicit-link'
                self.save()
                entry={**self.entry,'project_id':'demo',**{k:v for k,v in extra.items() if k not in ['removed','ambiguous','explicit']}}
                data={'entries':[entry],'techniques':[]}
                if extra.get('removed'):data['removed_references']={'demo-video':{'removed_at':'2026-10-27T12:00:00Z'}}
                if extra.get('ambiguous'):data['entries'].append({**entry,'id':'second-match'})
                self.catalog.write_text(json.dumps(data), encoding='utf-8');before={p:p.read_bytes() for p in [self.registry,self.catalog,self.project/'STATUS.md']}
                with self.assertRaises(reviews.ReviewError):reviews.apply_decision(self.body())
                self.assertFalse((self.project/'approval-state.json').exists())
                self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_reopen_preserves_final_reference_and_history(self):
        reviews.apply_decision(self.body())
        result = reviews.apply_decision(self.body('reopen'))
        p = result['projects'][0]
        self.assertEqual((p['state'], p['review_action'], p['review']['action']), ('review', 'reopened', 'approve'))
        self.assertFalse(p['stale'])
        self.assertEqual(len(json.loads((self.project / 'approval-state.json').read_text(encoding='utf-8'))['events']), 2)
        self.assertEqual(json.loads(self.catalog.read_text(encoding='utf-8'))['entries'][0]['delivery_status'], 'final')
        self.assertIn('Reopened for changes', (self.project / 'STATUS.md').read_text(encoding='utf-8'))

    def test_milestones_advance_only_their_stage_and_do_not_register_a_final(self):
        for kind, expected in [('spoken_cut', 'storyboard'), ('storyboard', 'edit')]:
            self.p = json.loads(self.registry.read_text(encoding='utf-8'))['projects'][0]
            self.p['artifacts'][0]['approval_kind'] = kind
            self.p.pop('review_decision', None)
            self.save()
            result = reviews.apply_decision(self.body())
            p = result['projects'][0]
            self.assertEqual((p['state'], p['stage']), ('in_progress', expected))
            self.assertNotIn('delivery_status', json.loads(self.catalog.read_text(encoding='utf-8'))['entries'][0])

    def test_stale_notes_media_and_old_artifact_cannot_be_approved(self):
        body = self.body()
        (self.project / 'review.mp4').write_bytes(b'changed current video')
        with self.assertRaises(reviews.ReviewError): reviews.apply_decision(body)
        body = self.body()
        (self.project / 'STATUS.md').write_text('New decisions.', encoding='utf-8')
        with self.assertRaises(reviews.ReviewError): reviews.apply_decision(body)
        self.assertFalse((self.project / 'approval-state.json').exists())
        self.p['source_notes'][0]['sha256'] = index.digest(self.project / 'STATUS.md')
        self.save()
        body = self.body(); body['artifact_id'] = 'old-review'
        with self.assertRaises(reviews.ReviewError): reviews.apply_decision(body)

    def test_library_version_mismatch_fails_before_any_metadata_write(self):
        original = (self.project / 'STATUS.md').read_bytes()
        data = json.loads(self.catalog.read_text(encoding='utf-8')); data['entries'][0]['version'] = 'V99'
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(reviews.ReviewError): reviews.apply_decision(self.body())
        self.assertEqual((self.project / 'STATUS.md').read_bytes(), original)
        self.assertFalse((self.project / 'approval-state.json').exists())

    def test_final_promotes_registered_older_source_and_preserves_technique_excerpt(self):
        (self.project/'old.mp4').write_bytes(b'prior accepted video')
        self.p['cover_path']='frame.png';self.p['artifacts'][0]['duration']=3
        self.p['artifacts'][1]['path']='old.mp4';self.save()
        data=json.loads(self.catalog.read_text(encoding='utf-8'));e=data['entries'][0]
        e.update(version='V01',media_path='projects/demo/old.mp4',project_id='demo',duration=3)
        example={'id':'old-move','style_id':'demo-video','source_version':'V01','source_path':e['media_path'],
                 'source_sha256':index.digest(self.project/'old.mp4'),'start':0,'end':1}
        data['techniques']=[{'id':'tech-old','examples':[example]}]
        data['removed_references']={'demo-video':{'removed_at':'2026-10-27T00:00:00Z'}}
        self.catalog.write_text(json.dumps(data), encoding='utf-8');body=self.body()
        reviews.apply_decision(body);after=json.loads(self.catalog.read_text(encoding='utf-8'))
        current=next(e for e in after['entries'] if e['id']=='demo-video')
        archived=next(e for e in after['entries'] if e.get('archived_from')=='demo-video')
        self.assertEqual((current['version'],current['media_path'],current['duration']),('V02','projects/demo/review.mp4',3))
        self.assertEqual(current['moments'],[])
        self.assertEqual((archived['version'],archived['media_path'],archived['traits']),('V01','projects/demo/old.mp4',self.entry['traits']))
        self.assertEqual(after['techniques'][0]['examples'][0],{**example,'style_id':archived['id']})
        self.assertEqual(after['removed_references'],data['removed_references'])
        self.assertEqual((self.project/'old.mp4').read_bytes(),b'prior accepted video')
        self.assertTrue(reviews.apply_decision(body)['duplicate'])
        self.assertEqual(len(json.loads(self.catalog.read_text(encoding='utf-8'))['entries']),2)

    def test_promotion_keeps_stale_or_foreign_sources_blocked(self):
        self.p['cover_path']='frame.png';self.save()
        for update in [{'version':'V01','project_id':'another-project'}, {'version':'V99'}]:
            data=json.loads(self.catalog.read_text(encoding='utf-8'));data['entries'][0].update(update);self.catalog.write_text(json.dumps(data), encoding='utf-8')
            before=self.catalog.read_bytes()
            with self.assertRaises(reviews.ReviewError):reviews.apply_decision(self.body())
            self.assertEqual(self.catalog.read_bytes(),before)
            self.assertFalse((self.project/'approval-state.json').exists())

    def test_changed_technique_source_is_not_silently_promoted(self):
        data = json.loads(self.catalog.read_text(encoding='utf-8'))
        data['techniques'] = [{'id': 'tech-demo', 'examples': [{'style_id': 'demo-video',
            'source_version': 'V02', 'source_path': 'projects/demo/review.mp4', 'source_sha256': '0' * 64}]}]
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(reviews.ReviewError, 'technique examples'):
            reviews.apply_decision(self.body())
        self.assertFalse((self.project / 'approval-state.json').exists())

    def test_failed_save_restores_every_written_file(self):
        paths = [self.project / 'STATUS.md', self.project / 'review-notes.md', self.project / 'active-edit.json', self.registry, self.catalog]
        before = {p: p.read_bytes() for p in paths}
        real_write = reviews.atomic_write
        failed = False
        def fail_once(path, data):
            nonlocal failed
            if path == self.registry and not failed:
                failed = True
                raise OSError('simulated disk error')
            return real_write(path, data)
        with patch.object(reviews, 'atomic_write', side_effect=fail_once):
            with self.assertRaises(reviews.ReviewError): reviews.apply_decision(self.body())
        self.assertTrue(failed)
        for path in paths: self.assertEqual(path.read_bytes(), before[path])
        self.assertFalse((self.project / 'approval-state.json').exists())
        manifest = next(reviews.JOURNALS.glob('*/transaction.json'))
        self.assertEqual(json.loads(manifest.read_text(encoding='utf-8'))['state'], 'rolled_back')

    def test_symlinked_status_cannot_be_written(self):
        outside = self.root / 'private.md'; outside.write_text('Untouched', encoding='utf-8')
        (self.project / 'STATUS.md').unlink(); (self.project / 'STATUS.md').symlink_to(outside)
        with self.assertRaises(reviews.ReviewError): reviews.apply_decision(self.body())
        self.assertEqual(outside.read_text(encoding='utf-8'), 'Untouched')

    def test_new_library_entry_uses_saved_project_artwork(self):
        self.p.pop('reference_id')
        self.catalog.write_text(json.dumps({'entries': [], 'techniques': []}), encoding='utf-8')
        self.p['reference_entry'] = {**self.entry, 'title': 'Demo', 'subtitle': 'Demo subtitle', 'creator': 'Owner',
            'creator_id': 'owner', 'summary': 'Saved source', 'tags': [], 'palette': ['#222222'], 'keep': [],
            'avoid': [], 'notes': ['projects/demo/review-notes.md'], 'evidence': 'Project notes'}
        self.p['reference_poster_source'] = 'frame.png'; self.save()
        result = reviews.apply_decision(self.body())
        self.assertEqual(result['projects'][0]['reference_id'], 'demo-video')
        e = json.loads(self.catalog.read_text(encoding='utf-8'))['entries'][0]
        self.assertEqual((self.base / 'dist' / e['poster']).read_bytes(), (self.project / 'frame.png').read_bytes())
        self.assertEqual(e['delivery_status'], 'final')

    def test_legacy_project_gets_a_status_file_without_replacing_old_notes(self):
        (self.project / 'STATUS.md').unlink()
        self.p['source_notes'] = [n for n in self.p['source_notes'] if n['path'] != 'STATUS.md']
        self.save()
        result = reviews.apply_decision(self.body())
        self.assertTrue((self.project / 'STATUS.md').exists())
        self.assertFalse(result['projects'][0]['stale'])
        self.assertIn('Keep the earlier edit.', (self.project / 'review-notes.md').read_text(encoding='utf-8'))
        self.assertEqual(len(json.loads((self.project / 'approval-state.json').read_text(encoding='utf-8'))['events']), 1)

    def test_approved_presentation_registers_a_project_reference(self):
        self.p.pop('reference_id')
        self.p['format'] = 'presentation'
        self.p['artifacts'][0].update(type='board', frames=[{'path': 'frame.png', 'title': 'Slide one'}])
        self.p['artifacts'][0].pop('path')
        seed = {**self.entry, 'asset_type': 'project', 'project_id': 'demo', 'media_path': None,
            'title': 'Demo section', 'subtitle': 'Presentation', 'creator': 'Owner', 'creator_id': 'owner',
            'summary': 'Saved slides', 'tags': ['Presentation'], 'palette': ['#222222'], 'keep': [],
            'avoid': [], 'moments': [], 'notes': ['projects/demo/review-notes.md'], 'evidence': 'Project notes'}
        self.p.update(reference_entry=seed, reference_poster_source='frame.png')
        self.catalog.write_text(json.dumps({'entries': [], 'techniques': []}), encoding='utf-8'); self.save()
        result = reviews.apply_decision(self.body())
        self.assertEqual(result['projects'][0]['state'], 'final')
        entry = json.loads(self.catalog.read_text(encoding='utf-8'))['entries'][0]
        self.assertEqual((entry['asset_type'], entry['project_id']), ('project', 'demo'))

    def test_interrupted_transaction_can_be_recovered(self):
        class PowerLoss(BaseException): pass
        body = self.body()
        before_catalog = self.catalog.read_bytes()
        real = reviews.atomic_write
        def stop(path, data):
            if path == self.project / 'STATUS.md': raise PowerLoss()
            return real(path, data)
        with patch.object(reviews, 'atomic_write', side_effect=stop):
            with self.assertRaises(PowerLoss): reviews.apply_decision(body)
        self.assertTrue((self.project / 'approval-state.json').exists())
        reviews.recover(body['request_id'])
        self.assertFalse((self.project / 'approval-state.json').exists())
        self.assertEqual(self.catalog.read_bytes(), before_catalog)
        self.assertFalse(index.public_index()['projects'][0]['stale'])

    def test_external_library_change_during_save_is_not_overwritten(self):
        real = reviews.commit
        def concurrent(changes, body, expected):
            self.catalog.write_text(json.dumps({'entries': [], 'note': 'Later human edit'}), encoding='utf-8')
            return real(changes, body, expected)
        with patch.object(reviews, 'commit', side_effect=concurrent):
            with self.assertRaises(reviews.ReviewError): reviews.apply_decision(self.body())
        self.assertIn('Later human edit', self.catalog.read_text(encoding='utf-8'))
        self.assertFalse((self.project / 'approval-state.json').exists())

    def test_post_requires_same_origin_explicit_header_and_bounded_json(self):
        body = json.dumps(self.body())
        valid = {'Origin': self.origin, 'X-Studio-Action': 'review', 'Content-Type': 'application/json'}
        def request(headers, value=body):
            c = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
            c.request('POST', '/review-action', body=value, headers=headers)
            r = c.getresponse(); result = (r.status, r.read()); c.close(); return result
        for key in ['Origin', 'X-Studio-Action']:
            headers = valid.copy(); headers.pop(key)
            self.assertEqual(request(headers)[0], 403)
        for extra in [{'Origin': 'https://example.invalid'}, {'Host': 'example.invalid'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(request({**valid, **extra})[0], 403)
        self.assertEqual(request({**valid, 'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(request(valid, 'x' * 8193)[0], 413)
        self.assertEqual(request(valid, '{broken json')[0], 400)
        self.assertEqual(request(valid)[0], 200)
        self.assertEqual(request(valid)[0], 200)  # Same request is idempotent.


if __name__ == '__main__': unittest.main()
