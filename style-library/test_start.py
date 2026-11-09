"""Task 19 fix round 1: start.py --open / --restart, run for real against a stand-in server.

start.py is copied into a temporary folder next to a tiny fake serve.py that answers
/api/health like the real one (root + pid), so these tests start and stop real processes
without touching this studio's own runtime/server.json or its running server.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

FAKE_SERVE = '''import argparse, json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT = str(Path(__file__).resolve().parent)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if Path(ROOT, 'slow').exists():
            time.sleep(1.5)  # a busy older server: slower than the old 1 s check, faster than 3 s
        body = json.dumps({'app': 'ai-video-studio', 'root': ROOT, 'pid': os.getpid()}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int); args = parser.parse_args()
ThreadingHTTPServer(('127.0.0.1', args.port), H).serve_forever()
'''

OPENED = '''import sys
open(sys.argv[2], 'w').write(sys.argv[1])
'''


def alive(url):
    try:
        return json.load(urllib.request.urlopen(url + '/api/health', timeout=.5))
    except Exception:
        return None


class StartScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # Same layout as the studio: <root>/style-library/start.py next to <root>/scripts/.
        self.base = Path(self.temp.name).resolve() / 'style-library'
        (self.base / 'dist').mkdir(parents=True)
        (self.base.parent / 'scripts').mkdir()
        shutil.copy2(HERE.parent / 'scripts/setup_messages.py', self.base.parent / 'scripts/setup_messages.py')
        shutil.copy2(HERE / 'start.py', self.base / 'start.py')
        shutil.copy2(HERE / 'atomic.py', self.base / 'atomic.py')  # the shared launch.js writer
        (self.base / 'serve.py').write_text(FAKE_SERVE, encoding='utf-8')
        (self.base / 'opened.py').write_text(OPENED, encoding='utf-8')
        self.pids = []

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        time.sleep(.3)
        self.temp.cleanup()

    def start(self, *flags, browser_log=None):
        env = {**os.environ}
        env.pop('BROWSER', None)
        if browser_log:
            # webbrowser runs $BROWSER with %s replaced; forward slashes survive its shlex split.
            env['BROWSER'] = f'{Path(sys.executable).as_posix()} {(self.base / "opened.py").as_posix()} %s {browser_log.as_posix()}'
        out = subprocess.run([sys.executable, str(self.base / 'start.py'), *flags], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout.strip().splitlines()[0])
        self.pids.append(result['pid'])
        return result

    def test_reuse_then_restart_replaces_only_our_server(self):
        first = self.start()
        info = alive(first['url'])
        self.assertEqual(info['root'], str(self.base))
        self.assertEqual(first['pid'], info['pid'], 'the server\'s own pid is recorded')
        self.assertEqual(self.start(), first, 'a second start reuses the running studio')
        second = self.start('--restart')
        self.assertNotEqual(second['pid'], first['pid'])
        self.assertEqual(alive(second['url'])['pid'], second['pid'])
        if second['url'] != first['url']:
            self.assertIsNone(alive(first['url']), 'the old server was stopped')
        self.assertEqual(json.loads((self.base / 'runtime/server.json').read_text(encoding='utf-8'))['pid'], second['pid'])

    def test_restart_refuses_a_server_it_cannot_verify(self):
        first = self.start()
        state = self.base / 'runtime/server.json'
        recorded = json.loads(state.read_text(encoding='utf-8'))
        state.write_text(json.dumps({**recorded, 'pid': recorded['pid'] + 99999}), encoding='utf-8')
        out = subprocess.run([sys.executable, str(self.base / 'start.py'), '--restart'], capture_output=True, timeout=60)
        self.assertNotEqual(out.returncode, 0)
        stderr = out.stderr.decode('utf-8')
        self.assertIn('הסטודיו כבר פתוח', stderr, 'a plain Hebrew message (the default language), no traceback')
        self.assertIn(first['url'], stderr, 'it says where the running studio is, so it can still be opened')
        self.assertNotIn('Traceback', stderr)
        self.assertEqual(alive(first['url'])['pid'], first['pid'], 'nothing was stopped')
        (self.base / 'settings.json').write_text('{"language": "en"}', encoding='utf-8')
        out = subprocess.run([sys.executable, str(self.base / 'start.py'), '--restart'], capture_output=True, timeout=60)
        self.assertIn('The studio is already open', out.stderr.decode('utf-8'))

    def test_a_slow_running_server_is_reused_not_duplicated(self):
        first = self.start()
        (self.base / 'slow').write_text('', encoding='utf-8')
        self.assertEqual(self.start(), first)

    def test_open_opens_the_browser_only_when_asked(self):
        quiet = self.base / 'quiet.txt'
        self.start(browser_log=quiet)
        time.sleep(1)
        self.assertFalse(quiet.exists())
        opened = self.base / 'opened.txt'
        result = self.start('--open', browser_log=opened)
        for _ in range(50):
            if opened.exists():
                break
            time.sleep(.1)
        self.assertEqual(opened.read_text(encoding='utf-8'), result['url'] + '/')


class ServeStartupTests(unittest.TestCase):
    def test_serve_picks_up_newly_installed_tools_and_reports_its_pid(self):
        import serve
        with patch.dict(sys.modules), patch('sys.path', list(sys.path)):
            fake = type(sys)('tools')
            fake.refresh_path = lambda: True
            sys.modules['tools'] = fake
            self.assertTrue(serve.refresh_tool_path())
        source = (HERE / 'serve.py').read_text(encoding='utf-8')
        self.assertIn("if __name__=='__main__':\n    refresh_tool_path()", source)
        self.assertIn("'pid':os.getpid()", source)

    def test_one_launch_js_template_for_start_and_serve(self):
        # Controller queue Q2: start.py and serve.py both write dist/launch.js through atomic.py.
        import atomic
        for name in ('start.py', 'serve.py'):
            source = (HERE / name).read_text(encoding='utf-8')
            self.assertIn('write_launch_js(BASE/', source, name)
            self.assertNotIn('location.replace', source, name)
        with tempfile.TemporaryDirectory() as folder:
            atomic.write_launch_js(Path(folder), 'http://127.0.0.1:4871')
            self.assertEqual((Path(folder) / 'launch.js').read_text(encoding='utf-8'),
                             'if(location.protocol === "file:"){location.replace("http://127.0.0.1:4871/" + location.search + location.hash);}\n')


if __name__ == '__main__':
    unittest.main()
