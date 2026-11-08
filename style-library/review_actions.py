"""Explicit local review decisions. Never render, publish, or approve on a GET request."""
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import uuid
import math
import shutil
import subprocess
import project_index as index
from library import BASE, project_reference_candidates
from atomic import atomic_write

CATALOG = BASE / 'catalog.json'
JOURNALS = BASE / 'runtime' / 'review-actions'
START = '<!-- studio-review:start -->'
END = '<!-- studio-review:end -->'


class ReviewError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def json_bytes(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode()


def write_target(project, filename):
    root = (index.STUDIO / 'projects' / project['id']).resolve()
    if root.parent != (index.STUDIO / 'projects').resolve() or root.parent.parent != index.STUDIO.resolve():
        raise ReviewError('The project folder needs to be relinked safely.')
    target = (root / filename).resolve()
    if target != root / filename or target.parent != root or target.suffix not in ['.md', '.json']:
        raise ReviewError('The decision file leaves this project.')
    return target


def check_storage():
    base = BASE.resolve()
    if (index.REGISTRY.resolve() != base / 'projects.json' or CATALOG.resolve() != base / 'catalog.json' or
        (base / 'runtime').resolve().parent != base or
        JOURNALS.resolve().parent != (base / 'runtime').resolve()):
        raise ReviewError('The studio decision files need safe local paths before saving.')


def commit(changes, body, expected=None):
    """Per-file atomic replacement, private recovery copies, rollback on any ordinary failure."""
    for target, before_hash in (expected or {}).items():
        if (index.digest(target) if target.exists() else None) != before_hash:
            raise ReviewError('Project or library files changed while saving. Refresh before trying again.')
    JOURNALS.mkdir(parents=True, exist_ok=True)
    folder = JOURNALS / body['request_id']
    folder.mkdir(mode=0o700)
    records, originals = [], {}
    for i, (target, after) in enumerate(changes.items()):
        if not target.resolve().is_relative_to(index.STUDIO.resolve()):
            raise ReviewError('A saved decision would leave the studio.')
        before = target.read_bytes() if target.exists() else None
        originals[target] = before
        backup = f'before-{i}.data'
        if before is not None:
            (folder / backup).write_bytes(before)
        records.append({'path': target.resolve().relative_to(index.STUDIO.resolve()).as_posix(), 'backup': backup,
                        'existed': before is not None,
                        'before_sha256': hashlib.sha256(before).hexdigest() if before is not None else None,
                        'after_sha256': hashlib.sha256(after).hexdigest()})
    manifest = {'state': 'prepared', 'request': body, 'files': records}
    journal = folder / 'transaction.json'
    atomic_write(journal, json_bytes(manifest))
    written = []
    try:
        for target, after in changes.items():
            atomic_write(target, after)
            written.append(target)
        manifest['state'] = 'committed'
        atomic_write(journal, json_bytes(manifest))
    except Exception as error:
        try:
            for target in reversed(written):
                before = originals[target]
                if before is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic_write(target, before)
            manifest['state'] = 'rolled_back'
            manifest['error'] = type(error).__name__
            atomic_write(journal, json_bytes(manifest))
        except Exception:
            # The prepared journal and originals remain for explicit recovery after a crash/disk fault.
            raise ReviewError('The decision could not finish. Ask your assistant to recover the saved approval transaction.', 503)
        raise ReviewError('The decision could not be saved. Previous files were restored; try again.', 503)


def recover(request_id):
    """Explicit recovery only; refuse to overwrite any later human/agent edits."""
    if str(uuid.UUID(request_id)) != request_id:
        raise ValueError('Use a transaction UUID')
    with index.STATE_LOCK:
        check_storage()
        folder = JOURNALS / request_id
        manifest = json.loads((folder / 'transaction.json').read_text(encoding='utf-8'))
        if manifest['state'] != 'prepared':
            raise ValueError('Only an unfinished transaction needs recovery')
        for record in manifest['files']:
            target = (index.STUDIO / record['path']).resolve()
            if not target.is_relative_to(index.STUDIO.resolve()):
                raise ValueError('Recovery path leaves studio')
            actual = index.digest(target) if target.exists() else None
            if actual not in [record['before_sha256'], record['after_sha256']]:
                raise ValueError('A file was edited later. Reconcile it manually before recovery.')
            if record['existed'] and index.digest(folder / record['backup']) != record['before_sha256']:
                raise ValueError('Recovery copy changed')
        for record in reversed(manifest['files']):
            target = (index.STUDIO / record['path']).resolve()
            if record['existed']:
                atomic_write(target, (folder / record['backup']).read_bytes())
            else:
                target.unlink(missing_ok=True)
        manifest['state'] = 'rolled_back'
        atomic_write(folder / 'transaction.json', json_bytes(manifest))
        return {'recovered': request_id}


def freeze_files(project, artifact):
    result = []
    for relative in index.primary_files(artifact):
        path = index.resolve(project, relative)
        result.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': index.digest(path)})
    if not result:
        raise ReviewError('This checkpoint has no registered files to approve.')
    return result


def promote_video(data, entry, project, artifact, event, changes, expected):
    """Promote a registered review, keeping prior media/analysis and exact technique sources."""
    old_path = entry.get('media_path')
    prior = next((a for a in project['artifacts'] if a.get('version') == entry.get('version') and
                  a.get('type') == 'video' and (Path('projects') / project['id'] / a['path']).as_posix() == old_path), None)
    if entry.get('collection') != 'mine' or entry.get('project_id', project['id']) != project['id'] or prior is None:
        raise ReviewError('The saved library source does not match this project’s version history. Ask your assistant to check it.')
    old_file = index.resolve(project, prior['path'])
    old_hash = index.digest(old_file)
    expected[old_file] = old_hash
    linked = [x for t in data.get('techniques', []) for x in t.get('examples', []) if x.get('style_id') == entry['id']]
    if any(x.get('source_version') != entry['version'] or x.get('source_path') != old_path or
           x.get('source_sha256') != old_hash for x in linked):
        raise ReviewError('This video’s technique examples need rechecking before final approval. Ask your assistant to reconcile them.')
    key = hashlib.sha256(json_bytes([entry['version'], old_path, old_hash])).hexdigest()[:16]
    archive_id = entry['id'] + '-saved-' + key
    archived = next((e for e in data['entries'] if e['id'] == archive_id), None)
    if archived is not None:
        if (archived.get('archived_from'), archived.get('version'), archived.get('media_path'), archived.get('source_sha256')) != (entry['id'], entry['version'], old_path, old_hash):
            raise ReviewError('A saved library version conflicts with this source. Ask your assistant to check it.')
    else:
        archived = copy.deepcopy(entry)
        archived.update(id=archive_id, archived_from=entry['id'], source_sha256=old_hash)
        data['entries'].append(archived)
    for example in linked:
        example['style_id'] = archive_id
    try: source = index.resolve(project, artifact.get('poster_path') or project.get('cover_path', ''))
    except (OSError, ValueError): raise ReviewError('This version needs a saved cover image before final approval.')
    if source.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.webp']:
        raise ReviewError('This version needs a saved cover image before final approval.')
    relative = f"assets/posters/{project['id']}-{artifact.get('version', 'final').lower()}-approved{source.suffix.lower()}"
    poster = BASE / 'dist' / relative
    if poster.resolve() != poster.absolute() or poster.parent.resolve() != (BASE / 'dist/assets/posters').resolve():
        raise ReviewError('The library poster folder needs repair.')
    poster.parent.mkdir(parents=True, exist_ok=True)
    image = source.read_bytes()
    if poster.exists() and poster.read_bytes() != image:
        raise ReviewError('That version’s poster already exists. Use a new version.')
    changes[poster] = image
    expected[poster] = index.digest(poster) if poster.exists() else None
    expected[source] = hashlib.sha256(image).hexdigest()
    path = index.resolve(project, artifact['path'])
    duration = artifact.get('duration')
    if shutil.which('ffprobe'):
        try:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)],
                                   capture_output=True, text=True, timeout=5)
            if probe.returncode == 0: duration = float(json.loads(probe.stdout)['format']['duration'])
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired): pass
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        duration = None
    from project_tools import source as editor_source
    composition = editor_source(project, artifact, index.STUDIO / 'projects' / project['id'])
    entry.update(version=artifact['version'], media_path=path.relative_to(index.STUDIO).as_posix(), poster=relative,
                 duration=duration, moments=[], source_url=None, source_sha256=next(f['sha256'] for f in event['files'] if f['path'] == artifact['path']),
                 summary=artifact.get('description') or project.get('summary', ''), subtitle=f"{project.get('subtitle', project['title'])} · Final {artifact['version']}",
                 state=f"Final {artifact['version']}", notes=[(Path('projects') / project['id'] / n['path']).as_posix() for n in project['source_notes']],
                 evidence=f"Explicit studio approval of {artifact['version']}. Earlier style analysis is preserved in {archive_id}; timed moments have not been inferred for the new version.")
    for field in ['poster_at', 'approval', 'composition']:
        entry.pop(field, None)
    if composition: entry['composition'] = (composition / 'index.html').relative_to(index.STUDIO).as_posix()


