"""Task 16b: local background removal (presenter matte). Never needs the real model:
a fake backend turns each frame's brightness into a mask through ffmpeg."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_matte', REPO_ROOT / 'scripts/matte.py')
matte = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matte)

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')


class FakeBackend:
    """Writes one grayscale PNG mask per frame of the normalized source (minus `short`)."""
    model = 'fake-model'

    def __init__(self, name='fake', ok=True, short=0):
        self.name, self.ok, self.short, self.calls = name, ok, short, 0

    def available(self):
        return self.ok

    def masks(self, source, masks_dir, frames, report):
        self.calls += 1
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-i', str(source),
                        '-vf', 'format=gray', str(masks_dir / '%06d.png')], check=True)
        for done in (0.25, 0.5, 0.75, 1.0):  # incremental progress, like a streaming backend
            report(done)
        for extra in sorted(masks_dir.glob('*.png'))[::-1][:self.short]:
            extra.unlink()


def probe(path):
    out = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                          '-show_entries', 'stream=width,height,r_frame_rate,nb_read_frames,pix_fmt',
                          '-of', 'json', str(path)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)['streams'][0]


class BackendChoiceTests(unittest.TestCase):
    def test_backend_auto_picks_first_available(self):
        backends = {'first': FakeBackend('first', ok=False), 'second': FakeBackend('second'),
                    'third': FakeBackend('third')}
        with patch.dict(matte.BACKENDS, backends, clear=True):
            self.assertEqual(matte.available_backends(), ['second', 'third'])
            self.assertEqual(matte.pick_backend('auto').name, 'second')
            self.assertEqual(matte.pick_backend('third').name, 'third')

    def test_no_backend_raises_coded_error(self):
        with patch.dict(matte.BACKENDS, {'only': FakeBackend('only', ok=False)}, clear=True):
            for name in ['auto', 'only', 'no-such-backend']:
                with self.assertRaises(matte.MatteError) as caught:
                    matte.pick_backend(name)
                self.assertEqual(caught.exception.code, 'matte.no-backend')

    def test_hyperframes_backend_needs_the_checked_model(self):
        with tempfile.TemporaryDirectory() as cache, patch.dict(os.environ, {'HYPERFRAMES_CACHE_DIR': cache}):
            backend = matte.HyperframesBackend()
            with self.assertRaises(matte.MatteError) as caught:
                backend.check_model()
            self.assertEqual(caught.exception.code, 'matte.model-missing')
            model = Path(cache) / 'background-removal' / 'models' / 'u2net_human_seg.onnx'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'not the real weights')
            with self.assertRaises(matte.MatteError) as caught:
                backend.check_model()
            self.assertEqual(caught.exception.code, 'matte.model-missing')

    def test_config_names_the_backend_and_model(self):
        config = json.loads((REPO_ROOT / 'studio.config.json').read_text(encoding='utf-8'))
        self.assertEqual(config['matting']['backend'], 'hyperframes')
        self.assertEqual(config['matting']['model'], 'u2net_human_seg')
        self.assertIn('hyperframes', matte.BACKENDS)


class NativeFpsTests(unittest.TestCase):
    def test_keeps_the_inputs_own_rate(self):
        F = matte.Fraction
        self.assertEqual(matte.native_fps({'r_frame_rate': '24/1', 'avg_frame_rate': '24/1'}), (F(24), False))
        self.assertEqual(matte.native_fps({'r_frame_rate': '30000/1001', 'avg_frame_rate': '30000/1001'}),
                         (F(30000, 1001), False))
        # A phone take that drops frames: base rate 30, average a little lower.
        self.assertEqual(matte.native_fps({'r_frame_rate': '30/1', 'avg_frame_rate': '2862000/95389'}),
                         (F(30), True))
        # A timebase-like base rate falls back to the average, snapped to a common rate.
        self.assertEqual(matte.native_fps({'r_frame_rate': '90000/1', 'avg_frame_rate': '2397/100'}),
                         (F(24000, 1001), True))


class HyperframesGuardTests(unittest.TestCase):
    """Reverse-engineered cache/runtime paths are trusted only for verified HyperFrames versions."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'studio'
        self.cache = Path(self.temp.name) / 'cache'
        (self.root / 'node_modules' / 'hyperframes' / 'bin').mkdir(parents=True)
        (self.root / 'node_modules' / 'hyperframes' / 'bin' / 'hyperframes.mjs').write_text('', encoding='utf-8')
        self.patches = [patch.object(matte, 'ROOT', self.root),
                        patch.object(matte.shutil, 'which', return_value='node'),
                        patch.dict(os.environ, {'HYPERFRAMES_CACHE_DIR': str(self.cache)})]
        for item in self.patches:
            item.start()
        self.backend = matte.HyperframesBackend()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def version(self, value):
        (self.root / 'node_modules' / 'hyperframes' / 'package.json').write_text(
            json.dumps({'name': 'hyperframes', 'version': value}), encoding='utf-8')

    def cli_calls(self):
        seen = []
        self.backend.remove_background = lambda source, cutout, env, frames, report: seen.append(env)
        return seen

    def test_verified_version_needs_the_installed_runtime_and_model(self):
        self.version('0.9.16')
        self.assertFalse(self.backend.available())
        runtime = self.cache / 'optional' / 'onnxruntime-node@1.21.1' / 'node_modules' / 'onnxruntime-node'
        runtime.mkdir(parents=True)
        (runtime / 'package.json').write_text(json.dumps({'version': '1.21.1'}), encoding='utf-8')
        self.assertTrue(self.backend.available())
        self.assertEqual(self.backend.model, 'u2net_human_seg')
        seen = self.cli_calls()
        with self.assertRaises(matte.MatteError) as caught:
            self.backend.masks(Path('in.mp4'), self.cache / 'masks', 10, lambda done: None)
        self.assertEqual(caught.exception.code, 'matte.model-missing')
        self.assertEqual(seen, [], 'the CLI must not run without the checked model')

    def test_unverified_version_just_runs_the_documented_cli(self):
        self.version('0.10.0')
        self.assertTrue(self.backend.available(), 'an unknown version must not hide the backend')
        self.assertEqual(self.backend.model, 'hyperframes 0.10.0 default')
        seen = self.cli_calls()
        with patch.object(matte, 'run'):
            self.backend.masks(Path('in.mp4'), self.cache / 'masks', 10, lambda done: None)
        self.assertEqual(len(seen), 1)
        self.assertNotIn('HYPERFRAMES_NO_OPTIONAL_INSTALL', seen[0])

    def test_missing_cli_is_not_available(self):
        self.version('0.9.16')
        (self.root / 'node_modules' / 'hyperframes' / 'bin' / 'hyperframes.mjs').unlink()
        self.assertFalse(self.backend.available())


