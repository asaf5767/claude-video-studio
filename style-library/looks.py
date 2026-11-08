"""Built-in style cards (Task 11) -- four ready-made "looks" a non-technical creator
picks in the UI's Look step. Each look lives at looks/<id>/card.md: Markdown with a
YAML-ish front-matter block (id, name_he, name_en, captions, titles, pace, transitions,
graphics, music, sfx, hook, avoid) plus a free-text body of practical notes. Claude reads
card(id) verbatim once the user picks a look; the UI calls list() to show the four cards
with a sample image. Shares the card format with Task 13's reference-derived custom looks.

Static, read-only, committed content (unlike materials.py's per-project uploads), so
there is no manifest, lock, or temp-dir indirection here -- just a confined read off disk.
"""
from pathlib import Path
import re

LOOKS_DIR = Path(__file__).resolve().parents[1] / 'looks'
IDS = ('soft', 'collage', 'signature', 'headline')
REQUIRED_KEYS = ('id', 'name_he', 'name_en', 'captions', 'titles', 'pace', 'transitions',
                  'graphics', 'music', 'sfx', 'hook', 'avoid')
# Everything GET /look-files/<id>/<file> is allowed to serve. card.md goes out through
# /looks (list()) and card() instead -- it is content, not a static asset -- and
# sample.html is a source file whose relative font URLs only resolve next to card.md,
# not when flattened onto this route. sample.mp4 is reserved for Task 21's renders.
ALLOWED_FILES = frozenset({'sample.jpg', 'sample.mp4'})
_ID_TOKEN = re.compile(r'[a-z][a-z-]*')


class LookError(Exception):
    """status: HTTP status to answer with."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _front_matter(text):
    """Split card.md into its front-matter dict and body text. Raises ValueError on a
    malformed card -- a bug in the shipped content, not user input, so callers let it
    surface rather than mapping it to a 404."""
    match = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z', text, re.DOTALL)
    if not match:
        raise ValueError('card.md is missing its --- front matter block')
    header, body = match.groups()
    fields = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(':')
        if not sep:
            raise ValueError(f'Malformed front-matter line: {line!r}')
        fields[key.strip()] = value.strip()
    return fields, body.strip('\n')


def parse_card(text):
    """Public parser for the card format: (front-matter fields dict, body text). Raises
    ValueError when the --- block is missing or a front-matter line has no colon. Used by
    Task 13's inspiration.py for reference-derived style cards."""
    return _front_matter(text)


def _read_card(look_id):
    path = LOOKS_DIR / look_id / 'card.md'
    return path.read_text(encoding='utf-8')


def validate_card(text):
    """Parse a card.md's front matter and check REQUIRED_KEYS are all present with a
    non-empty value. Returns the fields dict on success. Raises LookError(500,
    'looks.error.invalid-card: missing ...') naming the missing keys on failure -- the one
    place list() and card() both validate, so a malformed card always fails the same way
    (never a bare ValueError leaking out of this module). Public so Task 13's
    reference-derived custom looks can validate their generated cards the same way."""
    fields, _ = _front_matter(text)
    missing = [key for key in REQUIRED_KEYS if not fields.get(key, '').strip()]
    if missing:
        raise LookError(500, 'looks.error.invalid-card: missing ' + ', '.join(missing))
    return fields


def list():
    """looks.list() -> [{"id", "name_he", "name_en", "sample"}, ...], one per built-in
    look that actually has a card.md, in the fixed IDS order."""
    items = []
    for look_id in IDS:
        path = LOOKS_DIR / look_id / 'card.md'
        if not path.is_file():
            continue
        fields = validate_card(path.read_text(encoding='utf-8'))
        items.append({
            'id': look_id,
            'name_he': fields['name_he'],
            'name_en': fields['name_en'],
            'sample': f'/look-files/{look_id}/sample.jpg',
        })
    return items


def card(look_id):
    """looks.card(id) -> the full card.md text (front matter + body), for Claude to read
    once the look is chosen. Raises LookError(404) for an unknown id, LookError(500) if
    the shipped card itself is malformed."""
    if not isinstance(look_id, str) or not _ID_TOKEN.fullmatch(look_id):
        raise LookError(404, 'Unknown look')
    try:
        text = _read_card(look_id)
    except OSError:
        raise LookError(404, 'Unknown look')
    validate_card(text)
    return text


def file_path(look_id, filename):
    """Resolve <look_id>/<filename> confined to looks/<look_id>/, for GET
    /look-files/<id>/<file> (serve.py's existing Range-capable self.file()). A look id
    must be a known plain token, and filename must be one of ALLOWED_FILES exactly --
    not just path-safe, but an explicit whitelist, since card.md and sample.html are
    never meant to be served from this route (see ALLOWED_FILES)."""
    if not isinstance(look_id, str) or not _ID_TOKEN.fullmatch(look_id):
        raise LookError(404, 'Unknown look')
    if filename not in ALLOWED_FILES:
        raise LookError(404, 'Unknown file')
    root = (LOOKS_DIR / look_id).resolve()
    target = (root / filename).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise LookError(404, 'Unknown file')
    return target
