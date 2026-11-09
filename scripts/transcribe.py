"""Local word-timed transcription with whisper.cpp + a Hebrew (ivrit.ai) or English model.

Pipeline: ffmpeg transcodes the input media to a 16 kHz mono wav in a temp dir, then
`bin/whisper/whisper-cli(.exe)` (or a `whisper-cli` found on PATH, e.g. Homebrew
`whisper-cpp` on Mac) runs with `-ojf` (full JSON output, including per-token offsets),
and `merge_tokens()` turns whisper's BPE sub-word tokens into words: a token that starts
with a literal leading space, or whose script class (Hebrew/Latin/digit) differs from the
word in progress, starts a new word; a punctuation-only token always attaches to the
preceding word; a Hebrew prefix (ו/ה/ש/ב/ל/מ/כ) tokenized separately from its stem has no
leading space and the same script class, so it is never split from the word it attaches to.

Never re-transcribes an unchanged file: refuses to overwrite an existing out.json unless
--force. A missing ffmpeg/whisper-cli/model, a failed ffmpeg/whisper-cli run, or
unreadable whisper.cpp output is a coded TranscribeError (transcribe.exists,
transcribe.no-ffmpeg, transcribe.no-engine, transcribe.model-missing, transcribe.failed)
with a plain message, never a raw traceback.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)
import tools

ROOT = Path(__file__).resolve().parents[1]

# Hebrew prefixes that attach to the following word without a space (ו/ה/ש/ב/ל/מ/כ);
# kept here only for documentation -- merge_tokens() needs no special case for them,
# since a prefix token has no leading space and the same Hebrew script class as the
# stem it attaches to, so the default continuation rule already keeps them together.
HEBREW_PREFIXES = 'והשבלמכ'

_HEBREW_RE = re.compile('[֐-׿]')
_SPECIAL_TOKEN_RE = re.compile(r'^(\[_[A-Z]+[^\]]*\]|<\|[^>]*\|>)$')

# A UTF-8 character is at most 4 bytes, so a genuine split (see ggml-org/whisper.cpp#1798:
# whisper.cpp's byte-level BPE tokenizer can emit a multi-byte Hebrew/CJK/etc. character as
# two or more adjacent tokens, each individually invalid UTF-8) never needs more than 4
# pieces to repair. More than that is treated as real corruption, not a token split.
_MAX_SPLIT_JOIN = 4


class TranscribeError(Exception):
    """A coded, user-facing transcription failure (never a raw traceback)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _classify(ch):
    if ch.isspace():
        return 'space'
    if _HEBREW_RE.match(ch):
        return 'he'
    if ch.isdigit():
        return 'digit'
    if ch.isalpha():
        return 'latin'
    return 'punct'


def _is_special(text):
    return bool(_SPECIAL_TOKEN_RE.match(text.strip()))


def _parse_timestamp(value):
    """'HH:MM:SS,mmm' -> ms, whisper.cpp's SRT-style 'timestamps' fields."""
    match = re.match(r'^(\d+):(\d\d):(\d\d)[,.](\d+)$', value)
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def _token_span_ms(token):
    """Best-effort (startMs, endMs) for one whisper.cpp token, or (None, None)."""
    offsets = token.get('offsets')
    if isinstance(offsets, dict) and 'from' in offsets and 'to' in offsets:
        return int(offsets['from']), int(offsets['to'])
    timestamps = token.get('timestamps')
    if isinstance(timestamps, dict) and 'from' in timestamps and 'to' in timestamps:
        start = _parse_timestamp(timestamps['from'])
        end = _parse_timestamp(timestamps['to'])
        if start is not None and end is not None:
            return start, end
    t_dtw = token.get('t_dtw')
    if isinstance(t_dtw, (int, float)) and t_dtw >= 0:
        ms = int(t_dtw * 10)
        return ms, ms
    return None, None


