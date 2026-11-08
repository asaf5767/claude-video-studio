"""Optional, versioned project scripts. Saving never starts an edit or changes approval."""
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid
import project_index as index
import review_actions as storage
from feedback import project_for, FeedbackError

LIMIT = 50000


def safe_text(root, relative):
    path = root / relative
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise FeedbackError('This script needs a safe project-local path. Existing files are preserved.', 503)
    if not path.exists(): return path, None
    if not path.is_file() or path.stat().st_size > 200000:
        raise FeedbackError('This script needs attention in your editing chat.', 503)
    return path, path.read_text(encoding='utf-8')


def read(project):
    path = storage.write_target(project, 'script-state.json')
    if not path.exists(): return path, {'schema_version': 1, 'project_id': project['id'], 'current': None, 'versions': []}
    if path.stat().st_size > 8000000: raise FeedbackError('Your script history needs attention in chat. It is preserved.', 503)
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('project_id') != project['id'] or
            not isinstance(data.get('versions'), list)):
        raise FeedbackError('Saved scripts need repair. Your existing files are preserved.', 503)
    ids = []
    for v in data['versions']:
        if (not isinstance(v, dict) or not isinstance(v.get('text'), str) or len(v['text']) > LIMIT or
                v.get('id') != hashlib.sha256(v['text'].encode()).hexdigest() or
                not isinstance(v.get('request_ids'), list) or any(not isinstance(x, str) for x in v['request_ids'])):
            raise FeedbackError('Saved scripts need repair. Your existing files are preserved.', 503)
        ids.append(v['id'])
    if len(ids) != len(set(ids)) or data.get('current') not in ids:
        raise FeedbackError('Saved scripts need repair. Your existing files are preserved.', 503)
    return path, data


def context(project_id):
    project = project_for(project_id)
    path, data = read(project)
    root = index.STUDIO / 'projects' / project_id
    original_path, original = safe_text(root, 'script.txt')
    assembled = None
    spoken = [a for a in project['artifacts'] if a.get('type') == 'video' and
              (a.get('approval_kind') == 'spoken_cut' or re.search('spoken|speech', a.get('id', '')))]
    if spoken:
        a = max(spoken, key=lambda a: int((re.search(r'\d+', a.get('version', '')) or ['0'])[0]))
        candidates = [d['path'] for d in a.get('downloads', []) if re.search('script', d['label'], re.I) and d['path'].endswith('.txt')]
        version = a.get('version', '').lower()
        if re.fullmatch(r'v\d+', version): candidates.append('exports/assembled-script-' + version + '.txt')
        candidates.append('assembled-script.txt')
        for candidate in candidates:
            _, text = safe_text(root, candidate)
            if text is not None:
                assembled = {'text': text, 'version': a.get('version', '')}; break
    expected = {path: index.digest(path) if path.exists() else None,
                original_path: index.digest(original_path) if original_path.exists() else None,
                index.REGISTRY.resolve(): index.digest(index.REGISTRY)}
    revision = hashlib.sha256(storage.json_bytes([[p.relative_to(index.STUDIO).as_posix(), h] for p, h in expected.items()])).hexdigest()
    return project, path, data, original or '', assembled, expected, revision


def current(project_id, version=None):
    with index.STATE_LOCK:
        project, _, data, original, assembled, _, revision = context(project_id)
        if version is not None and (not isinstance(version, str) or not re.fullmatch(r'[a-f0-9]{64}', version)):
            raise FeedbackError('That saved script version is unavailable.', 404)
        chosen = data['current'] if version is None else version
        saved = next((v for v in data['versions'] if v['id'] == chosen), None)
        if version is not None and saved is None: raise FeedbackError('That saved script version is unavailable.', 404)
        return {'project_id': project_id, 'title': project['title'], 'revision': revision,
                'version_id': saved['id'] if saved else None, 'text': saved['text'] if saved else original,
                'current_version_id': data['current'],
                'versions': [{'id': v['id'], 'at': v.get('at', ''), 'origin': v.get('origin', 'studio'), 'preview': v['text'][:90]} for v in reversed(data['versions'])],
                'version_count': len(data['versions']), 'original': original, 'assembled': assembled}


def save(body, expected_files=None):
    if (not isinstance(body, dict) or set(body) != {'project_id', 'revision', 'request_id', 'text'} or
            not all(isinstance(v, str) for v in body.values()) or not re.fullmatch(r'[a-f0-9]{64}', body['revision'])):
        raise FeedbackError('Use a valid project script request.', 400)
    try:
        if str(uuid.UUID(body['request_id'])) != body['request_id']: raise ValueError()
    except ValueError: raise FeedbackError('Use a valid script save request.', 400)
    text = body['text'].strip()
    if not text or len(text) > LIMIT: raise FeedbackError('Enter a script up to 50,000 characters.', 400)
    with index.STATE_LOCK:
        storage.check_storage()
        project, path, data, original, _, expected, revision = context(body['project_id'])
        for v in data['versions']:
            if body['request_id'] in v.get('request_ids', []):
                if text != v['text']: raise FeedbackError('This save request was already used. Reload the saved script.')
                return {**current(project['id']), 'saved_version_id': v['id'], 'duplicate': True}
        if body['revision'] != revision: raise FeedbackError('This script changed elsewhere. Reload the saved script; your draft is kept.')
        if len(data['versions']) >= 80: raise FeedbackError('Your script history is full. Ask your editing chat to archive it safely.')
        for journal in storage.JOURNALS.glob('*/transaction.json'):
            if json.loads(journal.read_text(encoding='utf-8')).get('state') == 'prepared': raise FeedbackError('An earlier save needs recovery first.', 503)
        at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if not data['versions'] and original.strip():
            if len(original) > LIMIT: raise FeedbackError('The existing script is too long to version here. It is preserved.', 413)
            data['versions'].append({'id': hashlib.sha256(original.encode()).hexdigest(), 'text': original,
                                     'at': at, 'origin': 'script.txt', 'request_ids': []})
        version_id = hashlib.sha256(text.encode()).hexdigest()
        version = next((v for v in data['versions'] if v['id'] == version_id), None)
        if version is None:
            version = {'id': version_id, 'text': text, 'at': at, 'origin': 'studio', 'request_ids': []}
            data['versions'].append(version)
        version['request_ids'].append(body['request_id'])
        data['current'] = version_id
        storage.commit({path: storage.json_bytes(data)}, {**body, 'text': text, 'operation': 'save-project-script'}, {**expected, **(expected_files or {})})
        return {**current(project['id']), 'saved_version_id': version_id}
