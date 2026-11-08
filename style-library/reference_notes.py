"""Local borrowing notes for exact references; no AI invocation or source fetching."""
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid
from urllib.parse import urlencode
import library
import project_index as index
import review_actions as storage
from feedback import check_writes


class NoteError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def target():
    path = storage.BASE / 'reference-notes.json'
    if path.resolve() != storage.BASE.resolve() / 'reference-notes.json':
        raise NoteError('Reference notes need a safe local path before saving.', 503)
    return path


def read():
    path = target()
    if not path.exists():
        return path, {'schema_version': 1, 'notes': []}, None
    if path.stat().st_size > 4_000_000:
        raise NoteError('Reference notes need attention. Existing notes are preserved.', 503)
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get('schema_version') != 1 or
                not isinstance(data.get('notes'), list) or
                any(not isinstance(n, dict) or not isinstance(n.get('id'), str) for n in data['notes']) or
                len({n['id'] for n in data['notes']}) != len(data['notes'])):
            raise ValueError()
    except (ValueError, TypeError):
        raise NoteError('Saved reference notes need repair. Existing notes are preserved.', 503)
    return path, data, hashlib.sha256(raw).hexdigest()


def context(reference_id, example_id=None):
    if not isinstance(reference_id, str) or not index.TOKEN.fullmatch(reference_id):
        raise NoteError('Choose a saved reference.', 404)
    if example_id is not None and (not isinstance(example_id, str) or not index.TOKEN.fullmatch(example_id)):
        raise NoteError('Choose a valid technique example.', 400)
    # A fresh install has no catalog.json until something is saved to the library.
    catalog_bytes = storage.CATALOG.read_bytes() if storage.CATALOG.exists() else None
    data = json.loads(catalog_bytes) if catalog_bytes is not None else {'schema_version': 4, 'entries': [], 'techniques': []}
    entry = next((e for e in data['entries'] if e['id'] == reference_id), None)
    technique = next((t for t in data.get('techniques', []) if t['id'] == reference_id), None)
    example = None
    if technique:
        example = next((x for x in technique['examples'] if x['id'] == example_id), None)
        if not example:
            raise NoteError('Choose an exact technique example.', 409)
        entry = next((e for e in data['entries'] if e['id'] == example['style_id']), None)
    if not entry or (not technique and example_id is not None):
        raise NoteError('This reference is no longer available.', 404)
    if example and (example.get('source_version') != entry['version'] or
                    example.get('source_path') != entry.get('media_path')):
        raise NoteError('This example changed. Ask your assistant to recheck its source first.', 409)
    paths = [entry['media_path']] if entry.get('media_path') else []
    paths += [s['path'] for s in entry.get('slides', [])]
    files = []
    for relative in paths:
        if not isinstance(relative, str) or not relative or relative.startswith('/'):
            raise NoteError('The reference source needs a safe local path.', 409)
        path = (index.STUDIO / relative).resolve()
        if not path.is_relative_to(index.STUDIO.resolve()) or not path.is_file():
            raise NoteError('This source is unavailable. Your notes are preserved.', 409)
        stat = path.stat()
        files.append({'path': relative, 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                      'sha256': index.digest(path)})
    if example and (not entry.get('media_path') or not files or files[0]['sha256'] != example.get('source_sha256')):
        raise NoteError('The example source changed. Recheck its timing before using it.', 409)
    snapshot = {'style_id': entry.get('archived_from', entry['id']), 'version': entry.get('version', ''),
                'url': entry.get('source_url'), 'path': entry.get('media_path'),
                'slides': entry.get('slides', []), 'files': files,
                'duration': entry.get('duration'),
                'example': {k: example[k] for k in ['id', 'start', 'end', 'source_version', 'source_path', 'source_sha256']} if example else None}
    revision = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return {'reference_id': reference_id, 'example_id': example_id, 'context_revision': revision,
            'title': technique['title'] if technique else entry['title'], 'creator': entry['creator'],
            'example_label': example['label'] if example else None,
            'start': example['start'] if example else 0,
            'end': example['end'] if example else entry.get('duration'),
            'has_video': bool(entry.get('media_path')), 'slide_count': len(entry.get('slides', [])),
            'source': snapshot, 'catalog_hash': hashlib.sha256(catalog_bytes).hexdigest() if catalog_bytes is not None else None}


def current(reference_id, example_id=None):
    with index.STATE_LOCK:
        storage.check_storage()
        ctx = context(reference_id, example_id)
        _, data, _ = read()
        notes = [n for n in data['notes'] if n.get('reference_id') == reference_id and n.get('example_id') == example_id]
        return {**{k: v for k, v in ctx.items() if k not in {'catalog_hash', 'source'}},
                'notes': [n for n in notes if n.get('context_revision') == ctx['context_revision']],
                'earlier_notes': [n for n in notes if n.get('context_revision') != ctx['context_revision']]}


def clean_text(value, label, limit, required=False):
    if (not isinstance(value, str) or len(value) > limit or (required and not value.strip()) or
            any(ord(c) < 32 and c not in '\n\t\r' for c in value)):
        raise NoteError(f'{label} must be text of up to {limit} characters.', 400)
    return value.strip()