def merge_tokens(tokens):
    """Merge whisper.cpp sub-word tokens into words: [{"text","startMs","endMs"}, ...].

    A token starting with a literal leading space, or whose script class (Hebrew/Latin
    /digit) differs from the word being built, starts a new word. A punctuation-only
    token (","، ".", etc.) always attaches to the preceding word instead. Anything else
    (no leading space, same script class -- including a Hebrew prefix glued to its stem)
    continues the current word. Special/non-text tokens (e.g. "[_TT_180]") are skipped.
    """
    words = []
    cur_text = ''
    cur_kind = None
    cur_start = None
    cur_end = None

    def flush():
        nonlocal cur_text, cur_kind, cur_start, cur_end
        if cur_text:
            words.append({'text': cur_text, 'startMs': cur_start, 'endMs': cur_end})
        cur_text, cur_kind, cur_start, cur_end = '', None, None, None

    for token in tokens:
        raw = token.get('text', '')
        stripped = raw.strip()
        if not stripped or _is_special(stripped):
            continue
        start_ms, end_ms = _token_span_ms(token)
        first_kind = _classify(stripped[0])
        is_punct = all(_classify(ch) == 'punct' for ch in stripped)

        if is_punct and cur_text:
            cur_text += stripped
            if end_ms is not None:
                cur_end = end_ms
            continue

        has_leading_space = raw[:1] == ' '
        starts_new = not cur_text or has_leading_space or first_kind != cur_kind
        if starts_new:
            flush()
            cur_text, cur_kind, cur_start, cur_end = stripped, first_kind, start_ms, end_ms
        else:
            cur_text += stripped
            cur_kind = first_kind
            if end_ms is not None:
                cur_end = end_ms
    flush()
    return words


def _flatten_whisper_tokens(doc):
    """Flatten every segment's token list from a whisper.cpp `-ojf` document, in order."""
    tokens = []
    for segment in doc.get('transcription', []):
        tokens.extend(segment.get('tokens', []))
    return tokens


# Hebrew's UTF-8 lead bytes (U+05D0-U+05FF encodes as 2 bytes starting 0xD6 or 0xD7).
# Used only to recognize the *second* disguise below (never to validate real Hebrew text).
_HEBREW_LEAD_BYTES = (0xD6, 0xD7)
_HEBREW_RANGE = (0x0590, 0x05FF)


def _byte_value(ch, is_first, continuing):
    """If `ch` stands for a raw byte that needs UTF-8 reassembly, its byte value --
    whisper.cpp's -ojf writer can split one multi-byte character's bytes across two or
    more adjacent tokens (ggml-org/whisper.cpp#1798), and can disguise a split byte two
    ways: (1) `_read_whisper_json` preserves a genuinely invalid raw byte losslessly as
    a surrogate-escape codepoint (0xDC80-0xDCFF), regardless of position; or (2) a byte
    that otherwise decodes as "valid" text is smuggled through as the literal Unicode
    codepoint matching its numeric value (U+0080-U+00FF). Case (2) starting a run
    (`is_first`, not `continuing`) is NOT decided here -- `_repair_tokens` only reaches
    this branch for a Hebrew lead byte (0xD6/0xD7) after `_validated_disguised_lead` has
    already confirmed it's genuinely followed by a matching continuation byte that
    decodes to an actual Hebrew character; an unvalidated D6/D7 is ordinary text (a
    literal "×"/"Ö") and must never reach here. `continuing` (we already know we're
    extending a confirmed incomplete sequence) accepts any UTF-8 continuation byte,
    0x80-0xBF, as this token's own first character too."""
    code = ord(ch)
    if 0xDC80 <= code <= 0xDCFF:
        return code - 0xDC00
    if is_first:
        if code in _HEBREW_LEAD_BYTES:
            return code
        if continuing and 0x80 <= code <= 0xBF:
            return code
        return None
    return code if 0x80 <= code <= 0xBF else None


