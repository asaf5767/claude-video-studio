"""Task 8 fix round 1, finding 4: HTTP-level coverage for the materials routes --
PUT/GET /materials, POST /material-update, POST /material-from-library -- using a real
running server the same way test_new_video_server.py exercises /new-video.

T9b adds GET /project-materials/<project>/<item>?poster=1 -- a server-generated poster
JPEG for a video material, so the raw-take thumbnail never renders black for HEVC/HLG
footage shot on an iPhone, which Chrome on Windows can't decode. Those tests need a real
ffmpeg/ffprobe on PATH (same as test_posters.py assumes) and skip individually otherwise."""
import http.client
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.parse import quote

import project_index as index
from serve import Handler

FFMPEG = shutil.which('ffmpeg')


def _make_clip_bytes(path):
    subprocess.run([FFMPEG, '-y', '-f', 'lavfi', '-i', 'testsrc=duration=2:size=320x568:rate=10',
                     '-c:v', 'libx264', '-t', '2', str(path)], capture_output=True, check=True, timeout=30)
    return path.read_bytes()


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class MaterialsServerTest(unittest.TestCase):
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

    def make_project(self, project_id='demo'):
        root = self.root / 'projects' / project_id
        for sub in ('raw', 'broll', 'images', 'audio'):
            (root / 'materials' / sub).mkdir(parents=True)
        (root / 'materials.json').write_text(json.dumps({'items': []}), encoding='utf-8')
        self.registry.write_text(json.dumps({'schema_version': 1, 'projects': [
            {'id': project_id, 'title': project_id, 'kind': 'faceless', 'video_language': 'en',
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

    def put_headers(self, length, **extra):
        headers = {'Origin': self.origin, 'Content-Length': str(length), 'X-Studio-Action': 'materials'}
        headers.update(extra)
        return headers

    def post_headers(self, action, **extra):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': action}
        headers.update(extra)
        return headers

    # --- PUT /materials ---

    def test_put_succeeds_and_is_served_back_by_get(self):
        self.make_project()
        data = b'raw take bytes'
        status, body = self.request('PUT', '/materials?project=demo&name=' + quote('clip.mp4'), data,
                                     **self.put_headers(len(data)))
        self.assertEqual(status, 201)
        item = json.loads(body)
        self.assertEqual(item['tag'], 'raw')
        status, body = self.request('GET', '/materials?project=demo', Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['items'][0]['id'], item['id'])

    def test_put_missing_action_header_is_403(self):
        self.make_project()
        data = b'x'
        headers = self.put_headers(len(data))
        del headers['X-Studio-Action']
        status, _ = self.request('PUT', '/materials?project=demo&name=clip.mp4', data, **headers)
        self.assertEqual(status, 403)

    def test_put_wrong_action_header_is_403(self):
        self.make_project()
        data = b'x'
        status, _ = self.request('PUT', '/materials?project=demo&name=clip.mp4', data,
                                   **self.put_headers(len(data), **{'X-Studio-Action': 'not-materials'}))
        self.assertEqual(status, 403)

    def test_put_transfer_encoding_is_400(self):
        self.make_project()
        data = b'x'
        status, _ = self.request('PUT', '/materials?project=demo&name=clip.mp4', data,
                                   **self.put_headers(len(data), **{'Transfer-Encoding': 'chunked'}))
        self.assertEqual(status, 400)

    def test_put_oversize_content_length_is_413_before_reading(self):
        self.make_project()
        # Declares a body far past the 8 GiB cap but only actually sends one byte: a
        # server that read before checking would hang waiting for bytes that never
        # arrive, instead of answering promptly.
        import materials as materials_module
        status, _ = self.request('PUT', '/materials?project=demo&name=huge.mp4', b'x',
                                   **self.put_headers(materials_module.MAX_UPLOAD + 1))
        self.assertEqual(status, 413)

    def test_put_bad_extension_is_415(self):
        self.make_project()
        data = b'x'
        status, body = self.request('PUT', '/materials?project=demo&name=virus.exe', data,
                                      **self.put_headers(len(data)))
        self.assertEqual(status, 415)
        self.assertEqual(json.loads(body), {'error': 'materials.error.unsupportedType'})

    def test_put_unknown_project_is_404(self):
        data = b'x'
        status, body = self.request('PUT', '/materials?project=missing&name=clip.mp4', data,
                                      **self.put_headers(len(data)))
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {'error': 'materials.error.unknownProject'})

    # --- POST /material-update ---

    def test_update_missing_action_header_is_403(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'item': 'x', 'owned': True})
        headers = self.post_headers('material-update', **{'Content-Length': str(len(body))})
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/material-update', body, **headers)
        self.assertEqual(status, 403)

    def test_update_wrong_action_header_is_403(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'item': 'x', 'owned': True})
        status, _ = self.request('POST', '/material-update', body,
                                   **self.post_headers('wrong-action', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 403)

    def test_update_transfer_encoding_is_400(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'item': 'x', 'owned': True})
        status, _ = self.request('POST', '/material-update', body,
                                   **self.post_headers('material-update', **{'Content-Length': str(len(body)), 'Transfer-Encoding': 'chunked'}))
        self.assertEqual(status, 400)

    def test_update_unknown_project_is_404(self):
        body = json.dumps({'project': 'missing', 'item': 'x', 'owned': True})
        status, resp = self.request('POST', '/material-update', body,
                                      **self.post_headers('material-update', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(resp), {'error': 'materials.error.unknownProject'})

    def test_update_malformed_json_is_400(self):
        self.make_project()
        body = '{not valid json'
        status, resp = self.request('POST', '/material-update', body,
                                      **self.post_headers('material-update', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'materials.error.invalidRequest'})

    def test_update_missing_fields_is_400_not_503(self):
        self.make_project()
        body = json.dumps({'project': 'demo'})
        status, resp = self.request('POST', '/material-update', body,
                                      **self.post_headers('material-update', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'materials.error.invalidRequest'})

    # --- POST /material-from-library ---

    def test_from_library_missing_action_header_is_403(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'item': 'lib-1'})
        headers = self.post_headers('material-from-library', **{'Content-Length': str(len(body))})
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/material-from-library', body, **headers)
        self.assertEqual(status, 403)

    def test_from_library_wrong_action_header_is_403(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'item': 'lib-1'})
        status, _ = self.request('POST', '/material-from-library', body,
                                   **self.post_headers('wrong-action', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 403)

    def test_from_library_transfer_encoding_is_400(self):
        self.make_project()
        body = json.dumps({'project': 'demo', 'item': 'lib-1'})
        status, _ = self.request('POST', '/material-from-library', body,
                                   **self.post_headers('material-from-library', **{'Content-Length': str(len(body)), 'Transfer-Encoding': 'chunked'}))
        self.assertEqual(status, 400)

    def test_from_library_unknown_project_is_404(self):
        body = json.dumps({'project': 'missing', 'item': 'lib-1'})
        status, resp = self.request('POST', '/material-from-library', body,
                                      **self.post_headers('material-from-library', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(resp), {'error': 'materials.error.unknownProject'})

    def test_from_library_malformed_json_is_400(self):
        self.make_project()
        body = '{not valid json'
        status, resp = self.request('POST', '/material-from-library', body,
                                      **self.post_headers('material-from-library', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'materials.error.invalidRequest'})

    def test_from_library_missing_fields_is_400_not_503(self):
        self.make_project()
        body = json.dumps({'project': 'demo'})
        status, resp = self.request('POST', '/material-from-library', body,
                                      **self.post_headers('material-from-library', **{'Content-Length': str(len(body))}))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(resp), {'error': 'materials.error.invalidRequest'})

    def test_rejects_untrusted_origin(self):
        self.make_project()
        data = b'x'
        headers = self.put_headers(len(data), Origin='https://attacker.invalid')
        status, _ = self.request('PUT', '/materials?project=demo&name=clip.mp4', data, **headers)
        self.assertEqual(status, 403)

    # --- Task 9: GET /material-library ---

    def test_material_library_empty_when_no_library_yet(self):
        status, body = self.request('GET', '/material-library', Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'items': []})

    def test_material_library_lists_items(self):
        library_root = self.root / 'library'
        (library_root / 'images').mkdir(parents=True)
        (library_root / 'images' / 'brand-logo.png').write_bytes(b'logo-bytes')
        (library_root / 'materials.json').write_text(json.dumps({'items': [
            {'id': 'lib-1', 'file': 'images/brand-logo.png', 'tag': 'logo', 'note': '',
             'owned': True, 'size': 10, 'added_at': '2026-01-01T00:00:00+00:00'},
        ]}), encoding='utf-8')
        status, body = self.request('GET', '/material-library', Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['items'][0]['id'], 'lib-1')

    def test_material_library_rejects_untrusted_origin(self):
        status, _ = self.request('GET', '/material-library', Origin='https://attacker.invalid')
        self.assertEqual(status, 403)

    def test_material_library_query_string_is_400(self):
        status, _ = self.request('GET', '/material-library?x=1', Origin=self.origin)
        self.assertEqual(status, 400)

    # --- Task 9: GET /project-materials/<project>/<item> ---

    def test_project_materials_serves_uploaded_bytes(self):
        self.make_project()
        data = b'raw take bytes'
        status, body = self.request('PUT', '/materials?project=demo&name=' + quote('clip.mp4'), data,
                                     **self.put_headers(len(data)))
        self.assertEqual(status, 201)
        item = json.loads(body)
        status, served = self.request('GET', '/project-materials/demo/' + item['id'], Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(served, data)

    def test_project_materials_supports_range_requests(self):
        self.make_project()
        data = b'0123456789'
        status, body = self.request('PUT', '/materials?project=demo&name=clip.mp4', data,
                                     **self.put_headers(len(data)))
        item = json.loads(body)
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('GET', '/project-materials/demo/' + item['id'], headers={'Origin': self.origin, 'Range': 'bytes=2-4'})
        r = conn.getresponse()
        served = r.read()
        conn.close()
        self.assertEqual(r.status, 206)
        self.assertEqual(served, b'234')

    def test_project_materials_follows_a_tag_change_move(self):
        self.make_project()
        data = b'abc'
        status, body = self.request('PUT', '/materials?project=demo&name=clip.mp4', data,
                                     **self.put_headers(len(data)))
        item = json.loads(body)
        move_body = json.dumps({'project': 'demo', 'item': item['id'], 'tag': 'music'})
        status, _ = self.request('POST', '/material-update', move_body,
                                   **self.post_headers('material-update', **{'Content-Length': str(len(move_body))}))
        self.assertEqual(status, 200)
        status, served = self.request('GET', '/project-materials/demo/' + item['id'], Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(served, data)

    def test_project_materials_unknown_item_is_404(self):
        self.make_project()
        status, _ = self.request('GET', '/project-materials/demo/missing', Origin=self.origin)
        self.assertEqual(status, 404)

    def test_project_materials_unknown_project_is_404(self):
        status, _ = self.request('GET', '/project-materials/missing/x', Origin=self.origin)
        self.assertEqual(status, 404)

    def test_project_materials_rejects_untrusted_origin(self):
        self.make_project()
        status, _ = self.request('GET', '/project-materials/demo/x', Origin='https://attacker.invalid')
        self.assertEqual(status, 403)

    # --- T9b: GET /project-materials/<project>/<item>?poster=1 ---

    @unittest.skipUnless(FFMPEG, 'ffmpeg not found on PATH')
    def test_project_materials_poster_serves_a_generated_jpeg(self):
        self.make_project()
        with tempfile.TemporaryDirectory() as clip_dir:
            data = _make_clip_bytes(Path(clip_dir) / 'clip.mp4')
        status, body = self.request('PUT', '/materials?project=demo&name=clip.mp4', data,
                                     **self.put_headers(len(data)))
        item = json.loads(body)
        status, poster = self.request('GET', f"/project-materials/demo/{item['id']}?poster=1", Origin=self.origin)
        self.assertEqual(status, 200)
        self.assertTrue(poster.startswith(b'\xff\xd8'))  # JPEG magic bytes

    @unittest.skipUnless(FFMPEG, 'ffmpeg not found on PATH')
    def test_project_materials_poster_is_cached_on_disk(self):
        root = self.make_project()
        with tempfile.TemporaryDirectory() as clip_dir:
            data = _make_clip_bytes(Path(clip_dir) / 'clip.mp4')
        status, body = self.request('PUT', '/materials?project=demo&name=clip.mp4', data,
                                     **self.put_headers(len(data)))
        item = json.loads(body)
        self.request('GET', f"/project-materials/demo/{item['id']}?poster=1", Origin=self.origin)
        cached = root / 'materials' / '.posters' / f"{item['id']}.jpg"
        self.assertTrue(cached.is_file())

    def test_project_materials_poster_is_404_for_a_non_video_item(self):
        self.make_project()
        data = b'\x89PNG fake bytes'
        status, body = self.request('PUT', '/materials?project=demo&name=logo.png', data,
                                     **self.put_headers(len(data)))
        item = json.loads(body)
        status, _ = self.request('GET', f"/project-materials/demo/{item['id']}?poster=1", Origin=self.origin)
        self.assertEqual(status, 404)

    def test_project_materials_poster_unknown_item_is_404(self):
        self.make_project()
        status, _ = self.request('GET', '/project-materials/demo/missing?poster=1', Origin=self.origin)
        self.assertEqual(status, 404)

    def test_project_materials_poster_rejects_untrusted_origin(self):
        self.make_project()
        status, _ = self.request('GET', '/project-materials/demo/x?poster=1', Origin='https://attacker.invalid')
        self.assertEqual(status, 403)

    def test_project_materials_poster_rejects_unknown_query_params(self):
        self.make_project()
        status, _ = self.request('GET', '/project-materials/demo/x?poster=1&extra=1', Origin=self.origin)
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
