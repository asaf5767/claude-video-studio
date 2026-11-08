"""Integration fix: Handler.file() (the byte-range video/static-file write path) must
swallow BrokenPipeError/ConnectionResetError/ConnectionAbortedError quietly -- a browser
cancelling a video range request (seeking, navigating away) tears the socket down from the
client side, which is normal, not a server bug worth a traceback. ConnectionAbortedError is
WinError 10053 on Windows. These tests call Handler.file() directly against a minimal fake
handler whose wfile.write() raises, instead of a real socket, so they run the same on every
platform regardless of what errno the OS would actually raise.
"""
import tempfile
import unittest
from pathlib import Path

from serve import Handler


class _RaisingWfile:
    def __init__(self, exc):
        self._exc = exc

    def write(self, data):
        raise self._exc


class _FakeHandler:
    """Duck-types just the BaseHTTPRequestHandler surface Handler.file() touches."""

    def __init__(self, wfile):
        self.headers = {}
        self.wfile = wfile
        self.responses = []

    def send_response(self, status):
        self.responses.append(status)

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def send_error(self, status, *_args):
        self.responses.append(status)


class FileStreamAbortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'clip.mp4'
        self.path.write_bytes(b'fake video bytes' * 10)

    def tearDown(self):
        self.temp.cleanup()

    def test_broken_pipe_error_is_quiet(self):
        fake = _FakeHandler(_RaisingWfile(BrokenPipeError()))
        Handler.file(fake, self.path)  # must not raise

    def test_connection_reset_error_is_quiet(self):
        fake = _FakeHandler(_RaisingWfile(ConnectionResetError()))
        Handler.file(fake, self.path)  # must not raise

    def test_connection_aborted_error_is_quiet(self):
        # WinError 10053: the browser cancelled the video range request.
        fake = _FakeHandler(_RaisingWfile(ConnectionAbortedError()))
        Handler.file(fake, self.path)  # must not raise

    def test_unrelated_os_error_still_raises(self):
        # Only the three expected cancellation errors are swallowed; a real failure
        # should not disappear silently.
        fake = _FakeHandler(_RaisingWfile(OSError('disk full')))
        with self.assertRaises(OSError):
            Handler.file(fake, self.path)

    def test_head_request_never_touches_wfile(self):
        # A HEAD request skips the body loop entirely, so even a wfile that always
        # raises must not affect it.
        fake = _FakeHandler(_RaisingWfile(ConnectionAbortedError()))
        Handler.file(fake, self.path, head=True)  # must not raise
        self.assertEqual(fake.responses, [200])

    def test_missing_file_is_a_404_not_a_crash(self):
        fake = _FakeHandler(_RaisingWfile(ConnectionAbortedError()))
        Handler.file(fake, self.path.with_name('missing.mp4'))
        self.assertEqual(fake.responses, [404])


if __name__ == '__main__':
    unittest.main()
