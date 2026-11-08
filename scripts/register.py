"""Register an inspected checkpoint or reference; never approves a user's work.

    python scripts/register.py project <studio-entry.json> [--replace | --append-version]
    python scripts/register.py reference <entry.json> [--replace]

--append-version adds a new round's versions to an already registered project, including one
whose creator saved decisions in the studio (where --replace refuses). It keeps the record as it
is -- every saved decision/approval field and every existing artifact, byte for byte -- and only
adds the descriptor's new artifacts (ids not yet registered), points primary_artifact at one of
them, and updates state (review/in_progress only), stage, summary, next_step, missing
cover_path, source notes (fingerprints refreshed) and the reference_entry /
reference_poster_source seed that final approval in the studio needs. It refuses to change or drop an existing
artifact and to set or change review_decision/approval/baseline/review_action. It also
refuses (register.final) a project the creator marked final in the studio until they press
"פתיחה מחדש" / "Reopen" there -- appending would otherwise send it back to review and silently
undo that approval.

Appending may also write the reference_entry / reference_poster_source library seed (ruling
R42d): it is not a decision, only what the studio needs to file the video in the library when
the creator marks it final.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import os
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'style-library'))
import library
import project_index as index
import review_actions as storage
from security import registered_file, MEDIA, NOTES
sys.path.insert(0, str(Path(__file__).resolve().parent))
import new_version  # noqa: E402  (scripts/new_version.py: the shared register.final rule)

def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False,encoding='utf-8') as f:
        f.write(json.dumps(data,indent=2,ensure_ascii=False)+'\n'); name=f.name
    os.replace(name,path)

DECISIONS = ('review_decision', 'approval', 'baseline', 'review_action')
APPEND_FIELDS = ('state', 'stage', 'summary', 'next_step', 'primary_artifact')
FINAL_MESSAGE = new_version.FINAL_MESSAGE  # one refusal text for new_version.py and --append-version

def register(kind, manifest, replace=False, append=False):
    if replace and append:
        raise ValueError('Use either --replace or --append-version')
    with index.STATE_LOCK:
        storage.check_storage()
        for journal in storage.JOURNALS.glob('*/transaction.json'):
            if json.loads(journal.read_text(encoding='utf-8')).get('state') == 'prepared':
                raise ValueError('An earlier save needs recovery before registering work.')
        return register_locked(kind, manifest, replace, append)

def append_version(current, item):
    """The current record plus the descriptor's new artifacts; saved decisions untouched."""
    if new_version.is_final(current):
        raise ValueError(FINAL_MESSAGE)
    for key in DECISIONS:
        if key in item and item[key] != current.get(key):
            raise ValueError('An appended version cannot set or change saved decisions ('+key+')')
    if item.get('state') not in {'in_progress','review'}:
        raise ValueError('An appended version is in_progress or review; approval stays in the studio')
    old = {a['id']: a for a in current.get('artifacts', [])}
    added = []
    for artifact in item.get('artifacts', []):
        if artifact['id'] in old:
            if artifact != old[artifact['id']]:
                raise ValueError('A registered version cannot be changed; append a new version instead: '+artifact['id'])
        elif any(a['id'] == artifact['id'] for a in added):
            raise ValueError('Duplicate artifact ID: '+artifact['id'])
        else:
            added.append(artifact)
    if not added:
        raise ValueError('Nothing new to append')
    if item.get('primary_artifact') not in {a['id'] for a in added}:
        raise ValueError('The current checkpoint must be one of the appended versions')
    merged = copy.deepcopy(current)
    merged['artifacts'] = copy.deepcopy(added) + merged.get('artifacts', [])
    for key in APPEND_FIELDS:
        merged[key] = item[key]
    if item.get('cover_path') and not merged.get('cover_path'):
        merged['cover_path'] = item['cover_path']
    # The library seed the studio needs before the creator can mark a video final (not a decision).
    for key in ('reference_entry', 'reference_poster_source'):
        if key in item:
            merged[key] = item[key]
    notes = merged.setdefault('source_notes', [])
    for note in item.get('source_notes', []):
        if not any(n['path'] == note['path'] for n in notes):
            notes.append({'label': note['label'], 'path': note['path']})
    return merged

