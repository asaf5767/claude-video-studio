"""Prepare a project's uploaded materials for editing, without touching the originals.

    python scripts/prepare_media.py projects/<id> [--max-edge 1920]

Every video becomes an H.264 yuv420p SDR BT.709 mp4 at a constant frame rate (its own rate,
from matte.native_fps) with AAC 48 kHz audio, its long edge at most --max-edge: iPhone HEVC,
.mov and HLG/PQ HDR included (HDR is tone-mapped with matte.py's HDR_TO_SDR, the conversion
that kept the owner's skin from going red; every output is tagged bt709 so Chromium never
tone-maps it again). Audio becomes 48 kHz stereo wav; images become jpg (png keeps alpha).

Outputs go to work/media/<id>-<sha8>.<ext> (ASCII names, safe in HTML and on every OS); a
changed upload gets a new name, an unchanged one is reused, nothing is ever overwritten.
work/media/media.json lists the current items. Prints that JSON. Files that ffmpeg cannot
read are listed under "problems" instead of stopping the run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)
import matte  # noqa: E402  (HDR_TO_SDR, native_fps, ffmpeg_rate)
import tools  # noqa: E402

VIDEO = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi'}
AUDIO = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
IMAGE = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.heic', '.heif'}
FOLDERS = ('raw', 'broll', 'images', 'audio')
TAG_BY_FOLDER = {'raw': 'raw', 'broll': 'broll', 'images': 'image', 'audio': 'music'}
BT709 = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']


_sha256 = matte.sha256  # one streaming hasher for the media helpers


def _run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def _probe(path):
    out = _run([tools.resolve('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path])
    return json.loads(out.stdout)


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:40]


def _materials(project):
    """(relative path, manifest item or None) for every media file under materials/."""
    try:
        items = json.loads((project / 'materials.json').read_text(encoding='utf-8')).get('items', [])
    except (OSError, ValueError, AttributeError):
        items = []
    by_file = {i['file']: i for i in items if isinstance(i, dict) and isinstance(i.get('file'), str)}
    found = []
    for folder in FOLDERS:
        base = project / 'materials' / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            if path.is_file() and not path.name.startswith('.') and path.suffix.lower() in VIDEO | AUDIO | IMAGE:
                relative = path.relative_to(project).as_posix()
                found.append((relative, by_file.get(relative), folder))
    order = {name: n for n, name in enumerate(by_file)}
    return sorted(found, key=lambda row: (order.get(row[0], len(order)), row[0]))


def _encode(args, target):
    """Run ffmpeg into a temp file next to `target`, then move it into place."""
    fd, temp = tempfile.mkstemp(prefix='.prepare-', suffix=target.suffix, dir=target.parent)
    os.close(fd)
    try:
        _run([tools.resolve('ffmpeg'), '-nostdin', '-v', 'error', '-y', *args, temp])
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _video(source, target, video, has_audio, max_edge):
    fps, _vfr = matte.native_fps(video)
    steps = [f'fps={matte.ffmpeg_rate(fps)}']
    tone = matte.HDR_TO_SDR.get(video.get('color_transfer'))
    if tone:
        steps.append(tone)
    steps += [f"scale='if(gte(iw,ih),min(iw,{max_edge}),-2)':'if(gte(iw,ih),-2,min(ih,{max_edge}))'",
              'scale=trunc(iw/2)*2:trunc(ih/2)*2', 'setsar=1', 'format=yuv420p',
              # Frame tags win over -color_trc: without this an HLG source stays tagged HLG.
              'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709']
    args = ['-i', source, '-map', '0:v:0', '-vf', ','.join(steps), '-c:v', 'libx264', '-preset', 'medium',
            '-crf', '17', '-pix_fmt', 'yuv420p', *BT709]
    args += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'] if has_audio else ['-an']
    _encode(args + ['-movflags', '+faststart'], target)
    return fps


def _item(project, relative, entry, folder, max_edge):
    source = project / relative
    digest = _sha256(source)
    info = _probe(source)
    streams = info.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not (s.get('disposition') or {}).get('attached_pic')), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    suffix = source.suffix.lower()
    kind = 'image' if suffix in IMAGE else 'video' if video is not None else 'audio' if audio is not None else None
    if kind is None:
        raise ValueError('no audio or video stream')
    base = _slug(entry['id']) if entry and isinstance(entry.get('id'), str) and _slug(entry['id']) else \
        (_slug(source.stem) or 'file') + '-' + hashlib.sha256(relative.encode()).hexdigest()[:6]
    ext = {'video': '.mp4', 'audio': '.wav', 'image': '.png' if suffix == '.png' else '.jpg'}[kind]
    out_rel = f'work/media/{base}-{digest[:8]}{ext}'
    target = project / out_rel
    record = {'id': entry.get('id') if entry else base, 'source': relative,
              'tag': (entry or {}).get('tag') or TAG_BY_FOLDER[folder], 'note': (entry or {}).get('note', ''),
              'kind': kind, 'sha256': digest, 'output': out_rel, 'source_codec': (video or audio or {}).get('codec_name'),
              'reused': target.exists()}
    if kind == 'video':
        record['hdr'] = video.get('color_transfer') in matte.HDR_TO_SDR
        record['has_audio'] = audio is not None
        record['transcoded'] = True
        fps, _ = matte.native_fps(video)
        if not target.exists():
            fps = _video(source, target, video, audio is not None, max_edge)
        made = next(s for s in _probe(target)['streams'] if s.get('codec_type') == 'video')
        record.update(fps=matte.ffmpeg_rate(fps), width=made['width'], height=made['height'])
    elif kind == 'audio' and not target.exists():
        _encode(['-i', source, '-map', '0:a:0', '-vn', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le'], target)
    elif kind == 'image' and not target.exists():
        _encode(['-i', source, '-frames:v', '1'] + (['-q:v', '2'] if ext == '.jpg' else []), target)
    duration = (_probe(target).get('format') or {}).get('duration')
    if duration and kind != 'image':
        record['duration'] = round(float(duration), 3)
    return record


def prepare(project, max_edge=1920):
    project = Path(project)
    (project / 'work' / 'media').mkdir(parents=True, exist_ok=True)
    items, problems = [], []
    for relative, entry, folder in _materials(project):
        try:
            items.append(_item(project, relative, entry, folder, max_edge))
        except (subprocess.CalledProcessError, ValueError, KeyError, StopIteration, OSError) as error:
            detail = getattr(error, 'stderr', None) or str(error)
            problems.append({'source': relative, 'error': detail.strip()[-300:]})
    result = {'version': 1, 'items': items, 'problems': problems}
    manifest = project / 'work' / 'media' / 'media.json'
    fd, temp = tempfile.mkstemp(prefix='.media-', dir=manifest.parent)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    os.replace(temp, manifest)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path)
    parser.add_argument('--max-edge', type=int, default=1920)
    args = parser.parse_args(argv)
    if (code := jobscope.refuse(args.project)) is not None:
        return code
    if not (args.project / 'materials').is_dir():
        print(f'prepare_media: {args.project} has no materials folder', file=sys.stderr)
        return 2
    try:
        result = prepare(args.project, args.max_edge)
    except tools.ToolMissing as error:
        print(f'prepare_media: {error.name} is not installed (see SETUP.md)', file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
