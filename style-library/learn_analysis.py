"""Server-side analysis of an inspiration video, before Claude sees it (RULING R53).

"Learn this style" is the only job that reads another creator's content, so it gets no
shell: the studio measures the video here, with fixed commands (an argv list, never a
shell), and writes the results into references/<id>/analysis/rNN/:

    notes.md         the measurements in plain words (length, shots, pace, loudness, ...)
    analysis.json    the same, machine-readable, plus the list of files below
    sheet-NN.jpg     contact sheets, two frames per second, 5x4 per sheet (10 s each)
    hook.jpg         the frame at 0.5 s, larger
    words.json       word timings (only when the video has a sound track and
                     transcription is installed; a failure is noted, never fatal)
    card-example.md  the built-in look card format (looks/headline/card.md) to follow

The source is untrusted: every ffmpeg/ffprobe input gets -protocol_whitelist file and a
-format_whitelist of plain media demuxers, so a "video" that is really a playlist or a
concat list cannot pull in other files or addresses. The speech track is first turned
into a plain wav here, and only that wav is transcribed.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts'))
import tools  # noqa: E402

VIDEO_EXT = ('.mp4', '.mov', '.webm', '.m4v')
SAFE_INPUT = ['-protocol_whitelist', 'file', '-format_whitelist', 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,wav']
TIMEOUT = 1800
TRANSCRIBE_TIMEOUT = 3600


class AnalysisError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def source(folder):
    found = sorted(p for p in Path(folder).glob('source.*') if p.suffix.lower() in VIDEO_EXT and p.is_file())
    return found[0] if found else None


def next_round(folder):
    analysis = Path(folder) / 'analysis'
    taken = {int(m.group(1)) for p in analysis.glob('r*') if (m := re.fullmatch(r'r(\d{2})', p.name))}
    number = max(taken, default=0) + 1
    return analysis / f'r{number:02d}'


def _run(args, timeout=TIMEOUT):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=timeout, stdin=subprocess.DEVNULL)


def probe(src):
    done = _run([tools.resolve('ffprobe'), '-v', 'error', *SAFE_INPUT, '-show_entries',
                 'stream=codec_type,width,height,r_frame_rate:format=duration', '-of', 'json', src])
    if done.returncode != 0:
        raise AnalysisError('analysis.unreadable', 'ffprobe could not read this video.')
    try:
        data = json.loads(done.stdout or '{}')
    except ValueError:
        raise AnalysisError('analysis.unreadable', 'ffprobe gave no readable report.') from None
    streams = data.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    audio = any(s.get('codec_type') == 'audio' for s in streams)
    try:
        duration = float((data.get('format') or {}).get('duration') or 0)
    except ValueError:
        duration = 0.0
    if not video or duration <= 0:
        raise AnalysisError('analysis.unreadable', 'This file has no readable video.')
    return {'duration': round(duration, 3), 'width': video.get('width'), 'height': video.get('height'),
            'frame_rate': video.get('r_frame_rate'), 'has_audio': audio}


def cuts(src):
    ffmpeg = tools.resolve('ffmpeg')
    done = _run([ffmpeg, '-nostdin', '-hide_banner', *SAFE_INPUT, '-i', src, '-vf', "select='gt(scene,0.3)',showinfo",
                 '-an', '-f', 'null', '-'])
    return [round(float(t), 3) for t in re.findall(r'pts_time:([0-9.]+)', done.stderr)]


def stills(src, folder):
    ffmpeg = tools.resolve('ffmpeg')
    _run([ffmpeg, '-nostdin', '-v', 'error', '-n', *SAFE_INPUT, '-i', src, '-vf', 'fps=2,scale=216:-2,tile=5x4',
          '-q:v', '4', folder / 'sheet-%02d.jpg'])
    _run([ffmpeg, '-nostdin', '-v', 'error', '-n', '-ss', '0.5', *SAFE_INPUT, '-i', src, '-frames:v', '1',
          '-vf', 'scale=540:-2', '-q:v', '3', folder / 'hook.jpg'])
    return sorted(p.name for p in folder.glob('sheet-*.jpg')) + (['hook.jpg'] if (folder / 'hook.jpg').is_file() else [])


def loudness(src):
    ffmpeg = tools.resolve('ffmpeg')
    done = _run([ffmpeg, '-nostdin', '-hide_banner', *SAFE_INPUT, '-i', src, '-vn', '-af', 'ebur128', '-f', 'null', '-'])
    summary = done.stderr[done.stderr.rfind('Summary:'):] if 'Summary:' in done.stderr else ''
    values = {}
    for key, label in (('integrated_lufs', r'I:\s*(-?[0-9.]+) LUFS'), ('range_lu', r'LRA:\s*(-?[0-9.]+) LU')):
        match = re.search(label, summary)
        if match:
            values[key] = float(match.group(1))
    return values


def words(src, folder, language, studio):
    """(words list or None, a note). The sound is first copied out to a plain wav here."""
    ffmpeg = tools.resolve('ffmpeg')
    wav = folder / '.speech.wav'
    done = _run([ffmpeg, '-nostdin', '-v', 'error', '-y', *SAFE_INPUT, '-i', src, '-vn', '-ac', '1', '-ar', '16000',
                 '-c:a', 'pcm_s16le', wav])
    if done.returncode != 0 or not wav.is_file():
        return None, 'no readable sound track'
    try:
        out = folder / 'words.json'
        done = _run([sys.executable, Path(studio) / 'scripts' / 'transcribe.py', wav, out, '--language', language],
                    timeout=TRANSCRIBE_TIMEOUT)
        if done.returncode != 0 or not out.is_file():
            return None, 'transcription is not available: ' + ((done.stderr or done.stdout).strip().splitlines() or ['failed'])[-1][:200]
        try:
            return json.loads(out.read_text(encoding='utf-8')), None
        except ValueError:
            return None, 'transcription gave no readable words'
    finally:
        wav.unlink(missing_ok=True)


def notes_text(result, lang):
    he = lang == 'he'
    m = result['measured']
    lines = ['# ' + ('מדידות הסרטון' if he else 'Video measurements'), '']
    rows = [
        ('אורך' if he else 'Length', f"{m['duration']} s"),
        ('גודל' if he else 'Size', f"{m.get('width')}x{m.get('height')}, {m.get('frame_rate')}"),
        ('שוטים' if he else 'Shots', str(m['shots'])),
        ('אורך שוט ממוצע' if he else 'Average shot', f"{m['average_shot']} s"),
        ('חיתוכים ל-10 שניות' if he else 'Cuts per 10 s', str(m['cuts_per_10s'])),
    ]
    if m.get('words_per_second') is not None:
        rows.append(('מילים לשנייה' if he else 'Words per second', str(m['words_per_second'])))
    for key, label in (('integrated_lufs', 'LUFS'), ('range_lu', 'LRA')):
        if key in m:
            rows.append((label, str(m[key])))
    lines += [f'- {name}: {value}' for name, value in rows]
    lines += ['', ('זמני החיתוכים (שניות)' if he else 'Cut times (seconds)') + ': ' + (', '.join(str(t) for t in result['cuts']) or '-')]
    if result.get('words_note'):
        lines += ['', ('מילים' if he else 'Words') + ': ' + result['words_note']]
    return '\n'.join(lines) + '\n'


def analyze(folder, studio, language='he', lang='he'):
    """Measure references/<id>/source.* into a new round folder; returns analysis.json's content.

    `language`: the transcription language (he|en); `lang`: the notes' language (the UI's)."""
    folder = Path(folder)
    src = source(folder)
    if src is None:
        raise AnalysisError('analysis.no-source', 'There is no video file for this reference yet.')
    measured = probe(src)
    out = next_round(folder)
    out.mkdir(parents=True)
    times = cuts(src)
    files = stills(src, out)
    measured.update(loudness(src))
    word_list, note = (words(src, out, language, studio) if measured['has_audio'] else (None, 'no sound track'))
    shots = len(times) + 1
    measured.update(shots=shots, average_shot=round(measured['duration'] / shots, 2),
                    cuts_per_10s=round(len(times) / measured['duration'] * 10, 2))
    if word_list:
        files.append('words.json')
        span = max((w.get('endMs', 0) for w in word_list), default=0) / 1000 or measured['duration']
        measured['words_per_second'] = round(len(word_list) / span, 2) if span else None
    example = HERE.parent / 'looks' / 'headline' / 'card.md'
    if example.is_file():
        shutil.copy2(example, out / 'card-example.md')
        files.append('card-example.md')
    result = {'round': out.name, 'source': src.name, 'measured': measured, 'cuts': times, 'files': files,
              'words_note': note}
    (out / 'notes.md').write_text(notes_text(result, lang), encoding='utf-8')
    result['files'] = ['notes.md', 'analysis.json'] + files
    (out / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result
