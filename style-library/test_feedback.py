"""Feedback stays attached to exact versions and cannot change approvals or escape a project."""
import copy
import http.client
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import feedback
import project_index as index
import review_actions as storage
from serve import Handler


class Quiet(Handler):
    def log_message(self, *args):
        pass


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        self.project = self.root / 'projects/demo'
        self.project.mkdir(parents=True)
        (self.project / 'cut.mp4').write_bytes(b'original-media')
        (self.project / 'scene.png').write_bytes(b'original-frame')
        (self.project / 'STATUS.md').write_text('Accepted V01, V02 pending.', encoding='utf-8')
        (self.project / 'approval-state.json').write_text('{"history":[]}', encoding='utf-8')
        self.record = {'id': 'demo', 'primary_artifact': 'edit-v02', 'source_notes': [],
                       'artifacts': [{'id': 'edit-v02', 'type': 'video', 'path': 'cut.mp4',
                                      'role': 'current', 'label': 'Larger cards', 'version': 'V02'},
                                     {'id': 'board-v01', 'type': 'board', 'role': 'history',
                                      'label': 'Storyboard', 'frames': [{'path': 'scene.png'}]}]}
        self.registry = self.base / 'projects.json'
        self.registry.write_text(json.dumps({'projects': [self.record]}), encoding='utf-8')
        (self.base / 'catalog.json').write_text('{"entries":[]}', encoding='utf-8')
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry),
                        patch.object(storage, 'BASE', self.base), patch.object(storage, 'CATALOG', self.base / 'catalog.json'),
                        patch.object(storage, 'JOURNALS', self.base / 'runtime/review-actions')]
        for p in self.patches:
            p.start()
        self.body = {'project_id': 'demo', 'artifact_id': 'edit-v02',
                     'context_revision': feedback.current('demo')['contexts']['edit-v02'],
                     'text': 'Make the cards larger.', 'time': 15.25, 'frame': None,
                     'request_id': str(uuid.uuid4())}
        self.before = {p: p.read_bytes() for p in self.project.iterdir()}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_persistence_exact_context_and_no_approval_or_media_changes(self):
        result = feedback.save(self.body)
        note = result['notes'][0]
        self.assertEqual((note['version'], note['time'], note['status']), ('V02', 15.25, 'open'))
        self.assertEqual(feedback.current('demo')['notes'], result['notes'])
        for p, before in self.before.items():
            self.assertEqual(p.read_bytes(), before)
        self.assertTrue(list(storage.JOURNALS.glob('*/transaction.json')))

    def test_retry_is_idempotent_and_reused_request_cannot_change_note(self):
        feedback.save(self.body)
        self.assertEqual(len(feedback.save(self.body)['notes']), 1)
        with self.assertRaises(feedback.FeedbackError):
            feedback.save({**self.body, 'text': 'Different request'})

    def test_changed_checkpoint_refuses_save_without_losing_previous_notes(self):
        feedback.save(self.body)
        before = (self.project / 'review-feedback.json').read_bytes()
        (self.project / 'cut.mp4').write_bytes(b'newer-media')
        with self.assertRaisesRegex(feedback.FeedbackError, 'changed'):
            feedback.save({**self.body, 'request_id': str(uuid.uuid4())})
        self.assertEqual((self.project / 'review-feedback.json').read_bytes(), before)

    def test_historical_storyboard_note_keeps_scene_and_rejects_invalid_positions(self):
        body = {**self.body, 'artifact_id': 'board-v01', 'time': None, 'frame': 1,
                'context_revision': feedback.current('demo')['contexts']['board-v01']}
        self.assertEqual(feedback.save(body)['notes'][0]['frame'], 1)
        for frame in [0, 2, True, 1.5]:
            with self.assertRaises(feedback.FeedbackError):
                feedback.save({**body, 'frame': frame, 'request_id': str(uuid.uuid4())})
        for time in [-1, float('nan'), float('inf'), True, '15']:
            with self.assertRaises(feedback.FeedbackError):
                feedback.save({**self.body, 'time': time, 'request_id': str(uuid.uuid4())})

    def test_concurrent_notes_are_both_preserved(self):
        errors = []
        def save():
            try:
                feedback.save({**self.body, 'request_id': str(uuid.uuid4())})
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=save) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertFalse(errors)
        self.assertEqual(len(feedback.current('demo')['notes']), 2)

    def test_symlink_and_malformed_inputs_never_write_outside_project(self):
        outside = self.root / 'outside.json'
        outside.write_text('{"keep":"safe"}', encoding='utf-8')
        (self.project / 'review-feedback.json').symlink_to(outside)
        with self.assertRaises(storage.ReviewError):
            feedback.save(self.body)
        self.assertEqual(outside.read_text(encoding='utf-8'), '{"keep":"safe"}')
        for delta in [{'project_id': '../escape'}, {'artifact_id': 'unknown'}, {'text': ''},
                      {'text': 'x' * 2001}, {'text': 'bad\x00note'}, {'request_id': 'bad'}]:
            with self.assertRaises((feedback.FeedbackError, storage.ReviewError)):
                feedback.save({**self.body, **delta})
        (self.project / 'review-feedback.json').unlink()
        sibling=self.project.with_name('sibling')
        self.project.rename(sibling)
        self.project.symlink_to(sibling, target_is_directory=True)
        with self.assertRaises(feedback.FeedbackError):
            feedback.save(self.body)
        self.assertFalse((sibling / 'review-feedback.json').exists())

    def test_endpoint_guards_and_reload_persistence(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        valid = {'Origin': origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'feedback'}
        def request(headers, method='POST', body=None):
            c = http.client.HTTPConnection('127.0.0.1', server.server_port)
            c.request(method, '/feedback' if method == 'POST' else '/feedback?project=demo',
                      json.dumps(self.body) if body is None and method == 'POST' else body, headers)
            r = c.getresponse()
            result = r.status, r.read()
            c.close()
            return result
        try:
            for extra in [{'Origin': 'https://example.invalid'}, {'Host': 'example.invalid'},
                          {'Sec-Fetch-Site': 'cross-site'}, {'X-Studio-Action': 'review'}]:
                self.assertEqual(request({**valid, **extra})[0], 403)
            self.assertEqual(request({'Content-Type': 'application/json'})[0], 403)
            self.assertEqual(request({**valid, 'Content-Type': 'text/plain'})[0], 415)
            self.assertEqual(request(valid, body='x' * 16385)[0], 413)
            self.assertEqual(request(valid, body='{bad')[0], 400)
            self.assertEqual(request(valid)[0], 200)
            self.assertEqual(len(json.loads(request({}, 'GET')[1])['notes']), 1)
            self.assertEqual(request({'Origin': 'https://example.invalid'}, 'GET')[0], 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_compact_link_is_stable_exact_and_preserves_notes_and_production_files(self):
        first = feedback.save(self.body)['notes'][0]
        second = feedback.save({**self.body, 'request_id': str(uuid.uuid4()), 'text': 'Second note'})['notes'][-1]
        body = {'project_id': 'demo', 'artifact_id': 'edit-v02', 'note_ids': [first['id'], second['id']]}
        notes_before = (self.project / 'review-feedback.json').read_bytes()
        link = feedback.save_link(body)
        path = self.project / 'review-feedback-links.json'
        before = path.read_bytes(), path.stat().st_mtime_ns
        self.assertEqual(feedback.save_link({**body, 'note_ids': list(reversed(body['note_ids']))}), link)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(len(link['id']), 24)
        self.assertEqual(set(feedback.current('demo', link['id'])['selection']['note_ids']), set(body['note_ids']))
        self.assertEqual((self.project / 'review-feedback.json').read_bytes(), notes_before)
        for file, content in self.before.items():
            self.assertEqual(file.read_bytes(), content)

    def test_link_rejects_unknown_duplicate_cross_version_and_applied_notes(self):
        note = feedback.save(self.body)['notes'][0]
        body = {'project_id': 'demo', 'artifact_id': 'edit-v02', 'note_ids': [note['id']]}
        for change in [{'project_id': '../escape'}, {'artifact_id': 'unknown'}, {'artifact_id': 'board-v01'},
                       {'note_ids': []}, {'note_ids': [note['id'], note['id']]}, {'note_ids': [str(uuid.uuid4())]},
                       {'note_ids': ['bad']}, {'note_ids': 'bad'}, {'path': '/tmp/arbitrary'}]:
            with self.assertRaises(feedback.FeedbackError):
                feedback.save_link({**body, **change})
        self.assertFalse((self.project / 'review-feedback-links.json').exists())
        path = self.project / 'review-feedback.json'
        data = json.loads(path.read_text(encoding='utf-8')); data['notes'][0]['status'] = 'applied'; path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(feedback.FeedbackError, 'changed'):
            feedback.save_link(body)
        self.assertFalse((self.project / 'review-feedback-links.json').exists())

    def test_existing_link_never_expands_when_new_notes_arrive_or_old_notes_are_applied(self):
        note = feedback.save(self.body)['notes'][0]
        link = feedback.save_link({'project_id': 'demo', 'artifact_id': 'edit-v02', 'note_ids': [note['id']]})
        feedback.save({**self.body, 'request_id': str(uuid.uuid4()), 'text': 'Later note'})
        path = self.project / 'review-feedback.json'
        data = json.loads(path.read_text(encoding='utf-8')); data['notes'][0]['status'] = 'applied'; path.write_text(json.dumps(data), encoding='utf-8')
        result = feedback.current('demo', link['id'])
        self.assertEqual(result['selection']['note_ids'], [note['id']])
        self.assertEqual(result['notes'][0]['status'], 'applied')
        board_body = {**self.body, 'request_id': str(uuid.uuid4()), 'artifact_id': 'board-v01', 'time': None, 'frame': 1,
                      'context_revision': feedback.current('demo')['contexts']['board-v01']}
        board = feedback.save(board_body)['notes'][-1]
        current = feedback.current('demo')['notes'][1]
        combined = feedback.save_link({'project_id': 'demo', 'artifact_id': None, 'note_ids': [board['id'], current['id']]})
        self.assertEqual(combined['artifact_ids'], ['board-v01', 'edit-v02'])

    def test_corrupt_or_symlinked_link_storage_is_not_used_or_overwritten(self):
        note = feedback.save(self.body)['notes'][0]
        body = {'project_id': 'demo', 'artifact_id': 'edit-v02', 'note_ids': [note['id']]}
        link = feedback.save_link(body)
        path = self.project / 'review-feedback-links.json'
        data = json.loads(path.read_text(encoding='utf-8')); data['links'][link['id']]['artifact_id'] = None; path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(feedback.FeedbackError):
            feedback.current('demo', link['id'])
        with self.assertRaises(feedback.FeedbackError):
            feedback.save_link(body)
        outside = self.root / 'outside-links.json'; outside.write_text('{"keep":"safe"}', encoding='utf-8')
        path.unlink(); path.symlink_to(outside)
        with self.assertRaises(storage.ReviewError):
            feedback.save_link(body)
        self.assertEqual(outside.read_text(encoding='utf-8'), '{"keep":"safe"}')
        with self.assertRaises(feedback.FeedbackError):
            feedback.current('demo', '../outside')

    def test_concurrent_link_selections_preserve_both_records(self):
        first = feedback.save(self.body)['notes'][0]
        second = feedback.save({**self.body, 'request_id': str(uuid.uuid4()), 'text': 'Second note'})['notes'][-1]
        errors = []
        def save_link(note):
            try:
                feedback.save_link({'project_id': 'demo', 'artifact_id': 'edit-v02', 'note_ids': [note['id']]})
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=save_link, args=(n,)) for n in [first, second]]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertFalse(errors)
        self.assertEqual(len(json.loads((self.project / 'review-feedback-links.json').read_text(encoding='utf-8'))['links']), 2)
        self.assertEqual(len(feedback.current('demo')['notes']), 2)

    def test_link_endpoint_boundaries_and_exact_selection_reload(self):
        note = feedback.save(self.body)['notes'][0]
        body = {'project_id': 'demo', 'artifact_id': 'edit-v02', 'note_ids': [note['id']]}
        server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        valid = {'Origin': origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'feedback-link'}
        def request(headers, method='POST', payload=None, path='/feedback-link'):
            c = http.client.HTTPConnection('127.0.0.1', server.server_port)
            c.request(method, path, json.dumps(body) if payload is None and method == 'POST' else payload, headers)
            response = c.getresponse(); result = response.status, response.read(); c.close(); return result
        try:
            for extra in [{'Origin': 'https://example.invalid'}, {'Host': 'example.invalid'},
                          {'Sec-Fetch-Site': 'cross-site'}, {'X-Studio-Action': 'feedback'}, {'Transfer-Encoding': 'chunked'}]:
                self.assertIn(request({**valid, **extra})[0], [400, 403])
            self.assertEqual(request({'Content-Type': 'application/json'})[0], 403)
            self.assertEqual(request({**valid, 'Content-Type': 'text/plain'})[0], 415)
            # Reject the declared size before any upload. Sending the entire rejected
            # body races the server's close and can reset the client socket on macOS.
            self.assertEqual(request({**valid, 'Content-Length': '1048577'}, payload='')[0], 413)
            self.assertEqual(request(valid, payload='{bad')[0], 400)
            status, result = request(valid); self.assertEqual(status, 200)
            token = json.loads(result)['id']
            status, result = request({}, 'GET', path='/feedback?project=demo&selection=' + token)
            self.assertEqual(status, 200); self.assertEqual(json.loads(result)['selection']['note_ids'], [note['id']])
            self.assertEqual(request({}, 'GET', path='/feedback?project=demo&selection=bad')[0], 404)
            self.assertEqual(request({'Origin': 'https://example.invalid'}, 'GET', path='/feedback?project=demo&selection=' + token)[0], 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def change_body(self, note, action='edit', **extra):
        return {'project_id': 'demo', 'note_id': note['id'], 'revision': note['revision'],
                'action': action, 'request_id': str(uuid.uuid4()), **extra}

    def test_edit_delete_restore_keep_source_history_and_approval_bytes(self):
        note = feedback.save(self.body)['notes'][0]
        edit = self.change_body(note, text='Make only the opening cards larger.')
        result = feedback.change(edit)['notes'][0]
        self.assertEqual(result['text'], edit['text'])
        for field in ('id', 'created_at', 'artifact_id', 'version', 'time', 'frame', 'source', 'status', 'request'):
            self.assertEqual(result[field], note[field])
        self.assertEqual(result['history'][0]['before']['text'], note['text'])
        self.assertEqual(feedback.change(edit)['notes'], feedback.current('demo')['notes'])
        deleted = feedback.change(self.change_body(result, 'delete'))['notes'][0]
        self.assertIn('deleted_at', deleted)
        restored = feedback.change(self.change_body(deleted, 'restore'))['notes'][0]
        self.assertNotIn('deleted_at', restored)
        self.assertEqual([e['action'] for e in restored['history']], ['edit', 'delete', 'restore'])
        for p, before in self.before.items():
            self.assertEqual(p.read_bytes(), before)

    def test_applied_note_edit_retains_application_and_original_wording(self):
        feedback.save(self.body)
        path = self.project / 'review-feedback.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['notes'][0].update(status='applied', applied_in={'artifact_id': 'edit-v03', 'version': 'V03'})
        path.write_text(json.dumps(data), encoding='utf-8')
        note = feedback.current('demo')['notes'][0]
        result = feedback.change(self.change_body(note, text='Clarified historical note.'))['notes'][0]
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(result['applied_in'], note['applied_in'])
        self.assertEqual(result['history'][0]['before']['applied_in'], note['applied_in'])
        self.assertEqual(result['history'][0]['before']['text'], note['text'])

    def test_concurrent_note_actions_reject_stale_writes_and_changed_application(self):
        note = feedback.save(self.body)['notes'][0]
        stale = self.change_body(note, text='Stale edit')
        updated = feedback.change(self.change_body(note, text='Fresh edit'))['notes'][0]
        before = (self.project / 'review-feedback.json').read_bytes()
        for action in (stale, self.change_body(note, 'delete')):
            with self.assertRaisesRegex(feedback.FeedbackError, 'another window'):
                feedback.change(action)
        self.assertEqual((self.project / 'review-feedback.json').read_bytes(), before)
        path = self.project / 'review-feedback.json'
        data = json.loads(path.read_text(encoding='utf-8')); data['notes'][0]['status'] = 'applied'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(feedback.FeedbackError):
            feedback.change(self.change_body(updated, text='Cannot erase applied history'))

    def test_deleted_notes_reject_edits_and_copy_and_restore_is_idempotent(self):
        note = feedback.save(self.body)['notes'][0]
        delete = self.change_body(note, 'delete')
        removed = feedback.change(delete)['notes'][0]
        self.assertEqual(feedback.change(delete)['notes'][0], removed)
        for body in (self.change_body(removed, text='No'), self.change_body(removed, 'delete')):
            with self.assertRaises(feedback.FeedbackError): feedback.change(body)
        with self.assertRaises(feedback.FeedbackError):
            feedback.save_link({'project_id': 'demo', 'artifact_id': None, 'note_ids': [note['id']]})
        restore = self.change_body(removed, 'restore')
        restored = feedback.change(restore)['notes'][0]
        self.assertEqual(feedback.change(restore)['notes'][0], restored)
        with self.assertRaises(feedback.FeedbackError):
            feedback.change({**restore, 'action': 'delete'})

    def test_shared_links_detect_edits_but_allow_application_and_later_notes(self):
        note = feedback.save(self.body)['notes'][0]
        body = {'project_id': 'demo', 'artifact_id': note['artifact_id'], 'note_ids': [note['id']],
                'note_revisions': {note['id']: note['content_revision']}}
        link = feedback.save_link(body)
        edited = feedback.change(self.change_body(note, text='Different instruction'))['notes'][0]
        with self.assertRaisesRegex(feedback.FeedbackError, 'edited or deleted'):
            feedback.current('demo', link['id'])
        with self.assertRaises(feedback.FeedbackError): feedback.save_link(body)
        new_link = feedback.save_link({**body, 'note_revisions': {note['id']: edited['content_revision']}})
        self.assertNotEqual(link['id'], new_link['id'])
        path = self.project / 'review-feedback.json'
        data = json.loads(path.read_text(encoding='utf-8')); data['notes'][0]['status'] = 'applied'
        path.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(feedback.current('demo', new_link['id'])['selection']['note_ids'], [note['id']])

    def test_change_validation_and_http_origin_guards(self):
        note = feedback.save(self.body)['notes'][0]
        valid = self.change_body(note, text='Corrected note')
        for invalid in ({**valid, 'text': ''}, {**valid, 'action': 'erase'}, {**valid, 'revision': 'bad'},
                        {**valid, 'note_id': '../outside'}, {**valid, 'time': 1}, {**valid, 'text': 'a'*2001}):
            with self.assertRaises(feedback.FeedbackError): feedback.change(invalid)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            port = server.server_port
            def post(headers, body=valid):
                c = http.client.HTTPConnection('127.0.0.1', port)
                c.request('POST', '/feedback-note', json.dumps(body), headers)
                r = c.getresponse(); status = r.status; r.read(); c.close(); return status
            headers = {'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json', 'X-Studio-Action': 'feedback-note'}
            self.assertEqual(post({**headers, 'Origin': 'https://attacker.example'}), 403)
            self.assertEqual(post({**headers, 'X-Studio-Action': 'feedback'}), 403)
            self.assertEqual(post({**headers, 'Content-Type': 'text/plain'}), 415)
            self.assertEqual(post(headers), 200)
            self.assertEqual(post(headers), 200)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_legacy_links_remain_readable_until_selected_instruction_changes(self):
        note = feedback.save(self.body)['notes'][0]
        payload = {'project_id': 'demo', 'artifact_id': note['artifact_id'],
                   'artifact_ids': [note['artifact_id']], 'note_ids': [note['id']]}
        token = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
        record = {**payload, 'id': token, 'created_at': '2026-10-28T00:00:00Z'}
        (self.project / 'review-feedback-links.json').write_text(json.dumps(
            {'schema_version': 1, 'project_id': 'demo', 'links': {token: record}}), encoding='utf-8')
        self.assertEqual(feedback.current('demo', token)['selection'], record)
        feedback.change(self.change_body(note, text='Updated instruction'))
        with self.assertRaisesRegex(feedback.FeedbackError, 'edited or deleted'):
            feedback.current('demo', token)
        self.assertEqual(json.loads((self.project / 'review-feedback-links.json').read_text(encoding='utf-8'))['links'][token], record)
