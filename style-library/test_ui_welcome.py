"""Task 19: the first-run welcome card's dismissal ("welcome_seen") follows the /ui-motion pattern."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import library
from serve import Handler


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class UiWelcomeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.patch = patch.object(library, 'BASE', self.base)
        self.patch.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.patch.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, body, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def post_headers(self, **extra):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'ui-welcome'}
        headers.update(extra)
        return headers

    def seen(self):
        status, data = self.request('GET', '/ui-welcome')
        self.assertEqual(status, 200)
        return json.loads(data)['welcome_seen']

    def dismiss(self, **extra):
        return self.request('POST', '/ui-welcome', json.dumps({'welcome_seen': True}), **self.post_headers(**extra))

    def test_default_is_not_seen(self):
        self.assertIs(self.seen(), False)

    def test_post_true_marks_it_seen_and_persists(self):
        status, data = self.dismiss()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {'welcome_seen': True})
        self.assertIs(self.seen(), True)
        self.assertIs(json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))['welcome_seen'], True)

    def test_only_true_is_accepted(self):
        for body in [{'welcome_seen': False}, {'welcome_seen': 'true'}, {'welcome_seen': 1}, {'welcome_seen': True, 'motion': 'off'}, {}, [True]]:
            status, _ = self.request('POST', '/ui-welcome', json.dumps(body), **self.post_headers())
            self.assertEqual(status, 400, body)
        self.assertIs(self.seen(), False)
        self.assertFalse((self.base / 'settings.json').exists())

    def test_requires_action_header_same_origin_and_json(self):
        headers = self.post_headers()
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/ui-welcome', json.dumps({'welcome_seen': True}), **headers)
        self.assertEqual(status, 403)
        status, _ = self.dismiss(Origin='http://evil.example')
        self.assertEqual(status, 403)
        headers = self.post_headers()
        del headers['Origin']
        status, _ = self.request('POST', '/ui-welcome', json.dumps({'welcome_seen': True}), **headers)
        self.assertEqual(status, 403)
        status, _ = self.dismiss(**{'X-Studio-Action': 'ui-motion'})
        self.assertEqual(status, 403)
        status, _ = self.dismiss(**{'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)
        status, _ = self.request('GET', '/ui-welcome', **{'Host': 'evil.example'})
        self.assertEqual(status, 403)
        self.assertIs(self.seen(), False)

    def test_preserves_other_settings(self):
        (self.base / 'settings.json').write_text(json.dumps({'language': 'en', 'motion': 'off', 'studio_name': 'My Studio'}), encoding='utf-8')
        self.dismiss()
        saved = json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, {'language': 'en', 'motion': 'off', 'studio_name': 'My Studio', 'welcome_seen': True})

    def test_anything_but_true_on_disk_means_not_seen(self):
        for value in ['yes', 1, None, False]:
            (self.base / 'settings.json').write_text(json.dumps({'welcome_seen': value}), encoding='utf-8')
            self.assertIs(self.seen(), False, value)
        (self.base / 'settings.json').write_text('not json', encoding='utf-8')
        self.assertIs(self.seen(), False)

    def test_write_is_atomic(self):
        (self.base / 'settings.json').write_text(json.dumps({'language': 'he'}), encoding='utf-8')
        with patch.object(library, 'atomic_write', side_effect=OSError('disk full')):
            status, _ = self.dismiss()
        self.assertEqual(status, 503)
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8')), {'language': 'he'})


if __name__ == '__main__':
    unittest.main()
