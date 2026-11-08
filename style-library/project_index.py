"""Read-only navigation over explicit project checkpoints; production notes stay authoritative."""
from pathlib import Path
import copy
import hashlib
import json
import re
import sys
import threading
import posters
from library import BASE, STUDIO

REGISTRY = BASE / 'projects.json'
STATE_LOCK = threading.RLock()
TOKEN = re.compile(r'^[a-z0-9][a-z0-9-]*$')
START_REQUEST = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')
MIME = {
    '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.png': 'image/png',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
    '.md': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
    '.srt': 'text/plain; charset=utf-8', '.json': 'text/plain; charset=utf-8',
    '.csv': 'text/plain; charset=utf-8', '.zip': 'application/zip',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}


def registry():
    # An empty installation has no projects until its assistant registers one.
    if not REGISTRY.exists():
        return {'schema_version': 1, 'projects': []}
    data = json.loads(REGISTRY.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('projects'), list):
        raise ValueError('Invalid project navigation index')
    return data


def resolve(project, relative):
    """Require an existing, supported file inside this exact project, even through symlinks."""
    if not TOKEN.fullmatch(project['id']) or not isinstance(relative, str):
        raise ValueError('Invalid project or path')
    root = (STUDIO / 'projects' / project['id']).resolve()
    projects_root = (STUDIO / 'projects').resolve()
    if projects_root.parent != STUDIO.resolve() or root.parent != projects_root:
        raise ValueError('Project root leaves projects folder')
    raw = Path(relative)
    if raw.is_absolute() or '..' in raw.parts or any(p.startswith('.') for p in raw.parts):
        raise ValueError('Use project-relative paths')
    target = (root / raw).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in MIME or not target.is_file():
        raise ValueError('Missing or unsupported project file')
    return target


def files(project):
    """The sole allowlist for /project-files/: no arbitrary path or directory route."""
    paths = [n['path'] for n in project.get('source_notes', [])]
    if project.get('cover_path'):
        paths.append(project['cover_path'])
    for artifact in project.get('artifacts', []):
        if artifact.get('path'):
            paths.append(artifact['path'])
        for frame in artifact.get('frames', []):
            paths.append(frame['path'])
        for download in artifact.get('downloads', []):
            paths.append(download['path'])
    return list(dict.fromkeys(paths))


def get_file(project_id, slot):
    if not TOKEN.fullmatch(project_id) or not re.fullmatch(r'0|[1-9][0-9]*', slot):
        raise ValueError('Unknown project file')
    project = next(p for p in registry()['projects'] if p['id'] == project_id)
    target = resolve(project, files(project)[int(slot)])
    return target, MIME[target.suffix.lower()]


def get_asset(project_id, file_id):
    """Stable allowlisted file IDs survive inserting another version into the index."""
    if not TOKEN.fullmatch(project_id) or not re.fullmatch(r'[a-f0-9]{64}', file_id):
        raise ValueError('Unknown project asset')
    project = next(p for p in registry()['projects'] if p['id'] == project_id)
    relative = next(name for name in files(project) if hashlib.sha256(name.encode()).hexdigest() == file_id)
    target = resolve(project, relative)
    return target, MIME[target.suffix.lower()]


def get_asset_poster(project_id, file_id):
    """T9b: JPEG poster for a video project asset, served via
    GET /project-assets/<project>/<file_id>?poster=1 -- so a review/export video that
    Chrome on Windows can't decode (HEVC/HLG from an iPhone) still shows a real frame
    instead of a black box. Reuses get_asset()'s exact lookup and confinement, so a poster
    can only ever be made for a file the registry already allows serving as-is. Caches
    under projects/<id>/.posters/, keyed by the same stable file_id get_asset() uses, so a
    poster survives inserting another version into the index. Raises ValueError (same as
    an unknown asset) for a non-video asset; returns None, not an error, when ffmpeg could
    not produce a poster within its time budget."""
    target, mime = get_asset(project_id, file_id)
    if not mime.startswith('video/'):
        raise ValueError('Not a video asset')
    project_root = (STUDIO / 'projects' / project_id).resolve()
    cache_dir = project_root / '.posters'
    return posters.ensure(target, cache_dir, file_id)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_files(artifact):
    return list(dict.fromkeys(([artifact['path']] if artifact.get('path') else []) +
                             [f['path'] for f in artifact.get('frames', [])] +
                             [d['path'] for d in artifact.get('downloads', [])]))


def revision(project):
    """Optimistic guard over navigation, current decisions and exact checkpoint file stats."""
    parts = [json.dumps(project, sort_keys=True)]
    for note in project.get('source_notes', []):
        try:
            parts.append(digest(resolve(project, note['path'])))
        except (OSError, ValueError):
            parts.append('missing:' + note['path'])
    artifact = next(a for a in project['artifacts'] if a['id'] == project['primary_artifact'])
    for path in primary_files(artifact):
        try:
            info = resolve(project, path).stat()
            parts.append(f'{path}:{info.st_size}:{info.st_mtime_ns}')
        except (OSError, ValueError):
            parts.append('missing:' + path)
    return hashlib.sha256('\n'.join(parts).encode()).hexdigest()


