"""Project-local review notes. Saving feedback never approves or starts an edit."""
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid
import copy
import project_index as index
import review_actions as storage


class FeedbackError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def project_for(project_id):
    if not isinstance(project_id, str) or not index.TOKEN.fullmatch(project_id):
        raise FeedbackError('Choose a registered project.', 404)
    project = next((p for p in index.registry()['projects'] if p['id'] == project_id), None)
    if project is None:
        raise FeedbackError('This project is no longer registered.', 404)
    root = index.STUDIO / 'projects' / project_id
    if root.resolve() != root.absolute():
        raise FeedbackError('The project folder needs a safe local path before saving feedback.', 409)
    return project


def context_revision(project, artifact):
    parts = [json.dumps(artifact, sort_keys=True)]
    for name in index.primary_files(artifact):
        path = index.resolve(project, name)
        info = path.stat()
        parts.append(f'{name}:{info.st_size}:{info.st_mtime_ns}')
    return hashlib.sha256('\n'.join(parts).encode()).hexdigest()


def read(project):
    path = storage.write_target(project, 'review-feedback.json')
    if not path.exists():
        return path, {'schema_version': 1, 'project_id': project['id'], 'notes': []}
    if path.stat().st_size > 4_000_000:
        raise FeedbackError('The feedback file needs attention before adding more notes.', 503)
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('project_id') != project['id'] or
            data.get('schema_version') != 1 or not isinstance(data.get('notes'), list)):
        raise FeedbackError('The saved feedback needs repair. Existing notes were preserved.', 503)
    return path, data


def read_links(project):
    path = storage.write_target(project, 'review-feedback-links.json')
    if not path.exists():
        return path, {'schema_version': 1, 'project_id': project['id'], 'links': {}}
    if path.stat().st_size > 4_000_000:
        raise FeedbackError('The feedback links file needs attention. Your notes are preserved.', 503)
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema_version') != 1 or
            data.get('project_id') != project['id'] or not isinstance(data.get('links'), dict)):
        raise FeedbackError('Saved feedback links need repair. Your notes are preserved.', 503)
    return path, data


def note_revision(note):
    """Optimistic write token, including assistant-applied status and history."""
    return hashlib.sha256(storage.json_bytes({k: v for k, v in note.items() if k != 'revision'})).hexdigest()


def content_revision(note):
    # Applying a note does not change the instruction shared in a copied link.
    return hashlib.sha256(storage.json_bytes({k: note.get(k) for k in
        ('id', 'artifact_id', 'text', 'time', 'frame', 'context_revision')})).hexdigest()


def current(project_id, selection_id=None):
    with index.STATE_LOCK:
        project = project_for(project_id)
        _, data = read(project)
        contexts = {}
        for artifact in project['artifacts']:
            try:
                contexts[artifact['id']] = context_revision(project, artifact)
            except (ValueError, OSError):
                pass
        result = {**data, 'contexts': contexts, 'notes': [
            {**n, 'revision': note_revision(n), 'content_revision': content_revision(n)} for n in data['notes']]}
        if selection_id is not None:
            if (not isinstance(selection_id, str) or len(selection_id) != 24 or
                    any(c not in '0123456789abcdef' for c in selection_id)):
                raise FeedbackError('This feedback link is unavailable.', 404)
            _, links = read_links(project)
            selection = links['links'].get(selection_id)
            if (not isinstance(selection, dict) or selection.get('project_id') != project_id or
                    selection.get('id') != selection_id or not isinstance(selection.get('note_ids'), list) or
                    not selection['note_ids'] or any(not isinstance(n, str) for n in selection['note_ids']) or
                    len(selection['note_ids']) != len(set(selection['note_ids'])) or
                    not set(selection['note_ids']).issubset({n['id'] for n in data['notes']})):
                raise FeedbackError('This saved feedback selection is unavailable. Your other notes are preserved.', 404)
            payload = {k: selection.get(k) for k in ['project_id', 'artifact_id', 'artifact_ids', 'note_ids']}
            if 'note_revisions' in selection:
                payload['note_revisions'] = selection['note_revisions']
            selected_ids = set(selection['note_ids'])
            selected = [n for n in data['notes'] if n['id'] in selected_ids]
            if (hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24] != selection_id or
                    payload['artifact_ids'] != sorted({n['artifact_id'] for n in selected}) or
                    (payload['artifact_id'] is not None and any(n['artifact_id'] != payload['artifact_id'] for n in selected))):
                raise FeedbackError('This saved feedback selection needs repair. Your notes are preserved.', 404)
            revisions = selection.get('note_revisions')
            if revisions is not None and (not isinstance(revisions, dict) or set(revisions) != selected_ids):
                raise FeedbackError('This saved feedback selection needs repair. Your notes are preserved.', 404)
            changed = [n['id'] for n in selected if n.get('deleted_at') or
                       (revisions is not None and revisions[n['id']] != content_revision(n)) or
                       (revisions is None and any(a.get('action') == 'edit' for a in n.get('history', [])))]
            if changed:
                raise FeedbackError('Selected feedback was edited or deleted after copying. Review and copy again. Notes: ' + ', '.join(changed), 409)
            result['selection'] = selection
        return result