@unittest.skipUnless(FFMPEG, 'needs ffmpeg/ffprobe')
class OutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.clip = Path(cls.temp.name) / 'clip.mp4'
        # 1 s, 320x568 at 30 fps (an odd-free portrait size like a scaled 1080x1920 take).
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', str(cls.clip)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(dir=self.temp.name))
        self.fake = FakeBackend()
        self.patch = patch.dict(matte.BACKENDS, {'fake': self.fake}, clear=True)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_output_contract(self):
        result = matte.matte(self.clip, self.out)
        self.assertEqual(result, {'alpha': str(self.out / 'alpha.mp4'), 'fg': str(self.out / 'fg.webm'),
                                  'frames': 30, 'backend': 'fake', 'fps': '30/1', 'reused': False})
        alpha = probe(self.out / 'alpha.mp4')
        self.assertEqual((alpha['width'], alpha['height'], alpha['r_frame_rate'], alpha['nb_read_frames']),
                         (320, 568, '30/1', '30'))
        fg = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-c:v', 'libvpx-vp9', '-select_streams', 'v:0',
                             '-count_frames', '-show_entries', 'stream=width,height,nb_read_frames,pix_fmt',
                             '-of', 'json', str(self.out / 'fg.webm')], check=True, capture_output=True, text=True)
        fg = json.loads(fg.stdout)['streams'][0]
        self.assertEqual((fg['width'], fg['height'], fg['nb_read_frames']), (320, 568, '30'))
        self.assertEqual(fg['pix_fmt'], 'yuva420p')
        self.assertFalse(any(p.name.startswith('.matte-') for p in self.out.iterdir()), 'work folder left behind')

    def test_hlg_input_gives_sdr_bt709_outputs(self):
        hlg = Path(self.temp.name) / 'hlg.mov'
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc2=size=320x568:rate=30:duration=1', '-c:v', 'libx265', '-x265-params',
                        'log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc',
                        '-pix_fmt', 'yuv420p10le', str(hlg)], check=True)
        matte.matte(hlg, self.out)
        for name in ('alpha.mp4', 'fg.webm'):
            out = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                  'stream=color_transfer,color_primaries', '-of', 'json', str(self.out / name)],
                                 check=True, capture_output=True, text=True).stdout
            tags = json.loads(out)['streams'][0]
            self.assertEqual((tags.get('color_transfer'), tags.get('color_primaries')), ('bt709', 'bt709'), name)

    def test_matte_json_records_input_hash(self):
        matte.matte(self.clip, self.out)
        record = json.loads((self.out / 'matte.json').read_text(encoding='utf-8'))
        self.assertEqual(record['input_sha256'], hashlib.sha256(self.clip.read_bytes()).hexdigest())
        self.assertEqual((record['backend'], record['model'], record['fps'], record['frames']),
                         ('fake', 'fake-model', '30/1', 30))
        self.assertEqual((record['vfr_input'], record['retime_filter']), (False, 'fps=30/1'))
        self.assertTrue(matte.is_current(self.clip, self.out))
        other = Path(self.temp.name) / 'other.mp4'
        other.write_bytes(self.clip.read_bytes() + b'\0')
        self.assertFalse(matte.is_current(other, self.out))

    def test_refuses_overwrite_without_force(self):
        matte.matte(self.clip, self.out)
        before = (self.out / 'alpha.mp4').stat().st_mtime_ns
        with self.assertRaises(matte.MatteError) as caught:
            matte.matte(self.clip, self.out)
        self.assertEqual(caught.exception.code, 'matte.exists')
        self.assertEqual(self.fake.calls, 1, 'the backend must not rerun')
        self.assertEqual((self.out / 'alpha.mp4').stat().st_mtime_ns, before)
        matte.matte(self.clip, self.out, force=True)
        self.assertEqual(self.fake.calls, 2)

    def test_reuse_from_copies_a_matte_of_the_same_input(self):
        previous = self.out / 'v01-matte'
        matte.matte(self.clip, previous)
        self.assertEqual(self.fake.calls, 1)
        # The next round re-runs the same cut request: an identical file in another folder.
        again = Path(self.temp.name) / 'again.mp4'
        again.write_bytes(self.clip.read_bytes())
        target = self.out / 'v02-matte'
        seen = []
        result = matte.matte(again, target, reuse_from=previous, on_progress=lambda s, p: seen.append(s))
        self.assertEqual(self.fake.calls, 1, 'no backend call when the matte is reused')
        for name in ('alpha.mp4', 'fg.webm'):
            self.assertEqual((target / name).read_bytes(), (previous / name).read_bytes())
        record = json.loads((target / 'matte.json').read_text(encoding='utf-8'))
        self.assertEqual(record['input'], str(again.resolve()))
        self.assertEqual(record['reused_from'], str(previous.resolve()))
        self.assertTrue(matte.is_current(again, target))
        self.assertEqual((result['frames'], result['backend'], result['fps'], result['reused']), (30, 'fake', '30/1', True))
        self.assertEqual(seen, ['done'])
        # No overwrite without --force, reuse or not.
        with self.assertRaises(matte.MatteError) as caught:
            matte.matte(again, target, reuse_from=previous)
        self.assertEqual(caught.exception.code, 'matte.exists')

    def test_reuse_from_recomputes_for_another_input_backend_or_a_missing_dir(self):
        previous = self.out / 'v01-matte'
        matte.matte(self.clip, previous)
        other = Path(self.temp.name) / 'other-cut.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc=size=320x568:rate=30:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        str(other)], check=True)
        result = matte.matte(other, self.out / 'a', reuse_from=previous)  # different hash
        self.assertEqual((self.fake.calls, result['reused']), (2, False))
        result = matte.matte(self.clip, self.out / 'b', reuse_from=self.out / 'no-such-dir')  # missing dir
        self.assertEqual((self.fake.calls, result['reused']), (3, False))
        record = json.loads((previous / 'matte.json').read_text(encoding='utf-8'))
        (previous / 'matte.json').write_text(json.dumps(dict(record, model='older-model')), encoding='utf-8')
        result = matte.matte(self.clip, self.out / 'c', reuse_from=previous)  # same input, other model
        self.assertEqual((self.fake.calls, result['reused']), (4, False))
        (previous / 'matte.json').write_text(json.dumps(record), encoding='utf-8')
        (previous / 'fg.webm').unlink()
        result = matte.matte(self.clip, self.out / 'd', reuse_from=previous)  # incomplete set
        self.assertEqual((self.fake.calls, result['reused']), (5, False))

    def test_cli_reuse_from(self):
        previous = self.out / 'v01-matte'
        matte.matte(self.clip, previous)
        target = self.out / 'v02-matte'
        with patch.object(matte.sys, 'stdout') as stdout:
            self.assertEqual(matte.main([str(self.clip), str(target), '--reuse-from', str(previous)]), 0)
        self.assertTrue(json.loads(''.join(c.args[0] for c in stdout.write.call_args_list))['reused'])
        self.assertEqual(self.fake.calls, 1)
        record = json.loads((target / 'progress.json').read_text(encoding='utf-8'))
        self.assertEqual(record, [{'key': 'matte', 'state': 'done', 'detail': 'הרקע הוסר'}])

    def test_frame_count_mismatch_fails_cleanly(self):
        with patch.dict(matte.BACKENDS, {'fake': FakeBackend(short=3)}, clear=True):
            with self.assertRaises(matte.MatteError) as caught:
                matte.matte(self.clip, self.out)
        self.assertEqual(caught.exception.code, 'matte.failed')
        self.assertEqual(list(self.out.iterdir()), [], 'no partial outputs')

    def test_cli_prints_result_and_exit_code(self):
        with patch.object(matte.sys, 'stdout') as stdout:
            self.assertEqual(matte.main([str(self.clip), str(self.out), '--backend', 'fake']), 0)
        printed = ''.join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(json.loads(printed)['frames'], 30)
        with patch.object(matte.sys, 'stderr') as stderr:
            self.assertEqual(matte.main([str(self.clip), str(self.out)]), 2)
        self.assertIn('matte.exists', ''.join(call.args[0] for call in stderr.write.call_args_list))
        record = json.loads((self.out / 'progress.json').read_text(encoding='utf-8'))
        self.assertEqual(record, [{'key': 'matte', 'state': 'done', 'detail': 'הרקע הוסר'}])

    def make_clip(self, name, vf=None, rate=30):
        path = Path(self.temp.name) / name
        command = [shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                   '-i', f'testsrc2=size=320x568:rate={rate}:duration=1']
        if vf:
            command += ['-vf', vf, '-fps_mode', 'passthrough']
        subprocess.run(command + ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
        return path

    def test_keeps_native_24fps(self):
        result = matte.matte(self.make_clip('clip24.mp4', rate=24), self.out)
        self.assertEqual((result['frames'], result['fps']), (24, '24/1'))
        alpha = probe(self.out / 'alpha.mp4')
        self.assertEqual((alpha['r_frame_rate'], alpha['nb_read_frames']), ('24/1', '24'))
        record = json.loads((self.out / 'matte.json').read_text(encoding='utf-8'))
        self.assertEqual((record['fps'], record['frames'], record['vfr_input']), ('24/1', 24, False))

    def test_vfr_input_is_retimed_to_one_constant_rate(self):
        # Every 4th frame dropped: base rate 30, average 22 (like a phone take dropping frames).
        clip = self.make_clip('vfr.mp4', vf=r"select='not(eq(mod(n\,4)\,1))'")
        result = matte.matte(clip, self.out)
        record = json.loads((self.out / 'matte.json').read_text(encoding='utf-8'))
        self.assertEqual((record['fps'], record['vfr_input'], record['retime_filter']), ('30/1', True, 'fps=30/1'))
        alpha = probe(self.out / 'alpha.mp4')
        fg = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-c:v', 'libvpx-vp9', '-select_streams', 'v:0',
                             '-count_frames', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0',
                             str(self.out / 'fg.webm')], check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(alpha['r_frame_rate'], '30/1')
        self.assertEqual(int(alpha['nb_read_frames']), result['frames'])
        self.assertEqual(int(fg), result['frames'])
        self.assertEqual(record['frames'], result['frames'])
        self.assertGreaterEqual(result['frames'], 28)  # re-timed to ~1 s at 30 fps, not 22 frames

    def test_explicit_fps_overrides_the_native_rate(self):
        result = matte.matte(self.clip, self.out, fps='15')
        self.assertEqual((result['frames'], result['fps']), (15, '15/1'))
        self.assertEqual(probe(self.out / 'alpha.mp4')['r_frame_rate'], '15/1')

    def test_progress_runs_decode_matte_encode_done(self):
        events = []
        matte.matte(self.clip, self.out, on_progress=lambda stage, pct: events.append((stage, pct)))
        stages = [stage for stage, _ in events]
        self.assertEqual(sorted(set(stages), key=stages.index), ['decode', 'matte', 'encode', 'done'])
        percents = [pct for _, pct in events]
        self.assertEqual(percents, sorted(percents), 'progress never goes backwards')
        matting = {pct for stage, pct in events if stage == 'matte' and 5 < pct < 88}
        self.assertGreaterEqual(len(matting), 3, 'backend progress shows up while matting')
        self.assertEqual(events[-1], ('done', 100))

    def test_cli_progress_goes_into_the_skills_task14_step(self):
        progress = self.out / 'project-progress.json'
        progress.write_text(json.dumps([{'key': 'script', 'state': 'done'}, {'key': 'cutout', 'state': 'todo'}]),
                            encoding='utf-8')
        seen = []
        real = matte.ProgressFile.update

        def spy(self_, stage, pct):
            real(self_, stage, pct)
            seen.append(json.loads(progress.read_text(encoding='utf-8')))
        with patch.object(matte.ProgressFile, 'update', spy), patch.object(matte.sys, 'stdout'):
            self.assertEqual(matte.main([str(self.clip), str(self.out / 'm'), '--progress', str(progress),
                                         '--step', 'cutout']), 0)
        running = [steps[1] for steps in seen if steps[1]['state'] == 'running']
        self.assertTrue(any(step['detail'].startswith('מסירים רקע · ') and step['detail'].endswith('%')
                            for step in running))
        self.assertEqual(seen[-1], [{'key': 'script', 'state': 'done'},
                                    {'key': 'cutout', 'state': 'done', 'detail': 'הרקע הוסר'}])

    def test_progress_file_tolerates_junk(self):
        (self.out / 'progress.json').write_text('not json', encoding='utf-8')
        matte.ProgressFile(self.out / 'progress.json', lang='en').update('matte', 42)
        self.assertEqual(json.loads((self.out / 'progress.json').read_text(encoding='utf-8')),
                         [{'key': 'matte', 'state': 'running', 'detail': 'Removing the background · 42%'}])


if __name__ == '__main__':
    unittest.main()
