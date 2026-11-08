"""Task 7: POST /new-video creates a draft project and answers 201 + the registry record."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import project_index as index
from serve import Handler


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class NewVideoServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.registry = self.root / 'projects.json'
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry)]
        for p in self.patches:
            p.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, body, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def post_headers(self, **extra):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'new-video'}
        headers.update(extra)
        return headers

    def test_create_returns_201_and_record(self):
        status, data = self.request('POST', '/new-video', json.dumps(
            {'title': 'My First Reel', 'kind': 'faceless', 'video_language': 'en'}), **self.post_headers())
        self.assertEqual(status, 201)
        record = json.loads(data)
        self.assertEqual(record['id'], 'my-first-reel')
        self.assertEqual(record['state'], 'draft')
        self.assertTrue((self.root / 'projects' / 'my-first-reel' / 'brief.md').is_file())

    def test_invalid_kind_is_400_with_message_key(self):
        status, data = self.request('POST', '/new-video', json.dumps(
            {'title': 'Valid title', 'kind': 'nope', 'video_language': 'en'}), **self.post_headers())
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(data), {'error': 'newVideo.error.kind'})

    def test_requires_action_header(self):
        headers = self.post_headers()
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/new-video', json.dumps(
            {'title': 'Valid title', 'kind': 'faceless', 'video_language': 'en'}), **headers)
        self.assertEqual(status, 403)
        self.assertFalse(self.registry.exists())

    def test_rejects_untrusted_origin(self):
        headers = self.post_headers(Origin='https://example.invalid')
        status, _ = self.request('POST', '/new-video', json.dumps(
            {'title': 'Valid title', 'kind': 'faceless', 'video_language': 'en'}), **headers)
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
