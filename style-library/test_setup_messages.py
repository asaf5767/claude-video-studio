"""Plain-language setup: consent installs, bilingual messages, registry-block detection.

Loads scripts/setup.py and scripts/setup_messages.py the same way test_setup.py does
(importlib from a fixed path, not a package import), so this suite runs standalone
and never installs anything real -- subprocess is always patched.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

msg_spec = importlib.util.spec_from_file_location('setup_messages', ROOT / 'scripts/setup_messages.py')
setup_messages = importlib.util.module_from_spec(msg_spec)
msg_spec.loader.exec_module(setup_messages)

setup_spec = importlib.util.spec_from_file_location('studio_setup', ROOT / 'scripts/setup.py')
setup = importlib.util.module_from_spec(setup_spec)
setup_spec.loader.exec_module(setup)


class PlanInstallsTests(unittest.TestCase):
    def test_plan_windows_ffmpeg(self):
        self.assertEqual(setup.plan_installs('windows', {'ffmpeg'}), [["winget", "install", "--id", "Gyan.FFmpeg", "-e"]])

    def test_plan_mac_node(self):
        self.assertEqual(setup.plan_installs('mac', {'node'}), [["brew", "install", "node"]])

    def test_plan_windows_node_and_ffmpeg_is_deterministically_ordered(self):
        self.assertEqual(setup.plan_installs('windows', {'ffmpeg', 'node'}),
                          [["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e"],
                           ["winget", "install", "--id", "Gyan.FFmpeg", "-e"]])

    def test_plan_mac_whisper_cpp(self):
        self.assertEqual(setup.plan_installs('mac', {'whisper-cpp'}), [["brew", "install", "whisper-cpp"]])

    def test_plan_windows_has_no_whisper_cpp_package_id(self):
        # Windows gets whisper.cpp from the official release zip, not winget (no such package).
        self.assertEqual(setup.plan_installs('windows', {'whisper-cpp'}), [])

    def test_plan_unknown_os_is_empty(self):
        self.assertEqual(setup.plan_installs('linux', {'node'}), [])

    def test_plan_empty_missing_is_empty(self):
        self.assertEqual(setup.plan_installs('windows', set()), [])


class MessageTests(unittest.TestCase):
    def test_messages_exist_in_both_languages(self):
        he_keys = set(setup_messages.MESSAGES['he'])
        en_keys = set(setup_messages.MESSAGES['en'])
        self.assertTrue(he_keys, 'Hebrew message table must not be empty')
        self.assertEqual(he_keys, en_keys)

    def test_message_returns_requested_language(self):
        self.assertNotEqual(setup_messages.message('setup.missing-tool.ffmpeg', 'he'),
                             setup_messages.message('setup.missing-tool.ffmpeg', 'en'))

    def test_message_defaults_to_hebrew_for_unknown_language(self):
        self.assertEqual(setup_messages.message('setup.npm-blocked', 'fr'),
                          setup_messages.message('setup.npm-blocked', 'he'))

    def test_message_falls_back_to_key_for_unknown_key(self):
        self.assertEqual(setup_messages.message('setup.does-not-exist', 'he'), 'setup.does-not-exist')

    def test_hebrew_tool_message_is_plain_language_with_consent_question(self):
        text = setup_messages.message('setup.missing-tool.ffmpeg', 'he')
        self.assertIn('FFmpeg', text)
        self.assertIn('(כ/ל)', text)

    def test_english_tool_message_asks_consent(self):
        text = setup_messages.message('setup.missing-tool.ffmpeg', 'en')
        self.assertIn('FFmpeg', text)
        self.assertIn('(y/n)', text)


class RegistryBlockTests(unittest.TestCase):
    def test_detect_registry_block_true_on_nonzero_exit(self):
        with patch.object(setup.tools, 'resolve', return_value='/npm'), \
             patch.object(setup.subprocess, 'run', return_value=setup.subprocess.CompletedProcess(['npm', 'ping'], 1)):
            self.assertTrue(setup.detect_registry_block())

    def test_detect_registry_block_true_on_timeout(self):
        with patch.object(setup.tools, 'resolve', return_value='/npm'), \
             patch.object(setup.subprocess, 'run', side_effect=setup.subprocess.TimeoutExpired('npm ping', 15)):
            self.assertTrue(setup.detect_registry_block())

    def test_detect_registry_block_false_on_success(self):
        with patch.object(setup.tools, 'resolve', return_value='/npm'), \
             patch.object(setup.subprocess, 'run', return_value=setup.subprocess.CompletedProcess(['npm', 'ping'], 0)):
            self.assertFalse(setup.detect_registry_block())

    def test_registry_block_message_offered(self):
        """Patch detect_registry_block True -> friendly message printed, no traceback (clean SystemExit)."""
        buf = io.StringIO()
        with patch.object(setup, 'detect_registry_block', return_value=True), contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit):
                setup.ensure_npm_registry_open('he')
        self.assertIn(setup_messages.message('setup.npm-blocked', 'he'), buf.getvalue())
        self.assertNotIn('Traceback', buf.getvalue())

    def test_registry_open_does_not_raise(self):
        with patch.object(setup, 'detect_registry_block', return_value=False):
            setup.ensure_npm_registry_open('he')  # must not raise


class PrerequisitesMessageTests(unittest.TestCase):
    def test_hebrew_message_lists_missing_tools(self):
        with patch.object(setup.shutil, 'which', side_effect=lambda t: None if t in ('ffmpeg', 'ffprobe') else '/tool'):
            with self.assertRaises(SystemExit) as ctx:
                setup.raise_if_prerequisites_missing('he')
        self.assertEqual(str(ctx.exception), setup_messages.message('setup.prerequisites-missing', 'he').format(tools='ffmpeg, ffprobe'))

    def test_english_message_lists_missing_tools(self):
        with patch.object(setup.shutil, 'which', side_effect=lambda t: None if t == 'node' else '/tool'):
            with self.assertRaises(SystemExit) as ctx:
                setup.raise_if_prerequisites_missing('en')
        self.assertEqual(str(ctx.exception), setup_messages.message('setup.prerequisites-missing', 'en').format(tools='node'))

    def test_nothing_missing_does_not_raise(self):
        with patch.object(setup.shutil, 'which', return_value='/tool'):
            setup.raise_if_prerequisites_missing('he')  # must not raise


class AskConsentTests(unittest.TestCase):
    def test_auto_yes_short_circuits_even_without_a_tty(self):
        with patch.object(setup.sys.stdin, 'isatty', return_value=False):
            self.assertTrue(setup.ask_consent('x?', True))

    def test_non_tty_without_auto_yes_is_no(self):
        # No one is there to answer a prompt (e.g. piped/CI stdin) -> never install.
        with patch.object(setup.sys.stdin, 'isatty', return_value=False):
            self.assertFalse(setup.ask_consent('x?', False))

    def test_tty_reads_hebrew_yes(self):
        with patch.object(setup.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='כ'):
            self.assertTrue(setup.ask_consent('x?', False))

    def test_tty_reads_english_yes(self):
        with patch.object(setup.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='y'):
            self.assertTrue(setup.ask_consent('x?', False))

    def test_tty_reads_no(self):
        with patch.object(setup.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='ל'):
            self.assertFalse(setup.ask_consent('x?', False))

    def test_eof_is_no(self):
        with patch.object(setup.sys.stdin, 'isatty', return_value=True), patch('builtins.input', side_effect=EOFError):
            self.assertFalse(setup.ask_consent('x?', False))


class ModelDownloadPlanTests(unittest.TestCase):
    def test_model_without_url_or_sha_is_pending_not_downloaded(self):
        config = {'transcription': {'engine': 'whisper.cpp', 'models': {'he': {'path': 'models/ggml-he.bin'}}}}
        with patch.object(setup, 'download_and_verify', side_effect=AssertionError('must not download a pending model')):
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=True)
        self.assertEqual(result, {'he': 'pending'})

    def test_model_given_as_bare_string_path_is_pending(self):
        # Task 16's draft config shape (plain path string, no url/sha256 yet).
        config = {'transcription': {'engine': 'whisper.cpp', 'models': {'he': 'models/ggml-he.bin', 'en': 'models/ggml-en.bin'}}}
        with patch.object(setup, 'download_and_verify', side_effect=AssertionError('must not download a pending model')):
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=True)
        self.assertEqual(result, {'he': 'pending', 'en': 'pending'})

    def test_non_whisper_engine_is_skipped(self):
        config = {'transcription': {'engine': 'mlx-whisper'}}
        with patch.object(setup, 'download_and_verify', side_effect=AssertionError('legacy engine must not trigger whisper.cpp downloads')):
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=True)
        self.assertEqual(result, {})

    def test_model_with_url_and_sha_is_downloaded_when_missing(self):
        config = {'transcription': {'engine': 'whisper.cpp',
                                     'models': {'he': {'path': 'models/ggml-he.bin', 'url': 'https://example.invalid/ggml-he.bin', 'sha256': 'a' * 64}}}}
        with patch.object(setup, 'download_and_verify', return_value=True) as fake:
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=True)
        fake.assert_called_once()
        self.assertEqual(result, {'he': 'installed'})

    def test_model_download_declined_without_consent_is_skipped(self):
        config = {'transcription': {'engine': 'whisper.cpp',
                                     'models': {'he': {'path': 'models/ggml-he.bin', 'url': 'https://example.invalid/ggml-he.bin', 'sha256': 'a' * 64}}}}
        with patch.object(setup, 'download_and_verify', side_effect=AssertionError('must not download without consent')), \
             patch.object(setup, 'ask_consent', return_value=False):
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=False)
        self.assertEqual(result, {'he': 'skipped'})

    def test_real_task16_shape_models_string_plus_model_sources_dict(self):
        # studio.config.json as Task 16 actually recorded it: `models.<lang>` is a bare
        # path string, and the url/sha256 live in a sibling `model_sources.<lang>` dict
        # -- not inline on the model entry. ensure_transcription_models must join them.
        config = {'transcription': {
            'engine': 'whisper.cpp',
            'models': {'he': 'models/ggml-ivrit-ai-large-v3-turbo.bin'},
            'model_sources': {'he': {'url': 'https://example.invalid/ggml-model.bin', 'sha256': 'b' * 64, 'size_bytes': 123}},
        }}
        with patch.object(setup, 'download_and_verify', return_value=True) as fake:
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=True)
        fake.assert_called_once_with('https://example.invalid/ggml-model.bin', 'b' * 64,
                                      setup.ROOT / 'models/ggml-ivrit-ai-large-v3-turbo.bin', lang='he')
        self.assertEqual(result, {'he': 'installed'})

    def test_real_task16_shape_missing_model_sources_entry_is_pending(self):
        # 'en' has a path but no matching model_sources entry yet -> pending, not an error.
        config = {'transcription': {
            'engine': 'whisper.cpp',
            'models': {'he': 'models/x.bin', 'en': 'models/y.bin'},
            'model_sources': {'he': {'url': 'https://example.invalid/x.bin', 'sha256': 'c' * 64}},
        }}
        with patch.object(setup, 'download_and_verify', return_value=True):
            result = setup.ensure_transcription_models(config, lang='he', auto_yes=True)
        self.assertEqual(result, {'he': 'installed', 'en': 'pending'})


class DownloadAndVerifyTests(unittest.TestCase):
    def test_refuses_non_https_url(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'model.bin'
            with patch.object(setup.urllib.request, 'urlopen', side_effect=AssertionError('must not fetch a non-https url')):
                self.assertFalse(setup.download_and_verify('http://example.invalid/model.bin', 'a' * 64, dest))
            self.assertFalse(dest.exists())

    def test_refuses_non_https_url_prints_plain_message(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'model.bin'
            with contextlib.redirect_stdout(buf):
                setup.download_and_verify('ftp://example.invalid/model.bin', 'a' * 64, dest, lang='he')
        self.assertIn(setup_messages.message('setup.insecure-url', 'he'), buf.getvalue())


class ConsentInstallTests(unittest.TestCase):
    def test_missing_installable_tools_node_and_ffmpeg(self):
        with patch.object(setup.shutil, 'which', return_value=None):
            self.assertEqual(setup.missing_installable_tools({}), {'node', 'ffmpeg'})

    def test_missing_installable_tools_none_missing(self):
        with patch.object(setup.shutil, 'which', return_value='/tool'):
            self.assertEqual(setup.missing_installable_tools({}), set())

    def test_missing_installable_tools_adds_whisper_cpp_on_mac_when_engine_set(self):
        config = {'transcription': {'engine': 'whisper.cpp'}}

        def which(name):
            return '/tool' if name in ('node', 'ffmpeg') else None

        with patch.object(setup.shutil, 'which', side_effect=which), \
             patch.object(setup.platform, 'system', return_value='Darwin'):
            self.assertEqual(setup.missing_installable_tools(config), {'whisper-cpp'})

    def test_offer_consent_installs_runs_the_resolved_absolute_installer_path(self):
        # plan_installs()/plan_install_one() must keep returning the bare "winget"/
        # "brew" form (test_plan_windows_ffmpeg etc. depend on it) -- only the actual
        # subprocess call made here should use the resolved absolute path, so it runs
        # even when the bare name isn't directly executable (same Windows .CMD-shim
        # problem scripts/tools.py exists for).
        with patch.object(setup, 'missing_installable_tools', return_value={'ffmpeg'}), \
             patch.object(setup, 'detect_os', return_value='windows'), \
             patch.object(setup.shutil, 'which', return_value=r'C:\Windows\System32\winget.exe'), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'refresh_path', return_value=True), \
             patch.object(setup.subprocess, 'run', return_value=setup.subprocess.CompletedProcess([], 0)) as run:
            setup.offer_consent_installs('he', False, {})
        # Task 19: winget's own source/package-terms question is pre-answered (the owner
        # already said yes to this install), or it would wait forever without a terminal.
        run.assert_called_once_with([r"C:\Windows\System32\winget.exe", "install", "--id", "Gyan.FFmpeg", "-e",
                                     "--accept-source-agreements", "--accept-package-agreements"], check=True)

    def test_offer_consent_installs_skips_on_decline(self):
        with patch.object(setup, 'missing_installable_tools', return_value={'ffmpeg'}), \
             patch.object(setup, 'detect_os', return_value='windows'), \
             patch.object(setup.shutil, 'which', return_value='/winget'), \
             patch.object(setup, 'ask_consent', return_value=False), \
             patch.object(setup.subprocess, 'run', side_effect=AssertionError('must not install without consent')):
            setup.offer_consent_installs('he', False, {})  # must not raise

    def test_offer_consent_installs_explains_missing_winget(self):
        buf = io.StringIO()
        with patch.object(setup, 'missing_installable_tools', return_value={'ffmpeg'}), \
             patch.object(setup, 'detect_os', return_value='windows'), \
             patch.object(setup.shutil, 'which', return_value=None), \
             patch.object(setup, 'ask_consent', side_effect=AssertionError('must not ask when winget itself is missing')), \
             contextlib.redirect_stdout(buf):
            setup.offer_consent_installs('he', False, {})
        self.assertIn(setup_messages.message('setup.need-winget', 'he'), buf.getvalue())

    def test_offer_consent_installs_nothing_missing_is_silent(self):
        with patch.object(setup, 'missing_installable_tools', return_value=set()), \
             patch.object(setup, 'ask_consent', side_effect=AssertionError('nothing to ask about')):
            setup.offer_consent_installs('he', False, {})  # must not raise


class AssistantConsentTests(unittest.TestCase):
    """Task 19: an assistant asks the owner about each install in chat, then runs setup with
    --yes-to <exactly what they agreed to>; everything else is still asked (= "no" without a
    terminal). A tool winget just installed is found in the same run (PATH refresh)."""

    def test_consent_for_plain_bools_and_named_items(self):
        self.assertTrue(setup.consent_for(True, 'matting'))
        self.assertFalse(setup.consent_for(False, 'matting'))
        self.assertFalse(setup.consent_for(None, 'matting'))
        self.assertTrue(setup.consent_for({'node', 'model-he'}, 'model-he'))
        self.assertFalse(setup.consent_for({'node', 'model-he'}, 'model-en'))

    def test_only_the_named_tools_are_installed_without_a_terminal(self):
        with patch.object(setup, 'missing_installable_tools', return_value={'node', 'ffmpeg'}), \
             patch.object(setup, 'detect_os', return_value='mac'), \
             patch.object(setup.shutil, 'which', return_value='/opt/homebrew/bin/brew'), \
             patch.object(setup, 'refresh_path', return_value=False) as refresh, \
             patch.object(setup.sys.stdin, 'isatty', return_value=False), \
             patch.object(setup.subprocess, 'run', return_value=setup.subprocess.CompletedProcess([], 0)) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            setup.offer_consent_installs('he', {'ffmpeg'}, {})
        run.assert_called_once_with(['/opt/homebrew/bin/brew', 'install', 'ffmpeg'], check=True)
        refresh.assert_called_once_with()  # a Mac also picks up Homebrew's folders right away

    def test_windows_install_refreshes_path_so_the_new_tool_is_found(self):
        with patch.object(setup, 'missing_installable_tools', return_value={'node'}), \
             patch.object(setup, 'detect_os', return_value='windows'), \
             patch.object(setup.shutil, 'which', return_value='winget.exe'), \
             patch.object(setup, 'refresh_path') as refresh, \
             patch.object(setup.subprocess, 'run', return_value=setup.subprocess.CompletedProcess([], 0)), \
             contextlib.redirect_stdout(io.StringIO()):
            setup.offer_consent_installs('he', {'node'}, {})
        refresh.assert_called_once_with()

    def test_failed_install_does_not_refresh_or_crash(self):
        with patch.object(setup, 'missing_installable_tools', return_value={'node'}), \
             patch.object(setup, 'detect_os', return_value='windows'), \
             patch.object(setup.shutil, 'which', return_value='winget.exe'), \
             patch.object(setup, 'refresh_path', side_effect=AssertionError('nothing was installed')), \
             patch.object(setup.subprocess, 'run', side_effect=setup.subprocess.CalledProcessError(1, 'winget')), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            setup.offer_consent_installs('he', True, {})
        self.assertIn(setup_messages.message('setup.install-failed', 'he').format(tool='node'), out.getvalue())

    def test_refresh_appends_new_saved_entries_once_and_keeps_existing_order(self):
        sep = setup.os.pathsep
        base = sep.join(['/first', '/second'])
        with patch.dict(setup.os.environ, {'PATH': base}), patch.dict(setup.ENV, {'PATH': base}):
            self.assertTrue(setup.refresh_path(['/second', '/new/node', '/new/node', '/new/ffmpeg/']))
            self.assertEqual(setup.os.environ['PATH'], sep.join(['/first', '/second', '/new/node', '/new/ffmpeg/']))
            self.assertEqual(setup.ENV['PATH'], setup.os.environ['PATH'], 'commands setup runs see the new tools too')
            self.assertFalse(setup.refresh_path(['/first', '/new/node']))

    def test_refresh_is_a_no_op_off_windows_and_mac(self):
        with patch.object(setup.tools.os, 'name', 'posix'), patch.object(setup.tools.sys, 'platform', 'linux'),              patch.object(setup.tools, 'saved_windows_path', side_effect=AssertionError('no registry here')):
            self.assertFalse(setup.refresh_path())

    def test_models_and_matting_follow_their_own_names(self):
        config = {'transcription': {'engine': 'whisper.cpp', 'models': {'he': 'models/he.bin', 'en': 'models/en.bin'},
                                    'model_sources': {'he': {'url': 'https://example.invalid/he.bin', 'sha256': 'a' * 64},
                                                      'en': {'url': 'https://example.invalid/en.bin', 'sha256': 'b' * 64}}}}
        with patch.object(setup, 'download_and_verify', return_value=True) as fake, \
             patch.object(setup.sys.stdin, 'isatty', return_value=False), \
             contextlib.redirect_stdout(io.StringIO()):
            result = setup.ensure_transcription_models(config, lang='he', auto_yes={'model-he', 'matting'})
        self.assertEqual(result, {'he': 'installed', 'en': 'skipped'})
        fake.assert_called_once()
        with patch.object(setup, 'matting_runtime_available', return_value=False), \
             patch.object(setup.sys.stdin, 'isatty', return_value=False), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.install_matting({'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}, 'he', {'model-he'}),
                             {'matting': 'skipped'})

    def test_main_passes_exactly_the_agreed_items_and_rejects_unknown_ones(self):
        seen = {}

        def capture(name):
            def fake(*args, **kwargs):
                seen[name] = args
            return fake
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'style-library').mkdir()
            for name in ['catalog', 'projects', 'settings']:
                (root / f'style-library/{name}.example.json').write_text('{}', encoding='utf-8')
            with patch.object(setup, 'ROOT', root), \
                 patch.object(setup.sys, 'argv', ['setup', '--yes-to', 'node, model-he']), \
                 patch.object(setup, 'refresh_path', return_value=False), \
                 patch.object(setup, 'offer_consent_installs', side_effect=capture('tools')), \
                 patch.object(setup, 'raise_if_prerequisites_missing'), \
                 patch.object(setup, 'node_supported', return_value=True), \
                 patch.object(setup, 'guard_renderer_update'), \
                 patch.object(setup, 'PY', root / 'python'), \
                 patch.object(setup.venv, 'EnvBuilder'), \
                 patch.object(setup, 'run'), \
                 patch.object(setup, 'ensure_npm_registry_open'), \
                 patch.object(setup.tools, 'resolve', return_value='tool'), \
                 patch.object(setup.shutil, 'copy2'), \
                 patch.object(setup, 'ensure_whisper_engine', side_effect=capture('whisper')), \
                 patch.object(setup, 'ensure_transcription_models', side_effect=capture('models')), \
                 patch.object(setup, 'install_matting', side_effect=capture('matting')), \
                 patch.object(setup, 'capability_report', return_value={}), \
                 contextlib.redirect_stdout(io.StringIO()):
                setup.main()
        self.assertEqual(seen['tools'][1], {'node', 'model-he'})
        self.assertEqual(seen['whisper'][2], {'node', 'model-he'})
        self.assertEqual(seen['models'][2], {'node', 'model-he'})
        self.assertEqual(seen['matting'][2], {'node', 'model-he'})
        with patch.object(setup.sys, 'argv', ['setup', '--yes-to', 'node,everything']), \
             contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            setup.main()
        self.assertIn('everything', err.getvalue())


class WhisperEngineTests(unittest.TestCase):
    def test_whisper_cpp_windows_zip_is_pinned_to_a_release_with_assets(self):
        # v1.9.3-v1.9.5 ship no Windows assets at all (confirmed by Task 16's report);
        # v1.9.2 is the newest tag that actually has whisper-bin-x64.zip attached.
        self.assertIn('v1.9.2', setup.WHISPER_CPP_WINDOWS_ZIP_URL)
        self.assertIn('whisper-bin-x64.zip', setup.WHISPER_CPP_WINDOWS_ZIP_URL)
        self.assertNotIn('latest', setup.WHISPER_CPP_WINDOWS_ZIP_URL)

    def test_skipped_for_non_whisper_engine(self):
        self.assertIsNone(setup.ensure_whisper_engine({'transcription': {'engine': 'mlx-whisper'}}, 'he', True))

    def test_skipped_on_mac_handled_by_brew_elsewhere(self):
        with patch.object(setup.platform, 'system', return_value='Darwin'):
            self.assertIsNone(setup.ensure_whisper_engine({'transcription': {'engine': 'whisper.cpp'}}, 'he', True))

    def test_already_installed_on_windows(self):
        with patch.object(setup.os, 'name', 'nt'), \
             patch.object(setup.platform, 'system', return_value='Windows'), \
             patch.object(setup.Path, 'is_file', return_value=True), \
             patch.object(setup, 'download_whisper_cpp_windows', side_effect=AssertionError('already installed, must not download')):
            self.assertEqual(setup.ensure_whisper_engine({'transcription': {'engine': 'whisper.cpp'}}, 'he', True), 'installed')

    def test_download_declined_without_consent(self):
        with patch.object(setup.os, 'name', 'nt'), \
             patch.object(setup.platform, 'system', return_value='Windows'), \
             patch.object(setup.Path, 'is_file', return_value=False), \
             patch.object(setup, 'ask_consent', return_value=False), \
             patch.object(setup, 'download_whisper_cpp_windows', side_effect=AssertionError('must not download without consent')):
            self.assertEqual(setup.ensure_whisper_engine({'transcription': {'engine': 'whisper.cpp'}}, 'he', False), 'skipped')

    def test_download_success(self):
        with patch.object(setup.os, 'name', 'nt'), \
             patch.object(setup.platform, 'system', return_value='Windows'), \
             patch.object(setup.Path, 'is_file', return_value=False), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'download_whisper_cpp_windows', return_value=True):
            self.assertEqual(setup.ensure_whisper_engine({'transcription': {'engine': 'whisper.cpp'}}, 'he', True), 'installed')

    def test_download_failure(self):
        with patch.object(setup.os, 'name', 'nt'), \
             patch.object(setup.platform, 'system', return_value='Windows'), \
             patch.object(setup.Path, 'is_file', return_value=False), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'download_whisper_cpp_windows', return_value=False):
            self.assertEqual(setup.ensure_whisper_engine({'transcription': {'engine': 'whisper.cpp'}}, 'he', True), 'failed')


class LangResolutionTests(unittest.TestCase):
    def test_explicit_lang_wins(self):
        self.assertEqual(setup.resolve_lang('en'), 'en')
        self.assertEqual(setup.resolve_lang('he'), 'he')

    def test_falls_back_to_hebrew_when_library_unreadable(self):
        with patch.object(setup, 'ROOT', Path('/does/not/exist/on/this/machine')):
            self.assertEqual(setup.resolve_lang(None), 'he')


class HyperframesCacheDirTests(unittest.TestCase):
    def test_uses_env_var_when_set(self):
        with patch.dict(setup.os.environ, {'HYPERFRAMES_CACHE_DIR': '/custom/cache'}):
            self.assertEqual(setup.hyperframes_cache_dir(), Path('/custom/cache'))

    def test_defaults_to_home_cache(self):
        environ = dict(setup.os.environ)
        environ.pop('HYPERFRAMES_CACHE_DIR', None)
        with patch.dict(setup.os.environ, environ, clear=True):
            self.assertEqual(setup.hyperframes_cache_dir(), Path.home() / '.cache' / 'hyperframes')


class OnnxRuntimeNodeInstallTests(unittest.TestCase):
    def test_install_success(self):
        with patch.object(setup.tools, 'resolve', return_value='/npm'), \
             patch.object(setup.subprocess, 'run', return_value=setup.subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(setup.install_onnxruntime_node())
        run.assert_called_once()

    def test_install_failure(self):
        with patch.object(setup.tools, 'resolve', return_value='/npm'), \
             patch.object(setup.subprocess, 'run', side_effect=setup.subprocess.CalledProcessError(1, ['npm'])):
            self.assertFalse(setup.install_onnxruntime_node())

    def test_npm_missing(self):
        with patch.object(setup.tools, 'resolve', side_effect=setup.tools.ToolMissing('npm')):
            self.assertFalse(setup.install_onnxruntime_node())


class MattingRuntimeAvailableTests(unittest.TestCase):
    def test_true_when_the_pinned_version_sits_beside_the_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pkg = root / 'node_modules/onnxruntime-node/package.json'
            pkg.parent.mkdir(parents=True)
            pkg.write_text(json.dumps({'version': setup.ONNXRUNTIME_NODE_VERSION}), encoding='utf-8')
            with patch.object(setup, 'ROOT', root), patch.object(setup, 'hyperframes_cache_dir', return_value=root / 'cache'):
                self.assertTrue(setup.matting_runtime_available())

    def test_false_when_nowhere_to_be_found(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(setup, 'ROOT', root), patch.object(setup, 'hyperframes_cache_dir', return_value=root / 'cache'):
                self.assertFalse(setup.matting_runtime_available())

    def test_wrong_version_beside_the_cli_does_not_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pkg = root / 'node_modules/onnxruntime-node/package.json'
            pkg.parent.mkdir(parents=True)
            pkg.write_text(json.dumps({'version': '1.0.0'}), encoding='utf-8')
            with patch.object(setup, 'ROOT', root), patch.object(setup, 'hyperframes_cache_dir', return_value=root / 'cache'):
                self.assertFalse(setup.matting_runtime_available())


class MattingHookTests(unittest.TestCase):
    def test_install_matting_is_a_no_op_when_absent(self):
        with patch.object(setup.subprocess, 'run', side_effect=AssertionError('must not run anything')):
            self.assertIsNone(setup.install_matting({}))
            self.assertIsNone(setup.install_matting({'other': 1}))

    def test_unknown_backend_is_a_no_op(self):
        # Task 16b's actual decision ('hyperframes') is the only backend implemented
        # here; a different/future backend name must not crash or attempt anything.
        with patch.object(setup.subprocess, 'run', side_effect=AssertionError('unimplemented backend must not run installs')):
            self.assertIsNone(setup.install_matting({'matting': {'backend': 'rembg', 'model': 'u2net_human_seg'}}))

    def test_hyperframes_backend_already_installed_skips_consent(self):
        config = {'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}
        with patch.object(setup, '_file_matches_sha256', return_value=True), \
             patch.object(setup, 'matting_runtime_available', return_value=True), \
             patch.object(setup, 'ask_consent', side_effect=AssertionError('already installed, must not ask')):
            self.assertEqual(setup.install_matting(config, 'he', False), {'matting': 'installed'})

    def test_hyperframes_backend_declined_is_skipped(self):
        config = {'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}
        with patch.object(setup, '_file_matches_sha256', return_value=False), \
             patch.object(setup, 'matting_runtime_available', return_value=False), \
             patch.object(setup, 'ask_consent', return_value=False), \
             patch.object(setup, 'install_onnxruntime_node', side_effect=AssertionError('must not install without consent')), \
             patch.object(setup, 'download_and_verify', side_effect=AssertionError('must not download without consent')):
            self.assertEqual(setup.install_matting(config, 'he', False), {'matting': 'skipped'})

    def test_hyperframes_backend_installs_runtime_and_model_on_consent(self):
        config = {'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}
        with patch.object(setup, '_file_matches_sha256', return_value=False), \
             patch.object(setup, 'matting_runtime_available', return_value=False), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'install_onnxruntime_node', return_value=True) as runtime, \
             patch.object(setup, 'download_and_verify', return_value=True) as dl:
            self.assertEqual(setup.install_matting(config, 'he', True), {'matting': 'installed'})
        runtime.assert_called_once()
        dl.assert_called_once()

    def test_hyperframes_backend_runtime_already_ok_only_downloads_model(self):
        config = {'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}
        with patch.object(setup, '_file_matches_sha256', return_value=False), \
             patch.object(setup, 'matting_runtime_available', return_value=True), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'install_onnxruntime_node', side_effect=AssertionError('runtime already available, must not reinstall')), \
             patch.object(setup, 'download_and_verify', return_value=True):
            self.assertEqual(setup.install_matting(config, 'he', True), {'matting': 'installed'})

    def test_hyperframes_backend_runtime_install_failure_is_reported(self):
        config = {'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}
        with patch.object(setup, '_file_matches_sha256', return_value=False), \
             patch.object(setup, 'matting_runtime_available', return_value=False), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'install_onnxruntime_node', return_value=False), \
             patch.object(setup, 'download_and_verify', side_effect=AssertionError('must not try to download without a runtime')):
            self.assertEqual(setup.install_matting(config, 'he', True), {'matting': 'failed'})

    def test_hyperframes_backend_model_download_failure_is_reported(self):
        config = {'matting': {'backend': 'hyperframes', 'model': 'u2net_human_seg'}}
        with patch.object(setup, '_file_matches_sha256', return_value=False), \
             patch.object(setup, 'matting_runtime_available', return_value=True), \
             patch.object(setup, 'ask_consent', return_value=True), \
             patch.object(setup, 'download_and_verify', return_value=False):
            self.assertEqual(setup.install_matting(config, 'he', True), {'matting': 'failed'})


if __name__ == '__main__':
    unittest.main()
