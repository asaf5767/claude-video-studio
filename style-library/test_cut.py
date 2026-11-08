"""Task 17: scripts/cut.py, the talking-head skill's spoken cut: keep chosen word ranges of
one or more takes, shrink every pause to a target by punctuation, render one frame-exact
H.264 assembly and remap the word timings onto it. Synthetic media only."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_cut', REPO_ROOT / 'scripts/cut.py')
cut = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cut)

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')


def words(*rows):
    return [{'text': t, 'startMs': s, 'endMs': e} for t, s, e in rows]


# A 6 s take: two sentences with a long pause between them and a long pause mid-sentence.
TAKE = words(('שלום', 200, 600), ('לכולם.', 650, 1100),            # 1.9 s pause after the full stop
             ('היום', 3000, 3400), ('AI', 3450, 3700), ('חוסך', 4600, 5000),  # 0.9 s mid-sentence pause
             ('38', 5050, 5300), ('שניות.', 5350, 5800))


class PlanTests(unittest.TestCase):
    def test_pauses_shrink_by_punctuation(self):
        tight = cut.intervals(TAKE, 0, len(TAKE) - 1, 'tight', duration=6.0)
        self.assertEqual(len(tight), 3)  # cut after "לכולם." and inside "AI ... חוסך"
        kept = sum(e - s for s, e in tight)
        self.assertLess(kept, 3.5)
        # 0.26 s target after a full stop, plus the speech margins on either side.
        kept_silence = (tight[0][1] - 1.1) + (3.0 - tight[1][0])
        self.assertAlmostEqual(kept_silence, 0.26, delta=0.03)
        natural = cut.intervals(TAKE, 0, len(TAKE) - 1, 'natural', duration=6.0)
        self.assertGreater(sum(e - s for s, e in natural), kept)
        keep = cut.intervals(TAKE, 0, len(TAKE) - 1, 'keep-pauses', duration=6.0)
        self.assertEqual(len(keep), 2)  # only the 1.9 s dead air is shortened

    def test_every_word_stays_inside_a_kept_interval(self):
        for style in cut.STYLES:
            spans = cut.intervals(TAKE, 0, len(TAKE) - 1, style, duration=6.0)
            for word in TAKE:
                self.assertTrue(any(s <= word['startMs'] / 1000 and word['endMs'] / 1000 <= e for s, e in spans),
                                (style, word['text']))

    def test_range_limits_the_words(self):
        spans = cut.intervals(TAKE, 2, 3, 'tight', duration=6.0)
        self.assertEqual(len(spans), 1)
        self.assertLess(abs(spans[0][0] - 2.90), 0.02)
        self.assertLess(spans[0][1], 4.0)

    def test_intervals_are_clamped_to_the_media(self):
        spans = cut.intervals(words(('א', 0, 300), ('ב', 5900, 6000)), 0, 1, 'tight', duration=6.0)
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], 6.0)

    def test_bad_requests_are_coded_errors(self):
        cases = [({'style': 'fast', 'pieces': []}, 'cut.bad-request'),
                 ({'style': 'tight', 'pieces': []}, 'cut.bad-request'),
                 ({'style': 'tight', 'pieces': [{'media': 'm.mp4', 'words': 'w.json', 'from': 5, 'to': 2}]},
                  'cut.bad-request')]
        for request, code in cases:
            with self.assertRaises(cut.CutError) as caught:
                cut.validate(request)
            self.assertEqual(caught.exception.code, code)


@unittest.skipUnless(FFMPEG, 'ffmpeg/ffprobe not installed')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        media = self.project / 'work/media'
        media.mkdir(parents=True)
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=360x640:rate=30:duration=6', '-f', 'lavfi', '-i',
                        'sine=frequency=440:sample_rate=48000:duration=6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-shortest', str(media / 'take.mp4')], check=True)
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc=size=640x360:rate=25:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        str(media / 'silent.mp4')], check=True)
        (self.project / 'work/transcripts').mkdir(parents=True)
        (self.project / 'work/transcripts/take.json').write_text(json.dumps(TAKE, ensure_ascii=False), encoding='utf-8')
        (self.project / 'work/transcripts/silent.json').write_text(
            json.dumps(words(('סוף', 300, 900))), encoding='utf-8')
        self.request = {'style': 'tight', 'fps': 30, 'width': 360, 'height': 640,
                        'pieces': [{'media': 'work/media/take.mp4', 'words': 'work/transcripts/take.json',
                                    'from': 0, 'to': 6},
                                   {'media': 'work/media/silent.mp4', 'words': 'work/transcripts/silent.json',
                                    'from': 0, 'to': 0}]}

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, path):
        out = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json',
                              str(path)], check=True, capture_output=True, text=True).stdout
        return json.loads(out)

    def test_render_writes_assembly_words_and_map(self):
        out = self.project / 'versions/v01'
        result = cut.render(self.project, self.request, out)
        info = self.probe(out / 'cut.mp4')
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        self.assertEqual((video['codec_name'], video['width'], video['height']), ('h264', 360, 640))
        self.assertEqual(video['r_frame_rate'], '30/1')
        self.assertEqual(video.get('color_transfer'), 'bt709')
        self.assertIn('audio', {s['codec_type'] for s in info['streams']})
        duration = float(info['format']['duration'])
        self.assertAlmostEqual(duration, result['duration'], delta=0.08)
        self.assertLess(duration, 6.0)
        moved = json.loads((out / 'cut.words.json').read_text(encoding='utf-8'))
        self.assertEqual([w['text'] for w in moved], [w['text'] for w in TAKE] + ['סוף'])
        starts = [w['startMs'] for w in moved]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(w['endMs'] <= result['duration'] * 1000 + 1 for w in moved))
        self.assertEqual(moved[-1]['piece'], 1)
        plan = json.loads((out / 'cut.map.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['style'], 'tight')
        self.assertGreaterEqual(len(plan['intervals']), 4)

    def test_render_refuses_to_overwrite(self):
        out = self.project / 'versions/v01'
        cut.render(self.project, self.request, out)
        before = (out / 'cut.mp4').read_bytes()
        with self.assertRaises(cut.CutError) as caught:
            cut.render(self.project, self.request, out)
        self.assertEqual(caught.exception.code, 'cut.exists')
        self.assertEqual((out / 'cut.mp4').read_bytes(), before)

    def test_retry_redoes_an_unregistered_cut_in_the_same_version(self):
        out = self.project / 'versions/v01'
        cut.render(self.project, self.request, out)
        with self.assertRaises(cut.CutError) as caught:
            cut.render(self.project, self.request, out)
        self.assertIn('--retry', caught.exception.message)  # nothing registered: redo it here
        self.assertNotIn('new_version', caught.exception.message)
        self.request['style'] = 'natural'
        result = cut.render(self.project, self.request, out, retry=True)
        plan = json.loads((out / 'cut.map.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['style'], 'natural')
        self.assertAlmostEqual(plan['duration'], result['duration'])
        self.assertEqual([p.name for p in out.iterdir() if p.name.startswith('.cut-')], [])

    def test_retry_refuses_a_registered_version(self):
        out = self.project / 'versions/v01'
        cut.render(self.project, self.request, out)
        before = (out / 'cut.mp4').read_bytes()
        registry = self.project / 'projects.json'
        registry.write_text(json.dumps({'projects': [{'id': self.project.name, 'artifacts': [
            {'id': 'cut-v01', 'type': 'video', 'path': 'versions/v01/cut.mp4'}]}]}), encoding='utf-8')
        with patch.object(cut.new_version, 'REGISTRY', registry):
            for retry in (False, True):
                with self.assertRaises(cut.CutError) as caught:
                    cut.render(self.project, self.request, out, retry=retry)
                self.assertEqual(caught.exception.code, 'cut.exists')
                self.assertIn('new_version.py', caught.exception.message)
                self.assertIn('--from v01', caught.exception.message)
        self.assertEqual((out / 'cut.mp4').read_bytes(), before)

    def test_word_index_out_of_range(self):
        self.request['pieces'][0]['to'] = 99
        with self.assertRaises(cut.CutError) as caught:
            cut.render(self.project, self.request, self.project / 'versions/v02')
        self.assertEqual(caught.exception.code, 'cut.bad-request')
        self.assertFalse((self.project / 'versions/v02/cut.mp4').exists())

    def test_cli(self):
        request = self.project / 'cut-request.json'
        request.write_text(json.dumps(self.request), encoding='utf-8')
        done = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/cut.py'), str(self.project), str(request),
                               str(self.project / 'versions/v01')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('duration', json.loads(done.stdout))
        again = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/cut.py'), str(self.project), str(request),
                                str(self.project / 'versions/v01')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(again.returncode, 2)
        self.assertIn('cut.exists', again.stderr)
        self.assertNotIn('Traceback', again.stderr)


if __name__ == '__main__':
    unittest.main()
