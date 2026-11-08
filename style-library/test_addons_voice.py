"""Task 21 follow-up: scripts/addons_voice.py (optional ElevenLabs voice-over client).

Never makes a real network call -- `urllib.request.urlopen` is mocked throughout.
Follows style-library/test_addons.py's pattern of patching `library.BASE`/`STUDIO` at
a temp dir so `addons.py`'s settings.json/`.env` reads never touch the real studio.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location('studio_addons_voice', SCRIPTS / 'addons_voice.py')
addons_voice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(addons_voice)

import library  # style-library/library.py


def run_main(argv):
    """Run addons_voice.main(argv), returning (exit_code, printed_json_or_None)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = addons_voice.main(argv)
    text = buffer.getvalue().strip()
    parsed = json.loads(text) if text else None
    return code, parsed


class AddonsVoiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Path(self.temp.name).resolve()
        self.base = self.studio / 'style-library'
        self.base.mkdir()
        self.base_patch = patch.object(library, 'BASE', self.base)
        self.studio_patch = patch.object(library, 'STUDIO', self.studio)
        self.base_patch.start()
        self.studio_patch.start()

    def tearDown(self):
        self.studio_patch.stop()
        self.base_patch.stop()
        self.temp.cleanup()

    def enable_voice(self, key='sk-test-voice'):
        (self.base / 'settings.json').write_text(
            json.dumps({'addons': {'voice': {'enabled': True, 'provider': 'elevenlabs'}}}), encoding='utf-8')
        if key is not None:
            (self.studio / '.env').write_text(f'STUDIO_VOICE_KEY={key}\n', encoding='utf-8')

    def text_file(self, text):
        path = self.studio / 'script.txt'
        path.write_text(text, encoding='utf-8')
        return path

    # --- enabled + key: correct request, atomic write ---

    def test_enabled_with_key_calls_elevenlabs_and_writes_mp3_atomically(self):
        self.enable_voice()
        text_path = self.text_file('שלום עולם')
        out_path = self.studio / 'voice.mp3'
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            captured['headers'] = {k.lower(): v for k, v in request.headers.items()}
            captured['body'] = json.loads(request.data.decode('utf-8'))
            captured['timeout'] = timeout
            return io.BytesIO(b'FAKE-MP3-BYTES')

        with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])

        self.assertEqual(code, 0)
        self.assertEqual(captured['url'], f'https://api.elevenlabs.io/v1/text-to-speech/{addons_voice.DEFAULT_VOICE_ID}')
        self.assertEqual(captured['headers'].get('xi-api-key'), 'sk-test-voice')
        self.assertEqual(captured['body'], {'text': 'שלום עולם', 'model_id': 'eleven_multilingual_v2'})
        self.assertIsNotNone(captured['timeout'])
        self.assertEqual(out_path.read_bytes(), b'FAKE-MP3-BYTES')
        self.assertEqual(report, {'ok': True, 'out': str(out_path), 'chars': len('שלום עולם')})
        # No stray temp files left behind by the atomic write.
        self.assertEqual([p.name for p in self.studio.glob('.studio-write-*')], [])

    def test_custom_voice_id_is_used_in_the_url(self):
        self.enable_voice()
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'

        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'X')) as mock_open:
            run_main(['--text-file', str(text_path), '--out', str(out_path), '--voice', 'custom-id'])

        request = mock_open.call_args[0][0]
        self.assertEqual(request.full_url, 'https://api.elevenlabs.io/v1/text-to-speech/custom-id')

    def test_hebrew_text_round_trips_utf8(self):
        self.enable_voice()
        hebrew = 'זה טקסט בעברית עם ניקוד כמו שלום ותודה רבה.'
        text_path = self.text_file(hebrew)
        out_path = self.studio / 'voice.mp3'
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['body'] = json.loads(request.data.decode('utf-8'))
            return io.BytesIO(b'AUDIO')

        with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])

        self.assertEqual(code, 0)
        self.assertEqual(captured['body']['text'], hebrew)
        self.assertEqual(report['chars'], len(hebrew))
        self.assertEqual(out_path.read_text(encoding='utf-8', errors='replace'), 'AUDIO')

    # --- disabled / missing key: coded fallback, exit 3 ---

    def test_disabled_exits_3_with_coded_error(self):
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        mock_open.assert_not_called()
        self.assertFalse(out_path.exists())
        self.assertEqual(report['ok'], False)
        self.assertEqual(report['code'], 'addons.voice-disabled')
        self.assertTrue(report['message'])

    def test_missing_key_is_the_same_coded_disabled_error(self):
        self.enable_voice(key=None)  # enabled, but no STUDIO_VOICE_KEY in .env yet
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        mock_open.assert_not_called()
        self.assertEqual(report['code'], 'addons.voice-disabled')

    def test_disabled_addon_is_treated_the_same_even_with_a_key_present(self):
        (self.base / 'settings.json').write_text(
            json.dumps({'addons': {'voice': {'enabled': False, 'provider': None}}}), encoding='utf-8')
        (self.studio / '.env').write_text('STUDIO_VOICE_KEY=sk-test\n', encoding='utf-8')
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'
        code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.voice-disabled')

    # --- HTTP errors: coded, never leak the key ---

    def test_http_401_becomes_coded_error_without_leaking_the_key(self):
        self.enable_voice(key='sk-super-secret')
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'

        def raise_401(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', {}, io.BytesIO(b'sk-super-secret leaked'))

        with patch('addons_client.urllib.request.urlopen', side_effect=raise_401):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])

        self.assertEqual(code, 3)
        self.assertNotIn('sk-super-secret', json.dumps(report))
        self.assertEqual(report['code'], 'addons.http-401')
        self.assertFalse(out_path.exists())

    def test_http_429_and_500_become_distinct_coded_errors(self):
        self.enable_voice()
        text_path = self.text_file('hello')
        for status in (429, 500):
            out_path = self.studio / f'voice-{status}.mp3'

            def raise_error(request, timeout=None, status=status):
                raise urllib.error.HTTPError(request.full_url, status, 'error', {}, io.BytesIO(b''))

            with patch('addons_client.urllib.request.urlopen', side_effect=raise_error):
                code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
            self.assertEqual(code, 3)
            self.assertEqual(report['code'], f'addons.http-{status}')

    def test_network_error_is_coded_addons_network(self):
        self.enable_voice()
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'

        def raise_network(request, timeout=None):
            raise urllib.error.URLError('temporary failure in name resolution')

        with patch('addons_client.urllib.request.urlopen', side_effect=raise_network):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.network')

    # --- spending guard: --allow-cost, not --force (fix round 1, RULING R43) ---

    def test_text_over_5000_chars_is_refused_without_allow_cost(self):
        self.enable_voice()
        text_path = self.text_file('a' * 5001)
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.text-too-long')
        mock_open.assert_not_called()

    def test_allow_cost_bypasses_the_text_length_guard(self):
        self.enable_voice()
        text_path = self.text_file('a' * 5001)
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'X')):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path), '--allow-cost'])
        self.assertEqual(code, 0)
        self.assertEqual(report['chars'], 5001)

    def test_force_does_not_bypass_the_text_length_guard(self):
        self.enable_voice()
        text_path = self.text_file('a' * 5001)
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path), '--force'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.text-too-long')
        mock_open.assert_not_called()

    def test_disabled_is_reported_even_when_text_is_also_too_long(self):
        # require_enabled runs before the spending guard (fix round 1, minor finding):
        # the reported code must be the real reason, not whichever check runs first.
        text_path = self.text_file('a' * 5001)
        out_path = self.studio / 'voice.mp3'
        code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.voice-disabled')

    # --- overwrite: --force, not --allow-cost (fix round 1, RULING R43) ---

    def test_existing_out_is_refused_without_force(self):
        self.enable_voice()
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'
        out_path.write_bytes(b'OLD')
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.exists')
        mock_open.assert_not_called()
        self.assertEqual(out_path.read_bytes(), b'OLD')

    def test_force_overwrites_an_existing_out(self):
        self.enable_voice()
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'
        out_path.write_bytes(b'OLD')
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'NEW')):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path), '--force'])
        self.assertEqual(code, 0)
        self.assertEqual(out_path.read_bytes(), b'NEW')

    def test_allow_cost_does_not_bypass_the_overwrite_check(self):
        self.enable_voice()
        text_path = self.text_file('hello')
        out_path = self.studio / 'voice.mp3'
        out_path.write_bytes(b'OLD')
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path), '--allow-cost'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.exists')
        mock_open.assert_not_called()

    # --- model id: --model, else STUDIO_VOICE_MODEL, else the default ---

    def test_model_flag_overrides_the_default(self):
        self.enable_voice()
        text_path = self.text_file('hi')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'X')) as mock_open:
            run_main(['--text-file', str(text_path), '--out', str(out_path), '--model', 'eleven_turbo_v2_5'])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model_id'], 'eleven_turbo_v2_5')

    def test_studio_voice_model_env_var_is_used_when_no_model_flag(self):
        self.enable_voice()
        (self.studio / '.env').write_text(
            (self.studio / '.env').read_text(encoding='utf-8') + 'STUDIO_VOICE_MODEL=env-model\n', encoding='utf-8')
        text_path = self.text_file('hi')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'X')) as mock_open:
            run_main(['--text-file', str(text_path), '--out', str(out_path)])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model_id'], 'env-model')

    def test_model_flag_wins_over_the_env_var(self):
        self.enable_voice()
        (self.studio / '.env').write_text(
            (self.studio / '.env').read_text(encoding='utf-8') + 'STUDIO_VOICE_MODEL=env-model\n', encoding='utf-8')
        text_path = self.text_file('hi')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'X')) as mock_open:
            run_main(['--text-file', str(text_path), '--out', str(out_path), '--model', 'flag-model'])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model_id'], 'flag-model')

    def test_default_model_when_no_flag_and_no_env_var(self):
        self.enable_voice()
        text_path = self.text_file('hi')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'X')) as mock_open:
            run_main(['--text-file', str(text_path), '--out', str(out_path)])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model_id'], 'eleven_multilingual_v2')

    # --- --project: reads settings/.env from, and writes under, the given studio root ---

    def test_project_flag_reads_state_and_writes_output_under_that_studio_root(self):
        # setUp's patched library.BASE/STUDIO point at a *different*, disabled studio;
        # --project must override that for this one process, reading its own
        # settings.json/.env and writing --out relative to nothing but itself.
        other = tempfile.TemporaryDirectory()
        try:
            other_root = Path(other.name).resolve()
            other_base = other_root / 'style-library'
            other_base.mkdir()
            (other_base / 'settings.json').write_text(
                json.dumps({'addons': {'voice': {'enabled': True, 'provider': 'elevenlabs'}}}), encoding='utf-8')
            (other_root / '.env').write_text('STUDIO_VOICE_KEY=sk-other-project\n', encoding='utf-8')

            text_path = self.text_file('hi')  # lives in the *disabled* studio; --out below targets the other one
            out_path = other_root / 'voice.mp3'
            captured = {}

            def fake_urlopen(request, timeout=None):
                captured['headers'] = {k.lower(): v for k, v in request.headers.items()}
                return io.BytesIO(b'PROJECT-AUDIO')

            with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
                code, report = run_main(['--text-file', str(text_path), '--out', str(out_path),
                                          '--project', str(other_root)])

            self.assertEqual(code, 0)
            self.assertEqual(captured['headers'].get('xi-api-key'), 'sk-other-project')
            self.assertEqual(out_path.read_bytes(), b'PROJECT-AUDIO')
            self.assertEqual(report['out'], str(out_path))
        finally:
            other.cleanup()

    def test_project_flag_disabled_state_in_that_project_is_reported(self):
        self.enable_voice()  # this test's own (patched) studio IS enabled
        other = tempfile.TemporaryDirectory()
        try:
            other_root = Path(other.name).resolve()
            (other_root / 'style-library').mkdir()  # no settings.json/.env there: disabled by default
            text_path = self.text_file('hi')
            out_path = other_root / 'voice.mp3'
            with patch('addons_client.urllib.request.urlopen') as mock_open:
                code, report = run_main(['--text-file', str(text_path), '--out', str(out_path),
                                          '--project', str(other_root)])
            self.assertEqual(code, 3)
            self.assertEqual(report['code'], 'addons.voice-disabled')
            mock_open.assert_not_called()
        finally:
            other.cleanup()

    # --- invalid input encoding ---

    def test_invalid_utf8_text_file_is_a_coded_bad_input_error(self):
        self.enable_voice()
        text_path = self.studio / 'bad.txt'
        text_path.write_bytes(b'\xff\xfe not valid utf-8 \x80\x81')
        out_path = self.studio / 'voice.mp3'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.bad-input')
        mock_open.assert_not_called()

    # --- non-HTTPS endpoint: direct unit test of the shared helper (the script itself
    # always builds an https:// URL, so this exercises addons_client.http_request's
    # own guard the same way EnvFileTests in test_addons.py unit-tests addons.py's
    # private helpers directly) ---

    def test_non_https_endpoint_is_a_coded_bad_endpoint_error(self):
        import addons_client
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            with self.assertRaises(addons_client.AddonsClientError) as caught:
                addons_client.http_request('http://insecure.example/x', {}, b'{}')
        self.assertEqual(caught.exception.code, 'addons.bad-endpoint')
        mock_open.assert_not_called()

    # --- response size cap ---

    def test_oversized_response_is_a_coded_bad_response_error(self):
        import addons_client
        self.enable_voice()
        text_path = self.text_file('hi')
        out_path = self.studio / 'voice.mp3'
        oversized = io.BytesIO(b'x' * 20)
        with patch.object(addons_client, 'MAX_RESPONSE_BYTES', 10), \
             patch('addons_client.urllib.request.urlopen', return_value=oversized):
            code, report = run_main(['--text-file', str(text_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.bad-response')
        self.assertFalse(out_path.exists())


if __name__ == '__main__':
    unittest.main()
