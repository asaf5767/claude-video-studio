"""Write a project skill's progress file (Task 14 format) without hand-writing JSON.

    python scripts/progress.py <file> --start <skill> [--with matte]
    python scripts/progress.py <file> <key> <todo|running|done> [detail]

The studio's "Send to Claude" page polls <project or reference>/progress.json, a JSON list of
{"key", "state", "detail"?} in a fixed order per skill (STEPS). --start writes every step as
todo (call it first: the runner ignores a file older than the job). An update changes one step
and keeps the others; a step missing from the file is inserted in its canonical place. The
detail is one short line in the creator's language -- never a key, path or error dump.
Writes are atomic (temp file + os.replace), retried while the studio has the file open on
Windows. Standard library only.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)

STEPS = {
    'talking-head': ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard'],
    'faceless-reel': ['voice', 'transcribe', 'scenes', 'captions', 'sound', 'storyboard'],
    'learn-style': ['watch', 'analyze', 'card'],
}
# Optional steps a skill adds only when it needs them, and the step each one follows.
OPTIONAL = {'talking-head': {'matte': 'cut'}}
STATES = ('todo', 'running', 'done')
MAX_DETAIL = 120
RETRIES = 20


class ProgressError(Exception):
    pass


def _order(skill, extra=()):
    keys = list(STEPS[skill])
    for key in extra:
        after = OPTIONAL.get(skill, {}).get(key)
        if after is None:
            raise ProgressError(f'{key!r} is not an optional step of {skill}')
        if key not in keys:
            keys.insert(keys.index(after) + 1, key)
    return keys


def _canonical(key, keys=()):
    """The full canonical order (with optional steps) for `key`: of the skill the progress file
    already belongs to (every key it holds is in that skill's order), else of the first skill
    that has `key` -- so faceless-reel's `transcribe` lands after `voice`, not in talking-head's
    place (final review M16)."""
    orders = [order for order in (_order(skill, OPTIONAL.get(skill, {})) for skill in STEPS) if key in order]
    if not orders:
        raise ProgressError(f'unknown step {key!r}')
    return next((order for order in orders if keys and all(k in order for k in keys)), orders[0])


def _read(path):
    try:
        steps = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [s for s in steps if isinstance(s, dict) and isinstance(s.get('key'), str)] if isinstance(steps, list) else []


def _write(path, steps):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(steps, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd, temp = tempfile.mkstemp(prefix='.progress-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        for attempt in range(RETRIES):
            try:
                os.replace(temp, path)
                return
            except PermissionError:  # Windows: the studio is reading the file right now
                if attempt == RETRIES - 1:
                    raise ProgressError(f'could not write {path}: file is busy') from None
                time.sleep(0.05)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _detail(text):
    text = ' '.join(str(text).split())
    return text[:MAX_DETAIL - 1] + '…' if len(text) > MAX_DETAIL else text


def start(path, skill, extra=()):
    if skill not in STEPS:
        raise ProgressError(f'unknown skill {skill!r} (one of: {", ".join(STEPS)})')
    _write(path, [{'key': key, 'state': 'todo'} for key in _order(skill, extra)])


def update(path, key, state, detail=None):
    if state not in STATES:
        raise ProgressError(f'state must be one of: {", ".join(STATES)}')
    steps = _read(path)
    keys = [s['key'] for s in steps]
    order = _canonical(key, keys)
    step = {'key': key, 'state': state}
    if detail is not None and str(detail).strip():
        step['detail'] = _detail(detail)
    if key in keys:
        steps[keys.index(key)] = step
    else:
        later = [i for i, k in enumerate(keys) if k in order and order.index(k) > order.index(key)]
        steps.insert(later[0] if later else len(steps), step)
    _write(path, steps)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):  # Hebrew JSON on a Windows pipe/console (final review M5)
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('file', type=Path)
    parser.add_argument('--start', metavar='SKILL', choices=sorted(STEPS))
    parser.add_argument('--with', dest='extra', action='append', default=[], metavar='STEP')
    parser.add_argument('step', nargs='*', help='<key> <state> [detail]')
    args = parser.parse_args(argv)
    if (code := jobscope.refuse(args.file, write=True)) is not None:
        return code
    try:
        if args.start:
            if args.step:
                parser.error('use either --start or <key> <state> [detail]')
            start(args.file, args.start, args.extra)
        elif 2 <= len(args.step) <= 3:
            update(args.file, *args.step)
        else:
            parser.error('expected <key> <state> [detail]')
    except ProgressError as error:
        print(f'progress: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
