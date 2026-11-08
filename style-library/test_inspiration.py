"""Task 13: inspiration by link or file, with editable style cards.

Disposable studio folders only; no network, no real media (a few fake bytes stand in for a
video -- nothing here decodes it)."""
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlencode

import inspiration
import library
import project_index as index
import reference_intake as intake
import review_actions as storage
from serve import Handler


class Quiet(Handler):
    def log_message(self, *args):
        pass


CARD = """---
id: {id}
name_he: סגנון מהשראה
name_en: Inspiration style
captions: מילה אחת בכל פעם, לבן עם קו מתאר
titles: כותרת גדולה בפתיחה בלבד
pace: חיתוך כל שתיים-שלוש שניות
transitions: קאט חד, בלי מעברים מעוצבים
graphics: מסגרת דקה בצבע אחד
music: ביט רגוע ושקט מתחת לדיבור
sfx: וושש קטן בכל כותרת
hook: שאלה ישירה בשנייה הראשונה
avoid: לא להעתיק את הלוגו או את המשפטים של היוצר
---
הערות חופשיות: הטכניקה בלבד.
"""


class InspirationBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.base = self.root / 'style-library'
        self.base.mkdir()
        (self.root / 'references').mkdir()
        self.catalog = self.base / 'catalog.json'
        self.catalog.write_text(json.dumps({'schema_version': 4, 'entries': [], 'techniques': []}), encoding='utf-8')
        self.index = self.base / 'projects.json'
        self.index.write_text('{"projects":[]}', encoding='utf-8')
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.index),
                        patch.object(storage, 'BASE', self.base), patch.object(storage, 'CATALOG', self.catalog),
                        patch.object(storage, 'JOURNALS', self.base / 'runtime/review-actions'),
                        patch.object(intake, 'CATALOG', self.catalog)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def data(self):
        return json.loads(self.catalog.read_text(encoding='utf-8'))

    def entry(self, ref_id):
        return next(e for e in self.data()['entries'] if e['id'] == ref_id)

    def upload(self, data=b'fake video bytes', name='my reel.mp4', **params):
        return inspiration.upload(BytesIO(data), len(data), name, **params)

    def link(self):
        return intake.save({'action': 'create', 'url': 'https://www.instagram.com/reel/abc123/', 'title': 'Link',
                            'creator': 'Demo', 'note': ''})['id']


