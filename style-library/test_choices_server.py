"""Task 10: HTTP-level coverage for GET/POST /choices -- using a real running server the
same way test_materials_server.py exercises the materials routes."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import project_index as index
import choices
from serve import Handler, StudioServer


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class ChoicesServerTest(unittest.TestCase):
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

    def make_project(self, project_id='demo', video_language='he'):
        root = self.root / 'projects' / project_id
        root.mkdir(parents=True)
        (root / 'choices.json').write_text('{}', encoding='utf-8')
        (root / 'brief.md').write_text('# brief\n\n<!-- choices -->\n<!-- /choices -->\n', encoding='utf-8')
        self.registry.write_text(json.dumps({'schema_version': 1, 'projects': [
            {'id': project_id, 'title': project_id, 'kind': 'faceless', 'video_language': video_language,
             'state': 'draft', 'format': 'video', 'created_at': '2026-01-01T00:00:00+00:00',
             'primary_artifact': None, 'artifacts': [], 'source_notes': []},
        ]}), encoding='utf-8')
        return root

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, body, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def post_headers(self, **extra):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'choices'}
        headers.update(extra)
        return headers

    # --- GET /choices ---

    def test_get_choices_returns_saved_choices_and_config(self):
        self.make_project()
        status, body = self.request('GET', '/choices?project=demo', Origin=self.origin)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['choices'], {})
        self.assertIn('cut', data['config'])

    def test_get_choices_unknown_project_is_404(self):
        status, body = self.request('GET', '/choices?project=missing', Origin=self.origin)
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {'error': 'choices.error.unknownProject'})

    def test_get_choices_missing_query_is_400(self):
        status, _ = self.request('GET', '/choices', Origin=self.origin)
        self.assertEqual(status, 400)

    def test_get_choices_rejects_untrusted_origin(self):
        self.make_project()
        status, _ = self.request('GET', '/choices?project=demo', Origin='https://attacker.invalid')
        self.assertEqual(status, 403)

    # --- POST /choices ---

    def test_post_choices_saves_and_rewrites_brief(self):
        self.make_project(video_language='he')
        body = json.dumps({'project': 'demo', 'cut': 'tight'})
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(resp), {'cut': 'tight'})
        brief = (self.root / 'projects' / 'demo' / 'brief.md').read_text(encoding='utf-8')
        self.assertIn('חיתוך', brief)

    def test_post_choices_missing_action_header_is_403(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'tight'})
        headers = self.post_headers(**{'Content-Length': str(len(body))})
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/choices', body, **headers)
        self.assertEqual(status, 403)

    def test_post_choices_wrong_action_header_is_403(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'tight'})
        status, _ = self.request('POST', '/choices', body,
                                   **self.post_headers(**{'Content-Length': str(len(body)), 'X-Studio-Action': 'wrong'}))
        self.assertEqual(status, 403)

    def test_post_choices_transfer_encoding_is_400(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'tight'})
        status, _ = self.request('POST', '/choices', body,
                                   **self.post_headers(**{'Content-Length': str(len(body)), 'Transfer-Encoding': 'chunked'}))
        self.assertEqual(status, 400)

    def test_post_choices_unknown_project_is_404(self):
        body = json.dumps({'project': 'missing', 'cut': 'tight'})
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(resp), {'error': 'choices.error.unknownProject'})

    def test_post_choices_unknown_option_is_400(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'bogus'})
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'choices.error.unknownOption'})

    def test_post_choices_malformed_json_is_400(self):
        self.make_project()
        body = '{not valid json'
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'choices.error.invalidRequest'})

    def test_post_choices_missing_project_is_400_not_503(self):
        self.make_project()
        body = json.dumps({'cut': 'tight'})
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'choices.error.invalidRequest'})

    def test_post_choices_rejects_untrusted_origin(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'tight'})
        headers = self.post_headers(**{'Content-Length': str(len(body)), 'Origin': 'https://attacker.invalid'})
        status, _ = self.request('POST', '/choices', body, **headers)
        self.assertEqual(status, 403)

    def test_post_choices_preserves_effects_across_later_saves(self):
        self.make_project()
        first = json.dumps({'project': 'demo', 'effects': [{'effect': 'zoomthru', 'when': ''}]})
        self.request('POST', '/choices', first, **self.post_headers(**{'Content-Length': str(len(first))}))
        second = json.dumps({'project': 'demo', 'cut': 'natural'})
        status, resp = self.request('POST', '/choices', second, **self.post_headers(**{'Content-Length': str(len(second))}))
        self.assertEqual(status, 200)
        result = json.loads(resp)
        self.assertEqual(result['cut'], 'natural')
        self.assertEqual(result['effects'], [{'effect': 'zoomthru', 'when': ''}])

    def test_post_presenter_look_set_and_cleared(self):
        self.make_project()
        def post(payload):
            body = json.dumps({'project': 'demo', **payload})
            return self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        status, resp = post({'presenter': 'popout'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(resp)['presenter'], 'popout')
        status, resp = post({'presenter': None})
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(resp)['presenter'])
        status, resp = post({'presenter': 'nope'})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp)['error'], 'choices.error.unknownOption')

    # --- Fix round 2, controller ruling R33: the server-side seq guard is gone. A
    # straightforward last-request-wins save, and backward compatibility with any client
    # (or cached fix-round-1 bundle) that still sends a `seq` field. ---

    def test_post_choices_second_save_always_wins_no_seq_involved(self):
        self.make_project()
        first = json.dumps({'project': 'demo', 'cut': 'natural'})
        self.request('POST', '/choices', first, **self.post_headers(**{'Content-Length': str(len(first))}))
        second = json.dumps({'project': 'demo', 'cut': 'tight'})
        status, resp = self.request('POST', '/choices', second, **self.post_headers(**{'Content-Length': str(len(second))}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(resp)['cut'], 'tight')

    def test_post_choices_with_a_stray_seq_field_is_accepted_and_ignored(self):
        # Backward compatible with a browser tab that still has the fix-round-1 JS bundle
        # cached: the server used to read `seq`; now it just silently strips it rather than
        # rejecting the request as having an unknown field.
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'tight', 'seq': {'cut': 1}})
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(resp), {'cut': 'tight'})

    def test_get_choices_strips_a_legacy_seq_key_left_on_disk(self):
        root = self.make_project()
        (root / 'choices.json').write_text(json.dumps({'cut': 'tight', '_seq': {'cut': 4}}), encoding='utf-8')
        status, resp = self.request('GET', '/choices?project=demo', Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertNotIn('_seq', json.loads(resp)['choices'])

    def test_post_choices_never_exposes_seq_in_the_response(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'cut': 'tight'})
        status, resp = self.request('POST', '/choices', body, **self.post_headers(**{'Content-Length': str(len(body))}))
        self.assertEqual(status, 200)
        self.assertNotIn('_seq', json.loads(resp))


class StudioServerTest(unittest.TestCase):
    def test_server_accepts_a_burst_of_connections(self):
        # A page load opens a dozen connections at once; the stdlib backlog of 5 dropped some.
        self.assertGreaterEqual(StudioServer.request_queue_size, 64)
        self.assertTrue(StudioServer.daemon_threads)

if __name__ == '__main__':
    unittest.main()