def register_locked(kind, manifest, replace, append=False):
    snapshots = {}
    for path in [index.REGISTRY, storage.CATALOG]:
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError('Registry must not be a symlink')
        snapshots[path.resolve()] = path.read_bytes() if path.exists() else None
    projects = json.loads(snapshots[index.REGISTRY.resolve()]) if snapshots[index.REGISTRY.resolve()] is not None else {'schema_version': 1, 'projects': []}
    catalog = json.loads(snapshots[storage.CATALOG.resolve()]) if snapshots[storage.CATALOG.resolve()] is not None else {'schema_version': 4, 'entries': [], 'techniques': []}
    item=json.loads(Path(manifest).read_text(encoding='utf-8'))
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',item['id']):raise ValueError('Use a readable lowercase ID')
    if append:
        if kind!='project':raise ValueError('--append-version is for projects')
        current=next((p for p in projects['projects'] if p['id']==item['id']),None)
        if current is None:raise ValueError('No registered project to append to; register it first')
        item=append_version(current,item)
    if kind=='project':
        required={'title','format','summary','next_step','state','stage','primary_artifact','artifacts','source_notes'}
        if required-set(item):raise ValueError('Project descriptor missing: '+', '.join(sorted(required-set(item))))
        if item['state'] not in {'in_progress','review'}:raise ValueError('New registrations cannot claim approval; use explicit review controls or record actual user approval in chat')
        for path in index.files(item): index.resolve(item,path)
        for note in item['source_notes']:note['sha256']=index.digest(index.resolve(item,note['path']))
        if item['primary_artifact'] not in {a['id'] for a in item['artifacts']}:raise ValueError('Unknown primary checkpoint')
        item['synced_on']=datetime.now(timezone.utc).date().isoformat()
        item.setdefault('input_note','Source files, exact versions and decisions are saved with this project.')
        data=projects;target=index.REGISTRY;key='projects'
    else:
        required={'title','subtitle','version','collection','creator','creator_id','summary','tags','palette','traits','keep','avoid','moments','notes','poster','evidence'}
        if required-set(item):raise ValueError('Reference descriptor missing: '+', '.join(sorted(required-set(item))))
        if item['collection'] not in {'mine','reference'}:raise ValueError('Unknown collection')
        for path in [item.get('media_path'),*item.get('notes',[])]:
            if path:registered_file(ROOT,path,MEDIA|NOTES)
        poster=(ROOT/'style-library/dist'/item['poster']).resolve()
        if not poster.is_relative_to((ROOT/'style-library/dist/assets').resolve()) or not poster.is_file():raise ValueError('Create a genuine poster under dist/assets first')
        if item.get('delivery_status')=='final':raise ValueError('Register as review_pending; final requires an actual user decision')
        item['review_status']='review_pending' if item['collection']=='mine' else 'reference'
        data=catalog;target=storage.CATALOG;key='entries'
        source=library.source_key(item['source_url']) if item.get('source_url') else None
        if source and any(e['id']!=item['id'] and e.get('source_url') and library.source_key(e['source_url'])==source for e in data[key]):raise ValueError('That original source is already registered')
    existing=next((i for i,x in enumerate(data[key]) if x['id']==item['id']),None)
    if kind=='project':
        previous=data[key][existing].get('starter_request_id') if existing is not None else None
        if previous:
            item.setdefault('starter_request_id',previous)
            if item['starter_request_id']!=previous:
                raise ValueError('Keep the existing script starter request ID')
        request=index.starter_request(item)
        if request and any(row.get('starter_request_id')==request and row['id']!=item['id'] for row in data[key]):
            raise ValueError('This script starter request already has a project. Continue there.')
        previous_reference = data[key][existing].get('reference_id') if existing is not None else None
        if previous_reference:
            item.setdefault('reference_id', previous_reference)
        if not item.get('reference_id'):
            matches = library.project_reference_candidates(item, catalog)
            if len(matches) > 1:raise ValueError('More than one library entry matches this checkpoint. Reconcile them before registration.')
            if matches:item['reference_id'] = matches[0]['id']
    else:
        previous = data[key][existing] if existing is not None else None
        date_fields = ['created_at', 'added_at', 'added_on']
        if previous is not None:
            for field in date_fields:
                if field in previous:item[field] = previous[field]
                elif any(previous.get(key) for key in date_fields):item.pop(field, None)
        elif not any(item.get(field) for field in date_fields):
            item['created_at'] = datetime.now(timezone.utc).isoformat()
        else:
            for field in date_fields:
                if item.get(field):
                    try:datetime.fromisoformat(item[field].replace('Z', '+00:00'))
                    except (AttributeError, TypeError, ValueError):raise ValueError('Use an ISO date for the reference creation date.')
    if existing is not None and not append:
        if not replace:raise ValueError('ID already exists. Read its decisions, then use --replace intentionally.')
        if data[key][existing].get('review_decision') or data[key][existing].get('approval'):
            raise ValueError('This record has saved approvals. Reconcile those explicitly before replacing its descriptor.')
    if existing is not None:
        data[key][existing]=item
    # The Projects home lists projects.json in order, so a new project goes first.
    elif kind=='project':data[key].insert(0,item)
    else:data[key].append(item)
    changes = {target.resolve(): storage.json_bytes(data)}
    if kind == 'reference' and item['collection'] == 'mine':
        project = next((p for p in projects['projects'] if p['id'] == item.get('project_id')), None)
        if project and not project.get('reference_id'):
            matches = library.project_reference_candidates(project, catalog)
            if len(matches) > 1:raise ValueError('More than one library entry matches this checkpoint. Reconcile them before registration.')
            if matches:
                project['reference_id'] = matches[0]['id']
                changes[index.REGISTRY.resolve()] = storage.json_bytes(projects)
    if target.exists():
        backup=ROOT/'style-library/runtime/registration-backups'/f'{target.stem}-{hashlib.sha256(target.read_bytes()).hexdigest()}.json'
        if not backup.exists():atomic(backup,json.loads(target.read_text(encoding='utf-8')))
    expected = {path: hashlib.sha256(raw).hexdigest() if raw is not None else None for path, raw in snapshots.items()}
    storage.commit(changes, {'request_id': str(uuid.uuid4()), 'operation': 'register-'+kind, 'id': item['id']}, expected)
    return item['id']

def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);parser.add_argument('kind',choices=['project','reference']);parser.add_argument('manifest',type=Path);parser.add_argument('--replace',action='store_true');parser.add_argument('--append-version',action='store_true',help='add new versions to a registered project, keeping its saved decisions');args=parser.parse_args()
    try:print(register(args.kind,args.manifest,args.replace,args.append_version))
    except (ValueError,KeyError,OSError,storage.ReviewError) as e:parser.exit(1,str(e)+'\n')

if __name__=='__main__':
    main()