class UploadTests(InspirationBase):
    def test_upload_inspiration_file_creates_reference(self):
        result = self.upload(title='פתיחה שאהבתי', creator='', note='הכתוביות')
        self.assertTrue(result['saved'])
        self.assertFalse(result['duplicate'])
        ref_id = result['id']
        self.assertTrue(index.TOKEN.fullmatch(ref_id))
        source = self.root / 'references' / ref_id / 'source.mp4'
        self.assertEqual(source.read_bytes(), b'fake video bytes')
        e = self.entry(ref_id)
        self.assertEqual(e['collection'], 'reference')
        self.assertEqual(e['media_path'], f'references/{ref_id}/source.mp4')
        self.assertNotIn('source_url', e)
        self.assertEqual(e['title'], 'פתיחה שאהבתי')
        self.assertEqual(e['reference_note'], 'הכתוביות')
        self.assertEqual(e['creator'], 'Creator not added')
        self.assertEqual(e['analysis_status'], 'not_analyzed')
        self.assertEqual(e['source_sha256'], hashlib.sha256(b'fake video bytes').hexdigest())
        # The registered file is servable through the same confinement /media/ uses.
        from security import registered_file, MEDIA
        self.assertEqual(registered_file(self.root, e['media_path'], MEDIA), source)

    def test_title_defaults_to_the_file_name(self):
        e = self.entry(self.upload(name='קליפ יפה.mov')['id'])
        self.assertEqual(e['title'], 'קליפ יפה')
        self.assertTrue(e['media_path'].endswith('/source.mov'))

    def test_same_file_twice_is_a_duplicate_without_a_second_copy(self):
        first = self.upload()['id']
        again = self.upload(name='other name.mp4')
        self.assertEqual(again['id'], first)
        self.assertTrue(again['duplicate'])
        self.assertEqual(len(self.data()['entries']), 1)
        self.assertEqual([p.name for p in (self.root / 'references').iterdir()], [first])

    def test_unsupported_type_and_oversize_are_rejected_without_writes(self):
        before = self.catalog.read_bytes()
        with self.assertRaises(inspiration.InspirationError) as e:
            self.upload(name='notes.txt')
        self.assertEqual(e.exception.status, 415)
        with self.assertRaises(inspiration.InspirationError) as e:
            self.upload(name='photo.jpg')
        self.assertEqual(e.exception.status, 415)
        with patch.object(inspiration, 'MAX_UPLOAD', 4):
            with self.assertRaises(inspiration.InspirationError) as e:
                self.upload()
        self.assertEqual(e.exception.status, 413)
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertEqual(list((self.root / 'references').iterdir()), [])

    def test_short_body_leaves_no_reference(self):
        with self.assertRaises(inspiration.InspirationError) as e:
            inspiration.upload(BytesIO(b'abc'), 10, 'clip.mp4')
        self.assertEqual(e.exception.status, 400)
        self.assertEqual(self.data()['entries'], [])
        self.assertEqual(list((self.root / 'references').iterdir()), [])

    def test_upload_cap_is_one_gib(self):
        self.assertEqual(inspiration.MAX_UPLOAD, 1024 ** 3)

    def test_file_can_be_added_to_an_existing_link_reference(self):
        ref_id = self.link()
        result = self.upload(reference=ref_id)
        self.assertEqual(result['id'], ref_id)
        e = self.entry(ref_id)
        self.assertEqual(e['media_path'], f'references/{ref_id}/source.mp4')
        self.assertEqual(e['source_url'], 'https://www.instagram.com/reel/abc123/')
        # A later re-upload with another type replaces the earlier file.
        self.upload(data=b'second', name='again.webm', reference=ref_id)
        self.assertEqual(self.entry(ref_id)['media_path'], f'references/{ref_id}/source.webm')
        self.assertEqual(sorted(p.name for p in (self.root / 'references' / ref_id).iterdir()), ['source.webm'])

    def test_replacing_a_file_keeps_the_old_one_until_the_catalog_commits(self):
        ref_id = self.link()
        self.upload(data=b'first', reference=ref_id)
        folder = self.root / 'references' / ref_id
        with patch.object(intake, 'register_file', side_effect=intake.IntakeError('busy', 503)):
            with self.assertRaises(inspiration.InspirationError):
                self.upload(data=b'second', reference=ref_id)
        self.assertEqual((folder / 'source.mp4').read_bytes(), b'first')
        self.assertEqual([p.name for p in folder.iterdir()], ['source.mp4'])
        self.upload(data=b'second', reference=ref_id)
        self.assertEqual((folder / 'source.mp4').read_bytes(), b'second')
        self.assertEqual(self.entry(ref_id)['source_sha256'], hashlib.sha256(b'second').hexdigest())

    def test_file_cannot_replace_analyzed_media_or_unknown_references(self):
        ref_id = self.link()
        data = self.data()
        data['entries'][0]['media_path'] = 'references/elsewhere/sample.mp4'
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(inspiration.InspirationError) as e:
            self.upload(reference=ref_id)
        self.assertEqual(e.exception.status, 409)
        for bad in ('missing', '../escape', 'UPPER'):
            with self.subTest(bad=bad), self.assertRaises(inspiration.InspirationError) as e:
                self.upload(reference=bad)
            self.assertEqual(e.exception.status, 404)


