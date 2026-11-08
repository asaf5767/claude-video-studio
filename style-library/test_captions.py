"""Task 17: scripts/captions.py turns word timings into caption cues the skills paste into a
HyperFrames composition: one line of at most 28 characters, right-to-left, with every Latin
or number run isolated in <bdi dir="ltr"> so mixed Hebrew/English/numbers never reorder
(Review Focus 5: "AI חוסך 38 שניות")."""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_captions', REPO_ROOT / 'scripts/captions.py')
captions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(captions)


def words(text, start=0, step=300, gap=50):
    out, t = [], start
    for token in text.split():
        out.append({'text': token, 'startMs': t, 'endMs': t + step})
        t += step + gap
    return out


class BidiTests(unittest.TestCase):
    def test_review_focus_line(self):
        html = captions.line_html(['AI', 'חוסך', '38', 'שניות'], 'he')
        self.assertEqual(html, '<bdi dir="ltr">AI</bdi> חוסך <bdi dir="ltr">38</bdi> שניות')

    def test_consecutive_latin_words_share_one_isolate(self):
        html = captions.line_html(['עם', 'Claude', 'Code', 'היום'], 'he')
        self.assertEqual(html, 'עם <bdi dir="ltr">Claude Code</bdi> היום')

    def test_hebrew_prefix_stays_outside_the_isolate(self):
        self.assertEqual(captions.line_html(['ה-AI', 'שלי'], 'he'), 'ה-<bdi dir="ltr">AI</bdi> שלי')
        self.assertEqual(captions.line_html(['ב־2024'], 'he'), 'ב־<bdi dir="ltr">2024</bdi>')

    def test_numbers_with_symbols_and_decimals(self):
        self.assertEqual(captions.line_html(['חוסך', '100%', 'ב-3.5', 'דקות'], 'he'),
                         'חוסך <bdi dir="ltr">100%</bdi> ב-<bdi dir="ltr">3.5</bdi> דקות')

    def test_html_is_escaped(self):
        self.assertEqual(captions.line_html(['<b>', 'ו&'], 'he'), '<bdi dir="ltr">&lt;b&gt;</bdi> ו&amp;')

    def test_english_video_isolates_hebrew_runs(self):
        self.assertEqual(captions.line_html(['say', 'שלום', 'לכולם', 'now'], 'en'),
                         'say <bdi dir="rtl">שלום לכולם</bdi> now')

    def test_display_strips_edge_punctuation_but_keeps_inner(self):
        self.assertEqual(captions.display('שניות.'), 'שניות')
        self.assertEqual(captions.display('לכולם,'), 'לכולם')
        self.assertEqual(captions.display('SKILL.md.'), 'SKILL.md')
        self.assertEqual(captions.display('באמת?'), 'באמת?')
        self.assertEqual(captions.display('"שלום"'), 'שלום')