def _validated_disguised_lead(body, next_token_text):
    """A literal U+00D6 ('Ö') or U+00D7 ('×') numerically matches a disguised Hebrew
    UTF-8 lead byte -- but it's also just an ordinary character in real text, and
    accepting it on sight corrupted it (review round 3: '3×4', ' Österreich', '3'+' ×'+
    ' 4'). Only treat `body[0]` as a disguised lead byte when the very next code point --
    `body[1]` if `body` has more characters, else `next_token_text[0]` if `body` is just
    the lead byte alone and the next token doesn't start a new word -- is a UTF-8
    continuation byte (U+0080-U+00BF) that, combined with it, decodes to an actual
    Hebrew character (U+0590-U+05FF). Otherwise `body[0]` must be left untouched as
    ordinary text; `_repair_tokens` never calls `_leading_byte_run` on it."""
    if not body or ord(body[0]) not in _HEBREW_LEAD_BYTES:
        return False
    if len(body) > 1:
        cont_ch = body[1]
    elif next_token_text:
        cont_ch = next_token_text[0]
    else:
        return False
    cont = ord(cont_ch)
    if not (0x80 <= cont <= 0xBF):
        return False
    try:
        decoded = bytes([ord(body[0]), cont]).decode('utf-8')
    except UnicodeDecodeError:
        return False
    return _HEBREW_RANGE[0] <= ord(decoded) <= _HEBREW_RANGE[1]


def _leading_byte_run(text, continuing=False, max_len=_MAX_SPLIT_JOIN):
    """(raw_bytes, remainder): the leading run of `text`'s characters that stand for raw
    bytes (see `_byte_value`), and whatever ordinary text follows. Never more than
    `max_len` bytes -- no UTF-8 character needs more than 4."""
    raw = bytearray()
    for index, ch in enumerate(text):
        value = _byte_value(ch, index == 0, continuing)
        if value is None or len(raw) >= max_len:
            break
        raw.append(value)
    return bytes(raw), text[len(raw):]


def _starts_new_word_boundary(token):
    """True if this token's own text begins a new word (a literal leading space) -- a
    byte-level repair must never extend across this, even if the bytes accumulated so
    far are still a plausibly-completable incomplete sequence (ggml-org/whisper.cpp#1798
    review finding (a)): merging into the next word would silently corrupt it."""
    return token.get('text', '')[:1] == ' '


