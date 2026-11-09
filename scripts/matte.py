#!/usr/bin/env python3
"""Local, free presenter matte (background removal) for presenter looks.

    python scripts/matte.py <video> <out_dir> [--fps RATE] [--backend auto|hyperframes] [--force]
                            [--reuse-from DIR] [--progress FILE] [--step KEY] [--lang he|en]

Writes <out_dir>/alpha.mp4 (grayscale matte, white = presenter), <out_dir>/fg.webm (VP9 with
alpha: the presenter alone) and <out_dir>/matte.json (input hash, backend, model, timeline) so
callers can tell whether the matte is stale. ffmpeg does all decoding/encoding; a backend only
turns the normalized source into one grayscale mask PNG per frame.

--reuse-from DIR (ruling R45): when DIR holds a complete matte whose matte.json records the same
input hash, backend, model and frame rate as this run would use, its alpha.mp4 / fg.webm are
copied into out_dir (matte.json too, with "input" updated and "reused_from" added) instead of
recomputing -- a refine round re-runs the same cut request, which gives a byte-identical cut, so
the previous version's matte is still exact. Anything else (other hash, other model, missing or
incomplete DIR) recomputes. out_dir is still never overwritten without --force.

Timeline rule: the source is decoded once into a constant-frame-rate copy and every output is
made from that copy. The rate is the input's own (`r_frame_rate`: 24, 25, 30000/1001, 60 ...),
or --fps when given. Variable-frame-rate phone takes are re-timed to that rate with ffmpeg's
`fps` filter from the first frame (dropped frames repeat the previous one). matte.json records
`fps` (exact rational), `vfr_input` and `retime_filter`; a caller compositing the matte over the
original footage must decode the footage through the same `retime_filter` so frame N lines up.
Odd sizes are rounded down to even (the last row/column is dropped); matte.json records the
real width/height. Phone HDR (HLG/PQ) is converted to SDR BT.709 first so skin matches the edit.

Progress: matte() takes on_progress(stage, percent) with stages decode -> matte -> encode ->
done and an overall percent. The CLI writes it into a Task 14 progress file (a JSON list of
{"key","state","detail"}): by default <out_dir>/progress.json; the talking-head skill passes
--progress <project>/progress.json --step <its step key> so the studio shows e.g.
"מסירים רקע · 42%" on that step while keeping the skill's other steps.

Why not scripts/hf.py: hf.py hands the terminal to HyperFrames and exits with its code; matte
needs the CLI's stderr for error detail, live polling for progress, and extra env switches.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)
import tools  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ('alpha.mp4', 'fg.webm', 'matte.json')
BT709 = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']
# Frame tags win over the output flags above: without this, an HLG source's arib-std-b67 tag
# survives the SDR conversion and Chromium tone-maps the cut-out a second time (red skin).
RETAG = 'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709'
# Plain HLG -> SDR conversion that matched the owner's phone (red skin with zscale tone-mapping).
HDR_TO_SDR = {
    'arib-std-b67': "zscale=pin=bt2020:p=bt709:min=bt2020nc:m=bt709:tin=arib-std-b67:t=arib-std-b67:rin=tv:r=tv,"
                    "format=gbrp,curves=m='0/0 0.25/0.18 0.5/0.4 0.76/0.6 1/0.95':r='0/0 0.5/0.53 1/1':"
                    "b='0/0 0.5/0.46 1/1',eq=saturation=1.18,scale=out_color_matrix=bt709:out_range=tv",
    'smpte2084': "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                 "zscale=t=bt709:m=bt709:r=tv",
}
COMMON_RATES = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
                Fraction(50), Fraction(60000, 1001), Fraction(60)]
# Overall percent at the start of each stage.
SPAN = {'decode': (0, 5), 'matte': (5, 88), 'encode': (88, 100)}
STAGE_TEXT = {'he': {'decode': 'מכינים את הסרטון', 'matte': 'מסירים רקע', 'encode': 'שומרים את החיתוך',
                     'done': 'הרקע הוסר'},
              'en': {'decode': 'Preparing the video', 'matte': 'Removing the background',
                     'encode': 'Saving the cutout', 'done': 'Background removed'}}


class MatteError(Exception):
    """Codes: matte.no-backend, matte.model-missing, matte.failed, matte.exists (UI text lives in i18n)."""

    def __init__(self, code, detail=''):
        super().__init__(code + (': ' + detail if detail else ''))
        self.code, self.detail = code, detail


def run(args, env=None):
    # UTF-8 with replacement: the HyperFrames CLI prints spinners that cp1252 cannot decode on Windows.
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env)


def run_streaming(args, on_line, env=None, poll=None, interval=1.0):
    """Run with stdout+stderr merged and read line by line (\\r or \\n); call poll() every
    `interval` seconds while it runs. Raises CalledProcessError with the tail of the output."""
    process = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, env=env)
    tail = []

    def reader():
        buffer = b''
        for chunk in iter(lambda: process.stdout.read1(4096), b''):
            buffer += chunk
            *lines, buffer = re.split(rb'[\r\n]', buffer)
            for line in lines:
                text = line.decode('utf-8', 'replace').strip()
                if text:
                    tail[:] = (tail + [text])[-40:]
                    on_line(text)
        if buffer.strip():
            tail.append(buffer.decode('utf-8', 'replace').strip())

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    while process.poll() is None:
        thread.join(interval)
        if poll and process.poll() is None:
            poll()
    thread.join()
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, args, stderr='\n'.join(tail))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def rate(text):
    try:
        value = Fraction(str(text))
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def native_fps(stream):
    """(fps, vfr_input) for a probed video stream. r_frame_rate is ffmpeg's base rate (30 for a
    phone take that drops frames); an implausible one (a timebase like 90000) falls back to the
    average snapped to the nearest common rate."""
    base, average = rate(stream.get('r_frame_rate')), rate(stream.get('avg_frame_rate'))
    vfr = bool(base and average and base != average)
    if base and base <= 120:
        return base, vfr
    if average:
        return min(COMMON_RATES, key=lambda common: abs(common - average)), True
    raise MatteError('matte.failed', 'unknown frame rate')


def ffmpeg_rate(value):
    return f'{value.numerator}/{value.denominator}'


class HyperframesBackend:
    """The pinned HyperFrames CLI's documented `remove-background` command (u2net_human_seg,
    Apache-2.0, on onnxruntime-node: CPU everywhere, CoreML on Apple Silicon).

    Public: `remove-background <in> -o <out.webm> --quality best` writing VP9 with alpha.
    Internals (read from the published 0.8.33/0.9.16 source, trusted only for VERIFIED versions):
    the model cache path, where the optional onnxruntime-node install lives, and the
    HYPERFRAMES_NO_OPTIONAL_INSTALL switch. For a verified version setup installs the runtime and
    the checked model, and nothing is installed or downloaded at render time. Any other version
    is simply invoked and allowed to fetch what it needs; its own error becomes matte.failed.
    HyperFrames prints no per-frame progress when unattended, so progress is estimated from
    elapsed time (a "Frame N/M" line, if a version prints one, wins)."""
    name = 'hyperframes'
    MODEL = 'u2net_human_seg'
    MODEL_SHA256 = '01eb6a29a5c4d8edb30b56adad9bb3a2a0535338e480724a213e0acfd2d1c73c'
    RUNTIME = ('onnxruntime-node', '1.21.1')
    VERIFIED = ('0.8.33', '0.9.16')
    # Measured 0.55-0.71 s/frame at 1080x1920 on a 16-thread Xeon (CPU); CoreML is a guess.
    SECONDS_PER_FRAME = 0.25 if (sys.platform == 'darwin' and platform.machine() == 'arm64') else 0.7

    def package(self):
        return ROOT / 'node_modules' / 'hyperframes'

    def cli(self):
        return self.package() / 'bin' / 'hyperframes.mjs'

    def version(self):
        try:
            return json.loads((self.package() / 'package.json').read_text(encoding='utf-8')).get('version')
        except (OSError, ValueError):
            return None

    def verified(self):
        return self.version() in self.VERIFIED

    @property
    def model(self):
        return self.MODEL if self.verified() else f'hyperframes {self.version()} default'

    def cache(self):
        named = os.environ.get('HYPERFRAMES_CACHE_DIR')
        return Path(named).resolve() if named else Path.home() / '.cache' / 'hyperframes'

    def model_path(self):
        return self.cache() / 'background-removal' / 'models' / f'{self.MODEL}.onnx'

    def runtime_ready(self):
        name, version = self.RUNTIME
        for manifest in [ROOT / 'node_modules' / name / 'package.json',
                         self.cache() / 'optional' / f'{name}@{version}' / 'node_modules' / name / 'package.json']:
            try:
                if json.loads(manifest.read_text(encoding='utf-8')).get('version') == version:
                    return True
            except (OSError, ValueError):
                continue
        return False

    def available(self):
        if not self.cli().is_file() or shutil.which('node') is None:
            return False
        return self.runtime_ready() if self.verified() else True

    def check_model(self):
        path = self.model_path()
        if not path.is_file() or sha256(path) != self.MODEL_SHA256:
            raise MatteError('matte.model-missing', str(path))
        return path

    def remove_background(self, source, cutout, env, frames, report):
        started, seen = time.monotonic(), [0.0]

        def on_line(text):
            found = re.search(r'Frame (\d+)/(\d+)', text)
            if found and int(found.group(2)):
                seen[0] = int(found.group(1)) / int(found.group(2))

        def poll():
            guess = (time.monotonic() - started) / max(1.0, frames * self.SECONDS_PER_FRAME)
            report(seen[0] or min(0.95, guess))

        run_streaming([tools.resolve('node'), self.cli(), 'remove-background', source, '-o', cutout,
                       '--quality', 'best'], on_line, env=env, poll=poll)

    def masks(self, source, masks_dir, frames, report):
        env = {**os.environ, 'HYPERFRAMES_NO_UPDATE_CHECK': '1', 'HYPERFRAMES_NO_TELEMETRY': '1'}
        if self.verified():
            self.check_model()
            env['HYPERFRAMES_NO_OPTIONAL_INSTALL'] = '1'
        cutout = masks_dir.parent / 'hyperframes-cutout.webm'
        self.remove_background(source, cutout, env, frames, report)
        # The libvpx decoder keeps VP9 alpha (ffmpeg's native vp9 decoder drops it).
        run([tools.resolve('ffmpeg'), '-nostdin', '-v', 'error', '-c:v', 'libvpx-vp9', '-i', cutout,
             '-vf', 'alphaextract,format=gray', masks_dir / '%06d.png'])
        report(1.0)


BACKENDS = {'hyperframes': HyperframesBackend()}


def config():
    return json.loads((ROOT / 'studio.config.json').read_text(encoding='utf-8'))


def available_backends():
    return [name for name, backend in BACKENDS.items() if backend.available()]


def pick_backend(name='auto'):
    if name != 'auto':
        backend = BACKENDS.get(name)
        if backend is None or not backend.available():
            raise MatteError('matte.no-backend', name)
        return backend
    preferred = config().get('matting', {}).get('backend')
    order = ([preferred] if preferred in BACKENDS else []) + [n for n in BACKENDS if n != preferred]
    for candidate in order:
        if BACKENDS[candidate].available():
            return BACKENDS[candidate]
    raise MatteError('matte.no-backend', 'none of: ' + ', '.join(BACKENDS))


def probe(path, count=False):
    args = [tools.resolve('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,color_transfer,r_frame_rate,avg_frame_rate,duration,'
            'nb_read_packets:format=duration', '-of', 'json', path]
    out = json.loads(run(args[:1] + (['-count_packets'] if count else []) + args[1:]).stdout)
    streams = out.get('streams') or []
    if not streams:
        raise MatteError('matte.failed', f'no video stream in {path}')
    stream = streams[0]
    stream.setdefault('duration', (out.get('format') or {}).get('duration'))
    return stream


def ffmpeg_progress(args, total, report):
    """Run an ffmpeg command with -progress and report the done fraction of `total` frames."""
    def on_line(text):
        if text.startswith('frame=') and text[6:].strip().isdigit() and total:
            report(min(1.0, int(text[6:]) / total))
    run_streaming(args[:1] + ['-progress', 'pipe:1', '-nostats'] + args[1:], on_line)


def normalize(video, target, fps, info, report):
    """Constant-fps, upright, even-sized SDR BT.709 copy that every backend and encoder reads."""
    steps = [f'fps={ffmpeg_rate(fps)}']
    tone = HDR_TO_SDR.get(info.get('color_transfer'))
    if tone:
        steps.append(tone)
    steps += ['scale=trunc(iw/2)*2:trunc(ih/2)*2', 'setsar=1', 'format=yuv420p', RETAG]
    expected = round(float(info.get('duration') or 0) * fps)
    ffmpeg_progress([tools.resolve('ffmpeg'), '-nostdin', '-v', 'error', '-i', video, '-map', '0:v:0', '-an',
                     '-vf', ','.join(steps), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '10', *BT709,
                     target], expected, report)


def encode(source, masks, fps, frames, work, report):
    ffmpeg, pattern, rate_text = tools.resolve('ffmpeg'), masks / '%06d.png', ffmpeg_rate(fps)
    run([ffmpeg, '-nostdin', '-v', 'error', '-framerate', rate_text, '-i', pattern, '-vf', 'format=gray,' + RETAG,
         '-c:v', 'libx264', '-preset', 'medium', '-crf', '12', '-pix_fmt', 'yuv420p', '-r', rate_text,
         *BT709, work / 'alpha.mp4'])
    report(0.15)
    ffmpeg_progress([ffmpeg, '-nostdin', '-v', 'error', '-i', source, '-framerate', rate_text, '-i', pattern,
                     '-filter_complex', '[1:v]format=gray[m];[0:v][m]alphamerge,format=yuva420p,' + RETAG + '[v]',
                     '-map', '[v]', '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-crf', '18', '-b:v', '0',
                     '-row-mt', '1', '-deadline', 'good', '-cpu-used', '4', '-r', rate_text, *BT709,
                     work / 'fg.webm'], frames, lambda done: report(0.15 + 0.85 * done))


def reusable(previous, input_hash, chosen, fps):
    """The previous matte.json when DIR holds a complete matte of this exact input, else None."""
    if previous is None:
        return None
    previous = Path(previous)
    try:
        record = json.loads((previous / 'matte.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not all((previous / name).is_file() for name in OUTPUTS):
        return None
    if (record.get('input_sha256'), record.get('backend'), record.get('model')) != (input_hash, chosen.name, chosen.model):
        return None
    if fps is not None and record.get('fps') != ffmpeg_rate(rate(fps)):
        return None
    return record


def copy_matte(video, previous, record, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.matte-', dir=out_dir))
    try:
        for name in ('alpha.mp4', 'fg.webm'):
            shutil.copy2(Path(previous) / name, work / name)
        record = dict(record, input=str(video.resolve()), reused_from=str(Path(previous).resolve()))
        (work / 'matte.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (out_dir / 'matte.json').unlink(missing_ok=True)
        for name in OUTPUTS:  # matte.json last: its presence means the set is complete
            os.replace(work / name, out_dir / name)
    except OSError as error:
        raise MatteError('matte.failed', str(error)) from error
    finally:
        shutil.rmtree(work, ignore_errors=True)


def matte(video, out_dir, backend='auto', fps=None, force=False, on_progress=None, reuse_from=None):
    video, out_dir = Path(video), Path(out_dir)
    if not video.is_file():
        raise MatteError('matte.failed', f'no such video: {video}')
    present = [name for name in OUTPUTS if (out_dir / name).exists()]
    if present and not force:
        raise MatteError('matte.exists', str(out_dir / present[0]))
    chosen = pick_backend(backend)
    input_hash = sha256(video)
    record = reusable(reuse_from, input_hash, chosen, fps)
    if record is not None:
        copy_matte(video, reuse_from, record, out_dir)
        if on_progress:
            on_progress('done', 100)
        return {'alpha': str(out_dir / 'alpha.mp4'), 'fg': str(out_dir / 'fg.webm'), 'frames': record.get('frames'),
                'backend': chosen.name, 'fps': record.get('fps'), 'reused': True}
    last = [-1]

    def stage(name):
        low, high = SPAN[name]

        def report(fraction):
            percent = int(low + (high - low) * max(0.0, min(1.0, fraction)))
            if on_progress and percent >= last[0]:
                last[0] = percent
                on_progress(name, percent)
        return report

    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.matte-', dir=out_dir))
    try:
        info = probe(video)
        if fps is None:
            fps, vfr = native_fps(info)
        else:
            fps, vfr = rate(fps), native_fps(info)[1]
            if not fps or fps > 240:
                raise MatteError('matte.failed', 'bad --fps')
        source, masks = work / 'source.mp4', work / 'masks'
        masks.mkdir()
        stage('decode')(0)
        normalize(video, source, fps, info, stage('decode'))
        made_info = probe(source, count=True)
        frames = int(made_info['nb_read_packets'])
        stage('matte')(0)
        chosen.masks(source, masks, frames, stage('matte'))
        made = len(list(masks.glob('*.png')))
        if made != frames:
            raise MatteError('matte.failed', f'{chosen.name} made {made} masks for {frames} frames')
        stage('encode')(0)
        encode(source, masks, fps, frames, work, stage('encode'))
        record = {'input': str(video.resolve()), 'input_sha256': input_hash, 'input_bytes': video.stat().st_size,
                  'backend': chosen.name, 'model': chosen.model, 'fps': ffmpeg_rate(fps), 'frames': frames,
                  'vfr_input': vfr, 'retime_filter': f'fps={ffmpeg_rate(fps)}',
                  'width': made_info['width'], 'height': made_info['height']}
        (work / 'matte.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (out_dir / 'matte.json').unlink(missing_ok=True)  # never leave a record describing old outputs
        for name in OUTPUTS:  # matte.json last: its presence means the set is complete
            os.replace(work / name, out_dir / name)
    except (subprocess.CalledProcessError, OSError, tools.ToolMissing) as error:
        detail = getattr(error, 'stderr', None) or str(error)
        raise MatteError('matte.failed', detail.strip()[-2000:]) from error
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if on_progress:
        on_progress('done', 100)
    return {'alpha': str(out_dir / 'alpha.mp4'), 'fg': str(out_dir / 'fg.webm'), 'frames': frames,
            'backend': chosen.name, 'fps': ffmpeg_rate(fps), 'reused': False}


def is_current(video, out_dir):
    """True when out_dir holds a complete matte made from exactly this video file."""
    out_dir = Path(out_dir)
    try:
        record = json.loads((out_dir / 'matte.json').read_text(encoding='utf-8'))
        return all((out_dir / n).is_file() for n in OUTPUTS) and record.get('input_sha256') == sha256(video)
    except (OSError, ValueError):
        return False


class ProgressFile:
    """One step of a Task 14 progress file ([{"key","state","detail"?}]), written atomically.
    Other steps already in the file are kept as they are."""

    def __init__(self, path, key='matte', lang='he'):
        self.path, self.key, self.text = Path(path), key, STAGE_TEXT.get(lang, STAGE_TEXT['he'])

    def update(self, stage, percent):
        if stage == 'done':
            step = {'key': self.key, 'state': 'done', 'detail': self.text['done']}
        else:
            step = {'key': self.key, 'state': 'running', 'detail': f'{self.text[stage]} · {percent}%'}
        try:
            steps = json.loads(self.path.read_text(encoding='utf-8'))
            steps = steps if isinstance(steps, list) else []
        except (OSError, ValueError):
            steps = []
        keys = [s.get('key') for s in steps if isinstance(s, dict)]
        if self.key in keys:
            steps = [step if isinstance(s, dict) and s.get('key') == self.key else s for s in steps]
        else:
            steps.append(step)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix='.progress-', dir=self.path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(steps, stream, ensure_ascii=False, indent=2)
            os.replace(temp, self.path)
        except OSError:
            pass  # progress is best effort (e.g. the studio is reading the file on Windows)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):  # Hebrew JSON on a Windows pipe/console (final review M5)
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('video', type=Path)
    parser.add_argument('out_dir', type=Path)
    parser.add_argument('--fps', default=None, help="output rate, e.g. 30 or 30000/1001 (default: the input's own)")
    parser.add_argument('--backend', default='auto', help='auto or one of: ' + ', '.join(BACKENDS))
    parser.add_argument('--force', action='store_true', help='replace an existing matte in out_dir')
    parser.add_argument('--reuse-from', type=Path, default=None, metavar='DIR',
                        help="an earlier version's matte folder: copied when it was made from this exact video")
    parser.add_argument('--progress', type=Path, default=None, help='progress file (default: <out_dir>/progress.json)')
    parser.add_argument('--step', default='matte', help='step key inside the progress file')
    parser.add_argument('--lang', default='he', choices=sorted(STAGE_TEXT), help='language of the progress text')
    args = parser.parse_args(argv)
    if (code := jobscope.refuse(args.video, args.out_dir, args.reuse_from)
            or jobscope.refuse(args.progress, write=True)) is not None:
        return code
    progress = ProgressFile(args.progress or args.out_dir / 'progress.json', args.step, args.lang)
    try:
        result = matte(args.video, args.out_dir, args.backend, fps=args.fps, force=args.force,
                       on_progress=progress.update, reuse_from=args.reuse_from)
    except MatteError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
