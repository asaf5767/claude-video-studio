"""The studio's one way for a skill to run ffmpeg/ffprobe (RULING R51).

    python scripts/media.py ffmpeg  <ffmpeg arguments>
    python scripts/media.py ffprobe <ffprobe arguments>

The arguments are checked before the real tool runs (an argv list, never a shell):
  - only known options, each with its expected number of values and value shape; unknown
    options, -y, -protocol_whitelist, -safe, -progress, -report, -vstats*, -attach,
    -dump_attachment, -filter*_script, -pattern_type glob and "-/opt" file-loaded values are refused;
  - formats (-f) and filters only from the lists the skills use plus plain compositing ones;
    file-reading filters (movie, amovie, subtitles, sendcmd, zmq, metadata, frei0r, ladspa, ...)
    and file-naming filter options (file=, filename=, textfile=, stats_file=, psfile=,
    fontfile=, model=, ...) are refused;
  - no protocol-like token (`http:host`, `tcp://...`), `$` or backticks anywhere;
  - in a studio run (STUDIO_JOB_DIR set) every input is inside the job folder or a read-only
    asset folder (scripts/jobscope.py), every output is a NEW media file inside the job
    folder (or `-f null -`); ffprobe refuses -show_data / -show_packets.
ffmpeg always runs with -nostdin -n, and every file input gets -protocol_whitelist file and
-format_whitelist (plain media demuxers only: no playlist, concat or tee), with the checked,
resolved path.
A refusal prints {"ok": false, "code": "media.refused", "message"} and exits 2.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402
import tools  # noqa: E402

CODE = 'media.refused'


class Refused(Exception):
    pass


TIME = r'-?\d+(?:\.\d+)?(?:ms|us|s)?|\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?'
NUMBER = r'-?\d+(?:\.\d+)?'
RATE = r'\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?'
BITRATE = r'\d+(?:\.\d+)?[kKmM]?'
WORD = r'[A-Za-z0-9_.+-]{1,40}'
FLAGS = r'[+-]?[a-z_]+(?:[+-][a-z_]+)*'
CODECS = {'copy', 'libx264', 'libx265', 'h264', 'hevc', 'aac', 'libmp3lame', 'mp3', 'pcm_s16le', 'pcm_s24le',
          'pcm_f32le', 'mjpeg', 'png', 'libvpx', 'libvpx-vp9', 'libopus', 'opus', 'flac', 'prores_ks', 'qtrle',
          'libwebp', 'gif', 'apng', 'ffv1'}
FORMATS_IN = {'lavfi', 'image2', 'mp4', 'mov', 'matroska', 'webm', 'wav', 'mp3', 'aac', 'ogg', 'flac'}
FORMATS_OUT = {'null', 'mp4', 'mov', 'matroska', 'webm', 'wav', 'mp3', 'ipod', 'adts', 'image2', 'gif', 'apng', 'ogg',
               'flac', 'mjpeg'}
EXTENSIONS = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.wav', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.flac',
              '.jpg', '.jpeg', '.png', '.webp', '.gif', '.apng'}
# G2 (round 3): a fixed allow-list of filters, each with the option keys it may take and how
# many unnamed (positional) values. None of these filters reads or writes a file through any
# option, named or positional, so a value can never name a file; a key must be a plain word
# from the filter's list (no quotes, escapes or the FFmpeg 7 "/key" load-from-file form).
# drawtext, subtitles, movie, curves (psfile), sendcmd, zmq, metadata, frei0r, ladspa and every
# other filter are refused. The skills use: scale, select, showinfo, fps, tile, highpass,
# lowpass, afade, volume, adelay, amix, loudnorm, ebur128, sine, anoisesrc.
COMMON_KEYS = {'enable'}
FILTERS = {  # name: (allowed keys, max positional values)
    # sources (lavfi inputs)
    'sine': ({'frequency', 'f', 'beep_factor', 'b', 'sample_rate', 'r', 'duration', 'd', 'samples_per_frame'}, 2),
    'anoisesrc': ({'sample_rate', 'r', 'amplitude', 'a', 'duration', 'd', 'color', 'colour', 'c', 'seed', 's',
                   'nb_samples', 'n'}, 2),
    'anullsrc': ({'channel_layout', 'cl', 'sample_rate', 'r', 'nb_samples', 'n', 'duration', 'd'}, 2),
    'color': ({'color', 'c', 'size', 's', 'rate', 'r', 'duration', 'd', 'sar'}, 2),
    'nullsrc': ({'size', 's', 'rate', 'r', 'duration', 'd', 'sar'}, 1),
    'testsrc': ({'size', 's', 'rate', 'r', 'duration', 'd', 'sar'}, 1),
    'testsrc2': ({'size', 's', 'rate', 'r', 'duration', 'd', 'sar'}, 1),
    # video
    'scale': ({'w', 'h', 'width', 'height', 'flags', 'force_original_aspect_ratio', 'force_divisible_by',
               'in_color_matrix', 'out_color_matrix', 'in_range', 'out_range'}, 2),
    'crop': ({'w', 'h', 'x', 'y', 'out_w', 'out_h', 'keep_aspect', 'exact'}, 4),
    'pad': ({'w', 'h', 'x', 'y', 'width', 'height', 'color'}, 5),
    'fps': ({'fps', 'round', 'start_time'}, 1),
    'format': ({'pix_fmts'}, 1),
    'setsar': ({'sar', 'r', 'max'}, 1), 'setdar': ({'dar', 'r', 'max'}, 1),
    'setpts': ({'expr'}, 1), 'asetpts': ({'expr'}, 1),
    'trim': ({'start', 'end', 'duration', 'start_frame', 'end_frame', 'start_pts', 'end_pts'}, 2),
    'atrim': ({'start', 'end', 'duration', 'start_sample', 'end_sample', 'start_pts', 'end_pts'}, 2),
    'overlay': ({'x', 'y', 'format', 'shortest', 'eof_action', 'eval', 'repeatlast', 'alpha'}, 2),
    'concat': ({'n', 'v', 'a'}, 0),
    'split': (set(), 1), 'asplit': (set(), 1),
    'fade': ({'type', 't', 'start_frame', 's', 'nb_frames', 'n', 'alpha', 'start_time', 'st', 'duration', 'd',
              'color', 'c'}, 3),
    'select': ({'expr', 'e', 'outputs', 'n'}, 1), 'aselect': ({'expr', 'e', 'outputs', 'n'}, 1),
    'showinfo': ({'checksum'}, 0),
    'tile': ({'layout', 'nb_frames', 'margin', 'padding', 'color', 'overlap', 'init_padding'}, 1),
    'hflip': (set(), 0), 'vflip': (set(), 0), 'transpose': ({'dir', 'passthrough'}, 1),
    'colorkey': ({'color', 'similarity', 'blend'}, 3), 'chromakey': ({'color', 'similarity', 'blend', 'yuv'}, 3),
    'alphamerge': (set(), 0), 'alphaextract': (set(), 0), 'premultiply': ({'inplace'}, 0),
    'unpremultiply': ({'inplace'}, 0),
    'boxblur': ({'luma_radius', 'lr', 'luma_power', 'lp'}, 2), 'gblur': ({'sigma', 'steps', 'sigmaV'}, 0),
    'eq': ({'contrast', 'brightness', 'saturation', 'gamma', 'eval'}, 0), 'hue': ({'h', 's', 'b'}, 0),
    'setparams': ({'field_mode', 'range', 'color_primaries', 'color_trc', 'colorspace'}, 0),
    'zscale': ({'w', 'h', 'width', 'height', 'filter', 'f', 'dither', 'd', 'range', 'r', 'primaries', 'p',
                'transfer', 't', 'matrix', 'm', 'rangein', 'rin', 'primariesin', 'pin', 'transferin', 'tin',
                'matrixin', 'min', 'npl'}, 0),
    'tonemap': ({'tonemap', 'param', 'desat', 'peak'}, 1),
    'tpad': ({'start', 'stop', 'start_mode', 'stop_mode', 'start_duration', 'stop_duration', 'color'}, 0),
    'xfade': ({'transition', 'duration', 'offset'}, 0),
    'hstack': ({'inputs', 'shortest'}, 0), 'vstack': ({'inputs', 'shortest'}, 0),
    'null': (set(), 0), 'anull': (set(), 0), 'copy': (set(), 0),
    'unsharp': ({'lx', 'ly', 'la'}, 3), 'zoompan': ({'zoom', 'z', 'x', 'y', 'd', 's', 'fps'}, 0),
    # audio
    'afade': ({'type', 't', 'start_sample', 'ss', 'nb_samples', 'ns', 'start_time', 'st', 'duration', 'd',
               'curve', 'c'}, 0),
    'adelay': ({'delays', 'all'}, 1), 'amix': ({'inputs', 'duration', 'dropout_transition', 'weights', 'normalize'}, 0),
    'amerge': ({'inputs'}, 0), 'volume': ({'volume', 'precision', 'eval'}, 1),
    'loudnorm': ({'I', 'i', 'LRA', 'lra', 'TP', 'tp', 'measured_I', 'measured_LRA', 'measured_TP',
                  'measured_thresh', 'offset', 'linear', 'dual_mono', 'print_format'}, 0),
    'ebur128': ({'peak', 'dualmono', 'gauge', 'scale', 'framelog', 'target'}, 0),
    'highpass': ({'frequency', 'f', 'width_type', 't', 'width', 'w', 'poles', 'p', 'mix', 'm'}, 0),
    'lowpass': ({'frequency', 'f', 'width_type', 't', 'width', 'w', 'poles', 'p', 'mix', 'm'}, 0),
    'aresample': (set(), 1), 'aformat': ({'sample_fmts', 'f', 'sample_rates', 'r', 'channel_layouts', 'cl'}, 0),
    'apad': ({'pad_len', 'whole_len', 'pad_dur', 'whole_dur'}, 0),
    'acrossfade': ({'nb_samples', 'ns', 'duration', 'd', 'overlap', 'o', 'curve1', 'c1', 'curve2', 'c2'}, 0),
    'dynaudnorm': ({'framelen', 'f', 'gausssize', 'g', 'peak', 'p', 'maxgain', 'm'}, 0),
    'acompressor': ({'threshold', 'ratio', 'attack', 'release', 'makeup', 'knee', 'mix'}, 0),
    'sidechaincompress': ({'threshold', 'ratio', 'attack', 'release', 'makeup', 'knee', 'mix'}, 0),
    'alimiter': ({'limit', 'attack', 'release', 'level_in', 'level_out'}, 0),
    'equalizer': ({'frequency', 'f', 'width_type', 't', 'width', 'w', 'gain', 'g'}, 0),
    'silencedetect': ({'noise', 'n', 'duration', 'd'}, 0), 'volumedetect': (set(), 0),
}
SOURCES = {'sine', 'anoisesrc', 'anullsrc', 'color', 'nullsrc', 'testsrc', 'testsrc2'}
KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
NAME = re.compile(r'[a-z0-9_]+')
# G3: inputs are plain media files by name AND by content: ffmpeg/ffprobe may only pick one of
# these demuxers (no hls, concat, tee, data, ...), so a playlist renamed to .mp4 is refused too.
INPUT_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.wav', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.flac',
                    '.jpg', '.jpeg', '.png', '.webp', '.gif'}
FORMAT_WHITELIST = 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,wav,mp3,aac,ogg,flac,image2,png_pipe,jpeg_pipe,webp_pipe,gif'
SAFE_INPUT = ['-protocol_whitelist', 'file', '-format_whitelist', FORMAT_WHITELIST]
SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.\-]+:')
SPEC = re.compile(r'(?:[vasdt](?::\d+)?|\d+(?::\d+)?)')
REFUSED = {'-y', '-protocol_whitelist', '-protocol_blacklist', '-safe', '-progress', '-report', '-vstats',
           '-vstats_file', '-vstats_version', '-dump_attachment', '-attach', '-filter_script', '-filter_complex_script',
           '-passlogfile', '-sdp_file', '-stats_enc_pre', '-stats_enc_post', '-stats_mux_pre', '-show_data',
           '-show_packets', '-show_data_hash', '-dump'}

# ffmpeg: option -> (value pattern or a kind) ; None = no value
FFMPEG = {
    '-nostdin': None, '-hide_banner': None, '-n': None, '-stats': None, '-nostats': None, '-an': None, '-vn': None,
    '-sn': None, '-dn': None, '-shortest': None, '-copyts': None, '-accurate_seek': None,
    '-v': r'(?:quiet|panic|fatal|error|warning|info|verbose)', '-loglevel': r'(?:quiet|panic|fatal|error|warning|info|verbose)',
    '-i': 'input', '-f': 'format', '-ss': TIME, '-t': TIME, '-to': TIME, '-sseof': TIME, '-itsoffset': TIME,
    '-r': RATE, '-framerate': RATE, '-frames': r'\d+', '-vframes': r'\d+', '-aframes': r'\d+',
    '-vf': 'graph', '-af': 'graph', '-filter': 'graph', '-filter_complex': 'graph', '-lavfi': 'graph',
    '-map': r'-?(?:\[[A-Za-z0-9_]+\]|\d+(?::[vasdt])?(?::\d+)?\??)',
    '-c': 'codec', '-codec': 'codec', '-vcodec': 'codec', '-acodec': 'codec',
    '-preset': WORD, '-tune': WORD, '-crf': NUMBER, '-b': BITRATE, '-maxrate': BITRATE, '-minrate': BITRATE,
    '-bufsize': BITRATE, '-pix_fmt': r'[a-z0-9]+', '-color_primaries': r'[a-z0-9-]+', '-color_trc': r'[a-z0-9-]+',
    '-colorspace': r'[a-z0-9-]+', '-color_range': r'[a-z0-9-]+', '-ar': r'\d+', '-ac': r'\d+', '-movflags': FLAGS,
    '-q': NUMBER, '-qscale': NUMBER, '-s': r'\d+x\d+', '-aspect': r'\d+(?:[:/]\d+)?(?:\.\d+)?',
    '-loop': r'-?\d+', '-stream_loop': r'-?\d+', '-g': NUMBER, '-keyint_min': NUMBER, '-sc_threshold': NUMBER,
    '-threads': r'\d+', '-start_number': r'\d+', '-level': r'[\d.]+', '-profile': WORD,
    '-fps_mode': r'(?:passthrough|cfr|vfr|drop|auto|-?\d)', '-vsync': r'(?:passthrough|cfr|vfr|drop|auto|-?\d)',
    '-update': r'[01]', '-tag': r'[A-Za-z0-9]{4}', '-fflags': FLAGS, '-map_metadata': r'-1|\d+',
    '-map_chapters': r'-1|\d+', '-pattern_type': r'(?:sequence|none)', '-disposition': FLAGS, '-strict': WORD,
    '-metadata': r'[A-Za-z_]{1,30}=[^`$\r\n]{0,200}',
}
WITH_SPEC = {'-c', '-codec', '-b', '-q', '-qscale', '-frames', '-filter', '-profile', '-tag', '-metadata',
             '-disposition', '-pix_fmt', '-ar', '-ac'}
FFPROBE = {
    '-hide_banner': None, '-show_streams': None, '-show_format': None, '-show_frames': None, '-count_frames': None,
    '-count_packets': None, '-show_chapters': None, '-show_programs': None, '-pretty': None, '-show_error': None,
    '-v': r'(?:quiet|panic|fatal|error|warning|info|verbose)', '-loglevel': r'(?:quiet|panic|fatal|error|warning|info|verbose)',
    '-show_entries': r'[\w,:=|]+', '-of': r'(?:json|csv|flat|ini|xml|default|compact)(?:=[\w:=]+)?',
    '-print_format': r'(?:json|csv|flat|ini|xml|default|compact)(?:=[\w:=]+)?', '-select_streams': r'[vasdt](?::\d+)?|\d+',
    '-read_intervals': r'[\d%+:.,#-]+', '-i': 'input',
}


def _plain_token(token):
    if '$' in token or '`' in token or '\n' in token or '\r' in token:
        raise Refused(f'{token!r}: "$", backticks and line breaks are not allowed')


def _top_level(text, separator):
    """Split `text` at `separator` outside single quotes and backslash escapes (the way an
    ffmpeg filtergraph is split); brackets (pad labels) are kept whole."""
    parts, current, quote, depth, i = [], '', False, 0, 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            current += text[i:i + 2]
            i += 2
            continue
        if ch == "'":
            quote = not quote
        elif not quote and ch == '[':
            depth += 1
        elif not quote and ch == ']':
            depth -= 1
        if not quote and depth == 0 and ch == separator:
            parts.append(current)
            current = ''
        else:
            current += ch
        i += 1
    if quote or depth:
        raise Refused(f'{text!r}: unbalanced quotes or brackets in a filter graph')
    parts.append(current)
    return parts


def check_filter(item, sources_only=False):
    body = re.sub(r'^\s*(?:\[[A-Za-z0-9_:.]+\]\s*)*', '', item)
    body = re.sub(r'(?:\s*\[[A-Za-z0-9_]+\])*\s*$', '', body)
    name, _, args = body.partition('=')
    name = name.strip()
    if '@' in name:
        name, _, instance = name.partition('@')
        if not KEY.fullmatch(instance):
            raise Refused(f'{item!r}: a filter instance name must be a plain word')
    if not NAME.fullmatch(name):
        raise Refused(f'{item!r}: a filter name must be a plain word')
    if name not in FILTERS or (sources_only and name not in SOURCES):
        raise Refused(f'filter {name!r} is not available here')
    keys, positional_max = FILTERS[name]
    positional = 0
    for arg in (_top_level(args, ':') if args else []):
        pieces = _top_level(arg, '=')
        if len(pieces) > 1:
            key = pieces[0]
            if not KEY.fullmatch(key):  # catches "/key" (load from file) and quoting tricks
                raise Refused(f'{item!r}: option {key!r} is not a plain option name')
            if key not in keys and key not in COMMON_KEYS:
                raise Refused(f'{item!r}: option {key!r} is not available for {name}')
        else:
            positional += 1
            if positional > positional_max:
                raise Refused(f'{item!r}: too many unnamed values for {name}')
    return name


def check_graph(graph, sources_only=False):
    _plain_token(graph)
    if '\\' in graph:  # no escapes at all: ffmpeg unescapes twice, a checker should not guess
        raise Refused(f'{graph!r}: backslash escapes are not allowed in a filter graph')
    for chain in _top_level(graph, ';'):
        for item in _top_level(chain, ','):
            if not item.strip():
                raise Refused(f'{graph!r}: an empty filter is not allowed')
            check_filter(item, sources_only)


def _path(token):
    _plain_token(token)
    if token.startswith('-') or SCHEME.match(token) or token.startswith(('\\\\', '//')) or '|' in token:
        raise Refused(f'{token!r}: only plain local file paths are allowed')


def _use(token):
    """G11: the path ffmpeg gets is the one that was checked: resolved, in a studio run."""
    return str(Path(token).resolve()) if jobscope.active() else token


def check_input(token, fmt):
    """The input to pass on (a lavfi graph, or the checked, resolved file path)."""
    if fmt == 'lavfi':
        check_graph(token)
        return token
    _path(token)
    if Path(token).suffix.lower() not in INPUT_EXTENSIONS:
        raise Refused(f'{token!r}: an input must be a media file ({", ".join(sorted(INPUT_EXTENSIONS))})')
    if '%' in token:
        jobscope.confine(str(Path(token).parent), exists=True, read=True)
        jobscope.confine(token, read=True)
    else:
        jobscope.confine(token, exists=True, read=True)
    return _use(token)


def check_output(token, fmt):
    """The output to pass on ("-" for -f null, or the checked, resolved file path)."""
    if token == '-':
        if fmt != 'null':
            raise Refused('only "-f null -" may write to "-"')
        return token
    _path(token)
    if Path(token).suffix.lower() not in EXTENSIONS:
        raise Refused(f'{token!r}: the output must be a media file ({", ".join(sorted(EXTENSIONS))})')
    if '%' in token:
        jobscope.confine(str(Path(token).parent), exists=True)
        jobscope.confine(token, write=True)
    else:
        jobscope.confine(token, new=True, write=True)
    return _use(token)


def _option(token, table):
    """(base, spec) for an option token, or (None, None) when it is not an option."""
    if not token.startswith('-') or token == '-' or re.fullmatch(r'-\d+(?:\.\d+)?', token):
        return None, None
    if token.startswith('-/'):
        raise Refused(f'{token}: file-loaded option values are not allowed')
    base, _, spec = token.partition(':')
    if token in REFUSED or base in REFUSED:
        raise Refused(f'{token} is not allowed')
    if base not in table:
        raise Refused(f'{token} is not available here')
    if spec and (base not in WITH_SPEC or not SPEC.fullmatch(spec)):
        raise Refused(f'{token}: that stream specifier is not available here')
    return base, spec


def ffmpeg_args(args):
    """The checked argv (without the program) for ffmpeg, or raise Refused/JobScopeError."""
    out, fmt, i, outputs = ['-nostdin', '-n'], None, 0, 0
    while i < len(args):
        token = args[i]
        _plain_token(token)
        base, _ = _option(token, FFMPEG)
        if base is None:
            out.append(check_output(token, fmt))
            outputs += 1
            fmt = None
            i += 1
            continue
        kind = FFMPEG[base]
        if kind is None:
            if base not in ('-nostdin', '-n'):
                out.append(token)
            i += 1
            continue
        if i + 1 >= len(args):
            raise Refused(f'{token} needs a value')
        value = args[i + 1]
        _plain_token(value)
        if kind == 'input':
            if value == '-':
                raise Refused('reading from standard input is not allowed')
            used = check_input(value, fmt)
            if fmt != 'lavfi':
                out += SAFE_INPUT
            out += [token, used]
            fmt = None
        elif kind == 'format':
            if value not in FORMATS_IN | FORMATS_OUT:
                raise Refused(f'-f {value} is not available here')
            fmt = value
            out += [token, value]
        elif kind == 'graph':
            check_graph(value)
            out += [token, value]
        elif kind == 'codec':
            if value not in CODECS:
                raise Refused(f'codec {value!r} is not available here')
            out += [token, value]
        else:
            if not re.fullmatch(kind, value):
                raise Refused(f'{token} {value!r} is not an allowed value')
            out += [token, value]
        i += 2
    if outputs == 0:
        raise Refused('ffmpeg needs an output file (or "-f null -")')
    return out


def ffprobe_args(args):
    out, i, inputs = list(SAFE_INPUT), 0, 0
    while i < len(args):
        token = args[i]
        _plain_token(token)
        base, _ = _option(token, FFPROBE)
        if base is None:
            out.append(check_input(token, None))
            inputs += 1
            i += 1
            continue
        kind = FFPROBE[base]
        if kind is None:
            out.append(token)
            i += 1
            continue
        if i + 1 >= len(args):
            raise Refused(f'{token} needs a value')
        value = args[i + 1]
        _plain_token(value)
        if kind == 'input':
            value = check_input(value, None)
            inputs += 1
        elif not re.fullmatch(kind, value):
            raise Refused(f'{token} {value!r} is not an allowed value')
        out += [token, value]
        i += 2
    if inputs != 1:
        raise Refused('ffprobe needs exactly one input file')
    return out


def checked(argv):
    """[program, *checked args] for `media.py <ffmpeg|ffprobe> ...`."""
    if not argv or argv[0] not in ('ffmpeg', 'ffprobe'):
        raise Refused('use: python scripts/media.py ffmpeg|ffprobe <arguments>')
    return [argv[0], *(ffmpeg_args if argv[0] == 'ffmpeg' else ffprobe_args)(argv[1:])]


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    argv = sys.argv[1:] if argv is None else argv
    try:
        program, *args = checked(argv)
    except Refused as error:
        print(json.dumps({'ok': False, 'code': CODE, 'message': str(error)}, ensure_ascii=False))
        return 2
    except jobscope.JobScopeError as error:
        print(json.dumps({'ok': False, 'code': jobscope.CODE, 'message': str(error)}, ensure_ascii=False))
        return 2
    try:
        binary = tools.resolve(program)
    except tools.ToolMissing:
        print(json.dumps({'ok': False, 'code': 'media.missing', 'message': f'{program} is not installed (see SETUP.md)'}))
        return 2
    return subprocess.run([binary, *args]).returncode


if __name__ == '__main__':
    raise SystemExit(main())
