"""Materials upload into a project (raw takes, B-roll, images, logos, music, SFX) and a
studio-wide personal library (Task 8).

Mirrors new_project.py's error style (an HTTP status plus an i18n message KEY, never
English prose -- the studio UI calls I18N.t(message_key)) and atomic.py's temp-file +
fsync + os.replace write pattern. Large uploads stream through stream_to_file() in 1 MiB
chunks rather than buffering the whole body in memory; Task 13 reuses that helper for
inspiration-video uploads.
"""
import csv
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import project_index as index
import posters
from atomic import atomic_write
from security import MEDIA, AUDIO

CHUNK = 1024 * 1024  # 1 MiB
MAX_UPLOAD = 8 * 1024 * 1024 * 1024  # 8 GiB
MANIFEST_LOCK = threading.RLock()
# Captured before `list()` (the module-level function matching the brief's exact
# interface, materials.list) shadows the builtin of the same name for the rest of
# this module.
_list_type = list

# 'voice': the creator's voice-over recording (faceless reels). Audio still auto-tags as music;
# the creator switches it to voice in the tag menu.
TAGS = ('raw', 'broll', 'screen', 'image', 'logo', 'music', 'voice', 'sfx')
FOLDER_BY_TAG = {'raw': 'raw', 'broll': 'broll', 'screen': 'broll',
                  'image': 'images', 'logo': 'images', 'music': 'audio', 'voice': 'audio',
                  'sfx': 'audio'}
# Matches security.MEDIA exactly, split by kind so auto-tagging can tell video from image.
VIDEO_EXT = {'.mp4', '.mov', '.webm', '.m4v'}
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
ALLOWED_EXT = MEDIA | AUDIO
# Task 9: content type for serving a material's bytes back (GET /project-materials/...).
MIME_BY_EXT = {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm', '.m4v': 'video/x-m4v',
               '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif',
               '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4', '.aac': 'audio/aac'}

WINDOWS_RESERVED_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{d}' for d in '123456789'} | {f'LPT{d}' for d in '123456789'}

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
LEDGER_FIELDS = ['asset_id', 'file', 'role', 'spoken_beat', 'provenance', 'creator_or_vendor',
                  'license_or_permission', 'commercial_use_status', 'generated_with', 'notes']


class MaterialsError(Exception):
    """status: HTTP status to answer with. message_key: an i18n key, not English prose --
    the studio UI calls I18N.t(message_key) to show it in the active language."""
    def __init__(self, status, message_key):
        super().__init__(message_key)
        self.status = status
        self.message_key = message_key


def _split_ext(name):
    if '.' in name:
        stem, ext = name.rsplit('.', 1)
        return stem, '.' + ext
    return name, ''


def sanitize_filename(name):
    """Strip any directory parts (both / and \\), control chars and Windows-reserved
    characters, trim trailing dots/spaces, and prefix a reserved device name -- while
    keeping Unicode letters (Hebrew, etc.) and spaces untouched. Windows and Mac both need
    to accept the result as a plain file name."""
    if not isinstance(name, str):
        name = ''
    tail = name.replace('\\', '/').split('/')[-1]
    cleaned = ''.join(ch for ch in tail if ch not in WINDOWS_RESERVED_CHARS and ord(ch) >= 32 and ord(ch) != 127)
    cleaned = cleaned.rstrip(' .')
    if not cleaned:
        return 'file'
    stem, _ = _split_ext(cleaned)
    if stem.upper() in RESERVED_NAMES:
        cleaned = '_' + cleaned
    return cleaned


def _unique_name(dest_dir, name):
    stem, ext = _split_ext(name)
    candidate = name
    n = 2
    while (dest_dir / candidate).exists():
        candidate = f'{stem} ({n}){ext}'
        n += 1
    return candidate


def _auto_tag(ext, items):
    if ext in VIDEO_EXT:
        return 'broll' if any(i.get('tag') == 'raw' for i in items) else 'raw'
    if ext in IMAGE_EXT:
        return 'image'
    return 'music'  # the only remaining allowed kind is audio


def _project_root(project_id):
    """Confine to a project that is both registered (projects.json) and has the on-disk
    shape Task 7 creates -- registration alone isn't enough (fix round 1, finding 5): a
    stray directory that merely happens to have a materials.json must not be reachable
    just because its name matches a TOKEN."""
    if not isinstance(project_id, str) or not index.TOKEN.fullmatch(project_id):
        raise MaterialsError(404, 'materials.error.unknownProject')
    try:
        registered = any(p.get('id') == project_id for p in index.registry()['projects'])
    except (OSError, ValueError):
        raise MaterialsError(503, 'materials.error.filesystem')
    if not registered:
        raise MaterialsError(404, 'materials.error.unknownProject')
    projects_root = (index.STUDIO / 'projects').resolve()
    root = (index.STUDIO / 'projects' / project_id).resolve()
    if root.parent != projects_root or not root.is_dir() or not (root / 'materials.json').is_file():
        raise MaterialsError(404, 'materials.error.unknownProject')
    return root


