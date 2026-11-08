"""All reference-note writes use disposable catalogs and source files."""
import copy
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import reference_notes as notes
import project_index as index
import review_actions as storage
from serve import Handler


class Quiet(Handler):
    def log_message(self, *args): pass


class ReferenceNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        self.media = self.root / 'references/demo.mp4'
        self.media.parent.mkdir()
        self.media.write_bytes(b'exact-original-source')
        self.slide = self.root / 'references/slide.png'
        self.slide.write_bytes(b'exact-slide')
        self.catalog = self.base / 'catalog.json'
        self.registry = self.base / 'projects.json'
        self.registry.write_text('{"projects":[]}', encoding='utf-8')
        self.data = {'entries': [
            {'id': 'video', 'title': 'Creator video', 'creator': 'Demo', 'version': 'V01',
             'media_path': 'references/demo.mp4', 'duration': 10, 'collection': 'reference'},
            {'id': 'link', 'title': 'Saved link', 'creator': 'Demo', 'version': 'LINK',
             'source_url': 'https://example.com/source', 'collection': 'reference'},
            {'id': 'carousel', 'title': 'Carousel', 'creator': 'Demo', 'version': 'V01',
             'slides': [{'path': 'references/slide.png'}], 'collection': 'mine'}],
            'techniques': [{'id': 'tech-demo', 'title': 'Card reveal', 'examples': [
                {'id': 'first', 'style_id': 'video', 'label': 'First reveal', 'start': 2, 'end': 4,
                 'source_version': 'V01', 'source_path': 'references/demo.mp4',
                 'source_sha256': hashlib.sha256(self.media.read_bytes()).hexdigest()},
                {'id': 'second', 'style_id': 'video', 'label': 'Second reveal', 'start': 5, 'end': 8,
                 'source_version': 'V01', 'source_path': 'references/demo.mp4',
                 'source_sha256': hashlib.sha256(self.media.read_bytes()).hexdigest()}]}]}
        self.catalog.write_text(json.dumps(self.data), encoding='utf-8')
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry),
                        patch.object(storage, 'BASE', self.base), patch.object(storage, 'CATALOG', self.catalog),
                        patch.object(storage, 'JOURNALS', self.base / 'runtime/review-actions')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def body(self, id='video', example=None, **delta):
        return {'reference_id': id, 'example_id': example, 'slide': None,
                'context_revision': notes.current(id, example)['context_revision'], 'text': 'Borrow the card entrance.',
                'time': None, 'focus': '', 'request_id': str(uuid.uuid4()), 'legacy_key': None, **delta}

    def row(self, state, slide=None):
        return {k: state[k] for k in ['reference_id', 'example_id', 'context_revision']} | {
            'slide': slide, 'note_ids': [n['id'] for n in state['notes'] if n['slide'] in (None, slide)]}

    def test_read_and_handoff_without_notes_do_not_create_owner_files(self):
        state = notes.current('video')
        text = notes.handoff({'references': [self.row(state)]}, 'http://127.0.0.1:4870')['text']
        self.assertIn('Creator video — Demo', text)
        self.assertIn('#style=video', text)
        self.assertFalse((self.base / 'reference-notes.json').exists())
        self.assertFalse(storage.JOURNALS.exists())

    def test_missing_catalog_reads_as_an_empty_library(self):
        self.catalog.unlink()  # fresh install: nothing created catalog.json yet
        with self.assertRaises(notes.NoteError) as caught:
            notes.current('video')
        self.assertEqual(caught.exception.status, 404)
        self.assertFalse(self.catalog.exists())

    def test_preserved_technique_source_keeps_its_saved_note_context(self):
        before=notes.save(self.body('tech-demo','first'))
        data=json.loads(self.catalog.read_text(encoding='utf-8'));old=data['entries'][0]
        archived=copy.deepcopy(old);archived.update(id='video-saved-v01',archived_from='video')
        data['entries'].append(archived)
        for x in data['techniques'][0]['examples']:x['style_id']=archived['id']
        old['version']='V02';self.catalog.write_text(json.dumps(data), encoding='utf-8')
        after=notes.current('tech-demo','first')
        self.assertEqual(before['context_revision'],after['context_revision'])
        self.assertEqual(before['notes'],after['notes'])

    def test_save_zero_timestamp_is_persistent_and_preserves_sources(self):
        before = self.catalog.read_bytes(), self.media.read_bytes(), self.registry.read_bytes()
        body = self.body(time=0)
        state = notes.save(body)
        self.assertEqual(state['notes'][0]['time'], 0)
        self.assertEqual(notes.current('video')['notes'], state['notes'])
        text = notes.handoff({'references': [self.row(state)]}, 'http://127.0.0.1:4870')['text']
        self.assertIn('At 0:00: Borrow the card entrance.', text)
        self.assertNotIn('request_id', text)
        self.assertEqual(before, (self.catalog.read_bytes(), self.media.read_bytes(), self.registry.read_bytes()))

    def test_exact_example_range_and_note_ids_cannot_cross_sources(self):
        state = notes.save(self.body('tech-demo', 'first', time=3))
        text = notes.handoff({'references': [self.row(state)]}, 'http://127.0.0.1:4870')['text']
        self.assertIn('First reveal (0:02–0:04)', text)
        self.assertIn('#technique=tech-demo&example=first', text)
        other = notes.current('tech-demo', 'second')
        row = self.row(other) | {'note_ids': [state['notes'][0]['id']]}
        with self.assertRaises(notes.NoteError): notes.handoff({'references': [row]}, 'http://127.0.0.1:4870')
        for time in [0, 4.01, True, float('nan')]:
            with self.subTest(time=time), self.assertRaises(notes.NoteError): notes.save(self.body('tech-demo', 'first', time=time))

    def test_changed_source_keeps_earlier_notes_and_rejects_stale_copy_save(self):
        body = self.body(time=1)
        state = notes.save(body)
        self.media.write_bytes(b'new-source-must-not-inherit-old-timestamps')
        current = notes.current('video')
        self.assertEqual(current['notes'], [])
        self.assertEqual(current['earlier_notes'][0]['id'], body['request_id'])
        with self.assertRaises(notes.NoteError): notes.save(body | {'request_id': str(uuid.uuid4())})
        with self.assertRaises(notes.NoteError): notes.handoff({'references': [self.row(state)]}, 'http://127.0.0.1:4870')
        with self.assertRaises(notes.NoteError): notes.current('tech-demo', 'first')

    def test_carousel_scope_and_browser_import_are_exact_and_idempotent(self):
        first = notes.save(self.body('carousel', slide=1))
        legacy = self.body('carousel', text='Keep the original note.', focus='slides 1–2', legacy_key='a' * 64)
        notes.save(legacy)
        state = notes.save(legacy | {'request_id': str(uuid.uuid4())})
        self.assertEqual(len(state['notes']), 2)
        text = notes.handoff({'references': [self.row(state, 1)]}, 'http://127.0.0.1:4870')['text']
        self.assertIn('&slide=1', text)
        self.assertIn('slides 1–2', text)
        with self.assertRaises(notes.NoteError): notes.handoff({'references': [self.row(first) | {'note_ids': [first['notes'][0]['id']]}]}, 'http://127.0.0.1:4870')
        with self.assertRaises(notes.NoteError): notes.save(self.body('carousel', slide=2))
        with self.assertRaises(notes.NoteError): notes.save(self.body('carousel', time=1))
        with self.assertRaises(notes.NoteError): notes.save(legacy | {'request_id': str(uuid.uuid4()), 'text': 'Different note'})

    def test_retry_ids_and_invalid_payloads_do_not_overwrite_notes(self):
        body = self.body()
        state = notes.save(body)
        self.assertEqual(notes.save(body)['notes'], state['notes'])
        before = (self.base / 'reference-notes.json').read_bytes()
        for delta in [{'text': 'different'}, {'extra': True}, {'text': ''}, {'text': 'x' * 2001},
                      {'reference_id': '../outside'}, {'example_id': 'wrong'}, {'time': -1}, {'request_id': 'invalid'},
                      {'legacy_key': []}, {'focus': 'x' * 1001}, {'slide': True}]:
            with self.subTest(delta=delta), self.assertRaises(notes.NoteError): notes.save(body | delta)
        self.assertEqual(before, (self.base / 'reference-notes.json').read_bytes())
        with self.assertRaises(notes.NoteError): notes.save(self.body('link', time=1))

    def test_corrupt_symlink_and_escaped_sources_are_preserved(self):
        path = self.base / 'reference-notes.json'
        path.write_text('{bad', encoding='utf-8')
        with self.assertRaises(notes.NoteError): notes.current('video')
        self.assertEqual(path.read_text(encoding='utf-8'), '{bad')
        outside = self.root / 'outside.json'
        outside.write_text('{"schema_version":1,"notes":[]}', encoding='utf-8')
        path.unlink(); path.symlink_to(outside)
        with self.assertRaises(notes.NoteError): notes.current('video')
        self.assertEqual(outside.read_text(encoding='utf-8'), '{"schema_version":1,"notes":[]}')
        path.unlink()
        self.data['entries'][0]['media_path'] = '../outside.mp4'
        self.catalog.write_text(json.dumps(self.data), encoding='utf-8')
        with self.assertRaises(notes.NoteError): notes.current('video')

    def test_concurrent_saves_merge_and_external_catalog_changes_are_guarded(self):
        bodies = [self.body(text=f'Note {i}') for i in range(2)]
        errors = []
        def save(body):
            try: notes.save(body)
            except Exception as error: errors.append(error)
        threads = [threading.Thread(target=save, args=(b,)) for b in bodies]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertFalse(errors)
        self.assertEqual(len(notes.current('video')['notes']), 2)
        commit = storage.commit
        external = copy.deepcopy(self.data) | {'owner_change': 'Keep this'}
        def changed(*args, **kwargs):
            self.catalog.write_text(json.dumps(external), encoding='utf-8')
            return commit(*args, **kwargs)
        body = self.body()
        with patch.object(storage, 'commit', side_effect=changed), self.assertRaises(storage.ReviewError): notes.save(body)
        self.assertEqual(json.loads(self.catalog.read_text(encoding='utf-8')), external)
        self.assertEqual(len(notes.current('video')['notes']), 2)

    def test_source_changed_at_commit_cannot_receive_an_old_timestamp(self):
        body = self.body(time=2)
        commit = storage.commit
        def changed(*args, **kwargs):
            self.media.write_bytes(b'external-new-source')
            return commit(*args, **kwargs)
        with patch.object(storage, 'commit', side_effect=changed), self.assertRaises(storage.ReviewError): notes.save(body)
        self.assertFalse((self.base / 'reference-notes.json').exists())
        self.assertEqual(self.media.read_bytes(), b'external-new-source')

    def test_prepared_recovery_blocks_new_writes(self):
        body = self.body()
        folder = storage.JOURNALS / 'unfinished'; folder.mkdir(parents=True)
        (folder / 'transaction.json').write_text('{"state":"prepared"}', encoding='utf-8')
        with self.assertRaises(Exception): notes.save(body)
        self.assertFalse((self.base / 'reference-notes.json').exists())

    def test_endpoint_guards_and_explicit_stateless_copy(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        valid = {'Origin': origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'reference-note'}
        body = json.dumps(self.body())
        def request(headers, value=body, path='/reference-notes', method='POST'):
            c = http.client.HTTPConnection('127.0.0.1', server.server_port)
            c.request(method, path, body=value, headers=headers)
            r = c.getresponse(); result = r.status, r.read(); c.close(); return result
        try:
            for field in ['Origin', 'X-Studio-Action']:
                h = valid.copy(); h.pop(field); self.assertEqual(request(h)[0], 403)
            for extra in [{'Host': 'attacker.invalid'}, {'Origin': 'https://attacker.invalid'}, {'Sec-Fetch-Site': 'cross-site'}]:
                self.assertEqual(request(valid | extra)[0], 403)
            self.assertEqual(request(valid | {'Content-Type': 'text/plain'})[0], 415)
            self.assertEqual(request(valid, 'x' * 16385)[0], 413)
            self.assertEqual(request(valid, '{bad')[0], 400)
            self.assertEqual(request(valid)[0], 200)
            status, raw = request({}, '', '/reference-notes?id=video', 'GET')
            self.assertEqual(status, 200)
            before = (self.base / 'reference-notes.json').read_bytes()
            copied = request(valid | {'X-Studio-Action': 'reference-handoff'}, json.dumps({'references': [self.row(json.loads(raw))]}), '/reference-handoff')
            self.assertEqual(copied[0], 200)
            self.assertIn(origin, json.loads(copied[1])['text'])
            self.assertEqual(before, (self.base / 'reference-notes.json').read_bytes())
            self.assertEqual(request({'Origin': 'https://attacker.invalid'}, '', '/reference-notes?id=video', 'GET')[0], 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()