def review_options(project):
    artifact = next(a for a in project['artifacts'] if a['id'] == project['primary_artifact'])
    kind = artifact.get('approval_kind') or ('spoken_cut' if artifact.get('role') == 'assembly' else
            'storyboard' if artifact['type'] == 'board' and project.get('format') != 'presentation' else 'final')
    previous = project.get('review_decision', {})
    approved = (previous.get('action') == 'approve' and previous.get('artifact_id') == artifact['id'] and
                previous.get('version') == artifact.get('version'))
    action = 'reopen' if project.get('state') == 'final' or approved else 'approve'
    label = 'Reopen for changes' if action == 'reopen' else {
        'spoken_cut': 'Approve spoken cut', 'storyboard': 'Approve storyboard',
        'final': 'Approve section & mark final' if project.get('format') == 'presentation' else 'Approve & mark final',
    }.get(kind, 'Approve checkpoint')
    return {'action': action, 'kind': kind, 'label': label, 'artifact_id': artifact['id'],
            'version': artifact.get('version', ''), 'checkpoint': artifact.get('label', 'Review'),
            'revision': revision(project), 'decided_at': previous.get('at'),
            'enabled': not project.get('stale') and artifact.get('available', True) and
                       artifact['type'] in ['video', 'board', 'carousel'] and artifact.get('role') != 'history' and
                       kind in ['spoken_cut', 'storyboard', 'final']}


def public_index():
    with STATE_LOCK:
        return _public_index()


def _public_index():
    data = copy.deepcopy(registry())
    for project in data['projects']:
        registered = files(project)
        def expose(record):
            try:
                resolve(project, record['path'])
                record['url'] = f"/project-assets/{project['id']}/{hashlib.sha256(record['path'].encode()).hexdigest()}"
                record['available'] = True
            except (OSError, ValueError):
                record['available'] = False
                record.pop('url', None)
        project['stale'] = False
        for note in project.get('source_notes', []):
            expose(note)
            try:
                if digest(resolve(project, note['path'])) != note.get('sha256'):
                    project['stale'] = True
            except (OSError, ValueError):
                project['stale'] = True
        if project.get('cover_path'):
            cover = {'path': project['cover_path']}
            expose(cover)
            project['cover'] = cover.get('url', '')
        for artifact in project.get('artifacts', []):
            if artifact.get('path'):
                expose(artifact)
            for frame in artifact.get('frames', []):
                expose(frame)
            for download in artifact.get('downloads', []):
                expose(download)
            if artifact.get('frames'):
                artifact['available'] = all(f['available'] for f in artifact['frames'])
        # A draft created from the studio UI (Task 7) has no artifacts yet: there is
        # nothing to review, so skip the primary-artifact lookups below rather than
        # crash on an empty `artifacts` list.
        if not project.get('artifacts'):
            project['review'] = None
            continue
        # Compute the revision from the raw entry, never from response-only URLs/availability.
        raw = next(p for p in registry()['projects'] if p['id'] == project['id'])
        project['review'] = review_options(raw)
        project['review']['enabled'] = project['review']['enabled'] and not project['stale']
        primary = next(a for a in project['artifacts'] if a['id'] == project['primary_artifact'])
        project['review']['enabled'] = project['review']['enabled'] and primary.get('available', False)
        if any(not d['available'] for d in primary.get('downloads', [])):
            project['review']['enabled'] = False
    return data


def starter_request(project):
    if 'starter_request_id' not in project:
        return None
    value = project['starter_request_id']
    if project.get('format') != 'video' or not isinstance(value, str) or not START_REQUEST.fullmatch(value):
        raise ValueError('Use the copied script starter request ID for a video project')
    return value


COPY_KIND_KEY = {'talking-head': 'dialog.newVideo.kindTalkingHead', 'faceless': 'dialog.newVideo.kindFaceless'}
COPY_LANGUAGE_KEY = {'he': 'dialog.newVideo.languageHebrew', 'en': 'dialog.newVideo.languageEnglish'}


def _read_json(path, fallback):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback
    return data if isinstance(data, type(fallback)) else fallback


def _one_line(value):
    """Collapse every run of whitespace (newlines included) in user text to one space,
    recursively through lists and dicts (choices' effects)."""
    if isinstance(value, str):
        return ' '.join(value.split())
    if isinstance(value, list):
        return [_one_line(v) for v in value]
    if isinstance(value, dict):
        return {k: _one_line(v) for k, v in value.items()}
    return value


