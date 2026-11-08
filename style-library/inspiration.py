"""Inspiration by link or file, with editable style cards (Task 13).

A creator adds a reel they like to the Inspiration tab ("השראה") -- by link (Matt's
reference_intake.save) or by dropping the video file here (upload()) -- presses "ללמוד את
הסגנון" (Claude's learn-style skill writes references/<id>/style-card.md), then edits that
STYLE CARD and pins the parts to keep.

Files, per reference (references/<id>/):
  source.<ext>     the uploaded video (mp4/mov/webm/m4v, at most MAX_UPLOAD = 1 GiB -- a
                   reference reel is short; 1 GiB is generous for one and keeps a mistaken
                   drop of a long recording from filling the disk). Streamed through
                   materials.stream_to_file (temp file + length check + atomic replace).
  style-card.md    the card, in exactly the looks/<id>/card.md format (front matter with
                   looks.REQUIRED_KEYS + a free-text body), validated by looks.validate_card.
  style-card.json  {"pinned": {key: value}}: the rows the user keeps, WITH their values.
                   The learn-style skill writes style-card.md only, never this file
                   (docs/plan/learn-style-contract.md), and card() lays the pinned values
                   over whatever style-card.md says -- so re-learning can never change a
                   pinned row, even if the new card drops it. A card with pins restricts
                   which keys a project uses (card()["use"]); no pins means the whole card
                   applies. (An older {"pinned": [keys]} list is still read.)

Errors are InspirationError(status, i18n message key[, details]) -- never English prose.
Rule shown on every card: we learn the technique, never copy the content (footage, words,
logo) of the original creator.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import datetime, timezone

import looks
import materials
import project_index as index
import reference_intake as intake

MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GiB, see the module docstring
MAX_CARD = 32768                 # characters in style-card.md
VIDEO_EXT = frozenset(materials.VIDEO_EXT)
# The front-matter keys a user edits and can pin (everything but the identity keys).
CARD_KEYS = tuple(k for k in looks.REQUIRED_KEYS if k not in ('id', 'name_he', 'name_en'))
CARD_LOCK = threading.RLock()
_UNCHECKED = object()


class InspirationError(Exception):
    """status: HTTP status. message_key: i18n key. details: extra JSON fields for the reply
    (e.g. {"missing": [...]} naming the card keys that are absent or empty)."""
    def __init__(self, status, message_key, details=None):
        super().__init__(message_key)
        self.status = status
        self.message_key = message_key
        self.details = details or {}


def _references_root():
    return (index.STUDIO / 'references').resolve()


def _folder(ref_id):
    """references/<id>/, confined to the studio's references folder."""
    root = _references_root()
    folder = (root / ref_id).resolve()
    if folder.parent != root or root.parent != index.STUDIO.resolve():
        raise InspirationError(404, 'inspiration.error.unknownReference')
    return folder


