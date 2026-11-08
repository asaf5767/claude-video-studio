"""Task 21: optional voice and image add-ons (off by default, never required). Follows
the /ui-language, /ui-motion server-test pattern (library.py's settings.json), but also
patches library.STUDIO since the API key is written only to .env at the studio root,
never to settings.json."""
import http.client
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import addons
import library
from serve import Handler


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class AddonsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Path(self.temp.name).resolve()
        self.base = self.studio / 'style-library'
        self.base.mkdir()
        self.base_patch = patch.object(library, 'BASE', self.base)
        self.studio_patch = patch.object(library, 'STUDIO', self.studio)
        self.base_patch.start()
        self.studio_patch.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.studio_patch.stop()
        self.base_patch.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request(method, path, body, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def post_headers(self, **extra):
        headers = {'Origin': self.origin, 'Content-Type': 'application/json', 'X-Studio-Action': 'addons'}
        headers.update(extra)
        return headers

    def get_addons(self):
        status, data = self.request('GET', '/addons')
        self.assertEqual(status, 200)
        return json.loads(data)

    def post_addons(self, body):
        return self.request('POST', '/addons', json.dumps(body), **self.post_headers())

    # --- Step 1 failing tests from the brief ---

    def test_defaults_disabled(self):
        self.assertEqual(self.get_addons(), {
            'voice': {'enabled': False, 'provider': None, 'has_key': False},
            'image': {'enabled': False, 'provider': None, 'has_key': False},
        })

    def test_key_saved_to_env_not_settings(self):
        status, _ = self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-test-voice'}})
        self.assertEqual(status, 200)
        settings = json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))
        self.assertNotIn('sk-test-voice', json.dumps(settings))
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertIn('STUDIO_VOICE_KEY=sk-test-voice', env)

    def test_get_never_returns_key(self):
        self.post_addons({'image': {'enabled': True, 'provider': 'openai-images', 'key': 'sk-test-image'}})
        status, data = self.request('GET', '/addons')
        self.assertEqual(status, 200)
        self.assertNotIn('sk-test-image', data.decode())
        body = json.loads(data)
        self.assertEqual(body['image'], {'enabled': True, 'provider': 'openai-images', 'has_key': True})

    def test_unknown_provider_rejected(self):
        for patch_body in [
            {'voice': {'enabled': True, 'provider': 'unknown-voice-co'}},
            {'image': {'enabled': True, 'provider': 'midjourney'}},
            {'image': {'enabled': True, 'provider': 'elevenlabs'}},  # wrong kind's provider
        ]:
            status, _ = self.post_addons(patch_body)
            self.assertEqual(status, 400, patch_body)
        self.assertEqual(self.get_addons()['voice']['enabled'], False)
        self.assertEqual(self.get_addons()['image']['enabled'], False)

    # --- Further coverage ---

    def test_enabling_without_a_provider_is_rejected(self):
        status, _ = self.post_addons({'voice': {'enabled': True, 'provider': None}})
        self.assertEqual(status, 400)
        status, _ = self.post_addons({'voice': {'enabled': True}})
        self.assertEqual(status, 400)

    def test_disabling_clears_provider(self):
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs'}})
        self.post_addons({'voice': {'enabled': False, 'provider': None}})
        self.assertEqual(self.get_addons()['voice'], {'enabled': False, 'provider': None, 'has_key': False})

    def test_empty_key_clears_stored_key(self):
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-test-voice'}})
        self.assertTrue(self.get_addons()['voice']['has_key'])
        status, _ = self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': ''}})
        self.assertEqual(status, 200)
        self.assertFalse(self.get_addons()['voice']['has_key'])
        self.assertNotIn('STUDIO_VOICE_KEY', (self.studio / '.env').read_text(encoding='utf-8'))

    def test_omitting_key_leaves_existing_key_untouched(self):
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-test-voice'}})
        status, _ = self.post_addons({'voice': {'enabled': False, 'provider': None}})
        self.assertEqual(status, 200)
        self.assertTrue(self.get_addons()['voice']['has_key'])

    def test_updating_one_addon_preserves_the_other(self):
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-voice'}})
        self.post_addons({'image': {'enabled': True, 'provider': 'foundry', 'key': 'sk-image'}})
        data = self.get_addons()
        self.assertEqual(data['voice'], {'enabled': True, 'provider': 'elevenlabs', 'has_key': True})
        self.assertEqual(data['image'], {'enabled': True, 'provider': 'foundry', 'has_key': True})
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertIn('STUDIO_VOICE_KEY=sk-voice', env)
        self.assertIn('STUDIO_IMAGE_KEY=sk-image', env)

    def test_rejects_extra_keys_and_malformed_body(self):
        for body in [
            {'voice': {'enabled': True, 'provider': 'elevenlabs', 'extra': 1}},
            {'voice': {'enabled': 'yes', 'provider': 'elevenlabs'}},
            {'other': {'enabled': True}},
            {},
            ['voice'],
        ]:
            status, _ = self.post_addons(body)
            self.assertEqual(status, 400, body)

    def test_addons_requires_action_header_and_same_origin(self):
        headers = self.post_headers()
        del headers['X-Studio-Action']
        status, _ = self.request('POST', '/addons', json.dumps({'voice': {'enabled': False, 'provider': None}}), **headers)
        self.assertEqual(status, 403)
        status, _ = self.request('POST', '/addons', json.dumps({'voice': {'enabled': False, 'provider': None}}),
                                  **self.post_headers(Origin='http://evil.example'))
        self.assertEqual(status, 403)

    def test_addons_body_is_capped_small(self):
        huge = json.dumps({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'x' * 5000}})
        status, _ = self.request('POST', '/addons', huge, **self.post_headers())
        self.assertEqual(status, 413)

    def test_addons_write_is_atomic(self):
        (self.base / 'settings.json').write_text(json.dumps({'addons': {'voice': {'enabled': True, 'provider': 'elevenlabs'}}}), encoding='utf-8')
        with patch('addons.atomic_write', side_effect=OSError('disk full')):
            status, _ = self.post_addons({'image': {'enabled': True, 'provider': 'foundry'}})
        self.assertEqual(status, 503)
        saved = json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, {'addons': {'voice': {'enabled': True, 'provider': 'elevenlabs'}}})

    def test_env_file_preserves_unrelated_keys(self):
        (self.studio / '.env').write_text('UNRELATED_SETTING=keep-me\n', encoding='utf-8')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-voice'}})
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertIn('UNRELATED_SETTING=keep-me', env)
        self.assertIn('STUDIO_VOICE_KEY=sk-voice', env)

    # --- Fix round 1 ---

    def test_env_round_trip_preserves_comments_blanks_and_hand_written_formatting(self):
        raw = ('# header comment\n'
               '\n'
               'UNRELATED_SETTING = keep-me\n'
               'export OTHER_KEY=also-keep\n'
               '\n'
               '# trailing comment\n')
        (self.studio / '.env').write_text(raw, encoding='utf-8')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-voice'}})
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertIn('# header comment\n', env)
        self.assertIn('\n\n', env)  # the blank line survives
        self.assertIn('UNRELATED_SETTING = keep-me\n', env)
        self.assertIn('export OTHER_KEY=also-keep\n', env)
        self.assertIn('# trailing comment\n', env)
        self.assertIn('STUDIO_VOICE_KEY=sk-voice', env)

    def test_env_with_duplicate_key_lines_updates_the_first_and_drops_later_ones(self):
        (self.studio / '.env').write_text('STUDIO_VOICE_KEY=old1\nA=1\nSTUDIO_VOICE_KEY=old2\n', encoding='utf-8')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'new'}})
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertEqual(env.splitlines(), ['STUDIO_VOICE_KEY=new', 'A=1'])

    def test_env_with_duplicate_key_lines_crlf_updates_the_first_and_drops_later_ones(self):
        (self.studio / '.env').write_bytes(b'STUDIO_VOICE_KEY=old1\r\nA=1\r\nSTUDIO_VOICE_KEY=old2\r\n')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'new'}})
        data = (self.studio / '.env').read_bytes()
        self.assertEqual(data, b'STUDIO_VOICE_KEY=new\r\nA=1\r\n')

    def test_env_replaces_a_spaced_or_exported_existing_key_in_place(self):
        (self.studio / '.env').write_text('A=1\nexport STUDIO_VOICE_KEY = old-value\nB=2\n', encoding='utf-8')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'new-value'}})
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertEqual(env.splitlines(), ['A=1', 'STUDIO_VOICE_KEY=new-value', 'B=2'])

    def test_clearing_a_key_removes_only_that_line(self):
        (self.studio / '.env').write_text('A=1\nSTUDIO_VOICE_KEY=sk-voice\nB=2\n', encoding='utf-8')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': ''}})
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertEqual(env.splitlines(), ['A=1', 'B=2'])

    def test_env_preserves_crlf_line_endings_for_untouched_and_replaced_lines(self):
        (self.studio / '.env').write_bytes(b'A=1\r\nSTUDIO_VOICE_KEY=old\r\nB=2\r\n')
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'new'}})
        data = (self.studio / '.env').read_bytes()
        self.assertEqual(data, b'A=1\r\nSTUDIO_VOICE_KEY=new\r\nB=2\r\n')

    def test_key_value_with_internal_spaces_round_trips_exactly(self):
        value = '  spaced key value  '
        status, _ = self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': value}})
        self.assertEqual(status, 200)
        env = (self.studio / '.env').read_text(encoding='utf-8')
        self.assertIn(f'STUDIO_VOICE_KEY={value}\n', env)
        # has_key still reflects reality: a key of pure whitespace would read back as "unset"
        # (state() strips before checking emptiness), but padding around real content is kept.
        self.assertTrue(self.get_addons()['voice']['has_key'])

    @unittest.skipIf(os.name == 'nt', 'POSIX file-mode bits are not meaningful on Windows')
    def test_env_file_mode_is_0600_after_write(self):
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-voice'}})
        mode = stat.S_IMODE((self.studio / '.env').stat().st_mode)
        self.assertEqual(mode, 0o600)

    @unittest.skipIf(os.name == 'nt', 'POSIX file-mode bits are not meaningful on Windows')
    def test_env_file_mode_is_enforced_even_if_it_previously_had_looser_permissions(self):
        path = self.studio / '.env'
        path.write_text('A=1\n', encoding='utf-8')
        path.chmod(0o644)
        self.post_addons({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': 'sk-voice'}})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_addons_save_shares_librarys_settings_lock_with_ui_language_and_ui_motion(self):
        self.assertIs(addons.library._SETTINGS_LOCK, library._SETTINGS_LOCK)
        acquired_inner, release_outer = threading.Event(), threading.Event()

        def hold_lock():
            with library._SETTINGS_LOCK:
                acquired_inner.set()
                release_outer.wait(2)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        self.assertTrue(acquired_inner.wait(2))
        outcome = {}

        def do_save():
            outcome['result'] = addons.save({'voice': {'enabled': True, 'provider': 'elevenlabs'}})

        saver = threading.Thread(target=do_save)
        saver.start()
        time.sleep(0.2)  # addons.save() should still be blocked on the lock held above
        still_blocked = saver.is_alive()
        release_outer.set()
        saver.join(2)
        holder.join(2)
        self.assertTrue(still_blocked, "addons.save() did not wait for library's settings lock")
        self.assertIn('result', outcome)

    def test_two_threads_saving_addons_and_ui_motion_concurrently_never_lose_either_key(self):
        errors = []

        def retrying(fn):
            # The two threads are serialized by the shared lock, so a PermissionError
            # here is never about losing a write -- it's the same transient Windows
            # file-lock (e.g. AV briefly holding a just-replaced file) that
            # addons._chmod_best_effort already tolerates in production. A few retries
            # keep this stress test about the lock-sharing fix, not Windows I/O flakiness.
            for attempt in range(5):
                try:
                    return fn()
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02)

        def save_addons_repeatedly():
            try:
                for i in range(40):
                    retrying(lambda i=i: addons.save({'voice': {'enabled': True, 'provider': 'elevenlabs', 'key': f'sk-{i}'}}))
            except Exception as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        def save_motion_repeatedly():
            try:
                for i in range(40):
                    retrying(lambda i=i: library.set_ui_motion('always' if i % 2 else 'off'))
            except Exception as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        threads = [threading.Thread(target=save_addons_repeatedly), threading.Thread(target=save_motion_repeatedly)]
        for t in threads: t.start()
        for t in threads: t.join(10)
        self.assertEqual(errors, [])
        saved = json.loads((self.base / 'settings.json').read_text(encoding='utf-8'))
        self.assertIn(saved.get('motion'), library.MOTIONS)
        self.assertEqual(saved.get('addons', {}).get('voice', {}).get('provider'), 'elevenlabs')
        self.assertEqual(saved.get('addons', {}).get('voice', {}).get('enabled'), True)


class EnvFileTests(unittest.TestCase):
    """Fix round 1: direct unit tests for addons.py's raw .env read/write helpers --
    byte-for-byte preservation of everything an add-ons save doesn't itself touch."""

    def test_match_env_line_ignores_comments_and_blank_lines(self):
        self.assertIsNone(addons._match_env_line('# a comment'))
        self.assertIsNone(addons._match_env_line('   # indented comment'))
        self.assertIsNone(addons._match_env_line('   '))
        self.assertIsNone(addons._match_env_line(''))

    def test_match_env_line_tolerates_export_and_spacing_but_keeps_the_values_own_whitespace(self):
        self.assertEqual(addons._match_env_line('KEY=value'), ('KEY', 'value'))
        self.assertEqual(addons._match_env_line('export KEY=value'), ('KEY', 'value'))
        self.assertEqual(addons._match_env_line('KEY = value'), ('KEY', 'value'))
        # Whitespace immediately touching `=` is formatting, not value content (so
        # "KEY = value" above reads as 'value', not ' value'); trailing whitespace in
        # the value itself still survives exactly.
        self.assertEqual(addons._match_env_line('KEY=value with spaces  '), ('KEY', 'value with spaces  '))

    def test_apply_env_updates_preserves_comments_blanks_and_unrelated_lines_untouched(self):
        raw = '# header\n\nA=1\nexport B = two\n# trailing\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'sk-voice'})
        lines = out.splitlines(keepends=True)
        self.assertEqual(lines[:5], ['# header\n', '\n', 'A=1\n', 'export B = two\n', '# trailing\n'])
        self.assertEqual(lines[5], 'STUDIO_VOICE_KEY=sk-voice\n')

    def test_apply_env_updates_replaces_existing_key_in_place_regardless_of_spacing_or_export(self):
        raw = 'A=1\nexport STUDIO_VOICE_KEY = old\nB=2\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'new'})
        self.assertEqual(out.splitlines(), ['A=1', 'STUDIO_VOICE_KEY=new', 'B=2'])

    def test_apply_env_updates_removes_the_line_for_a_cleared_key(self):
        raw = 'A=1\nSTUDIO_VOICE_KEY=old\nB=2\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': None})
        self.assertEqual(out.splitlines(), ['A=1', 'B=2'])

    def test_apply_env_updates_preserves_crlf_line_endings_and_uses_crlf_for_a_new_line(self):
        raw = 'A=1\r\nB=2\r\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'sk-voice'})
        self.assertEqual(out, 'A=1\r\nB=2\r\nSTUDIO_VOICE_KEY=sk-voice\r\n')

    def test_apply_env_updates_replace_keeps_that_lines_own_crlf_ending(self):
        raw = 'A=1\r\nSTUDIO_VOICE_KEY=old\r\nB=2\r\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'new'})
        self.assertEqual(out, 'A=1\r\nSTUDIO_VOICE_KEY=new\r\nB=2\r\n')

    # --- Fix round 2: duplicate STUDIO_VOICE_KEY/STUDIO_IMAGE_KEY lines ---

    def test_apply_env_updates_updates_only_the_first_duplicate_and_drops_later_ones_lf(self):
        raw = 'STUDIO_VOICE_KEY=old1\nA=1\nSTUDIO_VOICE_KEY=old2\nB=2\nSTUDIO_VOICE_KEY=old3\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'new'})
        self.assertEqual(out.splitlines(), ['STUDIO_VOICE_KEY=new', 'A=1', 'B=2'])

    def test_apply_env_updates_updates_only_the_first_duplicate_and_drops_later_ones_crlf(self):
        raw = 'STUDIO_VOICE_KEY=old1\r\nA=1\r\nSTUDIO_VOICE_KEY=old2\r\nB=2\r\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'new'})
        self.assertEqual(out, 'STUDIO_VOICE_KEY=new\r\nA=1\r\nB=2\r\n')

    def test_apply_env_updates_clearing_a_duplicated_key_still_drops_every_occurrence(self):
        raw = 'STUDIO_VOICE_KEY=old1\nA=1\nSTUDIO_VOICE_KEY=old2\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': None})
        self.assertEqual(out.splitlines(), ['A=1'])

    def test_apply_env_updates_duplicate_handling_is_independent_per_key(self):
        raw = 'STUDIO_VOICE_KEY=v1\nSTUDIO_IMAGE_KEY=i1\nSTUDIO_VOICE_KEY=v2\nSTUDIO_IMAGE_KEY=i2\n'
        out = addons._apply_env_updates(raw, {'STUDIO_VOICE_KEY': 'new-voice', 'STUDIO_IMAGE_KEY': 'new-image'})
        self.assertEqual(out.splitlines(), ['STUDIO_VOICE_KEY=new-voice', 'STUDIO_IMAGE_KEY=new-image'])

    def test_apply_env_updates_adds_a_missing_trailing_newline_before_appending(self):
        out = addons._apply_env_updates('A=1', {'STUDIO_VOICE_KEY': 'sk-voice'})
        self.assertEqual(out, 'A=1\nSTUDIO_VOICE_KEY=sk-voice\n')

    def test_apply_env_updates_on_an_empty_file_just_appends(self):
        out = addons._apply_env_updates('', {'STUDIO_VOICE_KEY': 'sk-voice'})
        self.assertEqual(out, 'STUDIO_VOICE_KEY=sk-voice\n')

    def test_value_with_trailing_spaces_round_trips_through_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Path(tmp)
            with patch.object(library, 'STUDIO', studio):
                (studio / '.env').write_text('STUDIO_VOICE_KEY=padded value  \n', encoding='utf-8')
                self.assertEqual(addons._read_env()['STUDIO_VOICE_KEY'], 'padded value  ')


if __name__ == '__main__':
    unittest.main()
