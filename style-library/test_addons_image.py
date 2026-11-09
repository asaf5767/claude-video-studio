"""Task 21 follow-up: scripts/addons_image.py (optional OpenAI Images / Azure AI
Foundry image add-on client). Never makes a real network call --
`urllib.request.urlopen` is mocked throughout. Follows style-library/test_addons.py's
pattern of patching `library.BASE`/`STUDIO` at a temp dir."""
import base64
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

_spec = importlib.util.spec_from_file_location('studio_addons_image', SCRIPTS / 'addons_image.py')
addons_image = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(addons_image)

import library  # style-library/library.py


def run_main(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = addons_image.main(argv)
    text = buffer.getvalue().strip()
    parsed = json.loads(text) if text else None
    return code, parsed


def b64_response(*payloads):
    return io.BytesIO(json.dumps({'data': [{'b64_json': base64.b64encode(p).decode()} for p in payloads]}).encode())


class AddonsImageTest(unittest.TestCase):
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

    def enable_image(self, provider='openai-images', key='sk-test-image', endpoint=None):
        (self.base / 'settings.json').write_text(
            json.dumps({'addons': {'image': {'enabled': True, 'provider': provider}}}), encoding='utf-8')
        env_lines = []
        if key is not None:
            env_lines.append(f'STUDIO_IMAGE_KEY={key}')
        if endpoint is not None:
            env_lines.append(f'STUDIO_IMAGE_ENDPOINT={endpoint}')
        (self.studio / '.env').write_text('\n'.join(env_lines) + ('\n' if env_lines else ''), encoding='utf-8')

    def prompt_file(self, text):
        path = self.studio / 'prompt.txt'
        path.write_text(text, encoding='utf-8')
        return path

    # --- openai-images: correct request, atomic write ---

    def test_openai_images_enabled_with_key_calls_openai_and_writes_png_atomically(self):
        self.enable_image(provider='openai-images')
        prompt_path = self.prompt_file('תמונה של חוף בשקיעה')
        out_path = self.studio / 'scene.png'
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            captured['headers'] = {k.lower(): v for k, v in request.headers.items()}
            captured['body'] = json.loads(request.data.decode('utf-8'))
            return b64_response(b'PNGDATA')

        with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])

        self.assertEqual(code, 0)
        self.assertEqual(captured['url'], 'https://api.openai.com/v1/images/generations')
        self.assertEqual(captured['headers'].get('authorization'), 'Bearer sk-test-image')
        self.assertEqual(captured['body']['model'], addons_image.DEFAULT_MODEL)
        self.assertEqual(captured['body']['prompt'], 'תמונה של חוף בשקיעה')
        self.assertEqual(captured['body']['size'], '1024x1536')
        self.assertEqual(captured['body']['n'], 1)
        self.assertEqual(out_path.read_bytes(), b'PNGDATA')
        self.assertEqual(report, {'ok': True, 'out': str(out_path), 'bytes': len(b'PNGDATA')})
        self.assertEqual([p.name for p in self.studio.glob('.studio-write-*')], [])

    def test_custom_size_is_sent(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(b'P')) as mock_open:
            run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--size', '1024x1024'])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['size'], '1024x1024')

    def test_multiple_images_write_numbered_siblings(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen',
                   return_value=b64_response(b'ONE', b'TWO', b'THREE')):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--n', '3'])
        self.assertEqual(code, 0)
        self.assertEqual(out_path.read_bytes(), b'ONE')
        self.assertEqual((self.studio / 'scene-2.png').read_bytes(), b'TWO')
        self.assertEqual((self.studio / 'scene-3.png').read_bytes(), b'THREE')
        self.assertEqual(report['bytes'], len(b'ONE') + len(b'TWO') + len(b'THREE'))
        self.assertEqual(sorted(report['out']), sorted([str(out_path), str(self.studio / 'scene-2.png'), str(self.studio / 'scene-3.png')]))

    # --- foundry: endpoint-dependent request ---

    def test_foundry_uses_configured_endpoint_and_api_key_header(self):
        self.enable_image(provider='foundry', key='sk-foundry',
                           endpoint='https://my-resource.openai.azure.com/openai/deployments/my-deploy')
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            captured['headers'] = {k.lower(): v for k, v in request.headers.items()}
            return b64_response(b'FOUNDRY-PNG')

        with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])

        self.assertEqual(code, 0)
        self.assertEqual(captured['url'],
                          'https://my-resource.openai.azure.com/openai/deployments/my-deploy/images/generations'
                          f'?api-version={addons_image.FOUNDRY_API_VERSION}')
        self.assertEqual(captured['headers'].get('api-key'), 'sk-foundry')
        self.assertEqual(out_path.read_bytes(), b'FOUNDRY-PNG')

    def test_foundry_without_endpoint_is_a_coded_error(self):
        self.enable_image(provider='foundry', key='sk-foundry', endpoint=None)
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.no-endpoint')
        mock_open.assert_not_called()

    # --- disabled / missing key ---

    def test_disabled_exits_3_with_coded_error(self):
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.image-disabled')
        mock_open.assert_not_called()
        self.assertFalse(out_path.exists())

    def test_missing_key_is_the_same_coded_disabled_error(self):
        self.enable_image(key=None)
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.image-disabled')

    # --- HTTP errors: coded, never leak the key ---

    def test_http_401_becomes_coded_error_without_leaking_the_key(self):
        self.enable_image(key='sk-super-secret-image')
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'

        def raise_401(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', {}, io.BytesIO(b'sk-super-secret-image'))

        with patch('addons_client.urllib.request.urlopen', side_effect=raise_401):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertNotIn('sk-super-secret-image', json.dumps(report))
        self.assertEqual(report['code'], 'addons.http-401')
        self.assertFalse(out_path.exists())

    def test_http_429_and_500_become_distinct_coded_errors(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        for status in (429, 500):
            out_path = self.studio / f'scene-{status}.png'

            def raise_error(request, timeout=None, status=status):
                raise urllib.error.HTTPError(request.full_url, status, 'error', {}, io.BytesIO(b''))

            with patch('addons_client.urllib.request.urlopen', side_effect=raise_error):
                code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
            self.assertEqual(code, 3)
            self.assertEqual(report['code'], f'addons.http-{status}')

    def test_network_error_is_coded_addons_network(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', side_effect=urllib.error.URLError('dns failure')):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.network')

    def test_bad_response_without_image_data_is_a_coded_error(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', return_value=io.BytesIO(b'{"data": []}')):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.bad-response')

    # --- spending guard: --allow-cost, not --force (fix round 1, RULING R43) ---

    def test_more_than_4_images_is_refused_without_allow_cost(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--n', '5'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.too-many-images')
        mock_open.assert_not_called()

    def test_allow_cost_bypasses_the_image_count_guard(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        images = [f'IMG{i}'.encode() for i in range(5)]
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(*images)):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path),
                                      '--n', '5', '--allow-cost'])
        self.assertEqual(code, 0)
        self.assertEqual(len(report['out']), 5)

    def test_force_does_not_bypass_the_image_count_guard(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path),
                                      '--n', '5', '--force'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.too-many-images')
        mock_open.assert_not_called()

    def test_disabled_is_reported_even_when_n_is_also_too_many(self):
        # require_enabled runs before the spending guard (fix round 1, minor finding).
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--n', '5'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.image-disabled')

    # --- overwrite: --force, not --allow-cost (fix round 1, RULING R43) ---

    def test_existing_out_is_refused_without_force(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        out_path.write_bytes(b'OLD')
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.exists')
        mock_open.assert_not_called()
        self.assertEqual(out_path.read_bytes(), b'OLD')

    def test_force_overwrites_an_existing_out(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        out_path.write_bytes(b'OLD')
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(b'NEW')):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--force'])
        self.assertEqual(code, 0)
        self.assertEqual(out_path.read_bytes(), b'NEW')

    def test_allow_cost_does_not_bypass_the_overwrite_check(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        out_path.write_bytes(b'OLD')
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--allow-cost'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.exists')
        mock_open.assert_not_called()

    def test_existing_numbered_sibling_is_refused_without_force_even_if_out_itself_is_new(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        (self.studio / 'scene-2.png').write_bytes(b'OLD-SIBLING')
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--n', '2'])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.exists')
        mock_open.assert_not_called()
        self.assertFalse(out_path.exists())  # never written -- checked before the call

    # --- model id: --model, else STUDIO_IMAGE_MODEL, else the default ---

    def test_model_flag_overrides_the_default(self):
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(b'P')) as mock_open:
            run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--model', 'flag-model'])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model'], 'flag-model')

    def test_studio_image_model_env_var_is_used_when_no_model_flag(self):
        self.enable_image()
        (self.studio / '.env').write_text(
            (self.studio / '.env').read_text(encoding='utf-8') + 'STUDIO_IMAGE_MODEL=env-model\n', encoding='utf-8')
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(b'P')) as mock_open:
            run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model'], 'env-model')

    def test_model_flag_wins_over_the_env_var(self):
        self.enable_image()
        (self.studio / '.env').write_text(
            (self.studio / '.env').read_text(encoding='utf-8') + 'STUDIO_IMAGE_MODEL=env-model\n', encoding='utf-8')
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(b'P')) as mock_open:
            run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--model', 'flag-model'])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model'], 'flag-model')

    def test_foundry_request_also_carries_the_resolved_model(self):
        self.enable_image(provider='foundry', key='sk-foundry',
                           endpoint='https://my-resource.openai.azure.com/openai/deployments/my-deploy')
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen', return_value=b64_response(b'P')) as mock_open:
            run_main(['--prompt-file', str(prompt_path), '--out', str(out_path), '--model', 'flag-model'])
        body = json.loads(mock_open.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(body['model'], 'flag-model')

    # --- --project: reads settings/.env from, and writes under, the given studio root ---

    def test_project_flag_reads_state_and_writes_output_under_that_studio_root(self):
        other = tempfile.TemporaryDirectory()
        try:
            other_root = Path(other.name).resolve()
            other_base = other_root / 'style-library'
            other_base.mkdir()
            (other_base / 'settings.json').write_text(
                json.dumps({'addons': {'image': {'enabled': True, 'provider': 'openai-images'}}}), encoding='utf-8')
            (other_root / '.env').write_text('STUDIO_IMAGE_KEY=sk-other-project\n', encoding='utf-8')

            prompt_path = self.prompt_file('x')  # lives in the disabled default studio
            out_path = other_root / 'scene.png'
            captured = {}

            def fake_urlopen(request, timeout=None):
                captured['headers'] = {k.lower(): v for k, v in request.headers.items()}
                return b64_response(b'PROJECT-PNG')

            with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
                code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path),
                                          '--project', str(other_root)])

            self.assertEqual(code, 0)
            self.assertEqual(captured['headers'].get('authorization'), 'Bearer sk-other-project')
            self.assertEqual(out_path.read_bytes(), b'PROJECT-PNG')
            self.assertEqual(report['out'], str(out_path))
        finally:
            other.cleanup()

    def test_project_flag_disabled_state_in_that_project_is_reported(self):
        self.enable_image()  # this test's own (patched) studio IS enabled
        other = tempfile.TemporaryDirectory()
        try:
            other_root = Path(other.name).resolve()
            (other_root / 'style-library').mkdir()  # no settings.json/.env: disabled by default
            prompt_path = self.prompt_file('x')
            out_path = other_root / 'scene.png'
            with patch('addons_client.urllib.request.urlopen') as mock_open:
                code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path),
                                          '--project', str(other_root)])
            self.assertEqual(code, 3)
            self.assertEqual(report['code'], 'addons.image-disabled')
            mock_open.assert_not_called()
        finally:
            other.cleanup()

    # --- invalid input encoding ---

    def test_invalid_utf8_prompt_file_is_a_coded_bad_input_error(self):
        self.enable_image()
        prompt_path = self.studio / 'bad.txt'
        prompt_path.write_bytes(b'\xff\xfe not valid utf-8 \x80\x81')
        out_path = self.studio / 'scene.png'
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.bad-input')
        mock_open.assert_not_called()

    # --- non-HTTPS endpoint: direct unit test of the shared helper ---

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
        self.enable_image()
        prompt_path = self.prompt_file('x')
        out_path = self.studio / 'scene.png'
        oversized = io.BytesIO(b'x' * 20)
        with patch.object(addons_client, 'MAX_RESPONSE_BYTES', 10), \
             patch('addons_client.urllib.request.urlopen', return_value=oversized):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 3)
        self.assertEqual(report['code'], 'addons.bad-response')
        self.assertFalse(out_path.exists())

    # --- Hebrew prompt round-trips UTF-8 ---

    def test_hebrew_prompt_round_trips_utf8(self):
        self.enable_image()
        hebrew = 'ציור של ים כנרת בשעת בוקר, סגנון אקוורל.'
        prompt_path = self.prompt_file(hebrew)
        out_path = self.studio / 'scene.png'
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['body'] = json.loads(request.data.decode('utf-8'))
            return b64_response(b'PNG')

        with patch('addons_client.urllib.request.urlopen', side_effect=fake_urlopen):
            code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(out_path)])
        self.assertEqual(code, 0)
        self.assertEqual(captured['body']['prompt'], hebrew)

    # --- final review C1: Foundry endpoint host allowlist and the key-free --check ---

    def test_foundry_endpoint_outside_azure_is_refused_before_any_call(self):
        prompt_path = self.prompt_file('x')
        for endpoint in ('https://attacker.example/x', 'https://openai.azure.com.attacker.example/x',
                         'https://user@my.openai.azure.com/x', 'https://my.openai.azure.com:8443/x',
                         'http://my.openai.azure.com/x', 'https://my.openai.azure.com/x?k=1'):
            with self.subTest(endpoint=endpoint):
                self.enable_image(provider='foundry', key='sk-foundry', endpoint=endpoint)
                with patch('addons_client.urllib.request.urlopen') as mock_open:
                    code, report = run_main(['--prompt-file', str(prompt_path), '--out', str(self.studio / 'a.png')])
                self.assertEqual((code, report['code']), (3, 'addons.bad-endpoint'))
                self.assertNotIn('sk-foundry', json.dumps(report))
                mock_open.assert_not_called()

    def test_foundry_endpoint_on_each_azure_host_is_accepted(self):
        for host in ('my.openai.azure.com', 'my.services.ai.azure.com', 'my.cognitiveservices.azure.com'):
            with self.subTest(host=host):
                self.enable_image(provider='foundry', key='sk-foundry', endpoint=f'https://{host}/openai/deployments/d')
                self.assertEqual(addons_image.check(), {'ok': True, 'provider': 'foundry'})

    def test_check_reports_ready_or_the_coded_reason_without_the_key(self):
        with patch('addons_client.urllib.request.urlopen') as mock_open:
            code, report = run_main(['--check'])
            self.assertEqual((code, report['code']), (3, 'addons.image-disabled'))
            self.enable_image(key='sk-secret-image')
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = addons_image.main(['--check'])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(buffer.getvalue()), {'ok': True, 'provider': 'openai-images'})
            self.assertNotIn('sk-secret-image', buffer.getvalue())
            self.enable_image(provider='foundry', key='sk-foundry', endpoint=None)
            code, report = run_main(['--check'])
            self.assertEqual((code, report['code']), (3, 'addons.no-endpoint'))
        mock_open.assert_not_called()

    def test_without_check_the_prompt_and_out_are_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            addons_image.main(['--out', str(self.studio / 'a.png')])


if __name__ == '__main__':
    unittest.main()