def _manifest_path(project_root):
    return project_root / 'materials.json'


def _read_manifest(project_root):
    try:
        data = json.loads(_manifest_path(project_root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise MaterialsError(503, 'materials.error.filesystem')
    if not isinstance(data, dict) or not isinstance(data.get('items'), _list_type):
        raise MaterialsError(503, 'materials.error.filesystem')
    return data


def _write_manifest(project_root, manifest):
    try:
        atomic_write(_manifest_path(project_root), (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode())
    except OSError:
        raise MaterialsError(503, 'materials.error.filesystem')


def stream_to_file(stream, length, dest, limit):
    """Stream exactly `length` bytes from `stream` into `dest` in 1 MiB chunks, writing to
    a temp file in the same folder first so a failed upload never leaves a partial file
    under the final name (same discipline as atomic.atomic_write, sized for large media
    instead of buffering it all in memory). Raises MaterialsError(413) if `length` exceeds
    `limit` before any byte is read. Raises MaterialsError(400) -- never replacing the
    final name, and always clearing the temp file -- if the stream ends early (a
    disconnect or short body) and fewer than `length` bytes actually arrive (fix round 1,
    finding 1). Returns the number of bytes actually written."""
    if not isinstance(length, int) or length < 0 or length > limit:
        raise MaterialsError(413, 'materials.error.tooLarge')
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.studio-upload-', dir=dest.parent)
    written = 0
    try:
        with os.fdopen(fd, 'wb') as out:
            remaining = length
            while remaining > 0:
                data = stream.read(min(CHUNK, remaining))
                if not data:
                    break
                out.write(data)
                written += len(data)
                remaining -= len(data)
            out.flush()
            os.fsync(out.fileno())
        if written != length:
            raise MaterialsError(400, 'materials.error.incomplete')
        os.replace(temp, dest)
    except OSError:
        raise MaterialsError(503, 'materials.error.filesystem')
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return written


def save_upload(project_id, filename, stream, length):
    project_root = _project_root(project_id)
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise MaterialsError(415, 'materials.error.unsupportedType')
    if not isinstance(length, int) or length < 0:
        raise MaterialsError(400, 'materials.error.invalidRequest')
    if length > MAX_UPLOAD:
        raise MaterialsError(413, 'materials.error.tooLarge')
    with MANIFEST_LOCK:
        manifest = _read_manifest(project_root)
        tag = _auto_tag(ext, manifest['items'])
        folder = FOLDER_BY_TAG[tag]
        dest_dir = project_root / 'materials' / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = _unique_name(dest_dir, safe_name)
        dest = dest_dir / dest_name
        size = stream_to_file(stream, length, dest, MAX_UPLOAD)
        item = {'id': uuid.uuid4().hex[:12], 'file': f'materials/{folder}/{dest_name}',
                'tag': tag, 'note': '', 'owned': False, 'size': size,
                'added_at': datetime.now(timezone.utc).isoformat()}
        manifest['items'].append(item)
        _write_manifest(project_root, manifest)
    return item


def list(project_id):  # noqa: A001 - matches the brief's exact module interface
    project_root = _project_root(project_id)
    with MANIFEST_LOCK:
        return _read_manifest(project_root)['items']


def _ledger_path(project_root):
    """Create the project's asset-ledger.csv from the template on first use. Written
    utf-8-sig (a leading BOM) so Excel on Windows opens Hebrew filenames correctly
    instead of mojibake-ing them (fix round 1, finding 3); every later append reopens in
    plain utf-8 so that BOM is written exactly once, not before every row."""
    ledger = project_root / 'asset-ledger.csv'
    if not ledger.is_file():
        try:
            header = (TEMPLATES / 'asset-ledger.csv').read_text(encoding='utf-8')
        except OSError:
            raise MaterialsError(503, 'materials.error.filesystem')
        try:
            ledger.write_text(header, encoding='utf-8-sig', newline='')
        except OSError:
            raise MaterialsError(503, 'materials.error.filesystem')
    return ledger


def _append_ledger_row(project_root, item):
    ledger = _ledger_path(project_root)
    row = {'asset_id': item['id'], 'file': item['file'], 'role': item.get('tag', ''),
           'spoken_beat': '', 'provenance': 'owner-supplied', 'creator_or_vendor': '',
           'license_or_permission': 'owner-supplied', 'commercial_use_status': '',
           'generated_with': '', 'notes': item.get('note', '')}
    try:
        with ledger.open('a', encoding='utf-8', newline='') as f:
            csv.DictWriter(f, fieldnames=LEDGER_FIELDS, quoting=csv.QUOTE_MINIMAL).writerow(row)
    except OSError:
        raise MaterialsError(503, 'materials.error.filesystem')


def _move_item_file(project_root, item, new_folder):
    """Physically relocate an item's file to match a changed tag's folder, so
    FOLDER_BY_TAG stays true on disk for later tasks (fix round 1, finding 6). Renames on
    collision the same way a fresh upload does; updates item['file'] in place."""
    old_relative = item.get('file')
    if not isinstance(old_relative, str):
        raise MaterialsError(503, 'materials.error.filesystem')
    try:
        root_resolved = project_root.resolve()
        old_path = (project_root / old_relative).resolve()
    except OSError:
        raise MaterialsError(503, 'materials.error.filesystem')
    if not old_path.is_relative_to(root_resolved) or not old_path.is_file():
        raise MaterialsError(503, 'materials.error.filesystem')
    dest_dir = project_root / 'materials' / new_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = _unique_name(dest_dir, sanitize_filename(old_path.name))
    dest = dest_dir / dest_name
    try:
        os.replace(old_path, dest)
    except OSError:
        raise MaterialsError(503, 'materials.error.filesystem')
    item['file'] = f'materials/{new_folder}/{dest_name}'


def _revert_move(project_root, item, original_relative):
    """Best-effort undo of _move_item_file when the manifest write that was supposed to
    record the move then fails (fix round 2, finding 1): the persisted manifest never
    changed (atomic_write failed before os.replace-ing it), so the file should go back to
    where that still-current manifest says it is. Swallows a failed move-back -- there is
    nothing safer left to do than re-raise the original error -- but still points
    item['file'] at the original path so an in-memory caller doesn't disagree with disk."""
    current_relative = item.get('file')
    if isinstance(current_relative, str):
        try:
            current_path = (project_root / current_relative).resolve()
            original_path = (project_root / original_relative).resolve()
            if current_path.is_file():
                original_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(current_path, original_path)
        except OSError:
            pass
    item['file'] = original_relative


def update(project_id, item_id, patch):
    if not isinstance(patch, dict) or not patch or set(patch) - {'tag', 'note', 'owned'}:
        raise MaterialsError(400, 'materials.error.invalidRequest')
    if 'tag' in patch and patch['tag'] not in TAGS:
        raise MaterialsError(400, 'materials.error.invalidTag')
    if 'note' in patch and (not isinstance(patch['note'], str) or len(patch['note']) > 300):
        raise MaterialsError(400, 'materials.error.noteTooLong')
    if 'owned' in patch and not isinstance(patch['owned'], bool):
        raise MaterialsError(400, 'materials.error.invalidRequest')
    project_root = _project_root(project_id)
    with MANIFEST_LOCK:
        manifest = _read_manifest(project_root)
        item = next((i for i in manifest['items'] if i.get('id') == item_id), None)
        if item is None:
            raise MaterialsError(404, 'materials.error.unknownItem')
        became_owned = patch.get('owned') is True and not item.get('owned')
        new_tag = patch.get('tag')
        moved_from = None
        if new_tag and new_tag != item.get('tag'):
            new_folder = FOLDER_BY_TAG[new_tag]
            if new_folder != FOLDER_BY_TAG.get(item.get('tag')):
                moved_from = item.get('file')
                _move_item_file(project_root, item, new_folder)
        item.update(patch)
        try:
            _write_manifest(project_root, manifest)
        except MaterialsError:
            # The manifest on disk is unchanged (atomic_write never replaced it), but the
            # file already moved -- move it back (fix round 2, finding 1) so disk and the
            # still-persisted manifest agree again, rather than leaving materials.json
            # pointing at a path that no longer exists.
            if moved_from is not None:
                _revert_move(project_root, item, moved_from)
            raise
        if became_owned:
            _append_ledger_row(project_root, item)
        return item


def _library_root():
    return index.STUDIO / 'library'


def add_from_library(project_id, library_item_id):
    project_root = _project_root(project_id)
    library_root = _library_root()
    try:
        library_manifest = json.loads((library_root / 'materials.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise MaterialsError(404, 'materials.error.unknownLibraryItem')
    if not isinstance(library_manifest, dict) or not isinstance(library_manifest.get('items'), _list_type):
        raise MaterialsError(503, 'materials.error.filesystem')
    source_item = next((i for i in library_manifest['items'] if i.get('id') == library_item_id), None)
    if source_item is None or not isinstance(source_item.get('file'), str):
        raise MaterialsError(404, 'materials.error.unknownLibraryItem')
    try:
        source_path = (library_root / source_item['file']).resolve()
        resolved_library_root = library_root.resolve()
    except OSError:
        raise MaterialsError(404, 'materials.error.unknownLibraryItem')
    if not source_path.is_relative_to(resolved_library_root) or not source_path.is_file():
        raise MaterialsError(404, 'materials.error.unknownLibraryItem')
    ext = source_path.suffix.lower()
    if ext not in ALLOWED_EXT:
        raise MaterialsError(415, 'materials.error.unsupportedType')
    with MANIFEST_LOCK:
        manifest = _read_manifest(project_root)
        tag = source_item.get('tag') if source_item.get('tag') in TAGS else _auto_tag(ext, manifest['items'])
        folder = FOLDER_BY_TAG[tag]
        dest_dir = project_root / 'materials' / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = _unique_name(dest_dir, sanitize_filename(source_path.name))
        dest = dest_dir / dest_name
        try:
            data = source_path.read_bytes()
            atomic_write(dest, data)
        except OSError:
            raise MaterialsError(503, 'materials.error.filesystem')
        item = {'id': uuid.uuid4().hex[:12], 'file': f'materials/{folder}/{dest_name}', 'tag': tag,
                'note': source_item.get('note', '') if isinstance(source_item.get('note'), str) else '',
                'owned': bool(source_item.get('owned', False)), 'size': len(data),
                'added_at': datetime.now(timezone.utc).isoformat()}
        manifest['items'].append(item)
        _write_manifest(project_root, manifest)
        return item


def list_library():
    """Task 9: the personal library picker ("הוספה מהספרייה שלי") lists what
    add_from_library() can copy from. A fresh studio has no library yet -- that is not
    an error, just an empty shelf -- so a missing materials.json answers [] rather than
    404/503."""
    manifest_path = _library_root() / 'materials.json'
    if not manifest_path.is_file():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise MaterialsError(503, 'materials.error.filesystem')
    if not isinstance(data, dict) or not isinstance(data.get('items'), _list_type):
        raise MaterialsError(503, 'materials.error.filesystem')
    return data['items']


def file_path(project_id, item_id):
    """Task 9: resolve a project's material file by item id for GET /project-materials/
    (confined, Range-capable serving lives in serve.py's existing self.file()). Controller
    note: re-reads the manifest and resolves the on-disk path *inside* MANIFEST_LOCK, at
    request time, rather than trusting a path cached from an earlier /materials response --
    update()'s tag-change move (_move_item_file) also runs under this same lock, so the
    path resolved here can never straddle an in-flight rename. A Windows PermissionError
    hitting a resolve/stat while a rename is briefly mid-flight elsewhere becomes a 503
    (retry) through the OSError handler below, not an unhandled crash."""
    project_root = _project_root(project_id)
    with MANIFEST_LOCK:
        manifest = _read_manifest(project_root)
        item = next((i for i in manifest['items'] if i.get('id') == item_id), None)
        if item is None or not isinstance(item.get('file'), str):
            raise MaterialsError(404, 'materials.error.unknownItem')
        try:
            root_resolved = project_root.resolve()
            target = (project_root / item['file']).resolve()
            ok = target.is_relative_to(root_resolved) and target.suffix.lower() in ALLOWED_EXT and target.is_file()
        except OSError:
            raise MaterialsError(503, 'materials.error.filesystem')
        if not ok:
            raise MaterialsError(404, 'materials.error.unknownItem')
        return target, MIME_BY_EXT.get(target.suffix.lower(), 'application/octet-stream')


def poster_path(project_id, item_id):
    """T9b: server-generated JPEG poster for a video material, served via
    GET /project-materials/<project>/<item>?poster=1 -- the raw-take thumbnail (and the
    review player, through the equivalent project-asset route) would otherwise show a black
    frame for HEVC/HLG video shot on an iPhone, which Chrome on Windows can't decode.
    Raises MaterialsError(404) for an unknown item or a non-video material (nothing to
    extract a frame from, same key as an unknown item -- there is no file either way).
    Returns None, not an error, when ffmpeg could not produce a poster within its time
    budget: the route then answers 404 and the UI falls back to its placeholder icon."""
    target, _ = file_path(project_id, item_id)
    if target.suffix.lower() not in VIDEO_EXT:
        raise MaterialsError(404, 'materials.error.unknownItem')
    project_root = _project_root(project_id)
    cache_dir = project_root / 'materials' / '.posters'
    return posters.ensure(target, cache_dir, item_id)