def starter_request_text(project_id, lang=None):
    """The "copy to chat" request for one project (Task 15), in the UI language.

    The quiet fallback next to "Send to Claude": the same skill command the headless runner
    starts (/<skill> projects/<id>), plus everything the creator chose in the studio -- the
    choices (rendered with the same labels as the brief's choices block), the look's style
    card path, the presenter look (once: Task 12's choices block lists it with its id), the video language and every material's tag and note --
    so a pasted request works even without the runner. starter_request() above stays the
    starter-request-ID validator register.py relies on; its ID is included here when set.
    Raises LookupError for an unknown project."""
    import choices
    import claude_runner
    import library
    if not isinstance(project_id, str) or not TOKEN.fullmatch(project_id):
        raise LookupError('Unknown project')
    project = next((p for p in registry()['projects'] if p.get('id') == project_id), None)
    if project is None:
        raise LookupError('Unknown project')
    lang = lang if lang in ('he', 'en') else library.ui_language()
    strings = _read_json(BASE / 'dist' / 'i18n' / f'{lang}.json', {})

    def t(key, **values):
        text = strings.get(key, key)
        for name, value in values.items():
            text = text.replace('{' + name + '}', str(value))
        return text

    root = STUDIO / 'projects' / project_id
    folder = 'projects/' + project_id
    # Free text the creator typed (title, "something else?", material notes, effect cues) is
    # collapsed onto one line: a multi-line note is kept whole instead of cut at its first line,
    # and can't start a line of its own (e.g. a second slash command).
    picked = {k: _one_line(v) for k, v in _read_json(root / 'choices.json', {}).items() if k != '_seq'}
    skill = claude_runner.SKILL_BY_KIND.get(project.get('kind'))
    # The skill command goes first, so pasting the whole text into Claude Code runs it.
    lines = [f'/{skill} {folder}'] if skill else []
    lines += [t('claude.copy.intro', title=_one_line(project.get('title', project_id))),
              t('claude.copy.reply'), '', t('claude.copy.details')]
    if project.get('kind') in COPY_KIND_KEY:
        lines.append('- ' + t('claude.copy.kind', kind=t(COPY_KIND_KEY[project['kind']])))
    if project.get('video_language') in COPY_LANGUAGE_KEY:
        lines.append('- ' + t('claude.copy.videoLanguage', language=t(COPY_LANGUAGE_KEY[project['video_language']])))
    lines.append('- ' + t('claude.copy.brief', path=folder + '/brief.md'))
    look = picked.get('look')
    if isinstance(look, str) and look.startswith('ref:') and TOKEN.fullmatch(look[4:]):
        card = STUDIO / 'references' / look[4:] / 'style-card.md'
        path = f'references/{look[4:]}/' + ('style-card.md' if card.is_file() else '')
        lines.append('- ' + t('claude.copy.lookReference', path=path))
    elif isinstance(look, str) and TOKEN.fullmatch(look):
        lines.append('- ' + t('claude.copy.lookCard', path=f'looks/{look}/card.md'))
    try:
        block = choices.render_block(lang, picked)
        chosen = [row for row in block.splitlines() if row.startswith('- ')]
    except (choices.ChoicesError, OSError, ValueError, KeyError, TypeError, AttributeError):
        chosen = []
    if chosen:
        lines += ['', t('claude.copy.choices')] + chosen
    items = [i for i in _read_json(root / 'materials.json', {}).get('items', []) if isinstance(i, dict)]
    rows = []
    for item in items:
        if not isinstance(item.get('file'), str):
            continue
        parts = [item['file']]
        if isinstance(item.get('tag'), str):
            parts.append(t('materials.tag.' + item['tag']))
        if isinstance(item.get('note'), str) and item['note'].strip():
            parts.append(_one_line(item['note']))
        if item.get('owned') is True:
            parts.append(t('materials.ownedLabel'))
        rows.append('- ' + ' · '.join(parts))
    if rows:
        lines += ['', t('claude.copy.materials')] + rows
    request = project.get('starter_request_id')
    if isinstance(request, str) and START_REQUEST.fullmatch(request):
        lines += ['', t('claude.copy.starterId', id=request)]
    return '\n'.join(lines) + '\n'


def validate():
    projects = registry()['projects']
    ids = [p['id'] for p in projects]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate project ID')
    requests = [value for project in projects if (value := starter_request(project))]
    if len(requests) != len(set(requests)):
        raise ValueError('Duplicate script starter request ID')
    for project in projects:
        artifact_ids = [a['id'] for a in project['artifacts']]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError('Duplicate artifact ID')
        # A draft (Task 7) has no artifacts yet, so there is no primary one to check.
        if project['artifacts'] and project['primary_artifact'] not in artifact_ids:
            raise ValueError('Unknown primary artifact')
        for relative in files(project):
            resolve(project, relative)
        for note in project['source_notes']:
            if note['sha256'] != digest(resolve(project, note['path'])):
                raise ValueError(f"Stale navigation: {project['id']} / {note['path']}")
    return {'projects': len(projects), 'artifacts': sum(len(p['artifacts']) for p in projects),
            'files': sum(len(files(p)) for p in projects)}


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] != 'validate':
        raise SystemExit('Usage: python style-library/project_index.py validate')
    print(json.dumps(validate()))