def save(body):
    fields = {'reference_id', 'example_id', 'slide', 'context_revision', 'text', 'time', 'focus', 'request_id', 'legacy_key'}
    if not isinstance(body, dict) or set(body) != fields:
        raise NoteError('Use a valid reference note request.', 400)
    try:
        if not isinstance(body['request_id'], str) or str(uuid.UUID(body['request_id'])) != body['request_id']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise NoteError('Use a valid note save request.', 400)
    text = clean_text(body['text'], 'Note', 2000, True)
    focus = clean_text(body['focus'], 'Moment or slide', 1000)
    legacy = body['legacy_key']
    if legacy is not None and (not isinstance(legacy, str) or len(legacy) != 64 or any(c not in '0123456789abcdef' for c in legacy)):
        raise NoteError('Use a valid earlier-note request.', 400)
    with index.STATE_LOCK:
        check_writes()
        ctx = context(body['reference_id'], body['example_id'])
        path, data, before = read()
        existing = next((n for n in data['notes'] if n['id'] == body['request_id']), None)
        if existing:
            if existing.get('request') != body:
                raise NoteError('This save request already belongs to another note.', 409)
            return current(body['reference_id'], body['example_id'])
        if body['context_revision'] != ctx['context_revision']:
            raise NoteError('This source changed. Reopen it before saving; your draft is kept.', 409)
        slide, time = body['slide'], body['time']
        if slide is not None and (type(slide) is not int or not 1 <= slide <= ctx['slide_count']):
            raise NoteError('Choose a valid carousel slide.', 400)
        if time is not None:
            if (slide is not None or not ctx['has_video'] or isinstance(time, bool) or
                    not isinstance(time, (int, float)) or not math.isfinite(time) or
                    not ctx['start'] <= time <= (ctx['end'] if ctx['end'] is not None else 86400)):
                raise NoteError('Choose a moment inside this video or exact example.', 400)
        if legacy:
            previous = next((n for n in data['notes'] if n.get('legacy_key') == legacy and
                             n.get('reference_id') == body['reference_id'] and n.get('example_id') == body['example_id'] and
                             n.get('context_revision') == ctx['context_revision']), None)
            if previous:
                if previous['text'] != text or previous.get('focus', '') != focus:
                    raise NoteError('This earlier-note request already belongs to another note.', 409)
                return current(body['reference_id'], body['example_id'])
        if len(data['notes']) >= 5000:
            raise NoteError('Ask your assistant to archive older reference notes first.', 409)
        data['notes'].append({'id': body['request_id'], 'created_at': datetime.now(timezone.utc).isoformat(),
                              'reference_id': body['reference_id'], 'example_id': body['example_id'],
                              'context_revision': ctx['context_revision'], 'slide': slide, 'time': time,
                              'text': text, 'focus': focus, 'source': ctx['source'], 'legacy_key': legacy,
                              'request': body})
        encoded = storage.json_bytes(data)
        if len(encoded) > 4_000_000:
            raise NoteError('Reference notes need archiving before adding more.', 409)
        storage.commit({path: encoded}, {'request_id': body['request_id'], 'operation': 'reference-note'},
                       {path: before, storage.CATALOG.resolve(): ctx['catalog_hash'],
                        **{(index.STUDIO / f['path']).resolve(): f['sha256'] for f in ctx['source']['files']}})
        return current(body['reference_id'], body['example_id'])


def handoff(body, base_url):
    if not isinstance(body, dict) or set(body) != {'references'} or not isinstance(body['references'], list) or not 1 <= len(body['references']) <= 60:
        raise NoteError('Choose up to 60 exact references.', 400)
    with index.STATE_LOCK:
        storage.check_storage()
        _, data, _ = read()
        out = ['Use this reference:' if len(body['references']) == 1 else 'Use these references:', '']
        seen = set()
        for row in body['references']:
            if not isinstance(row, dict) or set(row) != {'reference_id', 'example_id', 'slide', 'context_revision', 'note_ids'}:
                raise NoteError('Choose valid references and saved notes.', 400)
            ctx = context(row['reference_id'], row['example_id'])
            ids, slide = row['note_ids'], row['slide']
            if (not isinstance(ids, list) or len(ids) > 5000 or any(not isinstance(i, str) for i in ids) or
                    len(ids) != len(set(ids)) or row['context_revision'] != ctx['context_revision']):
                raise NoteError('The selected source or notes changed. Review them before copying.', 409)
            if slide is not None and (type(slide) is not int or not 1 <= slide <= ctx['slide_count']):
                raise NoteError('Choose an exact carousel slide.', 400)
            token = (row['reference_id'], row['example_id'], slide)
            if token in seen:
                raise NoteError('Choose each exact reference once.', 400)
            seen.add(token)
            wanted = set(ids)
            selected = [n for n in data['notes'] if n['id'] in wanted]
            if len(selected) != len(ids) or any(n.get('reference_id') != row['reference_id'] or
                    n.get('example_id') != row['example_id'] or n.get('context_revision') != ctx['context_revision'] or
                    (n.get('slide') is not None and n.get('slide') != slide) for n in selected):
                raise NoteError('Those notes belong to a different source, example or slide.', 409)
            params = {'technique' if row['example_id'] else 'style': row['reference_id']}
            label = ctx['title'] + ' — ' + ctx['creator']
            if row['example_id']:
                params['example'] = row['example_id']
                label += f" · {ctx['example_label']} ({library.timestamp(ctx['start'])}–{library.timestamp(ctx['end'])})"
            if slide is not None:
                params['slide'] = slide
                label += f' · Slide {slide}'
            out += [label, base_url.rstrip('/') + '/#' + urlencode(params)]
            for n in selected:
                position = f"At {library.timestamp(n['time'])}" if n.get('time') is not None else f"Slide {n['slide']}" if n.get('slide') else 'What to borrow'
                if n.get('focus'):
                    position += ' · ' + n['focus']
                out.append(f"{position}: {n['text']}")
            out.append('')
        return {'text': '\n'.join(out).rstrip()}
