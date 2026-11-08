"""Task 11: the four built-in looks -- looks.py's list()/card()/file_path() and
GET /looks, GET /look-files/<id>/<file> on the real server (http-level coverage the same
way test_materials_server.py exercises the materials routes)."""
import http.client
import json
import re
import threading
import unittest
from http.server import ThreadingHTTPServer

import looks
from serve import Handler

EXPECTED_IDS = {'soft', 'collage', 'signature', 'headline'}

# One run of 2+ Latin letters, or one run of 1+ ASCII digits -- the content this app's RTL
# rule (AGENTS.md / every card.md) says must sit inside a <bdi dir="ltr"> isolate so it never
# reorders or merges with the surrounding Hebrew.
LATIN_OR_DIGIT_RUN = re.compile(r'[A-Za-z]{2,}|[0-9]+')
BDI_SPAN = re.compile(r'<bdi\b[^>]*>.*?</bdi>', re.DOTALL)


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class LooksModuleTest(unittest.TestCase):
    def test_four_builtin_looks_present(self):
        items = looks.list()
        self.assertEqual({item['id'] for item in items}, EXPECTED_IDS)
        for item in items:
            self.assertTrue(item['name_he'])
            self.assertTrue(item['name_en'])
            self.assertEqual(item['sample'], f"/look-files/{item['id']}/sample.jpg")

    def test_each_card_has_required_keys(self):
        for look_id in EXPECTED_IDS:
            text = looks.card(look_id)
            fields, body = looks._front_matter(text)
            for key in looks.REQUIRED_KEYS:
                self.assertIn(key, fields, f'{look_id} card.md is missing {key!r}')
                self.assertTrue(fields[key].strip(), f'{look_id} card.md has an empty {key!r}')
            self.assertEqual(fields['id'], look_id)
            self.assertTrue(body.strip(), f'{look_id} card.md has no body notes for Claude')

    def test_card_unknown_id_is_look_error_404(self):
        with self.assertRaises(looks.LookError) as ctx:
            looks.card('does-not-exist')
        self.assertEqual(ctx.exception.status, 404)

    def test_file_path_rejects_traversal(self):
        with self.assertRaises(looks.LookError):
            looks.file_path('soft', '../../x')
        with self.assertRaises(looks.LookError):
            looks.file_path('..', 'card.md')
        with self.assertRaises(looks.LookError):
            looks.file_path('soft', '/etc/passwd')

    def test_file_path_serves_the_sample_image(self):
        target = looks.file_path('soft', 'sample.jpg')
        self.assertTrue(target.is_file())
        self.assertEqual(target.name, 'sample.jpg')

    def test_file_path_rejects_non_whitelisted_filenames(self):
        # card.md is served through /looks (list()) and card() -- not as a raw file --
        # and sample.html is a source file for re-rendering, never served directly (its
        # relative font URLs would 404 once flattened onto /look-files/<id>/<file>).
        with self.assertRaises(looks.LookError):
            looks.file_path('soft', 'card.md')
        with self.assertRaises(looks.LookError):
            looks.file_path('soft', 'sample.html')

    def test_validate_card_returns_fields_for_a_valid_card(self):
        fields = looks.validate_card(looks.card('soft'))
        self.assertEqual(fields['id'], 'soft')

    def test_sample_html_references_the_presenter_cutout(self):
        # The presenter swap: each look's sample.html places the owner's cleared photo cutout
        # as the presenter, not the old illustrated SVG mannequin.
        for look_id in EXPECTED_IDS:
            html = (looks.LOOKS_DIR / look_id / 'sample.html').read_text(encoding='utf-8')
            self.assertIn('../_presenter/presenter-cutout.png', html,
                           f'{look_id}/sample.html does not reference the presenter cutout')

    def test_sample_html_wraps_latin_and_digit_runs_in_bdi(self):
        for look_id in EXPECTED_IDS:
            html = (looks.LOOKS_DIR / look_id / 'sample.html').read_text(encoding='utf-8')
            body = html.split('<body>', 1)[1].split('</body>', 1)[0]
            visible = re.sub(r'<[^>]+>', ' ', BDI_SPAN.sub(' ', body))  # text nodes outside any <bdi>
            hits = LATIN_OR_DIGIT_RUN.findall(visible)
            self.assertEqual(hits, [], f'{look_id}/sample.html: unwrapped Latin/digit run(s) outside <bdi>: {hits}')

    def test_validate_card_rejects_missing_keys(self):
        text = '---\nid: x\nname_he: x\n---\nbody\n'
        with self.assertRaises(looks.LookError) as ctx:
            looks.validate_card(text)
        self.assertEqual(ctx.exception.status, 500)
        message = str(ctx.exception)
        self.assertIn('looks.error.invalid-card', message)
        for key in looks.REQUIRED_KEYS:
            if key not in ('id', 'name_he'):
                self.assertIn(key, message, f'missing key {key!r} should be named in the error')

    def test_validate_card_accepts_values_with_colons_quotes_and_hebrew(self):
        header = '\n'.join(
            f'{key}: ערך עם "מרכאות" ו: נקודתיים, and some text' for key in looks.REQUIRED_KEYS
        )
        text = f'---\n{header}\n---\nbody notes\n'
        fields = looks.validate_card(text)
        self.assertIn('מרכאות', fields['hook'])
        self.assertIn(':', fields['avoid'])


class LooksServerTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def test_get_looks_lists_the_four_built_ins(self):
        status, body = self.request('GET', '/looks')
        self.assertEqual(status, 200)
        items = json.loads(body)['items']
        self.assertEqual({item['id'] for item in items}, EXPECTED_IDS)

    def test_get_looks_rejects_a_query_string(self):
        status, _ = self.request('GET', '/looks?project=demo')
        self.assertEqual(status, 400)

    def test_look_files_confined(self):
        status, _ = self.request('GET', '/look-files/soft/../../x')
        self.assertEqual(status, 404)

    def test_look_files_unknown_look_is_404(self):
        status, _ = self.request('GET', '/look-files/does-not-exist/card.md')
        self.assertEqual(status, 404)

    def test_look_files_rejects_card_md_and_sample_html(self):
        status, _ = self.request('GET', '/look-files/soft/card.md')
        self.assertEqual(status, 404)
        status, _ = self.request('GET', '/look-files/soft/sample.html')
        self.assertEqual(status, 404)

    def test_look_files_serves_the_sample_image(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('GET', '/look-files/headline/sample.jpg')
        r = conn.getresponse()
        body = r.read()
        conn.close()
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader('Content-Type'), 'image/jpeg')
        self.assertTrue(body.startswith(b'\xff\xd8'))  # JPEG magic bytes


if __name__ == '__main__':
    unittest.main()
