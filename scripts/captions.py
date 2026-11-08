"""Caption cues from word timings: short lines, bidi-safe HTML, ready for a composition.

    python scripts/captions.py <words.json> <out.json> [--lang he|en] [--mode line|word]
                               [--max-chars 28] [--lines 1|2] [--duration SECONDS]

<words.json> is a list of {"text","startMs","endMs"} (scripts/transcribe.py, or the cut's
cut.words.json). Line mode groups words into cues of one line (or two with --lines 2) of at most
--max-chars characters, breaking at a sentence end or a pause over 0.6 s. Word mode shows one
word at a time, pairing two quick short words so nothing flashes for 2-4 frames. Edge
punctuation is dropped from what is shown ("שניות." -> "שניות"); inner dots stay ("SKILL.md").

Every cue carries "html" built for the video's direction: in a Hebrew video each run of Latin
words or numbers is wrapped in ONE <bdi dir="ltr"> isolate (a Hebrew prefix such as "ה-" or
"ב־" stays outside it), so "AI חוסך 38 שניות" can never reorder; in an English video Hebrew
runs get <bdi dir="rtl">. Put the html inside an element with dir="rtl" (Hebrew) or dir="ltr"
(English) -- never dir on <html>. Times are seconds. --max-chars may be lowered, never raised
above 28 (the studio's caption line limit).

Never overwrites <out.json> by default (captions.exists). --retry replaces it only while
nothing from that version folder is registered in the studio; once it is, make a new version
(new_version.py --from vNN) and write the captions there.
"""
import argparse
import html
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import new_version  # noqa: E402

HEBREW = re.compile('[א-ת]')
LATIN_OR_DIGIT = re.compile(r'[A-Za-z0-9]')
PREFIX = re.compile('^([א-ת]{1,3}[-־])(.+)$')
EDGE = '.,;:"\'“”„«»()[]{}'
SENTENCE_END = re.compile(r'[.?!…]["\'”»)]*$')
LEAD, HOLD, PAUSE, PAIR_GAP, PAIR_LETTERS = 0.03, 0.5, 0.6, 0.24, 13
MAX_CHARS = 28  # the longest caption line the studio allows


def display(text):
    return text.strip().strip(EDGE).strip()


def _foreign(token, lang):
    if lang == 'he':
        return bool(LATIN_OR_DIGIT.search(token)) and not HEBREW.search(token)
    return bool(HEBREW.search(token)) and not LATIN_OR_DIGIT.search(token)


def line_html(tokens, lang):
    """HTML for one line of display tokens, isolating the runs that read the other way."""
    direction = 'ltr' if lang == 'he' else 'rtl'
    out, run, pending = [], [], ''

    def flush():
        nonlocal pending
        if run:
            out.append(pending + f'<bdi dir="{direction}">' + ' '.join(run) + '</bdi>')
            run.clear()
            pending = ''

    for token in tokens:
        prefix = PREFIX.match(token) if lang == 'he' else None
        if prefix and _foreign(prefix.group(2), lang):
            flush()
            pending = html.escape(prefix.group(1), quote=False)
            run.append(html.escape(prefix.group(2), quote=False))
        elif _foreign(token, lang):
            run.append(html.escape(token, quote=False))
        else:
            flush()
            out.append(html.escape(token, quote=False))
    flush()
    return ' '.join(out)


def _groups_line(words, max_chars, lines):
    cues, current, current_lines = [], [], [[]]
    for i, word in enumerate(words):
        text = word['show']
        if current:
            previous = words[i - 1]
            ends = SENTENCE_END.search(previous['text']) or word['start'] - previous['end'] > PAUSE
            line = current_lines[-1]
            fits = len(' '.join([w['show'] for w in line] + [text])) <= max_chars
            if ends or (not fits and len(current_lines) >= lines):
                cues.append((current, current_lines))
                current, current_lines = [], [[]]
            elif not fits:
                current_lines.append([])
        current.append(word)
        current_lines[-1].append(word)
    if current:
        cues.append((current, current_lines))
    return cues