class CueTests(unittest.TestCase):
    LONG = ('היום אני רוצה להראות לכם איך AI חוסך 38 שניות בכל פעם שאתם כותבים מייל ללקוח '
            'וזה עובד גם עם Claude Code וגם עם כלים אחרים שאתם כבר מכירים מהעבודה')

    def test_lines_never_exceed_the_limit(self):
        result = captions.build(words(self.LONG), lang='he', mode='line', max_chars=28)
        self.assertGreater(len(result['cues']), 3)
        for cue in result['cues']:
            self.assertEqual(len(cue['lines']), 1)
            self.assertLessEqual(len(cue['lines'][0]), 28, cue['lines'][0])
        joined = ' '.join(cue['text'] for cue in result['cues'])
        self.assertEqual(joined, self.LONG)
        self.assertEqual(result['dir'], 'rtl')

    def test_two_line_mode(self):
        result = captions.build(words(self.LONG), lang='he', mode='line', max_chars=28, lines=2)
        self.assertTrue(any(len(c['lines']) == 2 for c in result['cues']))
        self.assertTrue(all(len(line) <= 28 for c in result['cues'] for line in c['lines']))
        self.assertTrue(all(c['html'].count('<br>') == len(c['lines']) - 1 for c in result['cues']))

    def test_sentence_end_and_long_pause_start_a_new_cue(self):
        ws = words('שלום לכולם. מה נשמע')
        self.assertEqual([c['text'] for c in captions.build(ws, 'he')['cues']], ['שלום לכולם', 'מה נשמע'])
        ws = words('אחת שתיים') + [{'text': 'שלוש', 'startMs': 3000, 'endMs': 3300}]
        self.assertEqual([c['text'] for c in captions.build(ws, 'he')['cues']], ['אחת שתיים', 'שלוש'])

    def test_timing_is_monotonic_and_covers_the_words(self):
        cues = captions.build(words(self.LONG), 'he')['cues']
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['end'], b['start'] + 1e-9)
        for cue in cues:
            self.assertLess(cue['start'], cue['end'])
            self.assertLessEqual(cue['start'], cue['words'][0]['start'])
            self.assertGreaterEqual(cue['end'], cue['words'][-1]['end'] - 1e-9)

    def test_word_mode_pairs_quick_short_words(self):
        ws = [{'text': 'גם', 'startMs': 0, 'endMs': 100}, {'text': 'את', 'startMs': 120, 'endMs': 200},
              {'text': 'התשובה', 'startMs': 600, 'endMs': 1000}, {'text': 'הזאת', 'startMs': 1500, 'endMs': 1800}]
        cues = captions.build(ws, 'he', mode='word')['cues']
        self.assertEqual([c['text'] for c in cues], ['גם את', 'התשובה', 'הזאת'])
        self.assertAlmostEqual(cues[1]['end'], 1.47, places=2)  # held until just before the next word

    def test_no_cue_outlasts_the_edit(self):
        cue = captions.build([{'text': 'סוף', 'startMs': 1000, 'endMs': 1900}], 'he', duration=2.0)['cues'][-1]
        self.assertEqual(cue['end'], 2.0)

    def test_a_single_overlong_word_is_flagged_not_split(self):
        cue = captions.build([{'text': 'א' * 40, 'startMs': 0, 'endMs': 500}], 'he')['cues'][0]
        self.assertTrue(cue['too_long'])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'w.json', Path(tmp) / 'c.json'
            src.write_text(json.dumps(words('AI חוסך 38 שניות'), ensure_ascii=False), encoding='utf-8')
            done = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/captions.py'), str(src), str(out),
                                   '--lang', 'he'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stderr)
            cue = json.loads(out.read_text(encoding='utf-8'))['cues'][0]
            self.assertEqual(cue['html'], '<bdi dir="ltr">AI</bdi> חוסך <bdi dir="ltr">38</bdi> שניות')
            again = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/captions.py'), str(src), str(out),
                                    '--lang', 'he'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(again.returncode, 2)  # never overwrites
            self.assertIn('captions.exists', again.stderr)
            self.assertIn('--retry', again.stderr)  # not inside a registered version: redo it in place
            retry = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/captions.py'), str(src), str(out),
                                    '--lang', 'he', '--mode', 'word', '--retry'], capture_output=True, text=True,
                                   encoding='utf-8')
            self.assertEqual(retry.returncode, 0, retry.stderr)
            self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['mode'], 'word')

    def test_max_chars_above_28_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'w.json', Path(tmp) / 'c.json'
            src.write_text(json.dumps(words('AI חוסך 38 שניות'), ensure_ascii=False), encoding='utf-8')

            def run(n):
                return subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/captions.py'), str(src), str(out),
                                       '--max-chars', str(n)], capture_output=True, text=True, encoding='utf-8')
            done = run(29)
            self.assertEqual(done.returncode, 2)
            self.assertIn('28', done.stderr)
            self.assertNotIn('Traceback', done.stderr)
            self.assertFalse(out.exists())
            self.assertEqual(run(20).returncode, 0)
        with self.assertRaises(ValueError):
            captions.build(words('שלום'), 'he', max_chars=40)

    def test_captions_in_a_registered_version_point_to_a_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'projects' / 'demo'
            version = project / 'versions/v03'
            version.mkdir(parents=True)
            src, out = version / 'cut.words.json', version / 'captions.json'
            src.write_text(json.dumps(words('שלום לכולם'), ensure_ascii=False), encoding='utf-8')
            out.write_text('{}', encoding='utf-8')
            registry = Path(tmp) / 'projects.json'
            registry.write_text(json.dumps({'projects': [{'id': 'demo', 'artifacts': [
                {'id': 'video-v03', 'type': 'video', 'path': 'versions/v03/renders/final.mp4'}]}]}), encoding='utf-8')
            with patch.object(captions.new_version, 'REGISTRY', registry), \
                    patch('sys.stderr', new_callable=io.StringIO) as err:
                self.assertEqual(captions.main([str(src), str(out), '--retry']), 2)
            self.assertIn('new_version.py', err.getvalue())
            self.assertIn('--from v03', err.getvalue())
            self.assertEqual(out.read_text(encoding='utf-8'), '{}')


if __name__ == '__main__':
    unittest.main()
