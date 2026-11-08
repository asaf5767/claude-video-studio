"""T9b: server-generated poster frames for HEVC (iPhone) video that otherwise renders
BLACK in Chrome on Windows -- ffmpeg-based coverage for posters.py's ensure()/filter_for().

Needs a real ffmpeg + ffprobe on PATH (review_actions.py's duration probe already assumes
one); the whole module skips if either is missing. The HEVC-specific test additionally
needs an ffmpeg build with the libx265 encoder -- skipped with a clear reason if the
installed build lacks it, per the task brief, rather than failing CI on a minimal ffmpeg
install that only has libx264."""
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

import posters

FFMPEG = shutil.which('ffmpeg')
FFPROBE = shutil.which('ffprobe')


def _make_clip(path, codec, extra=()):
    subprocess.run([FFMPEG, '-y', '-f', 'lavfi', '-i', 'testsrc=duration=2:size=320x568:rate=10',
                     '-c:v', codec, *extra, '-t', '2', str(path)],
                   capture_output=True, check=True, timeout=30)


def _hevc_available():
    if not FFMPEG:
        return False
    try:
        out = subprocess.run([FFMPEG, '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=10)
        return 'libx265' in out.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg/ffprobe not found on PATH')
class PosterGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / '.posters'

    def tearDown(self):
        self.temp.cleanup()

    def test_generates_a_jpeg_poster_for_an_h264_clip(self):
        source = self.root / 'clip.mp4'
        _make_clip(source, 'libx264')
        poster = posters.ensure(source, self.cache, 'item-1')
        self.assertIsNotNone(poster)
        self.assertTrue(poster.is_file())
        self.assertTrue(poster.read_bytes().startswith(b'\xff\xd8'))  # JPEG magic bytes

    def test_cached_poster_is_reused_without_regenerating(self):
        source = self.root / 'clip.mp4'
        _make_clip(source, 'libx264')
        first = posters.ensure(source, self.cache, 'item-1')
        mtime = first.stat().st_mtime_ns
        time.sleep(0.05)
        second = posters.ensure(source, self.cache, 'item-1')
        self.assertEqual(second.stat().st_mtime_ns, mtime)

    def test_poster_regenerates_when_source_changes(self):
        source = self.root / 'clip.mp4'
        _make_clip(source, 'libx264')
        posters.ensure(source, self.cache, 'item-1')
        time.sleep(0.05)
        source.unlink()
        _make_clip(source, 'libx264')  # re-encoded: new mtime/size
        second = posters.ensure(source, self.cache, 'item-1')
        self.assertIsNotNone(second)
        meta = posters._meta_path(second)
        self.assertEqual(meta.read_text(encoding='utf-8'), posters._stamp(source))

    def test_missing_source_file_returns_none_without_raising(self):
        poster = posters.ensure(self.root / 'nope.mp4', self.cache, 'missing')
        self.assertIsNone(poster)

    def test_concurrent_requests_for_the_same_poster_run_ffmpeg_once(self):
        source = self.root / 'clip.mp4'
        _make_clip(source, 'libx264')
        calls = []
        real_generate = posters._generate

        def counting_generate(src, dest):
            calls.append(1)
            return real_generate(src, dest)

        results = []
        with unittest.mock.patch.object(posters, '_generate', side_effect=counting_generate):
            def worker():
                results.append(posters.ensure(source, self.cache, 'item-shared'))
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(r is not None for r in results))

    @unittest.skipUnless(_hevc_available(), 'This ffmpeg build has no libx265 encoder')
    def test_generates_a_poster_for_an_hevc_clip(self):
        source = self.root / 'clip-hevc.mp4'
        _make_clip(source, 'libx265', extra=['-tag:v', 'hvc1'])
        poster = posters.ensure(source, self.cache, 'item-hevc')
        self.assertIsNotNone(poster)
        self.assertTrue(poster.is_file())
        self.assertTrue(poster.read_bytes().startswith(b'\xff\xd8'))


class PosterTimeoutTests(unittest.TestCase):
    """Integration fix: POSTER_TIMEOUT is a per-subprocess budget (ffprobe x2, ffmpeg x1), not
    one combined total -- so a stuck/hanging tool on any one of those three calls must still
    make ensure() return None (the caller's 404 placeholder), never raise into a 500. No real
    ffmpeg/ffprobe needed: tools.resolve() and subprocess.run() are mocked."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / '.posters'
        self.source = self.root / 'clip.mp4'
        self.source.write_bytes(b'not a real video, never read by a mocked ffmpeg/ffprobe')

    def tearDown(self):
        self.temp.cleanup()

    def test_a_timed_out_subprocess_yields_none_not_a_crash(self):
        with unittest.mock.patch.object(posters.tools, 'resolve', side_effect=lambda name: name), \
             unittest.mock.patch.object(posters.subprocess, 'run',
                                         side_effect=subprocess.TimeoutExpired(cmd='ffmpeg', timeout=posters.POSTER_TIMEOUT)):
            poster = posters.ensure(self.source, self.cache, 'item-timeout')
        self.assertIsNone(poster)

    def test_a_timeout_only_on_the_frame_extract_still_yields_none(self):
        # Both ffprobe calls succeed (and already swallow their own timeout into a default,
        # per _probe_duration/_probe_color_transfer); only the final ffmpeg extract times out.
        def run(args, **kwargs):
            if args[0] == 'ffmpeg':
                raise subprocess.TimeoutExpired(cmd='ffmpeg', timeout=posters.POSTER_TIMEOUT)
            result = unittest.mock.Mock()
            result.stdout = '{}'
            return result

        with unittest.mock.patch.object(posters.tools, 'resolve', side_effect=lambda name: name), \
             unittest.mock.patch.object(posters.subprocess, 'run', side_effect=run):
            poster = posters.ensure(self.source, self.cache, 'item-timeout-2')
        self.assertIsNone(poster)


class FilterSelectionTests(unittest.TestCase):
    def test_plain_scale_for_sdr_transfer(self):
        self.assertEqual(posters.filter_for(''), 'scale=540:-2')
        self.assertEqual(posters.filter_for('bt709'), 'scale=540:-2')

    def test_tonemap_for_hlg(self):
        vf = posters.filter_for('arib-std-b67')
        self.assertTrue(vf.startswith('scale=540:-2,zscale=t=linear'))
        self.assertIn('tonemap=tonemap=hable', vf)

    def test_tonemap_for_pq_hdr10(self):
        vf = posters.filter_for('smpte2084')
        self.assertIn('tonemap=hable', vf)


if __name__ == '__main__':
    unittest.main()