def _groups_word(words):
    cues, i = [], 0
    while i < len(words):
        group = [words[i]]
        if i + 1 < len(words):
            a, b = words[i], words[i + 1]
            if (b['start'] - a['start'] <= PAIR_GAP and not SENTENCE_END.search(a['text']) and
                    len(a['show'].replace(' ', '')) + len(b['show'].replace(' ', '')) <= PAIR_LETTERS):
                group.append(b)
        cues.append((group, [group]))
        i += len(group)
    return cues


def build(words, lang='he', mode='line', max_chars=MAX_CHARS, lines=1, duration=None):
    if not 1 <= max_chars <= MAX_CHARS:
        raise ValueError(f'max_chars must be 1-{MAX_CHARS}')
    clean = []
    for word in words:
        show = display(str(word.get('text', '')))
        if show:
            clean.append({'text': str(word['text']), 'show': show,
                          'start': word['startMs'] / 1000, 'end': word['endMs'] / 1000})
    groups = _groups_word(clean) if mode == 'word' else _groups_line(clean, max_chars, lines)
    cues = []
    for n, (group, rows) in enumerate(groups):
        start = max(group[0]['start'] - LEAD, cues[-1]['end'] if cues else 0.0)
        end = group[-1]['end'] + HOLD
        if n + 1 < len(groups):
            end = min(end, max(group[-1]['end'], groups[n + 1][0][0]['start'] - LEAD))
        if duration is not None:
            end = min(end, duration)
        text_lines = [' '.join(w['show'] for w in row) for row in rows]
        cues.append({
            'start': round(start, 3), 'end': round(max(end, start + 0.04), 3),
            'text': ' '.join(text_lines), 'lines': text_lines,
            'html': '<br>'.join(line_html([w['show'] for w in row], lang) for row in rows),
            'too_long': any(len(line) > max_chars for line in text_lines),
            'words': [{'text': w['show'], 'start': round(w['start'], 3), 'end': round(w['end'], 3),
                       'html': line_html([w['show']], lang)} for w in group],
        })
    return {'lang': lang, 'dir': 'rtl' if lang == 'he' else 'ltr', 'mode': mode, 'max_chars': max_chars,
            'cues': cues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('words', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--lang', choices=['he', 'en'], default='he')
    parser.add_argument('--mode', choices=['line', 'word'], default='line')
    parser.add_argument('--max-chars', type=int, default=28)
    parser.add_argument('--lines', type=int, choices=[1, 2], default=1)
    parser.add_argument('--duration', type=float, help='length of the edit in seconds: no cue ends after it')
    parser.add_argument('--retry', action='store_true',
                        help='replace <out.json> (only while nothing from its version is registered)')
    args = parser.parse_args(argv)
    if not 1 <= args.max_chars <= MAX_CHARS:
        print(f'captions.bad-request: --max-chars must be between 1 and {MAX_CHARS} (a caption line is at most '
              f'{MAX_CHARS} characters; lower values are fine)', file=sys.stderr)
        return 2
    if args.out.exists() and (not args.retry or new_version.registered(args.out.parent)):
        if new_version.registered(args.out.parent):
            version = args.out.parent
            print(f'captions.exists: this version already has {args.out.name} and the studio shows it; make a new '
                  f'version with python scripts/new_version.py "{version.parent.parent.as_posix()}" --from '
                  f'{version.name}', file=sys.stderr)
        else:
            print(f'captions.exists: this version already has {args.out.name}; nothing from it is registered yet, '
                  f'so to redo it here run the same command again with --retry', file=sys.stderr)
        return 2
    try:
        words = json.loads(args.words.read_text(encoding='utf-8'))
        result = build(words, args.lang, args.mode, args.max_chars, args.lines, args.duration)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'captions: cannot read {args.words}: {error}', file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    long_cues = sum(cue['too_long'] for cue in result['cues'])
    print(json.dumps({'cues': len(result['cues']), 'too_long': long_cues, 'out': str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
