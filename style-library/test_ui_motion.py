"""Task 5 fix round 1: the persisted motion setting (auto/always/off) follows the /ui-language pattern."""
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


class UiMotionTest(unittest.TestCase):
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
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'ui-motion'}
        headers.update(extra)
        return headers

    def get_motion(self):
        status, data = self.request('GET', '/ui-motion')
        self.assertEqual(status, 200)
        return json.loads(data)['motion']

    def test_default_motion_is_auto(self):
        self.assertEqual(self.get_motion(), 'auto')

    def test_motion_roundtrip_for_every_value(self):
        for value in ['always', 'off', 'auto']:
            status, data = self.request('POST', '/ui-motion', json.dumps({'motion': value}), **self.post_headers())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data), {'motion': value})
            self.assertEqual(self.get_motion(), value)
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))['motion'], 'auto')

    def test_motion_rejects_other_values_and_extra_keys(self):
        for body in [{'motion': 'fast'}, {'motion': 'off', 'language': 'en'}, {'language': 'en'}, ['off']]:
            status, _ = self.request('POST', '/ui-motion', json.dumps(body), **self.post_headers())
            self.assertEqual(status, 400)
        self.assertEqual(self.get_motion(), 'auto')
        self.assertFalse((self.base / 'settings.json').exists())

    def test_motion_requires_action_header_and_same_origin(self):
        headers = self.post_headers()
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/ui-motion', json.dumps({'motion': 'off'}), **headers)
        self.assertEqual(status, 403)
        status, _ = self.request('POST', '/ui-motion', json.dumps({'motion': 'off'}), **self.post_headers(Origin='http://evil.example'))
        self.assertEqual(status, 403)
        self.assertEqual(self.get_motion(), 'auto')

    def test_motion_preserves_language_and_other_settings(self):
        (self.base / 'settings.json').write_text(json.dumps({'language': 'en', 'studio_name': 'My Studio'}), encoding='utf-8')
        self.request('POST', '/ui-motion', json.dumps({'motion': 'always'}), **self.post_headers())
        saved = json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, {'language': 'en', 'studio_name': 'My Studio', 'motion': 'always'})

    def test_unknown_saved_motion_falls_back_to_auto(self):
        (self.base / 'settings.json').write_text(json.dumps({'motion': 'sideways'}), encoding='utf-8')
        self.assertEqual(self.get_motion(), 'auto')

    def test_motion_write_is_atomic(self):
        (self.base / 'settings.json').write_text(json.dumps({'motion': 'off'}), encoding='utf-8')
        with patch.object(library, 'atomic_write', side_effect=OSError('disk full')):
            status, _ = self.request('POST', '/ui-motion', json.dumps({'motion': 'always'}), **self.post_headers())
        self.assertEqual(status, 503)
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8')), {'motion': 'off'})


if __name__ == '__main__':
    unittest.main()