class FileReferenceIntakeTests(InspirationBase):
    def test_reference_without_url_allowed_when_file_present(self):
        ref_id = self.upload(title='', creator='@someone')['id']
        state = intake.current(ref_id)
        self.assertEqual(state['url'], '')
        intake.save({'action': 'edit', 'id': ref_id, 'revision': state['revision'], 'title': 'כותרת חדשה',
                     'creator': '@someone', 'note': 'הקצב'})
        e = self.entry(ref_id)
        self.assertEqual(e['title'], 'כותרת חדשה')
        self.assertEqual(e['media_path'], f'references/{ref_id}/source.mp4')
        # Without a file, a link is still required.
        with self.assertRaises(intake.IntakeError):
            intake.save({'action': 'create', 'url': '', 'title': '', 'creator': '', 'note': ''})

    def test_file_reference_passes_library_validation(self):
        ref_id = self.upload()['id']
        (self.base / 'dist' / 'assets').mkdir(parents=True)
        (self.base / 'dist' / 'assets' / 'link-reference.svg').write_text('<svg/>', encoding='utf-8')
        with patch.object(library, 'BASE', self.base), patch.object(library, 'STUDIO', self.root):
            self.assertEqual(library.validate()['other_creators'], 1)
            self.assertIn(ref_id, library.entry_map())