def check_writes():
    storage.check_storage()
    for journal in storage.JOURNALS.glob('*/transaction.json'):
        if json.loads(journal.read_text(encoding='utf-8')).get('state') == 'prepared':
            raise FeedbackError('A previous save needs recovery before saving feedback.', 503)


def save_link(body):
    """Save an immutable note selection; never copy note text or change a note's state."""
    if not isinstance(body, dict) or set(body) not in (
            {'project_id', 'artifact_id', 'note_ids'}, {'project_id', 'artifact_id', 'note_ids', 'note_revisions'}):
        raise FeedbackError('Choose a valid saved feedback selection.', 400)
    ids = body['note_ids']
    if not isinstance(ids, list) or not 1 <= len(ids) <= 5000:
        raise FeedbackError('Choose saved feedback notes first.', 400)
    try:
        if any(not isinstance(i, str) or str(uuid.UUID(i)) != i for i in ids) or len(ids) != len(set(ids)):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise FeedbackError('Choose valid saved feedback notes.', 400)
    with index.STATE_LOCK:
        check_writes()
        project = project_for(body['project_id'])
        artifact_id = body['artifact_id']
        if artifact_id is not None and (not isinstance(artifact_id, str) or
                not any(a['id'] == artifact_id for a in project['artifacts'])):
            raise FeedbackError('This version is unavailable. Reopen the project before copying.', 409)
        notes_path = storage.write_target(project, 'review-feedback.json')
        notes_before = index.digest(notes_path) if notes_path.exists() else None
        _, notes = read(project)
        wanted = set(ids)
        selected = [n for n in notes['notes'] if n['id'] in wanted]
        revisions = {n['id']: content_revision(n) for n in selected}
        if (len(selected) != len(ids) or any(n['status'] != 'open' or n.get('deleted_at') for n in selected) or
                ('note_revisions' in body and body['note_revisions'] != revisions) or
                (artifact_id is not None and any(n['artifact_id'] != artifact_id for n in selected))):
            raise FeedbackError('The saved notes changed. Reopen this version, review the notes and copy again.', 409)
        payload = {'project_id': project['id'], 'artifact_id': artifact_id,
                   'artifact_ids': sorted({n['artifact_id'] for n in selected}), 'note_ids': sorted(ids),
                   'note_revisions': revisions}
        token = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
        path = storage.write_target(project, 'review-feedback-links.json')
        before = index.digest(path) if path.exists() else None
        _, data = read_links(project)
        existing = data['links'].get(token)
        if existing is not None:
            if not isinstance(existing, dict) or existing.get('id') != token or any(existing.get(k) != v for k, v in payload.items()):
                raise FeedbackError('This feedback link needs attention. Existing records were preserved.', 503)
            return existing
        record = {**payload, 'id': token, 'created_at': datetime.now(timezone.utc).isoformat()}
        data['links'][token] = record
        encoded = storage.json_bytes(data)
        if len(encoded) > 4_000_000:
            raise FeedbackError('Ask your assistant to archive old feedback links first.', 409)
        storage.commit({path: encoded}, {'request_id': str(uuid.uuid4()), 'operation': 'feedback-link',
                       'project_id': project['id'], 'selection_id': token},
                       {path: before, notes_path: notes_before})
        return record