def final_reference(project, artifact, event, changes, expected):
    # A fresh install has no catalog.json until something is saved to the library.
    catalog_bytes = CATALOG.read_bytes() if CATALOG.exists() else None
    expected[CATALOG.resolve()] = hashlib.sha256(catalog_bytes).hexdigest() if catalog_bytes is not None else None
    data = json.loads(catalog_bytes) if catalog_bytes is not None else {'schema_version': 4, 'entries': [], 'techniques': []}
    reference_id = project.get('reference_id')
    entry = next((e for e in data['entries'] if e['id'] == reference_id), None)
    if entry is not None and entry.get('project_id', project['id']) != project['id']:
        raise ReviewError('The saved library source belongs to another project. Ask your assistant to check it.')
    if entry is None and not reference_id:
        matches = project_reference_candidates(project, data)
        if len(matches) > 1:
            raise ReviewError('More than one library entry matches this checkpoint. Ask your assistant to reconcile them.')
        if matches:
            entry = matches[0]
            project['reference_id'] = entry['id']
    if entry is None:
        seed = project.get('reference_entry')
        if not isinstance(seed, dict) or not index.TOKEN.fullmatch(seed.get('id', '')):
            raise ReviewError('Ask your assistant to prepare this project’s library entry before marking it final.')
        if any(e['id'] == seed['id'] for e in data['entries']):
            raise ReviewError('This library ID is already in use. Ask your assistant to reconcile it.')
        entry = copy.deepcopy(seed)
        entry.setdefault('created_at', event['at'])
        required = ['title', 'subtitle', 'creator', 'creator_id', 'summary', 'tags', 'palette', 'traits',
                    'keep', 'avoid', 'moments', 'notes', 'version', 'collection', 'evidence']
        if any(k not in entry for k in required) or not isinstance(entry['traits'], dict):
            raise ReviewError('The prepared library entry is incomplete. Ask your assistant to finish it.')
        for key in ['tags', 'palette', 'keep', 'avoid', 'moments', 'notes']:
            if not isinstance(entry[key], list):
                raise ReviewError('The prepared library entry needs valid lists.')
        for relative in [*entry['notes'], entry.get('composition')]:
            if not relative:
                continue
            path = (index.STUDIO / relative).resolve()
            root = (index.STUDIO / 'projects' / project['id']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ReviewError('A prepared library source is unavailable or outside this project.')
        source = index.resolve(project, project['reference_poster_source'])
        if source.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.webp']:
            raise ReviewError('The library poster needs an actual saved image.')
        relative = f"assets/posters/{project['id']}-{artifact.get('version', 'final').lower()}-approved{source.suffix.lower()}"
        poster = (BASE / 'dist' / relative).resolve()
        if not poster.is_relative_to((BASE / 'dist' / 'assets' / 'posters').resolve()):
            raise ReviewError('The library poster leaves the registered poster folder.')
        poster.parent.mkdir(parents=True, exist_ok=True)
        if poster.exists() and poster.read_bytes() != source.read_bytes():
            raise ReviewError('That version’s poster already exists. Use a new version.')
        changes[poster] = source.read_bytes()
        expected[poster] = index.digest(poster) if poster.exists() else None
        entry['poster'] = relative
        data['entries'].insert(0, entry)
        project['reference_id'] = entry['id']
    if artifact['type'] == 'video' and entry.get('version') != artifact.get('version'):
        promote_video(data, entry, project, artifact, event, changes, expected)
    if entry['collection'] != 'mine' or entry['version'] != artifact.get('version'):
        raise ReviewError('The library points to another version. Ask your assistant to reconcile it before approval.')
    if artifact['type'] == 'video':
        media_path = (Path('projects') / project['id'] / artifact['path']).as_posix()
        if entry.get('media_path') != media_path:
            raise ReviewError('The library video differs from this checkpoint. Ask your assistant to reconcile it.')
        actual_hash = next(f['sha256'] for f in event['files'] if f['path'] == artifact['path'])
        if entry.get('source_sha256') is not None and entry['source_sha256'] != actual_hash:
            raise ReviewError('The saved library video hash differs from this checkpoint. Ask your assistant to reconcile it.')
        for technique in data.get('techniques', []):
            for example in technique.get('examples', []):
                if example.get('style_id') == entry['id'] and (
                    example.get('source_version') != entry['version'] or example.get('source_path') != media_path or
                    example.get('source_sha256') != actual_hash):
                    raise ReviewError('This video’s technique examples need rechecking before final approval. Ask your assistant to reconcile them.')
    elif artifact['type'] == 'carousel':
        slide_paths = [(Path('projects') / project['id'] / f['path']).as_posix() for f in artifact['frames']]
        if [f['path'] for f in entry.get('slides', [])] != slide_paths:
            raise ReviewError('The library slide set differs from this checkpoint.')
    elif entry.get('project_id') != project['id']:
        raise ReviewError('The library needs a link to this approved project’s assets.')
    entry.update(delivery_status='final', review_status='preferred')
    entry['project_id'] = project['id']
    entry['approval'] = {k: event[k] for k in ['request_id', 'at', 'artifact_id', 'version', 'files']}
    data['updated'] = event['at'][:10]
    changes[CATALOG.resolve()] = json_bytes(data)


def apply_decision(body):
    if not isinstance(body, dict) or set(body) != {'project_id', 'artifact_id', 'action', 'revision', 'request_id'}:
        raise ReviewError('Choose a project checkpoint and action.', 400)
    if not all(isinstance(v, str) for v in body.values()):
        raise ReviewError('Invalid review action.', 400)
    try:
        if str(uuid.UUID(body['request_id'])) != body['request_id']:
            raise ValueError()
    except ValueError:
        raise ReviewError('Invalid review request ID.', 400)
    if body['action'] not in ['approve', 'reopen'] or not re.fullmatch(r'[0-9a-f]{64}', body['revision']):
        raise ReviewError('Invalid review action or revision.', 400)
    with index.STATE_LOCK:
        check_storage()
        existing = JOURNALS / body['request_id'] / 'transaction.json'
        if existing.exists():
            saved = json.loads(existing.read_text(encoding='utf-8'))
            if saved['request'] == body and saved['state'] == 'committed':
                return {'projects': index.public_index()['projects'], 'library_changed': True, 'duplicate': True}
            raise ReviewError('This review request has already been used. Refresh before trying again.')
        for path in JOURNALS.glob('*/transaction.json'):
            if json.loads(path.read_text(encoding='utf-8'))['state'] == 'prepared':
                raise ReviewError('An earlier approval needs recovery. Ask your assistant to check the saved transaction.', 503)
        registry_bytes = index.REGISTRY.read_bytes()
        data = json.loads(registry_bytes)
        expected = {index.REGISTRY.resolve(): hashlib.sha256(registry_bytes).hexdigest()}
        project = next((p for p in data['projects'] if p['id'] == body['project_id']), None)
        if project is None:
            raise ReviewError('That project is not registered.', 404)
        current = next(p for p in index.public_index()['projects'] if p['id'] == project['id'])
        options = current['review']
        if body['revision'] != options['revision'] or not options['enabled']:
            raise ReviewError('The project or files changed. Refresh and read the current checkpoint before approving.')
        if body['artifact_id'] != project['primary_artifact'] or body['action'] != options['action']:
            raise ReviewError('Only the current checkpoint can receive this action. Refresh and review that version.')
        artifact = next(a for a in project['artifacts'] if a['id'] == project['primary_artifact'])
        for note in project['source_notes']:
            expected[index.resolve(project, note['path'])] = note['sha256']
        at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        frozen = freeze_files(project, artifact)
        event = {'request_id': body['request_id'], 'action': body['action'], 'kind': options['kind'],
                 'artifact_id': artifact['id'], 'label': artifact['label'], 'version': artifact.get('version', ''),
                 'at': at, 'actor': 'Local studio owner', 'files': frozen}
        changes = {}
        state_file = write_target(project, 'approval-state.json')
        expected[state_file] = index.digest(state_file) if state_file.exists() else None
        status = write_target(project, 'STATUS.md')
        expected.setdefault(status, index.digest(status) if status.exists() else None)
        decisions = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {'schema_version': 1, 'events': []}
        decisions['events'].append(event)
        decisions['current'] = event
        changes[state_file] = json_bytes(decisions)
        checkpoint = f"{artifact['label']} {artifact.get('version', '')}".strip()
        if body['action'] == 'reopen':
            reopened_stage = {'spoken_cut': 'assembly', 'storyboard': 'storyboard'}.get(options['kind'], 'refine')
            project.update(state='review', stage=reopened_stage, review_action='reopened')
            message = f'Changes requested after {checkpoint}. The approved files remain available.'
            project['next_step'] = 'Describe the changes in your editing chat. Keep the accepted version while a new review is built.'
            project['baseline'] = f'{checkpoint} was approved previously. A new round of changes is open.'
            title = 'Reopened for changes'
        elif options['kind'] == 'final':
            final_reference(project, artifact, event, changes, expected)
            project.update(state='final', stage='final')
            artifact['role'] = 'final'
            message = f'{checkpoint} was approved and marked final in the studio.'
            project['next_step'] = 'Final assets are ready and saved in the Reference Library. Reopen here for another round of changes.'
            title = 'Final approved'
        else:
            next_stage = 'storyboard' if options['kind'] == 'spoken_cut' else 'edit'
            project.update(state='in_progress', stage=next_stage)
            message = f'{checkpoint} was approved. The next step is {"storyboarding" if next_stage == "storyboard" else "editing"}.'
            project['next_step'] = f'Continue in your editing chat to start {"the visual storyboard" if next_stage == "storyboard" else "the designed edit"}.'
            title = 'Checkpoint approved'
        if body['action'] == 'approve':
            project.pop('review_action', None)
        project['review_decision'] = {k: v for k, v in event.items() if k != 'files'}
        project['summary'] = message
        project['synced_on'] = at[:10]
        old_status = status.read_text(encoding='utf-8') if status.exists() else '# ' + project['title'] + '\n'
        old_status = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n*', '', old_status, flags=re.S)
        block = f'{START}\n## Current studio review decision\n\n**{title}: {checkpoint}** — {at}.\n\n{message} {project["next_step"]}\n\nDecision: {event["request_id"]}. Exact file hashes and prior decisions: `approval-state.json`. This records review approval, not publication. This section supersedes older review-state wording for this checkpoint; production notes below are retained.\n{END}\n\n'
        changes[status] = (block + old_status).encode()
        notes = next((n for n in project['source_notes'] if re.fullmatch(r'review-notes(?:-v[0-9]+)?\.md', n['path'])), None)
        if notes is None:
            raise ReviewError('Register this project’s review-notes file before saving an approval.')
        review_notes = write_target(project, notes['path'])
        old_notes = review_notes.read_text(encoding='utf-8') if review_notes.exists() else '# Review notes\n'
        changes[review_notes] = (old_notes.rstrip() + f'\n\n## Studio decision — {at}\n\n{title}: **{checkpoint}**. {message}\n\nUser action in the local studio. Event `{event["request_id"]}`; exact files/hashes in approval-state.json. {project["next_step"]} No publishing action.\n').encode()
        active = write_target(project, 'active-edit.json')
        if active.exists():
            active_bytes = active.read_bytes()
            expected.setdefault(active, hashlib.sha256(active_bytes).hexdigest())
            pointers = json.loads(active_bytes)
            pointers['studio_review'] = project['review_decision']
            pointers['status'] = message
            changes[active] = json_bytes(pointers)
        for label, path in [('Current status', 'STATUS.md'), ('Saved review decisions', 'approval-state.json')]:
            if not any(n['path'] == path for n in project['source_notes']):
                project['source_notes'].append({'label': label, 'path': path})
        for note in project['source_notes']:
            target = ((index.STUDIO / 'projects' / project['id']) / note['path']).resolve()
            if target not in changes:
                target = index.resolve(project, note['path'])
            content = changes.get(target)
            note['sha256'] = hashlib.sha256(content).hexdigest() if content is not None else index.digest(target)
        changes[index.REGISTRY.resolve()] = json_bytes(data)
        # Recheck after hashing media and staging data, before any production metadata is changed.
        if index.revision(next(p for p in index.registry()['projects'] if p['id'] == project['id'])) != body['revision']:
            raise ReviewError('The checkpoint changed while saving. Refresh before trying again.')
        commit(changes, body, expected)
        return {'projects': index.public_index()['projects'], 'library_changed': body['action'] == 'approve' and options['kind'] == 'final'}


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != 'recover':
        raise SystemExit('Usage: python style-library/review_actions.py recover TRANSACTION-UUID')
    print(json.dumps(recover(sys.argv[2])))