def _reference(ref_id):
    """The catalog entry of a creator reference ("השראה"); 404 for anything else."""
    if not isinstance(ref_id, str) or not index.TOKEN.fullmatch(ref_id):
        raise InspirationError(404, 'inspiration.error.unknownReference')
    try:
        _, data = intake.read_catalog()
    except intake.IntakeError as error:
        raise InspirationError(error.status, 'inspiration.error.filesystem')
    entry = next((e for e in data['entries'] if isinstance(e, dict) and e.get('id') == ref_id), None)
    if entry is None or entry.get('collection') != 'reference':
        raise InspirationError(404, 'inspiration.error.unknownReference')
    return entry


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(materials.CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def upload(stream, length, filename, reference=None, title='', creator='', note=''):
    """Store an inspiration video. Without `reference` this creates a new file-only
    reference (title/creator/note optional; the title defaults to the file name) and
    returns {"id", "duplicate", "saved"} -- the same bytes uploaded twice return the
    existing reference as a duplicate. With `reference` the file is added to that existing
    reference (e.g. a saved link), replacing a file uploaded there before."""
    name = materials.sanitize_filename(filename)
    ext = '.' + name.rsplit('.', 1)[1].lower() if '.' in name else ''
    if ext not in VIDEO_EXT:
        raise InspirationError(415, 'inspiration.error.unsupportedType')
    if not isinstance(length, int) or length <= 0:
        raise InspirationError(400, 'inspiration.error.invalidRequest')
    if length > MAX_UPLOAD:
        raise InspirationError(413, 'inspiration.error.tooLarge')
    if reference is not None:
        entry = _reference(reference)
        if entry.get('media_path') and not intake.FILE_MEDIA.fullmatch(entry['media_path']):
            raise InspirationError(409, 'inspiration.error.hasMedia')
        ref_id, details = reference, None
    else:
        for value, limit in ((title, 120), (creator, 80), (note, 1000)):
            if not isinstance(value, str) or len(value) > limit:
                raise InspirationError(400, 'inspiration.error.invalidRequest')
        ref_id, details = 'file-' + uuid.uuid4().hex[:24], {'title': title, 'creator': creator, 'note': note}
    folder = _folder(ref_id)
    created = not folder.exists()
    dest = folder / ('source' + ext)
    # The new bytes land under a hidden temp name first; an earlier source.* stays in place
    # until the catalog commit succeeds, so a failed replacement never loses the old video.
    incoming = folder / f'.incoming-{uuid.uuid4().hex}{ext}'

    def discard():
        incoming.unlink(missing_ok=True)
        if created:
            shutil.rmtree(folder, ignore_errors=True)
    try:
        materials.stream_to_file(stream, length, incoming, MAX_UPLOAD)
        digest = _sha256(incoming)
        result = intake.register_file(ref_id, f'references/{ref_id}/source{ext}', digest, name, details)
    except materials.MaterialsError as error:
        discard()
        raise InspirationError(error.status, 'inspiration.error.' + error.message_key.rsplit('.', 1)[1])
    except intake.IntakeError as error:
        discard()
        raise InspirationError(error.status, 'inspiration.error.invalidRequest' if error.status == 400 else
                               'inspiration.error.unknownReference' if error.status == 404 else
                               'inspiration.error.hasMedia' if error.status == 409 else 'inspiration.error.filesystem')
    except OSError:
        discard()
        raise InspirationError(503, 'inspiration.error.filesystem')
    if result['duplicate']:
        discard()
        return result
    try:
        os.replace(incoming, dest)
    except OSError:
        incoming.unlink(missing_ok=True)
        raise InspirationError(503, 'inspiration.error.filesystem')
    for old in folder.glob('source.*'):
        if old != dest and old.suffix.lower() in VIDEO_EXT:
            old.unlink(missing_ok=True)
    return result


# --- style cards ---------------------------------------------------------------------

_BLOCK = re.compile(r'^---\r?\n.*?\r?\n---\r?\n?', re.DOTALL)


def _parse(text):
    """(fields, body, missing). A malformed card reports every required key as missing
    rather than raising; its body is what follows a (broken) --- block, never the block
    itself, so the editor cannot write the block twice."""
    try:
        fields, body = looks.parse_card(text)
    except ValueError:
        return {}, _BLOCK.sub('', text, count=1).strip('\n'), list(looks.REQUIRED_KEYS)
    return fields, body, _missing(fields)


def _missing(fields):
    return [key for key in looks.REQUIRED_KEYS if not fields.get(key, '').strip()]


def _read_pins(folder, fields):
    """{key: pinned value}. A legacy {"pinned": [keys]} list takes its values from the card."""
    try:
        pinned = json.loads((folder / 'style-card.json').read_text(encoding='utf-8')).get('pinned')
    except (OSError, ValueError, AttributeError):
        return {}
    if isinstance(pinned, list):
        pinned = {k: fields.get(k, '') for k in pinned if isinstance(k, str)}
    if not isinstance(pinned, dict):
        return {}
    return {k: v.strip() for k, v in pinned.items()
            if k in CARD_KEYS and isinstance(v, str) and v.strip() and '\n' not in v and '\r' not in v}


def _revision(folder):
    """sha256 over the card and its pins, or None when no card exists yet."""
    try:
        text = (folder / 'style-card.md').read_bytes()
    except FileNotFoundError:
        return None
    try:
        pins = (folder / 'style-card.json').read_bytes()
    except FileNotFoundError:
        pins = b''
    return hashlib.sha256(text + b'\0' + pins).hexdigest()


def card(ref_id):
    """inspiration.card(id) -> {"reference", "exists", "text", "fields", "body", "keys",
    "pinned", "use", "valid", "missing", "revision"}. "use" is the pinned subset of the
    card's keys, or every key when nothing is pinned -- what a project built from this
    reference should follow."""
    _reference(ref_id)
    folder = _folder(ref_id)
    with CARD_LOCK:
        try:
            text = (folder / 'style-card.md').read_text(encoding='utf-8')
        except FileNotFoundError:
            text = None
        except (OSError, UnicodeDecodeError):
            raise InspirationError(503, 'inspiration.error.filesystem')
        fields, body, missing = _parse(text) if text is not None else ({}, '', [])
        pins = _read_pins(folder, fields) if text is not None else {}
        revision = _revision(folder)
    if pins:  # even over an unparseable card (fields == {}), pinned rows still show
        fields = {**fields, **pins}  # a pinned row always shows the user's value
        missing = _missing(fields)
    pinned = [k for k in CARD_KEYS if k in pins]
    keys = pinned or [k for k in CARD_KEYS if fields.get(k, '').strip()]
    return {'reference': ref_id, 'exists': text is not None, 'text': text or '', 'fields': fields, 'body': body,
            'keys': list(CARD_KEYS), 'pinned': pinned, 'use': {k: fields[k] for k in keys if k in fields},
            'valid': text is not None and not missing, 'missing': missing, 'revision': revision}


def _write_pair(folder, files):
    """Replace several files as one logical step: write every new version to a temp file
    first, then swap them in; if any swap fails, put back what was there before."""
    temps, done, before = {}, [], {}
    try:
        for path, data in files.items():
            before[path] = path.read_bytes() if path.exists() else None
            fd, temp = tempfile.mkstemp(prefix='.studio-write-', dir=folder)
            temps[path] = temp
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
        for path, temp in temps.items():
            os.replace(temp, path)
            done.append(path)
    except OSError:
        for path in done:
            try:
                if before[path] is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(before[path])
            except OSError:
                pass
        raise
    finally:
        for temp in temps.values():
            if os.path.exists(temp):
                os.unlink(temp)


def save_card(ref_id, text, pinned, revision=_UNCHECKED):
    """inspiration.save_card(id, text, pinned) -> card(id). Validates the card with
    looks.validate_card (400 inspiration.error.invalidCard, details {"missing": [...]}),
    checks every pinned key is one of the card's editable keys (400
    inspiration.error.unknownPin, details {"unknown": [...]}), and -- when `revision` is
    given (the HTTP route always gives it; None means "no card yet") -- refuses to
    overwrite a card that changed since it was read (409). Writes atomically under a lock."""
    if not isinstance(text, str) or len(text) > MAX_CARD or any(ord(c) < 32 and c not in '\n\r\t' for c in text):
        raise InspirationError(400, 'inspiration.error.invalidRequest')
    if (not isinstance(pinned, list) or not all(isinstance(k, str) for k in pinned) or
            len(set(pinned)) != len(pinned)):
        raise InspirationError(400, 'inspiration.error.invalidRequest')
    fields, _, missing = _parse(text)
    if missing:
        raise InspirationError(400, 'inspiration.error.invalidCard', {'missing': missing})
    try:
        looks.validate_card(text)
    except (looks.LookError, ValueError):
        raise InspirationError(400, 'inspiration.error.invalidCard', {'missing': list(looks.REQUIRED_KEYS)})
    unknown = [k for k in pinned if k not in CARD_KEYS or not fields.get(k, '').strip()]
    if unknown:
        raise InspirationError(400, 'inspiration.error.unknownPin', {'unknown': unknown})
    _reference(ref_id)
    folder = _folder(ref_id)
    pins = {k: fields[k].strip() for k in CARD_KEYS if k in pinned}
    with CARD_LOCK:
        if revision is not _UNCHECKED and revision != _revision(folder):
            raise InspirationError(409, 'inspiration.error.changed')
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _write_pair(folder, {
                folder / 'style-card.md': text.encode('utf-8'),
                folder / 'style-card.json': (json.dumps({'pinned': pins, 'updated_at': datetime.now(timezone.utc).isoformat()},
                                                        ensure_ascii=False, indent=2) + '\n').encode(),
            })
        except OSError:
            raise InspirationError(503, 'inspiration.error.filesystem')
    return card(ref_id)