class CardTests(InspirationBase):
    def setUp(self):
        super().setUp()
        self.ref = self.upload()['id']
        self.text = CARD.format(id=self.ref)

    def test_card_is_empty_until_learned(self):
        card = inspiration.card(self.ref)
        self.assertFalse(card['exists'])
        self.assertIsNone(card['revision'])
        self.assertEqual(card['pinned'], [])
        self.assertEqual(card['keys'], list(inspiration.CARD_KEYS))

    def test_card_roundtrip_with_pins(self):
        saved = inspiration.save_card(self.ref, self.text, ['captions', 'pace'])
        self.assertTrue(saved['exists'])
        self.assertEqual(saved['pinned'], ['captions', 'pace'])
        self.assertEqual((self.root / 'references' / self.ref / 'style-card.md').read_text(encoding='utf-8'), self.text)
        self.assertEqual(json.loads((self.root / 'references' / self.ref / 'style-card.json').read_text(encoding='utf-8'))['pinned'],
                         {'captions': 'מילה אחת בכל פעם, לבן עם קו מתאר', 'pace': 'חיתוך כל שתיים-שלוש שניות'})
        card = inspiration.card(self.ref)
        self.assertEqual(card['text'], self.text)
        self.assertEqual(card['fields']['captions'], 'מילה אחת בכל פעם, לבן עם קו מתאר')
        self.assertEqual(card['pinned'], ['captions', 'pace'])
        self.assertEqual(card['body'], 'הערות חופשיות: הטכניקה בלבד.')
        # Pinned keys restrict what a project uses; with no pins the whole card applies.
        self.assertEqual(set(card['use']), {'captions', 'pace'})
        unpinned = inspiration.save_card(self.ref, self.text, [], card['revision'])
        self.assertEqual(set(unpinned['use']), set(inspiration.CARD_KEYS))

    def relearn(self, **values):
        """What the learn-style skill does: rewrite style-card.md only."""
        text = self.text
        for key, value in values.items():
            text = '\n'.join(key + ': ' + value if line.startswith(key + ':') else line for line in text.split('\n'))
        (self.root / 'references' / self.ref / 'style-card.md').write_text(text, encoding='utf-8')

    def test_pinned_values_survive_a_relearn(self):
        edited = self.text.replace('pace: חיתוך כל שתיים-שלוש שניות', 'pace: איטי ונינוח, כמו שאני אוהב')
        inspiration.save_card(self.ref, edited, ['captions', 'pace'])
        self.relearn(captions='כתוביות חדשות מקלוד', pace='מהיר מאוד', titles='כותרת חדשה')
        card = inspiration.card(self.ref)
        self.assertEqual(card['fields']['pace'], 'איטי ונינוח, כמו שאני אוהב')
        self.assertEqual(card['fields']['captions'], 'מילה אחת בכל פעם, לבן עם קו מתאר')
        self.assertEqual(card['fields']['titles'], 'כותרת חדשה')  # unpinned rows follow the new card
        self.assertEqual(card['use'], {'captions': 'מילה אחת בכל פעם, לבן עם קו מתאר', 'pace': 'איטי ונינוח, כמו שאני אוהב'})
        # The user can still change a pinned row themselves; the pin keeps the new value.
        mine = inspiration.save_card(self.ref, edited.replace('איטי ונינוח', 'בינוני'), ['pace'], card['revision'])
        self.assertEqual(mine['fields']['pace'], 'בינוני, כמו שאני אוהב')
        self.relearn(pace='שוב מהיר')
        self.assertEqual(inspiration.card(self.ref)['fields']['pace'], 'בינוני, כמו שאני אוהב')
        self.assertEqual(inspiration.card(self.ref)['fields']['captions'], 'מילה אחת בכל פעם, לבן עם קו מתאר')

    def test_a_pin_survives_even_if_a_relearn_drops_its_row(self):
        inspiration.save_card(self.ref, self.text, ['sfx'])
        (self.root / 'references' / self.ref / 'style-card.md').write_text(self.text.replace('sfx: וושש קטן בכל כותרת\n', ''), encoding='utf-8')
        card = inspiration.card(self.ref)
        self.assertEqual(card['fields']['sfx'], 'וושש קטן בכל כותרת')
        self.assertTrue(card['valid'])

    def test_pins_still_show_when_the_card_is_unparseable(self):
        inspiration.save_card(self.ref, self.text, ['pace', 'hook'])
        (self.root / 'references' / self.ref / 'style-card.md').write_text('---\nbroken line\n---\nהערות\n', encoding='utf-8')
        card = inspiration.card(self.ref)
        self.assertEqual(card['fields'], {'pace': 'חיתוך כל שתיים-שלוש שניות', 'hook': 'שאלה ישירה בשנייה הראשונה'})
        self.assertEqual(card['pinned'], ['pace', 'hook'])
        self.assertEqual(card['use'], card['fields'])
        self.assertFalse(card['valid'])
        self.assertIn('captions', card['missing'])
        self.assertNotIn('pace', card['missing'])
        self.assertEqual(card['body'], 'הערות')

    def test_legacy_pin_list_is_still_read(self):
        inspiration.save_card(self.ref, self.text, [])
        (self.root / 'references' / self.ref / 'style-card.json').write_text('{"pinned": ["hook"]}', encoding='utf-8')
        self.assertEqual(inspiration.card(self.ref)['pinned'], ['hook'])

    def test_card_and_pins_are_replaced_together_or_not_at_all(self):
        first = inspiration.save_card(self.ref, self.text, ['pace'])
        folder = self.root / 'references' / self.ref
        before = ((folder / 'style-card.md').read_bytes(), (folder / 'style-card.json').read_bytes())
        real, calls = inspiration.os.replace, []
        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError('disk full')
            return real(src, dst)
        with patch.object(inspiration.os, 'replace', flaky), self.assertRaises(inspiration.InspirationError) as e:
            inspiration.save_card(self.ref, self.text.replace('קאט חד', 'קאט קופץ'), ['hook'], first['revision'])
        self.assertEqual(e.exception.status, 503)
        self.assertEqual(((folder / 'style-card.md').read_bytes(), (folder / 'style-card.json').read_bytes()), before)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['source.mp4', 'style-card.json', 'style-card.md'])

    def test_malformed_card_body_does_not_repeat_its_front_matter(self):
        folder = self.root / 'references' / self.ref
        (folder / 'style-card.md').write_text('---\nid: x\nthis line has no colon\n---\nהערות\n', encoding='utf-8')
        card = inspiration.card(self.ref)
        self.assertFalse(card['valid'])
        self.assertEqual(card['body'], 'הערות')

    def test_pinned_keys_must_exist_in_card(self):
        for pinned in (['captions', 'colour'], ['id'], 'captions', [1], ['pace', 'pace']):
            with self.subTest(pinned=pinned), self.assertRaises(inspiration.InspirationError) as e:
                inspiration.save_card(self.ref, self.text, pinned)
            self.assertEqual(e.exception.status, 400)
        self.assertFalse((self.root / 'references' / self.ref / 'style-card.md').exists())

    def test_invalid_card_names_the_missing_keys(self):
        text = self.text.replace('pace: חיתוך כל שתיים-שלוש שניות\n', '').replace('hook: שאלה ישירה בשנייה הראשונה', 'hook:   ')
        with self.assertRaises(inspiration.InspirationError) as e:
            inspiration.save_card(self.ref, text, [])
        self.assertEqual(e.exception.status, 400)
        self.assertEqual(e.exception.message_key, 'inspiration.error.invalidCard')
        self.assertEqual(e.exception.details, {'missing': ['pace', 'hook']})
        with self.assertRaises(inspiration.InspirationError) as e:
            inspiration.save_card(self.ref, 'no front matter', [])
        self.assertEqual(e.exception.status, 400)
        self.assertEqual(e.exception.details['missing'], list(inspiration.looks.REQUIRED_KEYS))

    def test_stale_revision_is_a_conflict(self):
        first = inspiration.save_card(self.ref, self.text, [])
        inspiration.save_card(self.ref, self.text.replace('קאט חד', 'קאט קופץ'), [], first['revision'])
        with self.assertRaises(inspiration.InspirationError) as e:
            inspiration.save_card(self.ref, self.text, ['pace'], first['revision'])
        self.assertEqual(e.exception.status, 409)
        with self.assertRaises(inspiration.InspirationError) as e:
            inspiration.save_card(self.ref, self.text, [], None)  # "no card yet", but one exists
        self.assertEqual(e.exception.status, 409)

    def test_a_card_written_by_claude_is_read_even_when_incomplete(self):
        folder = self.root / 'references' / self.ref
        (folder / 'style-card.md').write_text(self.text.replace('sfx: וושש קטן בכל כותרת\n', ''), encoding='utf-8')
        card = inspiration.card(self.ref)
        self.assertTrue(card['exists'])
        self.assertFalse(card['valid'])
        self.assertEqual(card['missing'], ['sfx'])
        (folder / 'style-card.json').write_text('not json', encoding='utf-8')
        self.assertEqual(inspiration.card(self.ref)['pinned'], [])

    def test_card_for_unknown_or_own_work_is_404(self):
        for bad in ('missing', '../x', ''):
            with self.subTest(bad=bad), self.assertRaises(inspiration.InspirationError) as e:
                inspiration.card(bad)
            self.assertEqual(e.exception.status, 404)
        data = self.data()
        data['entries'].append({**data['entries'][0], 'id': 'mine-1', 'collection': 'mine'})
        self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(inspiration.InspirationError):
            inspiration.save_card('mine-1', self.text, [])

    def test_link_reference_card_creates_its_folder(self):
        ref_id = self.link()
        inspiration.save_card(ref_id, CARD.format(id=ref_id), ['hook'])
        self.assertTrue((self.root / 'references' / ref_id / 'style-card.md').is_file())

    def test_oversized_or_binary_text_is_rejected(self):
        for text in ('x' * (inspiration.MAX_CARD + 1), self.text + '\x00', 5):
            with self.subTest(n=len(str(text))), self.assertRaises(inspiration.InspirationError) as e:
                inspiration.save_card(self.ref, text, [])
            self.assertEqual(e.exception.status, 400)


