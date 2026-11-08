"""The spoken cut for a talking-head video: keep chosen word ranges, shrink the pauses.

    python scripts/cut.py projects/<id> <request.json> <out_dir>

request.json (paths relative to the project folder):
    {"style": "tight" | "natural" | "keep-pauses",
     "fps": 30, "width": 1080, "height": 1920, "fit": "cover" | "pad",
     "pieces": [{"media": "work/media/<file>.mp4", "words": "work/transcripts/<file>.json",
                 "from": 0, "to": 41}, ...]}

Each piece keeps words[from..to] (inclusive) of one prepared take, in the order listed: drop a
flubbed line or an earlier retake by leaving its words out (split the take into two pieces).
Inside a piece every pause longer than the style allows is shortened by punctuation (full
stop / comma / other / between pieces), keeping a margin around each word so no syllable is
clipped. Boundaries snap to the output frame grid; each part is cut with an accurate seek and
12 ms audio fades, then joined. Writes <out_dir>/cut.mp4 (H.264 yuv420p, BT.709, AAC 48 kHz),
cut.words.json (the kept words re-timed onto the cut, {text,startMs,endMs,piece,index}) and
cut.map.json (source/output time of every kept interval).

Never overwrites a cut the studio already shows: when <out_dir> already has cut.mp4 it answers
cut.exists. If nothing from that version is registered yet (the cut check found a clipped word
before the storyboard), run the same command again with --retry to redo the cut in the same
version; once the version is registered, make a new one (new_version.py --from vNN).
Errors are coded (cut.bad-request, cut.exists, cut.failed) with a plain message.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tools  # noqa: E402
import new_version  # noqa: E402

# Seconds of silence to keep after a word ending in . ? ! : / a comma / anything else / between
# pieces, the speech margin kept before (pre) and after (post) every word, and the shortest
# pause worth cutting at all.
STYLES = {
    'tight': {'stop': 0.26, 'comma': 0.14, 'other': 0.06, 'piece': 0.20, 'pre': 0.06, 'post': 0.10, 'min_cut': 0.0},
    'natural': {'stop': 0.45, 'comma': 0.25, 'other': 0.12, 'piece': 0.35, 'pre': 0.08, 'post': 0.14,
                'min_cut': 0.35},
    'keep-pauses': {'stop': 0.70, 'comma': 0.50, 'other': 0.40, 'piece': 0.50, 'pre': 0.10, 'post': 0.20,
                    'min_cut': 1.0},
}
FADE = 0.012
BT709 = 'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709'


class CutError(Exception):
    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code, self.message = code, message


def _target(text, rules):
    end = text.rstrip('"\'»”)').strip()[-1:] if text.strip() else ''
    return rules['stop'] if end in '.?!:…' and end else rules['comma'] if end in ',;־–—' and end else rules['other']


def intervals(words, first, last, style, duration):
    """[(start, end)] seconds of the source to keep for words[first..last]."""
    rules = STYLES[style]
    edge = rules['piece'] / 2
    spans = []
    start = max(0.0, words[first]['startMs'] / 1000 - max(rules['pre'], edge))
    for a, b in zip(words[first:last], words[first + 1:last + 1]):
        end_a, start_b = a['endMs'] / 1000, b['startMs'] / 1000
        target = _target(a['text'], rules)
        tail, lead = max(rules['post'], target / 2), max(rules['pre'], target / 2)
        gap = start_b - end_a
        if gap > max(tail + lead + 0.05, rules['min_cut']):
            spans.append((start, end_a + tail))
            start = start_b - lead
    spans.append((start, min(duration, words[last]['endMs'] / 1000 + max(rules['post'], edge))))
    return [(round(s, 4), round(e, 4)) for s, e in spans]


def validate(request):
    if not isinstance(request, dict) or request.get('style') not in STYLES:
        raise CutError('cut.bad-request', f'style must be one of {", ".join(STYLES)}')
    pieces = request.get('pieces')
    if not isinstance(pieces, list) or not pieces:
        raise CutError('cut.bad-request', 'pieces must be a non-empty list')
    for n, piece in enumerate(pieces):
        if (not isinstance(piece, dict) or not isinstance(piece.get('media'), str) or
                not isinstance(piece.get('words'), str) or not isinstance(piece.get('from'), int) or
                not isinstance(piece.get('to'), int) or not 0 <= piece['from'] <= piece['to']):
            raise CutError('cut.bad-request', f'piece {n}: needs media, words and 0 <= from <= to')
    if request.get('fit', 'cover') not in ('cover', 'pad'):
        raise CutError('cut.bad-request', 'fit must be cover or pad')
    for key, default in (('fps', 30), ('width', 1080), ('height', 1920)):
        value = request.get(key, default)
        if not isinstance(value, int) or value <= 0 or (key != 'fps' and value % 2):
            raise CutError('cut.bad-request', f'{key} must be a positive (even) integer')


def _run(args):
    try:
        return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
    except subprocess.CalledProcessError as error:
        raise CutError('cut.failed', (error.stderr or '').strip()[-600:]) from None


def _probe(path):
    info = json.loads(_run([tools.resolve('ffprobe'), '-v', 'error', '-show_streams', '-show_format',
                            '-of', 'json', path]).stdout)
    streams = info.get('streams', [])
    if not any(s.get('codec_type') == 'video' for s in streams):
        raise CutError('cut.bad-request', f'{path} has no video')
    return float(info['format']['duration']), any(s.get('codec_type') == 'audio' for s in streams)


def _inside(project, relative):
    path = (Path(project) / relative).resolve()
    if not path.is_relative_to(Path(project).resolve()) or not path.is_file():
        raise CutError('cut.bad-request', f'{relative} is not a file in this project')
    return path


def exists_message(project, out_dir, name):
    """Why <out_dir>/<name> cannot be written now, and the one correct way on."""
    if new_version.registered(out_dir):
        return (f'this version already has {name} and the studio shows it; make a new version with '
                f'python scripts/new_version.py "{Path(project).as_posix()}" --from {Path(out_dir).name}')
    return (f'this version already has {name}; nothing from it is registered yet, so to redo it here run '
            f'the same command again with --retry')


def render(project, request, out_dir, retry=False):
    validate(request)
    project, out_dir = Path(project), Path(out_dir)
    fps, width, height = request.get('fps', 30), request.get('width', 1080), request.get('height', 1920)
    output = out_dir / 'cut.mp4'
    if output.exists() and (not retry or new_version.registered(out_dir)):
        raise CutError('cut.exists', exists_message(project, out_dir, 'cut.mp4'))
    if request.get('fit', 'cover') == 'cover':
        frame = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}'
    else:
        frame = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2'
    plan = []
    for n, piece in enumerate(request['pieces']):
        media = _inside(project, piece['media'])
        try:
            words = json.loads(_inside(project, piece['words']).read_text(encoding='utf-8'))
        except ValueError:
            raise CutError('cut.bad-request', f'{piece["words"]} is not valid JSON') from None
        if piece['to'] >= len(words):
            raise CutError('cut.bad-request', f'piece {n}: "to" {piece["to"]} but the transcript has {len(words)} words')
        duration, has_audio = _probe(media)
        for start, end in intervals(words, piece['from'], piece['to'], request['style'], duration):
            first, last = round(start * fps), round(end * fps)
            if last > first:
                plan.append({'piece': n, 'media': piece['media'], 'path': media, 'has_audio': has_audio,
                             'in_frame': first, 'frames': last - first, 'words': words,
                             'range': (piece['from'], piece['to'])})
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.cut-', dir=out_dir))
    try:
        ffmpeg = tools.resolve('ffmpeg')
        for i, part in enumerate(plan):
            seconds = part['frames'] / fps
            args = [ffmpeg, '-nostdin', '-v', 'error', '-ss', f'{part["in_frame"] / fps:.6f}', '-i', part['path']]
            audio = (f'aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{seconds:.6f},'
                     f'afade=t=in:d={FADE},afade=t=out:st={max(0.0, seconds - FADE):.6f}:d={FADE}')
            if not part['has_audio']:
                args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            args += ['-map', '0:v:0', '-map', '0:a:0' if part['has_audio'] else '1:a:0',
                     '-vf', f'fps={fps},{frame},setsar=1,format=yuv420p,{BT709}', '-frames:v', str(part['frames']),
                     '-af', audio, '-t', f'{seconds:.6f}', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16',
                     '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', work / f'{i:04}.mov']
            _run(args)
        (work / 'list.txt').write_text(''.join(f"file '{i:04}.mov'\n" for i in range(len(plan))), encoding='utf-8')
        _run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', work / 'list.txt',
              '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart',
              work / 'cut.mp4'])
        moved, rows, position = [], [], 0
        for part in plan:
            start, frames = part['in_frame'] / fps, part['frames']
            end = start + frames / fps
            first, last = part['range']
            kept = [i for i in range(first, last + 1) if start <= part['words'][i]['startMs'] / 1000 < end]
            offset = position / fps
            for i in kept:
                word = part['words'][i]
                begin = offset + word['startMs'] / 1000 - start
                finish = min(offset + frames / fps, offset + word['endMs'] / 1000 - start)
                moved.append({'text': word['text'], 'startMs': round(begin * 1000), 'endMs': round(finish * 1000),
                              'piece': part['piece'], 'index': i})
            rows.append({'piece': part['piece'], 'media': part['media'], 'source_in': round(start, 4),
                         'source_out': round(end, 4), 'output_in': round(offset, 4),
                         'output_out': round(offset + frames / fps, 4),
                         'words': [kept[0], kept[-1]] if kept else []})
            position += frames
        total = round(position / fps, 4)
        (work / 'cut.words.json').write_text(json.dumps(moved, ensure_ascii=False, indent=2), encoding='utf-8')
        (work / 'cut.map.json').write_text(json.dumps({'style': request['style'], 'fps': fps, 'duration': total,
                                                       'intervals': rows}, ensure_ascii=False, indent=2),
                                           encoding='utf-8')
        for name in ('cut.words.json', 'cut.map.json', 'cut.mp4'):  # the video last: it marks a complete set
            os.replace(work / name, out_dir / name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {'cut': str(output), 'duration': total, 'words': len(moved), 'intervals': len(plan)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path)
    parser.add_argument('request', type=Path)
    parser.add_argument('out_dir', type=Path)
    parser.add_argument('--retry', action='store_true',
                        help='replace this version\'s cut (only while nothing from the version is registered)')
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding='utf-8'))
        result = render(args.project, request, args.out_dir, retry=args.retry)
    except (OSError, ValueError) as error:
        print(f'cut.bad-request: {error}', file=sys.stderr)
        return 2
    except CutError as error:
        print(str(error), file=sys.stderr)
        return 2
    except tools.ToolMissing as error:
        print(f'cut.failed: {error.name} is not installed (see SETUP.md)', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