def save(body):
    required = {'project_id', 'artifact_id', 'context_revision', 'text', 'time', 'frame', 'request_id'}
    if not isinstance(body, dict) or set(body) != required:
        raise FeedbackError('Use a valid feedback request.', 400)
    try:
        if str(uuid.UUID(body['request_id'])) != body['request_id']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise FeedbackError('Use a valid save request.', 400)
    text = body['text']
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or
            any(ord(c) < 32 and c not in '\n\t\r' for c in text)):
        raise FeedbackError('Write a note of up to 2,000 characters.', 400)
    with index.STATE_LOCK:
        check_writes()
        project = project_for(body['project_id'])
        artifact = next((a for a in project['artifacts'] if a['id'] == body['artifact_id']), None)
        if artifact is None:
            raise FeedbackError('This version is no longer registered. Refresh the project.', 409)
        path, data = read(project)
        existing = next((n for n in data['notes'] if n['id'] == body['request_id']), None)
        if existing:
            if existing.get('request') != body:
                raise FeedbackError('This save request was already used for a different note.', 409)
            return current(project['id'])
        if len(data['notes']) >= 5000:
            raise FeedbackError('Ask your assistant to archive completed feedback first.', 409)
        try:
            revision = context_revision(project, artifact)
        except (ValueError, OSError):
            raise FeedbackError('This version has a missing file. Your note has not been discarded.', 409)
        if revision != body['context_revision']:
            raise FeedbackError('This version changed. Refresh its context before saving your note.', 409)
        time, frame = body['time'], body['frame']
        if artifact['type'] == 'video':
            if (frame is not None or (time is not None and
                    (isinstance(time, bool) or not isinstance(time, (int, float)) or
                     not math.isfinite(time) or not 0 <= time <= 86400))):
                raise FeedbackError('Choose a valid moment in the video.', 400)
        elif artifact.get('frames'):
            if time is not None or type(frame) is not int or not 1 <= frame <= len(artifact['frames']):
                raise FeedbackError('Choose a valid storyboard scene or slide.', 400)
        elif time is not None or frame is not None:
            raise FeedbackError('This note applies to the whole document.', 400)
        before = index.digest(path) if path.exists() else None
        event = {'id': body['request_id'], 'created_at': datetime.now(timezone.utc).isoformat(),
                 'artifact_id': artifact['id'], 'version': artifact.get('version', ''),
                 'label': artifact['label'], 'text': text.strip(), 'time': time, 'frame': frame,
                 'context_revision': revision, 'status': 'open', 'request': body,
                 'source': {'path': artifact.get('path'),
                            'scene_path': artifact['frames'][frame - 1]['path'] if frame else None}}
        data['notes'].append(event)
        encoded = storage.json_bytes(data)
        if len(encoded) > 4_000_000:
            raise FeedbackError('Ask your assistant to archive completed feedback before adding more.', 409)
        storage.commit({path: encoded}, body, {path: before})
        return current(project['id'])


def change(body):
    """Edit or reversibly remove a note without changing its source or application."""
    required = {'project_id', 'note_id', 'revision', 'action', 'request_id'}
    if not isinstance(body, dict) or body.get('action') not in ('edit', 'delete', 'restore'):
        raise FeedbackError('Choose a valid feedback action.', 400)
    if set(body) != required | ({'text'} if body['action'] == 'edit' else set()):
        raise FeedbackError('Use a valid feedback change request.', 400)
    try:
        for key in ('request_id', 'note_id'):
            if str(uuid.UUID(body[key])) != body[key]:
                raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise FeedbackError('Choose a valid saved note and request.', 400)
    revision = body['revision']
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in '0123456789abcdef' for c in revision):
        raise FeedbackError('Refresh this note before changing it.', 400)
    if body['action'] == 'edit':
        text = body['text']
        if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or
                any(ord(c) < 32 and c not in '\n\t\r' for c in text)):
            raise FeedbackError('Write a note of up to 2,000 characters.', 400)
    with index.STATE_LOCK:
        check_writes()
        project = project_for(body['project_id'])
        path = storage.write_target(project, 'review-feedback.json')
        before = index.digest(path) if path.exists() else None
        _, data = read(project)
        for saved in data['notes']:
            for event in saved.get('history', []):
                if event.get('request', {}).get('request_id') == body['request_id']:
                    if event['request'] != body:
                        raise FeedbackError('This change request was already used for another action.', 409)
                    return current(project['id'])
            if saved['id'] == body['request_id']:
                raise FeedbackError('Use a new change request.', 409)
        note = next((n for n in data['notes'] if n['id'] == body['note_id']), None)
        if note is None:
            raise FeedbackError('This saved note is unavailable.', 404)
        if note_revision(note) != revision:
            raise FeedbackError('This note changed in another window or editing chat. Refresh the notes before saving; your draft is preserved.', 409)
        if bool(note.get('deleted_at')) != (body['action'] == 'restore'):
            raise FeedbackError('This note was already deleted or restored. Refresh the notes.', 409)
        stamp = datetime.now(timezone.utc).isoformat()
        snapshot = copy.deepcopy({k: v for k, v in note.items() if k != 'history'})
        note.setdefault('history', []).append({'action': body['action'], 'at': stamp,
                                               'request': body, 'before': snapshot})
        if body['action'] == 'edit':
            note['text'] = body['text'].strip()
            note['updated_at'] = stamp
        elif body['action'] == 'delete':
            note['deleted_at'] = stamp
        else:
            note.pop('deleted_at', None)
        encoded = storage.json_bytes(data)
        if len(encoded) > 4_000_000:
            raise FeedbackError('Feedback history is full. Existing notes were preserved.', 409)
        storage.commit({path: encoded}, body, {path: before})
        return current(project['id'])
