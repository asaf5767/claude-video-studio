"""Task 8: materials upload into a project and copying from the personal library."""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import project_index as index
import materials


class MaterialsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Path(self.temp.name).resolve()
        self.registry_path = self.studio / 'projects.json'
        self.patches = [patch.object(index, 'STUDIO', self.studio), patch.object(index, 'REGISTRY', self.registry_path)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def make_project(self, project_id='demo'):
        root = self.studio / 'projects' / project_id
        for sub in ('raw', 'broll', 'images', 'audio'):
            (root / 'materials' / sub).mkdir(parents=True)
        (root / 'materials.json').write_text(json.dumps({'items': []}), encoding='utf-8')
        registry = json.loads(self.registry_path.read_text(encoding='utf-8')) if self.registry_path.exists() else {'schema_version': 1, 'projects': []}
        registry['projects'].append({'id': project_id, 'title': project_id, 'kind': 'faceless', 'video_language': 'en',
                                      'state': 'draft', 'format': 'video', 'created_at': '2026-01-01T00:00:00+00:00',
                                      'primary_artifact': None, 'artifacts': [], 'source_notes': []})
        self.registry_path.write_text(json.dumps(registry), encoding='utf-8')
        return root

    def test_upload_hebrew_name_with_spaces(self):
        root = self.make_project()
        data = b'raw take bytes'
        item = materials.save_upload('demo', 'צילום 1.mov', io.BytesIO(data), len(data))
        self.assertEqual(item['tag'], 'raw')
        self.assertEqual(item['file'], 'materials/raw/צילום 1.mov')
        saved = root / 'materials' / 'raw' / 'צילום 1.mov'
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_bytes(), data)
        # Served back via GET /materials: the manifest is the source for that endpoint.
        listed = materials.list('demo')
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['file'], item['file'])
        self.assertEqual(listed[0]['id'], item['id'])

    def test_streams_large_body_without_reading_all(self):
        self.make_project()
        size = 50 * 1024 * 1024

        class GeneratorStream:
            def __init__(self):
                self.remaining = size

            def read(self, n=-1):
                if self.remaining <= 0:
                    return b''
                chunk = min(n, self.remaining)
                self.remaining -= chunk
                return b'x' * chunk

        stream = GeneratorStream()
        with patch.object(stream, 'read', wraps=stream.read) as reader:
            item = materials.save_upload('demo', 'big.mp4', stream, size)
        self.assertEqual(item['size'], size)
        self.assertTrue(reader.call_args_list)
        for call in reader.call_args_list:
            requested = call.args[0] if call.args else call.kwargs.get('n')
            self.assertLessEqual(requested, 1024 * 1024)

    def test_rejects_path_traversal_name(self):
        root = self.make_project()
        item = materials.save_upload('demo', '../../x.mp4', io.BytesIO(b'd'), 1)
        self.assertEqual(item['file'], 'materials/raw/x.mp4')
        self.assertTrue((root / 'materials' / 'raw' / 'x.mp4').is_file())

    def test_rejects_exe(self):
        self.make_project()
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.save_upload('demo', 'virus.exe', io.BytesIO(b'd'), 1)
        self.assertEqual(ctx.exception.status, 415)

    def test_rejects_over_limit(self):
        self.make_project()

        class ExplodingStream:
            def read(self, n=-1):
                raise AssertionError('must not read before the size check')

        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.save_upload('demo', 'huge.mp4', ExplodingStream(), materials.MAX_UPLOAD + 1)
        self.assertEqual(ctx.exception.status, 413)

    def test_iphone_photos_are_accepted_as_images(self):
        # Final review I4: HEIC/HEIF is the iPhone default; prepare_media.py converts it.
        root = self.make_project()
        for name in ('IMG_0001.HEIC', 'תמונה.heif'):
            item = materials.save_upload('demo', name, io.BytesIO(b'photo'), 5)
            self.assertEqual(item['tag'], 'image')
            self.assertTrue((root / item['file']).is_file())
            self.assertTrue(item['file'].startswith('materials/images/'))
        target, mime = materials.file_path('demo', item['id'])
        self.assertEqual(mime, 'image/heif')
        with patch.object(materials.posters, 'ensure', return_value=root / 'poster.jpg') as ensure:
            self.assertEqual(materials.poster_path('demo', item['id']), root / 'poster.jpg')
        self.assertEqual(ensure.call_args.args[0], target)

    def test_upload_streams_outside_the_manifest_lock(self):
        # Final review M4: a long upload must not hold the lock every listing/serve needs.
        root = self.make_project()
        done = []
        def other_thread_lists():
            done.append(materials.list('demo'))
        import threading as _threading
        class Blocking(io.BytesIO):
            def read(self, n=-1):
                worker = _threading.Thread(target=other_thread_lists)
                worker.start(); worker.join(timeout=5)
                return super().read(n)

        item = materials.save_upload('demo', 'clip.mp4', Blocking(b'abc'), 3)
        self.assertEqual(len(done), 1, 'another thread could read the manifest while bytes were streaming')
        self.assertEqual((root / item['file']).read_bytes(), b'abc')
        self.assertFalse([p for p in (root / 'materials').rglob('.studio-upload-*')])

    def test_a_failed_manifest_write_rolls_the_file_back(self):
        # Final review M4 (round 2): never a file the manifest does not list.
        root = self.make_project()
        with patch.object(materials, '_write_manifest', side_effect=OSError('disk full')):
            with self.assertRaises(materials.MaterialsError):
                materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'abc'), 3)
        self.assertFalse([p for p in (root / 'materials').rglob('*') if p.is_file() and p.name != 'materials.json'])

    def test_stale_upload_temp_files_are_cleaned_at_start(self):
        root = self.make_project()
        stale = [root / 'materials' / '.studio-upload-abc', root / 'materials' / 'raw' / '.studio-upload-def']
        for path in stale:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'partial')
        keep = root / 'materials' / 'raw' / 'take.mp4'
        keep.write_bytes(b'video')
        self.assertEqual(materials.clean_stale_uploads(root.parents[1]), 2)
        self.assertFalse(any(path.exists() for path in stale))
        self.assertTrue(keep.exists())

    def test_a_short_upload_leaves_no_temp_file(self):
        root = self.make_project()
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'ab'), 5)
        self.assertEqual(ctx.exception.status, 400)
        self.assertFalse([p for p in (root / 'materials').rglob('*') if p.is_file() and p.name != 'materials.json'])

    def test_collision_renames(self):
        root = self.make_project()
        first = materials.save_upload('demo', 'logo.png', io.BytesIO(b'a'), 1)
        second = materials.save_upload('demo', 'logo.png', io.BytesIO(b'b'), 1)
        self.assertEqual(first['file'], 'materials/images/logo.png')
        self.assertEqual(second['file'], 'materials/images/logo (2).png')
        self.assertEqual((root / 'materials' / 'images' / 'logo.png').read_bytes(), b'a')
        self.assertEqual((root / 'materials' / 'images' / 'logo (2).png').read_bytes(), b'b')

    def test_owned_appends_ledger_row(self):
        root = self.make_project()
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'a'), 1)
        updated = materials.update('demo', item['id'], {'owned': True})
        self.assertTrue(updated['owned'])
        ledger = root / 'asset-ledger.csv'
        self.assertTrue(ledger.is_file())
        with ledger.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['asset_id'], item['id'])
        self.assertEqual(rows[0]['file'], item['file'])
        self.assertEqual(rows[0]['license_or_permission'], 'owner-supplied')
        # Setting owned=True again must not duplicate the ledger row.
        materials.update('demo', item['id'], {'owned': True})
        with ledger.open(encoding='utf-8-sig', newline='') as f:
            rows_again = list(csv.DictReader(f))
        self.assertEqual(len(rows_again), 1)

    def test_ledger_starts_with_bom_and_round_trips_hebrew_commas_and_quotes(self):
        root = self.make_project()
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'a'), 1)
        tricky_note = 'שיר "אהבה", חלק 2'
        materials.update('demo', item['id'], {'note': tricky_note})
        materials.update('demo', item['id'], {'owned': True})
        ledger = root / 'asset-ledger.csv'
        raw = ledger.read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'), 'ledger must start with a UTF-8 BOM for Excel on Windows')
        # Only the header carries a BOM; the appended row underneath must not repeat it.
        self.assertEqual(raw.count(b'\xef\xbb\xbf'), 1)
        with ledger.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['notes'], tricky_note)
        self.assertEqual(rows[0]['asset_id'], item['id'])

    def test_add_from_library_copies(self):
        root = self.make_project()
        library_root = self.studio / 'library'
        (library_root / 'images').mkdir(parents=True)
        (library_root / 'images' / 'brand-logo.png').write_bytes(b'logo-bytes')
        (library_root / 'materials.json').write_text(json.dumps({'items': [
            {'id': 'lib-1', 'file': 'images/brand-logo.png', 'tag': 'logo', 'note': '',
             'owned': True, 'size': 10, 'added_at': '2026-01-01T00:00:00+00:00'},
        ]}), encoding='utf-8')
        item = materials.add_from_library('demo', 'lib-1')
        self.assertEqual(item['tag'], 'logo')
        self.assertEqual(item['file'], 'materials/images/brand-logo.png')
        saved = root / 'materials' / 'images' / 'brand-logo.png'
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_bytes(), b'logo-bytes')
        listed = materials.list('demo')
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['id'], item['id'])

    def test_rejects_unknown_project(self):
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.save_upload('missing', 'clip.mp4', io.BytesIO(b'd'), 1)
        self.assertEqual(ctx.exception.status, 404)

    def test_rejects_project_directory_not_in_registry(self):
        # A directory can look exactly right on disk but still must not be reachable
        # unless it is also a registered project (fix round 1, finding 5).
        root = self.studio / 'projects' / 'unregistered'
        for sub in ('raw', 'broll', 'images', 'audio'):
            (root / 'materials' / sub).mkdir(parents=True)
        (root / 'materials.json').write_text(json.dumps({'items': []}), encoding='utf-8')
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.save_upload('unregistered', 'clip.mp4', io.BytesIO(b'd'), 1)
        self.assertEqual(ctx.exception.status, 404)

    def test_incomplete_upload_leaves_no_file_and_no_temp(self):
        root = self.make_project()

        class ShortStream:
            """Declares 10 bytes but the connection drops after 4 -- same shape as a
            real client disconnecting mid-upload."""
            def __init__(self):
                self.sent = False

            def read(self, n=-1):
                if self.sent:
                    return b''
                self.sent = True
                return b'abcd'

        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.save_upload('demo', 'short.mp4', ShortStream(), 10)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.message_key, 'materials.error.incomplete')
        raw_dir = root / 'materials' / 'raw'
        self.assertEqual(list(raw_dir.iterdir()), [])
        self.assertEqual(materials.list('demo'), [])

    def test_tag_change_moves_file_to_new_folder(self):
        root = self.make_project()
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'a'), 1)
        self.assertEqual(item['file'], 'materials/raw/clip.mp4')
        updated = materials.update('demo', item['id'], {'tag': 'music'})
        self.assertEqual(updated['tag'], 'music')
        self.assertEqual(updated['file'], 'materials/audio/clip.mp4')
        self.assertFalse((root / 'materials' / 'raw' / 'clip.mp4').exists())
        moved = root / 'materials' / 'audio' / 'clip.mp4'
        self.assertTrue(moved.is_file())
        self.assertEqual(moved.read_bytes(), b'a')
        self.assertEqual(materials.list('demo')[0]['file'], 'materials/audio/clip.mp4')

    def test_voice_tag_for_a_voice_over(self):
        root = self.make_project()
        item = materials.save_upload('demo', 'קול.m4a', io.BytesIO(b'v'), 1)
        self.assertEqual(item['tag'], 'music')  # audio still auto-tags as music
        updated = materials.update('demo', item['id'], {'tag': 'voice'})
        self.assertEqual((updated['tag'], updated['file']), ('voice', 'materials/audio/קול.m4a'))
        self.assertTrue((root / 'materials' / 'audio' / 'קול.m4a').is_file())
        self.assertIn('voice', materials.TAGS)

    def test_tag_change_within_same_folder_does_not_move_the_file(self):
        root = self.make_project()
        materials.save_upload('demo', 'first.mp4', io.BytesIO(b'a'), 1)  # tag=raw
        second = materials.save_upload('demo', 'second.mp4', io.BytesIO(b'b'), 1)  # tag=broll (raw taken)
        self.assertEqual(second['tag'], 'broll')
        updated = materials.update('demo', second['id'], {'tag': 'screen'})  # also folder 'broll'
        self.assertEqual(updated['file'], second['file'])
        self.assertTrue((root / second['file']).is_file())

    def test_tag_change_move_renames_on_collision(self):
        root = self.make_project()
        (root / 'materials' / 'audio' / 'clip.mp4').write_bytes(b'existing')
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'a'), 1)
        updated = materials.update('demo', item['id'], {'tag': 'music'})
        self.assertEqual(updated['file'], 'materials/audio/clip (2).mp4')
        self.assertEqual((root / 'materials' / 'audio' / 'clip (2).mp4').read_bytes(), b'a')
        self.assertEqual((root / 'materials' / 'audio' / 'clip.mp4').read_bytes(), b'existing')

    def test_tag_change_reverts_move_when_manifest_write_fails(self):
        # Fix round 2, finding 1: a cross-folder tag change moves the file first, then
        # persists the manifest. If the manifest write fails, the (unchanged, still-old)
        # manifest on disk would otherwise point at a path that no longer exists.
        root = self.make_project()
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'a'), 1)  # raw
        with patch('materials.atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(materials.MaterialsError) as ctx:
                materials.update('demo', item['id'], {'tag': 'music'})
        self.assertEqual(ctx.exception.status, 503)
        self.assertTrue((root / 'materials' / 'raw' / 'clip.mp4').is_file())
        self.assertFalse((root / 'materials' / 'audio' / 'clip.mp4').exists())
        self.assertEqual((root / 'materials' / 'raw' / 'clip.mp4').read_bytes(), b'a')
        listed = materials.list('demo')
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['file'], 'materials/raw/clip.mp4')
        self.assertEqual(listed[0]['tag'], 'raw')

    # --- Task 9: materials.list_library() ---

    def test_list_library_missing_is_empty_not_error(self):
        self.assertEqual(materials.list_library(), [])

    def test_list_library_returns_items(self):
        library_root = self.studio / 'library'
        (library_root / 'images').mkdir(parents=True)
        (library_root / 'images' / 'brand-logo.png').write_bytes(b'logo-bytes')
        (library_root / 'materials.json').write_text(json.dumps({'items': [
            {'id': 'lib-1', 'file': 'images/brand-logo.png', 'tag': 'logo', 'note': '',
             'owned': True, 'size': 10, 'added_at': '2026-01-01T00:00:00+00:00'},
        ]}), encoding='utf-8')
        items = materials.list_library()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], 'lib-1')

    def test_list_library_corrupt_manifest_is_503(self):
        library_root = self.studio / 'library'
        library_root.mkdir(parents=True)
        (library_root / 'materials.json').write_text('{not valid json', encoding='utf-8')
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.list_library()
        self.assertEqual(ctx.exception.status, 503)

    # --- Task 9: materials.file_path() ---

    def test_file_path_resolves_uploaded_item(self):
        root = self.make_project()
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'video-bytes'), len(b'video-bytes'))
        target, mime = materials.file_path('demo', item['id'])
        self.assertEqual(target, (root / 'materials' / 'raw' / 'clip.mp4').resolve())
        self.assertEqual(mime, 'video/mp4')
        self.assertEqual(target.read_bytes(), b'video-bytes')

    def test_file_path_follows_a_tag_change_move(self):
        self.make_project()
        item = materials.save_upload('demo', 'clip.mp4', io.BytesIO(b'a'), 1)
        materials.update('demo', item['id'], {'tag': 'music'})
        target, mime = materials.file_path('demo', item['id'])
        self.assertEqual(target.name, 'clip.mp4')
        self.assertIn('audio', target.parts)
        self.assertEqual(mime, 'video/mp4')  # mime follows the extension, not the tag

    def test_file_path_unknown_item_is_404(self):
        self.make_project()
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.file_path('demo', 'missing-item')
        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(ctx.exception.message_key, 'materials.error.unknownItem')

    def test_file_path_unknown_project_is_404(self):
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.file_path('missing', 'x')
        self.assertEqual(ctx.exception.status, 404)

    def test_file_path_rejects_traversal_recorded_in_manifest(self):
        # A malformed/tampered manifest entry pointing outside materials/ must never be
        # served, even though file_path() trusts the manifest for the relative path.
        root = self.make_project()
        manifest_path = root / 'materials.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['items'].append({'id': 'evil', 'file': '../../etc/passwd', 'tag': 'raw', 'note': '',
                                   'owned': False, 'size': 0, 'added_at': '2026-01-01T00:00:00+00:00'})
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.file_path('demo', 'evil')
        self.assertEqual(ctx.exception.status, 404)

    def test_file_path_rejects_unsupported_extension_recorded_in_manifest(self):
        root = self.make_project()
        (root / 'materials' / 'raw' / 'virus.exe').write_bytes(b'x')
        manifest_path = root / 'materials.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['items'].append({'id': 'bad-ext', 'file': 'materials/raw/virus.exe', 'tag': 'raw', 'note': '',
                                   'owned': False, 'size': 1, 'added_at': '2026-01-01T00:00:00+00:00'})
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.file_path('demo', 'bad-ext')
        self.assertEqual(ctx.exception.status, 404)

    def test_file_path_missing_file_on_disk_is_404(self):
        root = self.make_project()
        manifest_path = root / 'materials.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['items'].append({'id': 'gone', 'file': 'materials/raw/gone.mp4', 'tag': 'raw', 'note': '',
                                   'owned': False, 'size': 0, 'added_at': '2026-01-01T00:00:00+00:00'})
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(materials.MaterialsError) as ctx:
            materials.file_path('demo', 'gone')
        self.assertEqual(ctx.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
