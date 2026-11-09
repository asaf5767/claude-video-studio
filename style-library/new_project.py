"""Create a draft video project directly from the studio UI (Task 7).

Unlike scripts/register.py (an assistant-facing CLI around a two-phase commit over
several files), this is a same-process, same-request creation path driven by a short
studio form: title, kind and video language. The registry write reuses atomic.py's
atomic_write -- the same temp-file + fsync + os.replace helper library.py already uses
for settings.json -- rather than adding a third way to write it.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil

import project_index as index
import choices
from atomic import atomic_write
from security import RESERVED_NAMES

KINDS = ('talking-head', 'faceless')
LANGUAGES = ('he', 'en')
TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
TITLE_LABEL = {'he': 'כותרת', 'en': 'Title'}
# Windows reserved device names (case-insensitive, no extension involved here since the
# slug becomes a directory name directly) -- a project "named" one of these would make
# its own folder impossible to open/delete reliably on a Windows machine.


class NewProjectError(Exception):
    """status: HTTP status to answer with. message_key: an i18n key, not English prose --
    the studio UI calls I18N.t(message_key) to show it in the active language."""
    def __init__(self, status, message_key):
        super().__init__(message_key)
        self.status = status
        self.message_key = message_key


def _slug(title):
    """ASCII-only slug: Hebrew (or any non-ASCII) collapses away, leaving only Latin
    letters/digits from the title, if any."""
    ascii_text = title.encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+', '-', ascii_text).strip('-')


def _timestamp_id():
    return 'video-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')


def _unique_id(base, existing):
    if base not in existing:
        return base
    n = 2
    while f'{base}-{n}' in existing:
        n += 1
    return f'{base}-{n}'


def brief_section(video_language):
    """Pull just this language's section out of templates/brief.md, with the
    `<!-- lang:.. -->` / `<!-- /lang:.. -->` wrapper markers stripped.

    Shared with scripts/studio.py's legacy `new` scaffold (fix round 1) so that CLI
    stops copying templates/brief.md verbatim -- which would otherwise leak both
    language sections' wrapper markers into a project's brief.md.
    """
    template = (TEMPLATES / 'brief.md').read_text(encoding='utf-8')
    match = re.search(r'<!-- lang:' + video_language + r' -->\n(.*?)\n<!-- /lang:' + video_language + r' -->',
                       template, re.DOTALL)
    if not match:
        raise ValueError(f'templates/brief.md has no {video_language!r} section')
    return match.group(1).strip('\n') + '\n'


def _brief_text(video_language, title, choices_data):
    """This project's brief.md: its language section with the title line prefilled and
    the <!-- choices --> block already rendered from `choices_data` (Task 10 fix round 1,
    finding 5). A project created from an inspiration reference starts with
    choices.json == {"look": "ref:<id>"}; without rendering that into brief.md here too,
    the two files would disagree about the project's look until the user's first tap in
    the choices UI -- Claude reading the brief right after creation would see nothing."""
    try:
        block = brief_section(video_language)
    except (OSError, ValueError):
        raise NewProjectError(503, 'newVideo.error.filesystem')
    label = TITLE_LABEL[video_language]
    # The title is free text: neutralize comment markers so it can never end or fake the
    # <!-- choices --> block a later save rewrites (final review M14).
    text = block.replace(f'- {label}:', f'- {label}: {choices._brief_safe(title)}', 1)
    try:
        rendered = choices.render_block(video_language, choices_data)
    except choices.ChoicesError:
        raise NewProjectError(503, 'newVideo.error.filesystem')
    return choices.apply_block(text, rendered)


def _status_text():
    try:
        return (TEMPLATES / 'STATUS.md').read_text(encoding='utf-8')
    except OSError:
        return '# Project status\n'


def create(body):
    if not isinstance(body, dict):
        raise NewProjectError(400, 'newVideo.error.invalidRequest')
    title, kind, video_language = body.get('title'), body.get('kind'), body.get('video_language')
    reference_id = body.get('reference_id')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
        raise NewProjectError(400, 'newVideo.error.title')
    if kind not in KINDS:
        raise NewProjectError(400, 'newVideo.error.kind')
    if video_language not in LANGUAGES:
        raise NewProjectError(400, 'newVideo.error.language')
    if reference_id is not None and (not isinstance(reference_id, str) or not index.TOKEN.fullmatch(reference_id)):
        raise NewProjectError(400, 'newVideo.error.invalidRequest')
    title = title.strip()

    with index.STATE_LOCK:
        data = index.registry()
        existing = {p['id'] for p in data['projects']}
        base = _slug(title)
        if len(base) < 3 or base.upper() in RESERVED_NAMES:
            base = _timestamp_id()
        project_id = _unique_id(base, existing)

        root = index.STUDIO / 'projects' / project_id
        # A fresh id normally has no folder yet, but never delete one that was already
        # sitting there before this call (e.g. a stray leftover) if something fails below.
        pre_existing = root.exists()

        def cleanup():
            if not pre_existing:
                shutil.rmtree(root, ignore_errors=True)

        choices_data = {'look': f'ref:{reference_id}'} if reference_id else {}
        try:
            for sub in ('raw', 'broll', 'images', 'audio'):
                (root / 'materials' / sub).mkdir(parents=True, exist_ok=True)
            (root / 'brief.md').write_text(_brief_text(video_language, title, choices_data), encoding='utf-8')
            (root / 'STATUS.md').write_text(_status_text(), encoding='utf-8')
            (root / 'materials.json').write_text(json.dumps({'items': []}, indent=2) + '\n', encoding='utf-8')
            (root / 'choices.json').write_text(json.dumps(choices_data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        except OSError:
            cleanup()
            raise NewProjectError(503, 'newVideo.error.filesystem')
        except NewProjectError:
            cleanup()
            raise

        record = {
            'id': project_id, 'title': title, 'kind': kind, 'video_language': video_language,
            'state': 'draft', 'format': 'video', 'created_at': datetime.now(timezone.utc).isoformat(),
            'primary_artifact': None, 'artifacts': [], 'source_notes': [],
        }
        data['projects'].insert(0, record)
        try:
            atomic_write(index.REGISTRY, (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode())
        except OSError:
            cleanup()
            raise NewProjectError(503, 'newVideo.error.filesystem')
    return record
