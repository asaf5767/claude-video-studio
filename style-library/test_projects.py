"""Project handoff boundaries: stale notes, explicit files, confinement and seekable previews.

T9b adds GET /project-assets/<project>/<file_id>?poster=1 -- a server-generated poster JPEG
for a video project artifact, so the review/export player's <video poster> is never a black
box for HEVC/HLG footage shot on an iPhone, which Chrome on Windows can't decode. Those
positive-path tests need a real ffmpeg on PATH and skip individually otherwise."""
import copy
import hashlib
import http.client
import json
import shutil
import subprocess
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
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


class ProjectsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / 'projects' / 'demo'
        self.project.mkdir(parents=True)
        (self.project / 'STATUS.md').write_text('Review V02; V01 accepted.', encoding='utf-8')
        (self.project / 'review.mp4').write_bytes(b'0123456789')
        (self.project / 'unregistered.txt').write_text('Never serve by guessed filename.', encoding='utf-8')
        self.record = {
            'id': 'demo', 'primary_artifact': 'review', 'state': 'review',
            'source_notes': [{'label': 'Status', 'path': 'STATUS.md',
                              'sha256': hashlib.sha256((self.project / 'STATUS.md').read_bytes()).hexdigest()}],
            'artifacts': [{'id': 'review', 'type': 'video', 'path': 'review.mp4', 'role': 'current'}],
        }
        self.registry = self.root / 'projects.json'
        self.save()
        self.patches = [patch.object(index, 'STUDIO', self.root), patch.object(index, 'REGISTRY', self.registry)]
        for p in self.patches:
            p.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f'127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def save(self):
        self.registry.write_text(json.dumps({'schema_version': 1, 'projects': [self.record]}), encoding='utf-8')

    def request(self, path, method='GET', **headers):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        c.request(method, path, headers=headers)
        r = c.getresponse()
        result = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return result

    def test_changed_status_flags_snapshot_without_inventing_new_approval(self):
        self.assertFalse(index.public_index()['projects'][0]['stale'])
        (self.project / 'STATUS.md').write_text('A new experiment needs review.', encoding='utf-8')
        p = index.public_index()['projects'][0]
        self.assertTrue(p['stale'])
        self.assertEqual(p['state'], 'review')
        with self.assertRaisesRegex(ValueError, 'Stale navigation'):
            index.validate()

    def test_missing_file_is_visible_as_unavailable(self):
        (self.project / 'review.mp4').unlink()
        a = index.public_index()['projects'][0]['artifacts'][0]
        self.assertFalse(a['available'])
        self.assertNotIn('url', a)

    def test_only_registered_numeric_slots_and_bounded_indexes(self):
        self.assertEqual(self.request('/project-files/demo/1')[0], 200)
        for suffix in ['-1', '2', '01', 'review.mp4', 'unregistered.txt', '1/extra', '..%2fSTATUS.md']:
            self.assertEqual(self.request('/project-files/demo/' + suffix)[0], 404, suffix)
        self.assertEqual(self.request('/project-files/unknown/0')[0], 404)

    def test_outside_absolute_and_symlink_paths_rejected(self):
        outside = self.root / 'outside.txt'
        outside.write_text('Outside the requested project.', encoding='utf-8')
        (self.project / 'escape.txt').symlink_to(outside)
        for value in ['../outside.txt', str(outside), 'escape.txt']:
            self.record['artifacts'][0]['path'] = value
            self.save()
            self.assertEqual(self.request('/project-files/demo/1', method='HEAD')[0], 404, value)

    def test_project_routes_reject_untrusted_host_origin_and_fetch_site(self):
        for path in ['/projects.json', '/project-files/demo/1']:
            for headers in [{'Host': 'example.invalid'}, {'Origin': 'https://example.invalid'},
                            {'Sec-Fetch-Site': 'cross-site'}]:
                self.assertEqual(self.request(path, method='HEAD', **headers)[0], 403)
            self.assertEqual(self.request(path, Origin='http://' + self.host)[0], 200)

    def test_preview_range_and_explicit_content_type(self):
        status, headers, body = self.request('/project-files/demo/1', Range='bytes=2-5')
        self.assertEqual((status, body, headers['Content-Type']), (206, b'2345', 'video/mp4'))
        self.assertEqual(headers['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(self.request('/project-files/demo/1', Range='bytes=12-')[0], 416)
        self.assertTrue(self.request('/project-files/demo/0')[1]['Content-Type'].startswith('text/plain'))

    def test_stable_asset_link_survives_inserting_a_new_version(self):
        url = index.public_index()['projects'][0]['artifacts'][0]['url']
        (self.project / 'new.mp4').write_bytes(b'new version')
        self.record['artifacts'].insert(0, {'id': 'new', 'type': 'video', 'path': 'new.mp4', 'role': 'history'})
        self.save()
        self.assertEqual(self.request(url)[2], b'0123456789')
        self.assertEqual(self.request(url, Range='bytes=2-5')[2], b'2345')
        self.assertEqual(self.request(url, Origin='https://example.invalid')[0], 403)

    def test_empty_setup_and_duplicate_registry_validation(self):
        self.registry.unlink()
        self.assertEqual(index.public_index()['projects'], [])
        self.save()
        data = json.loads(self.registry.read_text(encoding='utf-8'))
        data['projects'].append(copy.deepcopy(self.record))
        self.registry.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate project'):
            index.validate()

    def test_draft_project_with_no_artifacts_is_safe(self):
        """Task 7: a brand-new draft has no artifacts yet; this must never crash
        public_index()/validate(), and the card still gets a usable review=None."""
        draft = {'id': 'draft-one', 'title': 'Draft one', 'state': 'draft', 'format': 'video',
                 'primary_artifact': None, 'artifacts': [], 'source_notes': []}
        data = json.loads(self.registry.read_text(encoding='utf-8'))
        data['projects'].append(draft)
        self.registry.write_text(json.dumps(data), encoding='utf-8')
        result = index.public_index()
        found = next(p for p in result['projects'] if p['id'] == 'draft-one')
        self.assertEqual(found['state'], 'draft')
        self.assertIsNone(found['review'])
        self.assertFalse(found['stale'])
        index.validate()  # must not raise

    # --- T9b: GET /project-assets/<project>/<file_id>?poster=1 ---

    def _asset_url(self):
        return index.public_index()['projects'][0]['artifacts'][0]['url']

    @unittest.skipUnless(FFMPEG, 'ffmpeg not found on PATH')
    def test_asset_poster_serves_a_generated_jpeg_for_a_real_video(self):
        with tempfile.TemporaryDirectory() as clip_dir:
            (self.project / 'review.mp4').write_bytes(_make_clip_bytes(Path(clip_dir) / 'clip.mp4'))
        status, headers, body = self.request(self._asset_url() + '?poster=1')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/jpeg')
        self.assertTrue(body.startswith(b'\xff\xd8'))

    @unittest.skipUnless(FFMPEG, 'ffmpeg not found on PATH')
    def test_asset_poster_is_cached_under_dot_posters(self):
        with tempfile.TemporaryDirectory() as clip_dir:
            (self.project / 'review.mp4').write_bytes(_make_clip_bytes(Path(clip_dir) / 'clip.mp4'))
        file_id = self._asset_url().rsplit('/', 1)[1]
        self.request(self._asset_url() + '?poster=1')
        self.assertTrue((self.project / '.posters' / f'{file_id}.jpg').is_file())

    def test_asset_poster_404_when_the_file_cannot_be_decoded(self):
        # self.project/'review.mp4' is the fake b'0123456789' fixture from setUp(), not a
        # real video -- ffmpeg can't extract a frame from it, so ensure() returns None and
        # the route answers 404 (never a 500) the same way a missing poster would.
        status, _, _ = self.request(self._asset_url() + '?poster=1')
        self.assertEqual(status, 404)

    def test_asset_poster_404_for_a_non_video_asset(self):
        notes_url = index.public_index()['projects'][0]['source_notes'][0]['url']
        status, _, _ = self.request(notes_url + '?poster=1')
        self.assertEqual(status, 404)

    def test_asset_poster_rejects_untrusted_origin(self):
        status, _, _ = self.request(self._asset_url() + '?poster=1', Origin='https://example.invalid')
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
