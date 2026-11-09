"""Server-side poster frames (JPEG) for video materials and project video artifacts.

Controller finding (T9b, real-data check): HEVC video shot on an iPhone renders BLACK in
Chrome on Windows -- both the raw-take thumbnail in the materials card and the HEVC
review/export video players. Chromium's software HEVC path on Windows can decode the
stream but not the HDR (HLG/PQ) color volume many iPhone clips carry, so it paints black
instead of refusing outright. A poster JPEG -- one frame pulled with ffmpeg and tone-mapped
down to SDR -- gives every video tile and player a real, correctly colored frame to show
immediately, independent of whether the browser can actually decode the source at all.

Generation is synchronous and time-boxed, not a 202-then-poll flow: POSTER_TIMEOUT is ONE
total budget for the whole poster (final review M1), shared by its three subprocess calls (an
ffprobe duration probe, an ffprobe color-transfer probe, then the ffmpeg frame extract) --
each call gets only the time left. The first GET with ?poster=1 for a given file blocks (up
to POSTER_TIMEOUT) while ffprobe/ffmpeg run; every later request for that same, unchanged
file is an instant disk read (see _is_current()). A per-destination-path lock (see
_lock_for()) makes sure two concurrent first requests for the same poster only ever run
ffmpeg once; the second request simply waits for the first's result. Subprocess output is
decoded as UTF-8 with replacement (Hebrew file names in ffmpeg's messages never raise on a
Windows code page), and ffmpeg runs with -v error.

HDR frames are converted with matte.HDR_TO_SDR -- the same curve prepare_media.py uses for
the edit, tuned so skin does not go red (final review M2). An iPhone photo (HEIC/HEIF) gets a
poster too: browsers other than Safari cannot show HEIC, so its tile shows this JPEG.

On any failure -- ffmpeg/ffprobe missing from PATH, a non-zero exit, a timeout on any one of
the three subprocess calls above, or a source file ffmpeg can't read at all -- ensure()
returns None rather than raising. Callers serve their own placeholder (a 404 the UI treats as
"no poster yet", never a 500) in that case.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import tools  # noqa: E402
import matte  # noqa: E402  (HDR_TO_SDR: the studio's one HDR -> SDR conversion)

POSTER_TIMEOUT = 10  # seconds for the whole poster (all three subprocess calls together)
POSTER_WIDTH = 540
# HLG (Hybrid Log-Gamma, arib-std-b67) and PQ/HDR10 (SMPTE ST 2084) are the two HDR transfer
# functions iPhone HEVC clips actually carry. Both need an explicit conversion to SDR, or skin
# tones render blown-out/red when a plain scale filter reinterprets HDR samples as SDR ones.
HDR_TRANSFERS = set(matte.HDR_TO_SDR)
# Still images that get a poster: iPhone photos, which browsers other than Safari cannot show.
STILL_EXT = {'.heic', '.heif'}

_locks_guard = threading.Lock()
_locks = {}


def _lock_for(path):
    key = str(path)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _run(args, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(args, 0)
    return subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=remaining)


def _probe_duration(ffprobe, source, deadline):
    try:
        result = _run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(source)], deadline)
        return float(json.loads(result.stdout or '{}').get('format', {}).get('duration') or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def _probe_color_transfer(ffprobe, source, deadline):
    try:
        result = _run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=color_transfer', '-of', 'json', str(source)], deadline)
        streams = json.loads(result.stdout or '{}').get('streams') or [{}]
        return streams[0].get('color_transfer') or ''
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return ''


def filter_for(transfer):
    """The -vf expression for a poster frame: scale to POSTER_WIDTH wide, and -- only when
    `transfer` names an HDR transfer function -- convert HDR to SDR first with
    matte.HDR_TO_SDR, the same conversion the edit itself gets."""
    scale = f'scale={POSTER_WIDTH}:-2'
    if transfer not in HDR_TRANSFERS:
        return scale
    return matte.HDR_TO_SDR[transfer] + ',' + scale + ',format=yuv420p'


def _stamp(path):
    stat = path.stat()
    return f'{stat.st_mtime_ns}:{stat.st_size}'


def _meta_path(dest):
    return dest.with_name(dest.name + '.src')


def _is_current(source, dest):
    meta = _meta_path(dest)
    if not dest.is_file() or not meta.is_file():
        return False
    try:
        return meta.read_text(encoding='utf-8') == _stamp(source)
    except OSError:
        return False


def _generate(source, dest):
    try:
        ffmpeg = tools.resolve('ffmpeg')
        ffprobe = tools.resolve('ffprobe')
    except tools.ToolMissing:
        return False
    deadline = time.monotonic() + POSTER_TIMEOUT
    still = source.suffix.lower() in STILL_EXT
    duration = 0.0 if still else _probe_duration(ffprobe, source, deadline)
    timestamp = min(1.0, duration * 0.1) if duration > 0 else 1.0
    transfer = _probe_color_transfer(ffprobe, source, deadline)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # ffmpeg picks its output muxer from the filename's extension -- keep .jpg on the temp
    # name too (not just a bare .tmp suffix) or it refuses the output with "Unable to choose
    # an output format".
    tmp = dest.parent / (dest.stem + '.tmp.jpg')
    try:
        seek = [] if still else ['-ss', f'{timestamp:.3f}']
        _run([ffmpeg, '-v', 'error', '-y', *seek, '-i', str(source), '-frames:v', '1',
              '-vf', filter_for(transfer), '-q:v', '4', str(tmp)], deadline)
        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise OSError('ffmpeg produced no poster')
        os.replace(tmp, dest)
        _meta_path(dest).write_text(_stamp(source), encoding='utf-8')
        return True
    except (OSError, subprocess.TimeoutExpired):
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return False


def ensure(source, cache_dir, key):
    """Return the Path to a ready poster JPEG for `source` (a video file or an iPhone photo), generating or
    regenerating it synchronously when the cached one is missing or `source` has changed
    (by mtime/size) since it was made. The poster is cached at `cache_dir`/`key`.jpg.
    Returns None -- never raises -- if a poster could not be produced, including when the
    whole poster runs past POSTER_TIMEOUT; the caller should serve its own placeholder (a
    404) in that case, never a 500."""
    dest = cache_dir / f'{key}.jpg'
    lock = _lock_for(dest)
    with lock:
        if _is_current(source, dest):
            return dest
        return dest if _generate(source, dest) else None
