"""RULING R51: scripts/media.py is the only way a skill runs ffmpeg/ffprobe. Every command the
skills show passes it inside a studio run; the confirmed attacks (and their spellings) are
refused before any tool starts. Dummy files only -- never a real .env."""
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(f'studio_{name}', SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


media = load('media')
check_skills = load('check_skills')
jobscope = media.jobscope


class JobFolder(unittest.TestCase):
    """A throwaway studio, cwd inside it, STUDIO_JOB_DIR set to projects/demo (or references/demo)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        for folder in ('projects/demo/versions/v01/renders', 'projects/demo/versions/v01/sfx',
                       'projects/demo/versions/v01/storyboard', 'references/demo/analysis/r01', 'scripts'):
            (self.root / folder).mkdir(parents=True)
        for name in ('projects/demo/versions/v01/renders/video-only.mp4', 'projects/demo/versions/v01/mix.wav',
                     'projects/demo/versions/v01/cut.mp4', 'projects/demo/versions/v01/sfx/whoosh.wav',
                     'projects/demo/versions/v01/renders/draft.mp4', 'references/demo/source.mp4'):
            (self.root / name).write_bytes(b'dummy media')
        (self.root / '.ENV').write_text('STUDIO_VOICE_KEY=dummy-not-a-key\n', encoding='utf-8')
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.saved = os.environ.get(jobscope.ENV)
        self.use('projects/demo')

    def tearDown(self):
        os.chdir(self.cwd)
        if self.saved is None:
            os.environ.pop(jobscope.ENV, None)
        else:
            os.environ[jobscope.ENV] = self.saved
        self.tmp.cleanup()

    def use(self, folder):
        os.environ[jobscope.ENV] = str(self.root / folder)

    def refused(self, command):
        with self.assertRaises((media.Refused, jobscope.JobScopeError), msg=command):
            media.checked(shlex.split(command))


class SkillCommandsPass(JobFolder):
    def test_every_documented_command_passes(self):
        seen = 0
        for skill in check_skills.FIXED_STEPS:
            _, texts = check_skills._texts(REPO, skill)
            for text in texts.values():
                for command in check_skills._commands(text):
                    if not command.startswith('python "<studio>/scripts/media.py" ') or '…' in command or '<in>' in command:
                        continue
                    command = command.replace('<id>', 'demo')
                    tokens = shlex.split(command)[2:]
                    if len(tokens) < 3:
                        continue  # prose ("python scripts/media.py ffmpeg"), not a command
                    self.use('references/demo' if 'references/' in command else 'projects/demo')
                    for i, token in enumerate(tokens):  # this command's own inputs exist, its output does not
                        if token == '-i' and tokens[i - 1] != 'lavfi':
                            (self.root / tokens[i + 1]).write_bytes(b'dummy media')
                    if tokens[0] == 'ffmpeg' and tokens[-1] != '-':
                        (self.root / tokens[-1]).unlink(missing_ok=True)
                    if tokens[0] == 'ffprobe':
                        (self.root / tokens[-1]).write_bytes(b'dummy media')
                    with self.subTest(command=command):
                        args = media.checked(tokens)
                        seen += 1
                        if args[0] == 'ffmpeg':
                            self.assertEqual(args[1:3], ['-nostdin', '-n'])
                            for i, token in enumerate(args):
                                if token == '-i' and args[i - 1] != 'lavfi':
                                    self.assertEqual(args[i - 4:i], media.SAFE_INPUT)
                        else:
                            self.assertEqual(args[1:5], media.SAFE_INPUT)
        self.assertGreater(seen, 10)


class AttacksAreRefused(JobFolder):
    def test_the_confirmed_attacks(self):
        for command in (
            # (a) a raw copy written as a module the next helper would import / a settings file
            'ffmpeg -f lavfi -i color=c=black -c:v rawvideo -f rawvideo scripts/json.py',
            'ffmpeg -i projects/demo/versions/v01/cut.mp4 -c copy -f data .claude/settings.local.json',
            'ffmpeg -i projects/demo/versions/v01/cut.mp4 -c copy CLAUDE.local.md',
            'ffmpeg -i projects/demo/versions/v01/cut.mp4 -c copy projects/demo/json.py',
            # (b) printing a key file whatever its case or spelling
            'ffprobe -show_packets -show_data .ENV',
            'ffprobe -v error .ENV', 'ffprobe ".env "', 'ffprobe .env::$DATA', 'ffprobe projects/demo/../../.ENV',
            'ffmpeg -f data -i .ENV -c copy -f data projects/demo/k.mp4',
        ):
            with self.subTest(command=command):
                self.refused(command)

    def test_spellings_and_tricks(self):
        cut = 'projects/demo/versions/v01/cut.mp4'
        out = 'projects/demo/versions/v01/new.mp4'
        for command in (
            f'ffmpeg -i http:attacker.example/x {out}', f'ffmpeg -i https://attacker.example/x {out}',
            f'ffmpeg -i tcp://1.2.3.4:9 {out}', f'ffmpeg -i "$U" {out}', f'ffmpeg -i {cut} "`id`.mp4"',
            f'ffmpeg -"y" -i {cut} {out}', f'ffmpeg -y -i {cut} {out}', f'ffmpeg -i {cut} -f tee "[f=mp4]{out}"',
            f'ffmpeg -i {cut} -vf "movie=CLAUDE.md" {out}', f'ffmpeg -i {cut} -af "amovie=x.wav" {out}',
            f'ffmpeg -i {cut} -vf "frei0r=x" {out}', f'ffmpeg -i {cut} -vf "metadata=mode=print:file=CLAUDE.md" {out}',
            f'ffmpeg -i {cut} -vf "drawtext=textfile=.ENV" {out}', f'ffmpeg -i {cut} -vf "subtitles=x.srt" {out}',
            f'ffmpeg -i {cut} -vf "sendcmd=f=x" {out}', f'ffmpeg -i {cut} -af "ladspa=x" {out}',
            f'ffmpeg -i {cut} -vf "curves=psfile=x" {out}', f'ffmpeg -i {cut} -vf zmq {out}',
            f'ffmpeg -i ../x.mp4 {out}', f'ffmpeg -i {cut} ../x.mp4', f'ffmpeg -i C:/Windows/win.ini {out}',
            f'ffmpeg -i //server/share/x.mp4 {out}', f'ffmpeg -i {cut} {cut}', f'ffmpeg -i {cut} CLAUDE.md',
            f'ffmpeg -i {cut} projects/demo/notes.md', f'ffmpeg -protocol_whitelist file,http -i {cut} {out}',
            f'ffmpeg -f concat -safe 0 -i list.txt {out}', f'ffmpeg -i {cut} -progress p.txt {out}',
            f'ffmpeg -report -i {cut} {out}', f'ffmpeg -i {cut} -vstats_file v.txt {out}',
            f'ffmpeg -dump_attachment:t x.ttf -i {cut} {out}', f'ffmpeg -i {cut} -attach x.ttf {out}',
            f'ffmpeg -i {cut} -filter_complex_script g.txt {out}', f'ffmpeg -i {cut} -/vf g.txt {out}',
            f'ffmpeg -pattern_type glob -i "*.mp4" {out}', f'ffmpeg -i - {out}', f'ffmpeg -i {cut} -f null other',
            f'ffmpeg -i {cut} -passlogfile x {out}', f'ffmpeg -i {cut}', 'ffprobe -show_data ' + cut,
            'ffprobe ' + cut + ' ' + cut, 'ffprobe -i http:attacker.example/x', 'ffmpeg', 'curl x',
        ):
            with self.subTest(command=command):
                self.refused(command)

    def test_round3_filter_escapes_and_file_loading_are_refused(self):
        # G2: a fixed filter list with fixed option keys; no escapes, no "/key", no file filters.
        cut = 'projects/demo/versions/v01/cut.mp4'
        out = 'projects/demo/versions/v01/new.mp4'
        for graph in ("drawtext=text'file'=.ENV", r'drawtext=tex\tfile=.ENV', "drawtext=text='x'",
                      'scale=/w=CLAUDE.md', 'scale=w=100:/h=CLAUDE.md', 'curves=none::::::x.acv',
                      'scale=100:100:flags=x:extra=1', 'scale=1:2:3', "'scale'=1:2", 'sendcmd=c=x',
                      r'select=gt(scene\,0.3)', 'lut3d=x.cube', 'scale@/x=1:2', 'Scale=1:2',
                      'afade=t=in:textfile=x', 'volume=1:2'):
            with self.subTest(graph=graph):
                self.refused(f'ffmpeg -i {cut} -vf "{graph}" {out}')
        for graph in ("select='gt(scene,0.3)',showinfo", 'scale=540:-2', 'fps=2,scale=216:-2,tile=5x4',
                      'afade=t=out:st=0.2:d=0.25,volume=0.5', '[1:a]adelay=1200|1200[w];[0:a][w]amix=inputs=2'):
            with self.subTest(graph=graph):
                media.check_graph(graph)

    def test_round3_inputs_must_be_plain_media(self):
        # G3: by name (extension) and by content (-format_whitelist, checked with a real ffmpeg below).
        (self.root / 'projects/demo/list.m3u8').write_text('#EXTM3U' + chr(10), encoding='utf-8')
        (self.root / 'projects/demo/list.txt').write_text("file 'x.mp4'" + chr(10), encoding='utf-8')
        for command in ('ffmpeg -i projects/demo/list.m3u8 projects/demo/o.mp4',
                        'ffmpeg -f concat -i projects/demo/list.txt projects/demo/o.mp4',
                        'ffprobe projects/demo/list.m3u8'):
            with self.subTest(command=command):
                self.refused(command)

    def test_round3_checked_paths_are_the_ones_passed_on(self):
        # G11: ffmpeg gets the resolved path that was checked.
        args = media.checked(['ffmpeg', '-i', 'projects/demo/versions/v01/cut.mp4', 'projects/demo/versions/v01/n.mp4'])
        self.assertIn(str((self.root / 'projects/demo/versions/v01/cut.mp4').resolve()), args)
        self.assertEqual(args[-1], str((self.root / 'projects/demo/versions/v01/n.mp4').resolve()))

    def test_round3_studio_records_are_never_outputs(self):
        # G8: no output may replace a studio-owned record, whatever its extension check says.
        self.refused('ffmpeg -i projects/demo/versions/v01/cut.mp4 projects/demo/approval-state.json')

    def test_the_cli_prints_a_coded_refusal_and_runs_nothing(self):
        env = {**os.environ, 'PATH': ''}  # if anything slipped through, ffmpeg could not even start
        done = subprocess.run([sys.executable, str(SCRIPTS / 'media.py'), 'ffprobe', '-show_data', '.ENV'],
                              capture_output=True, text=True, encoding='utf-8', env=env, cwd=self.root)
        self.assertEqual(done.returncode, 2)
        self.assertIn(json.loads(done.stdout)['code'], ('media.refused', 'job.outside-folder'))
        self.assertNotIn('dummy-not-a-key', done.stdout + done.stderr)


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
class RealRun(JobFolder):
    def test_a_playlist_renamed_to_mp4_is_refused_by_ffmpeg_itself(self):
        # G3: the -format_whitelist does what the extension check cannot.
        (self.root / 'projects/demo/fake.mp4').write_text(chr(10).join(['#EXTM3U', '#EXTINF:1,', 'http://attacker.example/x.ts', '']),
                                                          encoding='utf-8')
        done = subprocess.run([sys.executable, str(SCRIPTS / 'media.py'), 'ffprobe', '-v', 'error',
                               'projects/demo/fake.mp4'], capture_output=True, text=True, encoding='utf-8', cwd=self.root)
        self.assertNotEqual(done.returncode, 0)

    def test_a_real_clip_still_passes_the_whitelists(self):
        clip = self.root / 'projects/demo/versions/v01/real.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=duration=1:size=160x120',
                        '-pix_fmt', 'yuv420p', str(clip)], check=True, timeout=60)
        done = subprocess.run([sys.executable, str(SCRIPTS / 'media.py'), 'ffmpeg', '-v', 'error', '-i',
                               'projects/demo/versions/v01/real.mp4', '-frames:v', '1',
                               'projects/demo/versions/v01/still.jpg'],
                              capture_output=True, text=True, encoding='utf-8', cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_real_lavfi_tone_is_written_inside_the_job(self):
        out = 'projects/demo/versions/v01/sfx/tick.wav'
        done = subprocess.run([sys.executable, str(SCRIPTS / 'media.py'), 'ffmpeg', '-v', 'error', '-f', 'lavfi',
                               '-i', 'sine=frequency=2000:duration=0.03', '-ar', '48000', '-ac', '2', out],
                              capture_output=True, text=True, encoding='utf-8', cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertGreater((self.root / out).stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
