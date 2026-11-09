"""Persisted UI language: GET/POST /ui-language roundtrips, rejects unsupported values, and guards writes."""
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


class UiLanguageTest(unittest.TestCase):
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
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'ui-language'}
        headers.update(extra)
        return headers

    def test_default_language_is_hebrew(self):
        status, data = self.request('GET', '/ui-language')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {'language': 'he'})

    def test_language_roundtrip(self):
        status, _ = self.request('POST', '/ui-language', json.dumps({'language': 'en'}), **self.post_headers())
        self.assertEqual(status, 200)
        status, data = self.request('GET', '/ui-language')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {'language': 'en'})
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))['language'], 'en')

    def test_language_rejects_other(self):
        status, _ = self.request('POST', '/ui-language', json.dumps({'language': 'fr'}), **self.post_headers())
        self.assertEqual(status, 400)
        status, data = self.request('GET', '/ui-language')
        self.assertEqual(json.loads(data), {'language': 'he'})

    def test_language_requires_action_header(self):
        headers = self.post_headers()
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/ui-language', json.dumps({'language': 'en'}), **headers)
        self.assertEqual(status, 403)
        status, data = self.request('GET', '/ui-language')
        self.assertEqual(json.loads(data), {'language': 'he'})

    def test_language_preserves_other_settings(self):
        (self.base / 'settings.json').write_text(json.dumps({'studio_name': 'My Studio'}), encoding='utf-8')
        self.request('POST', '/ui-language', json.dumps({'language': 'en'}), **self.post_headers())
        saved = json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['studio_name'], 'My Studio')
        self.assertEqual(saved['language'], 'en')

    def test_a_corrupt_settings_file_is_quarantined_not_lost(self):
        # Final review M12: a hand-edit typo must not make the next click drop add-ons/branding.
        broken = '{"studio_name": "My Studio", "addons": {"voice": {"enabled": true},}'
        (self.base / 'settings.json').write_text(broken, encoding='utf-8')
        with patch('sys.stderr'):
            status, _ = self.request('POST', '/ui-language', json.dumps({'language': 'en'}), **self.post_headers())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8')), {'language': 'en'})
        kept = list(self.base.glob('settings.corrupt-*.json'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding='utf-8'), broken)
        import addons
        (self.base / 'settings.json').write_text('[1, 2]', encoding='utf-8')
        with patch('sys.stderr'):
            addons.save({'voice': {'enabled': False, 'provider': None}})
        self.assertEqual(len(list(self.base.glob('settings.corrupt-*.json'))), 2)

    def test_write_failure_leaves_existing_settings_file_intact(self):
        """A crash mid-write must never leave settings.json truncated or half-written."""
        (self.base / 'settings.json').write_text(json.dumps({'language': 'he'}), encoding='utf-8')
        with patch.object(library, 'atomic_write', side_effect=OSError('disk full')):
            status, _ = self.request('POST', '/ui-language', json.dumps({'language': 'en'}), **self.post_headers())
        self.assertEqual(status, 503)
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8')), {'language': 'he'})

    def test_write_uses_the_shared_atomic_write_helper(self):
        """set_ui_language must go through the same temp-file+fsync+os.replace helper as review_actions."""
        import atomic
        calls = []
        real = atomic.atomic_write
        with patch.object(library, 'atomic_write', side_effect=lambda path, data: (calls.append((path, data)), real(path, data))[1]):
            status, _ = self.request('POST', '/ui-language', json.dumps({'language': 'en'}), **self.post_headers())
        self.assertEqual(status, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], self.base / 'settings.json')
        self.assertEqual(json.loads((self.base / 'settings.json').read_text(encoding='utf-8')), {'language': 'en'})


if __name__ == '__main__':
    unittest.main()