class ServerTests(InspirationBase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, body, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, (json.loads(data) if data and r.getheader('Content-Type', '').startswith('application/json') else data)

    def put(self, data, action='inspiration-file', **params):
        return self.request('PUT', '/inspiration-file?' + urlencode(params), data, Origin=self.origin,
                            **{'Content-Length': str(len(data)), 'X-Studio-Action': action})

    def post_card(self, body, action='style-card'):
        raw = json.dumps(body, ensure_ascii=False).encode()
        return self.request('POST', '/style-card', raw, Origin=self.origin, **{'Content-Type': 'application/json',
                            'Content-Length': str(len(raw)), 'X-Studio-Action': action})

    def test_put_creates_a_file_reference_with_hebrew_details(self):
        status, body = self.put(b'video', name='רילס.mp4', title='פתיחה', creator='', note='')
        self.assertEqual(status, 201)
        self.assertEqual(self.entry(body['id'])['title'], 'פתיחה')
        status, body = self.put(b'video', action='materials', name='x.mp4')
        self.assertEqual(status, 403)
        status, body = self.put(b'video', name='x.mp4', project='demo')
        self.assertEqual(status, 400)
        status, body = self.put(b'video', name='x.exe')
        self.assertEqual(status, 415)
        self.assertEqual(body['error'], 'inspiration.error.unsupportedType')

    def test_put_without_origin_is_refused(self):
        status, _ = self.request('PUT', '/inspiration-file?name=x.mp4', b'v', **{'Content-Length': '1',
                                 'X-Studio-Action': 'inspiration-file'})
        self.assertEqual(status, 403)

    def test_running_learn_style_job_is_found_by_reference(self):
        """The panel's mount-time lookup against the real GET /claude-job?reference= handler:
        it answers {"job": <id>, "state": "running", ...}, the shape inspiration-ui.js's
        lookup() attaches to; with no job it answers {"job": null}."""
        import os, time
        import claude_runner as runner
        ref_id = self.put(b'video', name='a.mp4')[1]['id']
        with patch.object(runner, 'STUDIO', self.root), patch.object(library, 'BASE', self.base):
            status, body = self.request('GET', '/claude-job?reference=' + quote(ref_id), Origin=self.origin)
            self.assertEqual((status, body), (200, {'job': None}))
            job = 'f' * 32
            (self.root / 'logs').mkdir()
            (self.root / 'logs' / 'jobs.json').write_text(json.dumps({'jobs': {job: {
                'job': job, 'task': 'learn-style', 'project': None, 'reference': ref_id, 'target': 'references/' + ref_id,
                'pid': os.getpid(), 'created': runner._proc_created(os.getpid()), 'state': 'running',
                'message_key': None, 'exit_code': None, 'started': time.time()}}}), encoding='utf-8')
            status, body = self.request('GET', '/claude-job?reference=' + quote(ref_id), Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual((body['job'], body['state']), (job, 'running'))
        self.assertIsInstance(body['steps'], list)

    def test_style_card_get_and_post(self):
        ref_id = self.put(b'video', name='a.mp4')[1]['id']
        status, card = self.request('GET', '/style-card?reference=' + quote(ref_id), Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertFalse(card['exists'])
        status, card = self.post_card({'reference': ref_id, 'text': CARD.format(id=ref_id), 'pinned': ['music'],
                                       'revision': None})
        self.assertEqual(status, 200)
        self.assertEqual(card['pinned'], ['music'])
        status, again = self.request('GET', '/style-card?reference=' + quote(ref_id), Origin=self.origin)
        self.assertEqual(again['fields']['music'], 'ביט רגוע ושקט מתחת לדיבור')
        status, body = self.post_card({'reference': ref_id, 'text': CARD.format(id=ref_id).replace('music: ביט רגוע ושקט מתחת לדיבור\n', ''),
                                       'pinned': [], 'revision': card['revision']})
        self.assertEqual(status, 400)
        self.assertEqual(body, {'error': 'inspiration.error.invalidCard', 'missing': ['music']})
        status, body = self.post_card({'reference': ref_id, 'text': CARD.format(id=ref_id), 'pinned': ['colour'],
                                       'revision': card['revision']})
        self.assertEqual(status, 400)
        self.assertEqual(body, {'error': 'inspiration.error.unknownPin', 'unknown': ['colour']})
        status, _ = self.post_card({'reference': ref_id, 'text': '', 'pinned': [], 'revision': None}, action='reference')
        self.assertEqual(status, 403)
        status, _ = self.post_card({'reference': ref_id, 'text': '', 'pinned': [], 'revision': None, 'extra': 1})
        self.assertEqual(status, 400)
        status, body = self.request('GET', '/style-card?reference=nope', Origin=self.origin)
        self.assertEqual(status, 404)


class ParseCardTests(unittest.TestCase):
    def test_parse_card_is_public(self):
        fields, body = inspiration.looks.parse_card('---\nid: a\ncaptions: x: y\n---\nbody\n')
        self.assertEqual((fields, body), ({'id': 'a', 'captions': 'x: y'}, 'body'))
        with self.assertRaises(ValueError):
            inspiration.looks.parse_card('no block')


if __name__ == '__main__':
    unittest.main()
