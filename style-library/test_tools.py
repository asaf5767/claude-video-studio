"""Windows-safe tool resolution: never call npm/npx/node/python3 by bare name."""
import importlib.util
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'scripts/tools.py'
spec = importlib.util.spec_from_file_location('studio_tools', path)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class ResolveTests(unittest.TestCase):
    def test_resolve_uses_which_result(self):
        with patch.object(tools.shutil, 'which', return_value='C:\\nodejs\\npm.CMD') as which:
            self.assertEqual(tools.resolve('npm'), 'C:\\nodejs\\npm.CMD')
        which.assert_called_once_with('npm')

    def test_resolve_missing_raises(self):
        with patch.object(tools.shutil, 'which', return_value=None):
            with self.assertRaises(tools.ToolMissing) as error:
                tools.resolve('npm')
        self.assertEqual(str(error.exception), 'npm')
        self.assertEqual(error.exception.name, 'npm')


class MacHomebrewFallbackTests(unittest.TestCase):
    """Task 19 fix round 1: right after Homebrew installs, its folders are not on PATH yet."""

    def test_mac_finds_a_tool_in_homebrew_when_path_misses_it(self):
        def isfile(candidate):
            return candidate.replace(os.sep, '/') == '/opt/homebrew/bin/ffmpeg'
        with patch.object(tools.shutil, 'which', return_value=None), patch.object(tools.sys, 'platform', 'darwin'),              patch.object(tools.os.path, 'isfile', side_effect=isfile), patch.object(tools.os, 'access', return_value=True):
            self.assertEqual(tools.resolve('ffmpeg').replace(os.sep, '/'), '/opt/homebrew/bin/ffmpeg')

    def test_intel_mac_folder_is_the_second_choice(self):
        def isfile(candidate):
            return candidate.replace(os.sep, '/') == '/usr/local/bin/node'
        with patch.object(tools.shutil, 'which', return_value=None), patch.object(tools.sys, 'platform', 'darwin'),              patch.object(tools.os.path, 'isfile', side_effect=isfile), patch.object(tools.os, 'access', return_value=True):
            self.assertEqual(tools.resolve('node').replace(os.sep, '/'), '/usr/local/bin/node')

    def test_no_homebrew_fallback_off_mac_or_when_not_installed(self):
        with patch.object(tools.shutil, 'which', return_value=None), patch.object(tools.sys, 'platform', 'win32'),              patch.object(tools.os.path, 'isfile', return_value=True), self.assertRaises(tools.ToolMissing):
            tools.resolve('ffmpeg')
        with patch.object(tools.shutil, 'which', return_value=None), patch.object(tools.sys, 'platform', 'darwin'),              patch.object(tools.os.path, 'isfile', return_value=False), self.assertRaises(tools.ToolMissing):
            tools.resolve('ffmpeg')

    def test_which_still_wins_on_a_mac(self):
        with patch.object(tools.shutil, 'which', return_value='/custom/ffmpeg'), patch.object(tools.sys, 'platform', 'darwin'):
            self.assertEqual(tools.resolve('ffmpeg'), '/custom/ffmpeg')


class RefreshPathTests(unittest.TestCase):
    def test_appends_only_new_entries_in_order(self):
        sep = os.pathsep
        with patch.dict(os.environ, {'PATH': sep.join(['/a', '/b'])}):
            self.assertTrue(tools.refresh_path(['/b', '/c', '/c/', '/d']))
            self.assertEqual(os.environ['PATH'], sep.join(['/a', '/b', '/c', '/d']))
            self.assertFalse(tools.refresh_path(['/a', '/d']))

    def test_mac_adds_existing_homebrew_folders(self):
        with patch.object(tools.os, 'name', 'posix'), patch.object(tools.sys, 'platform', 'darwin'),              patch.object(tools.os.path, 'isdir', side_effect=lambda folder: folder == '/opt/homebrew/bin'),              patch.dict(os.environ, {'PATH': '/usr/bin'}):
            self.assertTrue(tools.refresh_path())
            self.assertEqual(os.environ['PATH'].split(os.pathsep), ['/usr/bin', '/opt/homebrew/bin'])

    def test_windows_reads_the_saved_path(self):
        with patch.object(tools.os, 'name', 'nt'), patch.object(tools, 'saved_windows_path', return_value=['/new/tool']),              patch.dict(os.environ, {'PATH': '/old'}):
            self.assertTrue(tools.refresh_path())
            self.assertIn('/new/tool', os.environ['PATH'])

    def test_other_systems_and_registry_errors_are_a_no_op(self):
        with patch.object(tools.os, 'name', 'posix'), patch.object(tools.sys, 'platform', 'linux'):
            self.assertFalse(tools.refresh_path())
        with patch.object(tools.os, 'name', 'nt'), patch.object(tools, 'saved_windows_path', side_effect=OSError('no registry')):
            self.assertFalse(tools.refresh_path())


class PythonTests(unittest.TestCase):
    def test_python_is_the_running_interpreter(self):
        self.assertEqual(tools.python(), sys.executable)


class HintTests(unittest.TestCase):
    def test_hint_windows(self):
        with patch.object(os, 'name', 'nt'):
            self.assertEqual(tools.hint('style-library/start.py'), 'python style-library/start.py')

    def test_hint_elsewhere(self):
        with patch.object(os, 'name', 'posix'):
            self.assertEqual(tools.hint('style-library/start.py'), 'python3 style-library/start.py')


if __name__ == '__main__':
    unittest.main()
