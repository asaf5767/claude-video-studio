"""Task 17: scripts/prepare_media.py turns a project's uploaded materials into files every
later step (and Chrome on Windows) can use: H.264 SDR mp4 at a constant frame rate, wav
audio, jpg/png stills -- under work/media/, never touching the originals. Synthetic media
only (ffmpeg test patterns and tones)."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_prepare_media', REPO_ROOT / 'scripts/prepare_media.py')
prepare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepare)

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')


def ffmpeg(*args):
    subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-y', *map(str, args)], check=True)


def stream(path, kind='v'):
    out = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-select_streams', f'{kind}:0', '-show_entries',
                          'stream=codec_name,pix_fmt,color_transfer,color_primaries,width,height,r_frame_rate,'
                          'avg_frame_rate,sample_rate', '-of', 'json', str(path)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)['streams'][0]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(FFMPEG, 'ffmpeg/ffprobe not installed')
class PrepareMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / 'projects' / 'demo'
        for sub in ('raw', 'broll', 'images', 'audio'):
            (self.project / 'materials' / sub).mkdir(parents=True)
        self.items = []

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, relative, tag, item_id):
        self.items.append({'id': item_id, 'file': relative, 'tag': tag, 'note': '', 'owned': False})
        (self.project / 'materials.json').write_text(json.dumps({'items': self.items}), encoding='utf-8')
        return self.project / relative

    def manifest(self):
        return json.loads((self.project / 'work/media/media.json').read_text(encoding='utf-8'))

    def test_hevc_mov_with_hebrew_name_becomes_h264_mp4_and_original_is_untouched(self):
        src = self.add('materials/raw/צילום 1.mov', 'raw', 'aaa111')
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=360x640:rate=30:duration=1', '-f', 'lavfi',
               '-i', 'sine=frequency=300:sample_rate=48000:duration=1', '-c:v', 'libx265', '-x265-params',
               'log-level=error', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', src)
        before = sha(src)
        result = prepare.prepare(self.project)
        item = result['items'][0]
        out = self.project / item['output']
        self.assertTrue(item['output'].startswith('work/media/aaa111-'))
        self.assertTrue(item['output'].endswith('.mp4'))
        self.assertTrue(item['output'].isascii())
        self.assertEqual(item['source_codec'], 'hevc')
        self.assertTrue(item['transcoded'])
        self.assertEqual(stream(out)['codec_name'], 'h264')
        self.assertEqual(stream(out)['pix_fmt'], 'yuv420p')
        self.assertEqual(stream(out, 'a')['codec_name'], 'aac')
        self.assertEqual(sha(src), before)
        self.assertEqual(self.manifest()['items'][0]['source'], 'materials/raw/צילום 1.mov')

    def test_hlg_hdr_is_tone_mapped_to_sdr_bt709(self):
        src = self.add('materials/raw/hdr.mov', 'raw', 'bbb222')
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx265',
               '-x265-params', 'log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc',
               '-pix_fmt', 'yuv420p10le', src)
        item = prepare.prepare(self.project)['items'][0]
        self.assertTrue(item['hdr'])
        info = stream(self.project / item['output'])
        self.assertEqual(info['color_transfer'], 'bt709')
        self.assertEqual(info['color_primaries'], 'bt709')
        self.assertEqual(info['pix_fmt'], 'yuv420p')
        self.assertEqual((info['width'] % 2, info['height'] % 2), (0, 0))
        self.assertFalse(item['has_audio'])

    def test_large_vertical_video_is_scaled_to_the_long_edge_and_vfr_becomes_cfr(self):
        src = self.add('materials/raw/big.mp4', 'raw', 'ccc333')
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=30:duration=1', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', src)
        item = prepare.prepare(self.project, max_edge=640)['items'][0]
        info = stream(self.project / item['output'])
        self.assertEqual((info['width'], info['height']), (360, 640))
        self.assertEqual(info['r_frame_rate'], info['avg_frame_rate'])
        self.assertEqual(item['fps'], '30/1')

    def test_second_run_reuses_unchanged_outputs(self):
        src = self.add('materials/raw/take.mp4', 'raw', 'ddd444')
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', src)
        first = prepare.prepare(self.project)['items'][0]
        out = self.project / first['output']
        stamp = out.stat().st_mtime_ns
        second = prepare.prepare(self.project)['items'][0]
        self.assertEqual(first['output'], second['output'])
        self.assertEqual(out.stat().st_mtime_ns, stamp)
        self.assertTrue(second['reused'])
        # A changed upload gets a new output name (and, later, a new transcript).
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=25:duration=1', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', src)
        third = prepare.prepare(self.project)['items'][0]
        self.assertNotEqual(third['output'], first['output'])
        self.assertTrue(out.exists())  # the earlier output is kept, never overwritten

    def test_audio_and_images(self):
        voice = self.add('materials/audio/קול.m4a', 'music', 'eee555')
        ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=44100:duration=1', '-c:a', 'aac', voice)
        logo = self.add('materials/images/logo.png', 'logo', 'fff666')
        ffmpeg('-f', 'lavfi', '-i', 'color=c=red:size=64x64', '-frames:v', '1', logo)
        photo = self.add('materials/images/photo.webp', 'image', 'abc777')
        ffmpeg('-f', 'lavfi', '-i', 'color=c=blue:size=64x64', '-frames:v', '1', photo)
        items = {i['id']: i for i in prepare.prepare(self.project)['items']}
        self.assertEqual(items['eee555']['kind'], 'audio')
        self.assertTrue(items['eee555']['output'].endswith('.wav'))
        self.assertEqual(stream(self.project / items['eee555']['output'], 'a')['sample_rate'], '48000')
        self.assertTrue(items['fff666']['output'].endswith('.png'))  # keeps transparency
        self.assertTrue(items['abc777']['output'].endswith('.jpg'))

    def test_files_dropped_without_a_manifest_entry_are_included(self):
        loose = self.project / 'materials/broll/loose clip.mp4'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', loose)
        item = prepare.prepare(self.project)['items'][0]
        self.assertEqual(item['source'], 'materials/broll/loose clip.mp4')
        self.assertEqual(item['tag'], 'broll')
        self.assertTrue(item['output'].isascii())

    def test_broken_file_is_reported_not_fatal(self):
        self.add('materials/raw/broken.mp4', 'raw', 'bad000').write_bytes(b'not a video')
        good = self.add('materials/raw/good.mp4', 'raw', 'good00')
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', good)
        result = prepare.prepare(self.project)
        self.assertEqual([i['id'] for i in result['items']], ['good00'])
        self.assertEqual([p['source'] for p in result['problems']], ['materials/raw/broken.mp4'])

    def test_cli_prints_json_summary(self):
        src = self.add('materials/raw/a.mp4', 'raw', 'cli000')
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', src)
        out = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/prepare_media.py'), str(self.project)],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)['items'][0]['id'], 'cli000')


if __name__ == '__main__':
    unittest.main()