def _repair_tokens(tokens):
    """Reassemble a token whose `text` starts with a partial multi-byte UTF-8 sequence
    (see `_byte_value`) by pulling in only as many further tokens as are needed to
    complete it -- never across a word boundary (`_starts_new_word_boundary`), never more
    than `_MAX_SPLIT_JOIN` bytes, and never a token that itself contributes no further
    bytes. Each repaired token's span runs from the first piece's start to the last
    piece's end. A byte run that still can't be completed (a lone invalid byte, or one
    blocked by a word boundary) is `errors='replace'`-decoded and the U+FFFD dropped --
    the word's timing is kept, nothing merges into a neighbour, and this never raises:
    per controller ruling R32, one bad token must not abort a whole transcription. Only
    `_read_whisper_json` failing to parse the file at all raises (transcribe.failed)."""
    repaired = []
    i, n = 0, len(tokens)
    while i < n:
        text = tokens[i].get('text', '')
        leading_space = ' ' if text[:1] == ' ' else ''
        body = text[1:] if leading_space else text

        # A disguised Hebrew lead byte (0xD6/0xD7) only ever starts a byte run once
        # validated against what actually follows it -- see _validated_disguised_lead.
        # A surrogate-escape codepoint (a genuinely invalid raw byte) needs no such
        # lookahead gate; it's unambiguous regardless of position.
        disguised_ok = True
        if body and ord(body[0]) in _HEBREW_LEAD_BYTES:
            next_token_text = ''
            if i + 1 < n and not _starts_new_word_boundary(tokens[i + 1]):
                next_token_text = tokens[i + 1].get('text', '')
            disguised_ok = _validated_disguised_lead(body, next_token_text)

        byte_prefix, remainder = _leading_byte_run(body) if disguised_ok else (b'', body)
        if not byte_prefix:
            repaired.append(dict(tokens[i]))
            i += 1
            continue

        raw = bytearray(byte_prefix)
        end = i
        tail_remainder = remainder
        while True:
            try:
                resolved = bytes(raw).decode('utf-8')
                break
            except UnicodeDecodeError as error:
                incomplete_at_tail = error.reason == 'unexpected end of data' and error.end == len(raw)
                next_idx = end + 1
                extendable = (incomplete_at_tail and len(raw) < _MAX_SPLIT_JOIN
                              and next_idx < n and not _starts_new_word_boundary(tokens[next_idx]))
                next_prefix = next_remainder = None
                if extendable:
                    next_prefix, next_remainder = _leading_byte_run(
                        tokens[next_idx].get('text', ''), continuing=True, max_len=_MAX_SPLIT_JOIN - len(raw))
                if not extendable or not next_prefix:
                    resolved = bytes(raw).decode('utf-8', errors='replace').replace('�', '')
                    break
                raw.extend(next_prefix)
                end, tail_remainder = next_idx, next_remainder

        merged = dict(tokens[i])
        merged['text'] = leading_space + resolved + tail_remainder
        if end != i:
            first_offsets = tokens[i].get('offsets') or {}
            last_offsets = tokens[end].get('offsets') or {}
            if first_offsets or last_offsets:
                merged['offsets'] = {'from': first_offsets.get('from'), 'to': last_offsets.get('to', first_offsets.get('to'))}
            first_ts = tokens[i].get('timestamps') or {}
            last_ts = tokens[end].get('timestamps') or {}
            if first_ts or last_ts:
                merged['timestamps'] = {'from': first_ts.get('from'), 'to': last_ts.get('to', first_ts.get('to'))}
        repaired.append(merged)
        i = end + 1
    return repaired


def _read_whisper_json(path):
    """Read a whisper.cpp `-ojf` output file that may contain raw invalid UTF-8 bytes
    (see `_repair_tokens`) without ever raising UnicodeDecodeError: decode with
    `errors='surrogateescape'` so every byte round-trips losslessly, then parse JSON."""
    try:
        raw = path.read_bytes()
        doc = json.loads(raw.decode('utf-8', errors='surrogateescape'))
    except (OSError, json.JSONDecodeError) as error:
        raise TranscribeError('transcribe.failed', f'Could not read whisper.cpp output: {error}')
    if not isinstance(doc, dict):
        raise TranscribeError('transcribe.failed', 'Unexpected whisper.cpp output (not a JSON object).')
    return doc


def _tail(text, lines=4):
    """The last few non-empty lines of a subprocess's stderr, for a coded error message."""
    kept = [line for line in text.strip().splitlines() if line.strip()]
    return '\n'.join(kept[-lines:])


def _studio_config():
    return json.loads((ROOT / 'studio.config.json').read_text(encoding='utf-8'))


def _whisper_binary():
    name = 'whisper-cli.exe' if os.name == 'nt' else 'whisper-cli'
    bundled = ROOT / 'bin' / 'whisper' / name
    if bundled.is_file():
        return bundled
    on_path = shutil.which('whisper-cli')
    if on_path:
        return Path(on_path)
    raise TranscribeError(
        'transcribe.no-engine',
        'Local transcription engine not found. Run setup to install whisper.cpp, or see SETUP.md.',
    )


def _model_path(language):
    try:
        rel = _studio_config()['transcription']['models'][language]
    except (KeyError, FileNotFoundError, json.JSONDecodeError):
        rel = None
    if not rel:
        raise TranscribeError(
            'transcribe.model-missing',
            f'No transcription model configured for language "{language}".',
        )
    model = ROOT / rel
    if not model.is_file():
        raise TranscribeError(
            'transcribe.model-missing',
            f'Transcription model missing: {rel}. Run setup to download it, or see SETUP.md.',
        )
    return model


def _ffmpeg_binary():
    try:
        return tools.resolve('ffmpeg')
    except tools.ToolMissing:
        raise TranscribeError('transcribe.no-ffmpeg', 'ffmpeg not found. Run setup first, or see SETUP.md.')


def _thread_count():
    return str(min(os.cpu_count() or 4, 8))


def _to_wav(media, tmp_dir):
    ffmpeg = _ffmpeg_binary()
    wav = tmp_dir / 'audio.wav'
    try:
        subprocess.run(
            [ffmpeg, '-y', '-i', str(media), '-ar', '16000', '-ac', '1', '-vn', str(wav)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        stderr = _tail(error.stderr.decode('utf-8', errors='replace')) if error.stderr else ''
        raise TranscribeError('transcribe.failed', 'ffmpeg could not read this media file.' + (' ' + stderr if stderr else ''))
    return wav


def _run_whisper(whisper_bin, model, language, wav, tmp_dir):
    out_prefix = tmp_dir / 'out'
    try:
        subprocess.run(
            [str(whisper_bin), '-m', str(model), '-l', language, '-f', str(wav),
             '-t', _thread_count(), '-ojf', '-of', str(out_prefix)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        stderr = _tail(error.stderr.decode('utf-8', errors='replace')) if error.stderr else ''
        raise TranscribeError('transcribe.failed', 'whisper-cli could not transcribe this audio.' + (' ' + stderr if stderr else ''))
    return out_prefix.with_suffix('.json')


def transcribe(media, out, language, force=False):
    """Transcribe `media` (any ffmpeg-readable file, incl. iPhone HEVC/.mov) to word-timed
    JSON at `out`. Returns the list of words. Raises TranscribeError on a missing engine
    or model, and refuses to overwrite an existing `out` unless `force`."""
    media, out = Path(media), Path(out)
    if out.exists() and not force:
        raise TranscribeError('transcribe.exists', f'{out} already exists. Use --force to overwrite.')

    whisper_bin = _whisper_binary()
    model = _model_path(language)

    tmp_dir = Path(tempfile.mkdtemp(prefix='transcribe-'))
    try:
        wav = _to_wav(media, tmp_dir)
        json_path = _run_whisper(whisper_bin, model, language, wav, tmp_dir)
        doc = _read_whisper_json(json_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    try:
        # Controller ruling R32: _repair_tokens() never raises for a byte-level decode
        # problem in one token -- a single bad byte must not abort a whole
        # transcription, so it falls back to errors='replace' internally (see its
        # docstring). This try/except is only for a structurally malformed `doc` (e.g.
        # a token that isn't a dict at all) -- genuinely unreadable/unparsable output,
        # not an ordinary split-byte repair.
        tokens = _repair_tokens(_flatten_whisper_tokens(doc))
        words = merge_tokens(tokens)
    except (KeyError, TypeError, AttributeError) as error:
        raise TranscribeError('transcribe.failed', f'Unexpected whisper.cpp output: {error}')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding='utf-8')
    return words


def main():
    if hasattr(sys.stdout, 'reconfigure'):  # Hebrew JSON on a Windows pipe/console (final review M5)
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('media', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--language', choices=['he', 'en'], required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if (code := jobscope.refuse(args.media) or jobscope.refuse(args.out, write=True)) is not None:
        raise SystemExit(code)
    try:
        words = transcribe(args.media, args.out, args.language, force=args.force)
    except TranscribeError as error:
        raise SystemExit(error.message)
    except subprocess.CalledProcessError as error:
        # Defensive fallback only: _to_wav/_run_whisper already convert their own
        # subprocess failures into a coded TranscribeError with the stderr tail.
        raise SystemExit(f'Transcription failed ({error.cmd[0] if error.cmd else "subprocess"}): run again, or see SETUP.md.')
    print(f'Wrote {len(words)} words to {args.out}')


if __name__ == '__main__':
    main()
