"""Version-scoped sound summaries and explicit local editor working copies."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import uuid
import project_index as index
import review_actions as storage

OPEN_LOCK=threading.Lock()
CODE={'.html','.css','.js','.mjs','.json','.md','.txt','.csv','.srt','.svg','.py'}
class ToolsError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

def context(project_id,artifact_id):
    if not all(isinstance(v,str) and index.TOKEN.fullmatch(v) for v in [project_id,artifact_id]):raise ToolsError('Choose a project version.',404)
    p=next((p for p in index.registry()['projects'] if p['id']==project_id),None)
    a=next((a for a in p['artifacts'] if a['id']==artifact_id),None) if p else None
    if not a:raise ToolsError('This project version is unavailable.',404)
    root=(index.STUDIO/'projects'/p['id']).resolve()
    if root.parent!=(index.STUDIO/'projects').resolve() or root.parent.parent!=index.STUDIO.resolve():raise ToolsError('The project folder needs repair.',503)
    return p,a,root

def safe_file(root,name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts:raise ToolsError('Use a source inside this project.',503)
    target=(root/path).resolve()
    if not target.is_relative_to(root) or not target.is_file():raise ToolsError('The editable source is unavailable.',404)
    return target

def source(p,a,root):
    if a.get('type')!='video':return None
    # Explicit editor_source is preferred. Legacy current checkpoints name their exact
    # working folder with an Editable project notes download. Never infer history.
    name=a.get('editor_source')
    if not name and a['id']==p['primary_artifact']:
        notes=[d['path'] for d in a.get('downloads',[]) if d.get('label','').lower()=='editable project notes']
        if len(notes)==1:name=(Path(notes[0]).parent/'index.html').as_posix()
    if not name:return None
    try:
        path=safe_file(root,name)
        if path.name!='index.html' or path.stat().st_size>2*1024*1024 or 'data-composition-id' not in path.read_text(encoding='utf-8'):return None
        return path.parent
    except (OSError,UnicodeError,ToolsError):return None

def inventory(folder):
    """Bound the copy, reject escaping/cyclic symlinks, fingerprint editable content."""
    rows=[];seen=set();total=0
    for current,dirs,files in os.walk(folder,followlinks=True):
        here=Path(current);resolved=here.resolve()
        if not resolved.is_relative_to(index.STUDIO.resolve()) or resolved in seen:raise ToolsError('The editable source contains an unsafe or cyclic link.',503)
        seen.add(resolved);dirs[:]=[d for d in dirs if d not in {'.git','.venv','node_modules','__pycache__','.hyperframes','studio-editor'}]
        for name in sorted(files):
            path=here/name;target=path.resolve()
            if not target.is_relative_to(index.STUDIO.resolve()) or not target.is_file():raise ToolsError('The editable source contains an unavailable linked file.',503)
            stat=target.stat();total+=stat.st_size
            if len(rows)>=12000 or total>5*1024**3:raise ToolsError('Ask your editing chat to prepare a smaller editable copy of this version.',413)
            value=index.digest(target) if path.suffix.lower() in CODE else f'{stat.st_size}:{stat.st_mtime_ns}'
            rows.append((path.relative_to(folder).as_posix(),value))
    return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest(),rows

def sound_summary(p,a,root,folder):
    candidates=[d['path'] for d in a.get('downloads',[]) if d.get('label','').lower()=='sound plan' and Path(d['path']).suffix=='.json']
    if not candidates and folder and (folder/'sound-plan.json').is_file():candidates=[(folder/'sound-plan.json').relative_to(root).as_posix()]
    if not candidates:return {'recorded':False,'music':'Not recorded','effects':'Not recorded','direction':''}
    try:
        path=safe_file(root,candidates[0])
        if path.stat().st_size>524288:return {'recorded':False}
        data=json.loads(path.read_text(encoding='utf-8'));music=data.get('music');cues=data.get('cues',data.get('effects'))
        if music is False or music is None or music=='' or isinstance(music,dict) and music.get('enabled') is False:music_label='No background music' if 'music' in data else 'Not recorded'
        elif isinstance(music,str):music_label=music[:250]
        elif isinstance(music,dict):music_label=' · '.join(str(music[k])[:120] for k in ['title','artist'] if music.get(k)) or 'Music bed recorded'
        else:music_label='See the saved sound plan'
        effects=f'{len(cues)} timed effect'+('' if len(cues)==1 else 's') if isinstance(cues,list) else 'See the saved sound plan'
        direction=data.get('direction') or data.get('mix_notes') or ''
        return {'recorded':True,'music':music_label,'effects':effects,'direction':direction[:500] if isinstance(direction,str) else ''}
    except (OSError,ValueError,TypeError,ToolsError):return {'recorded':False,'music':'Not recorded','effects':'Not recorded','direction':''}

def session_path(p,a):
    parent=index.REGISTRY.parent/'runtime/editor-sessions'
    if parent.resolve()!=parent:raise ToolsError('The editor-session folder needs repair.',503)
    return parent/(p['id']+'--'+a['id']+'.json')

def working_copy(p,a,root,revision):
    path=session_path(p,a)
    if not path.exists():return None
    if path.is_symlink():raise ToolsError('The editor-session path needs repair.',503)
    try:
        data=json.loads(path.read_text(encoding='utf-8'));copy=(root/'work/studio-editor'/data['folder'])
        if (data.get('revision')==revision and isinstance(data['folder'],str) and re.fullmatch(re.escape(a['id'])+r'-[0-9a-f]{8}',data['folder']) and copy.resolve()==copy and (copy/'index.html').is_file()):return copy
    except (OSError,ValueError,TypeError,KeyError):pass
    return None

def preview_url(output,copy,port=None):
    for line in reversed(output.splitlines()):
        try:
            data=json.loads(line);url=data.get('studioUrl') or data.get('studio_url') or data.get('result',{}).get('studioUrl') or data.get('session',{}).get('studioUrl')
            expected=r'http://(?:127\.0\.0\.1|localhost):'+(str(port) if port else r'[0-9]{1,5}')+r'/#project/'+re.escape(copy.name)
            if isinstance(url,str) and re.fullmatch(expected,url):return url
        except (ValueError,AttributeError):continue
    return None

def state(project_id,artifact_id):
    with index.STATE_LOCK:
        p,a,root=context(project_id,artifact_id);folder=source(p,a,root)
        result={'project_id':p['id'],'artifact_id':a['id'],'editor':None,'sound':sound_summary(p,a,root,folder)}
        cli=index.STUDIO/'node_modules/hyperframes/bin/hyperframes.mjs'
        if folder:
            try:
                revision,_=inventory(folder)
                result['editor']={'revision':revision,'ready':cli.is_file() and shutil.which('node') is not None,'working_copy':working_copy(p,a,root,revision) is not None}
            except ToolsError as e:result['editor_error']=str(e)
        return result

def open_editor(body):
    if not isinstance(body,dict) or set(body)!={'project_id','artifact_id','revision'} or not isinstance(body.get('revision'),str) or not re.fullmatch('[a-f0-9]{64}',body['revision']):raise ToolsError('Refresh this version before opening its editor.')
    if not OPEN_LOCK.acquire(blocking=False):raise ToolsError('An editor is already opening. Try again shortly.',409)
    try:
        with index.STATE_LOCK:
            p,a,root=context(body['project_id'],body['artifact_id']);folder=source(p,a,root)
            if not folder:raise ToolsError('No editable source is registered for this version.',404)
            cli=index.STUDIO/'node_modules/hyperframes/bin/hyperframes.mjs';node=shutil.which('node')
            if not cli.is_file() or not node:raise ToolsError('Ask your editing chat to finish the local HyperFrames setup.',503)
            revision,_=inventory(folder)
            if revision!=body['revision']:raise ToolsError('The working source changed. Refresh before opening the editor.',409)
            copy=working_copy(p,a,root,revision)
            if copy is None:
                parent=root/'work/studio-editor'
                if parent.resolve()!=parent or (root/'work').is_symlink():raise ToolsError('The working-copy folder needs repair.',503)
                parent.mkdir(parents=True,exist_ok=True)
                copy=parent/(a['id']+'-'+uuid.uuid4().hex[:8]);copy.mkdir()
                try:
                    shutil.copytree(folder,copy,dirs_exist_ok=True,symlinks=False,ignore=shutil.ignore_patterns('.git','.venv','node_modules','__pycache__','.hyperframes','studio-editor'))
                    if inventory(folder)[0]!=revision:raise ToolsError('The source changed while copying. Refresh and try again.',409)
                except Exception:
                    shutil.rmtree(copy);raise
                record=session_path(p,a);record.parent.mkdir(parents=True,exist_ok=True)
                storage.atomic_write(record,storage.json_bytes({'revision':revision,'folder':copy.name}))
        # No shell and no user-controlled command flags. A GET never launches a process.
        env={**os.environ,'HYPERFRAMES_NO_UPDATE_CHECK':'1','HYPERFRAMES_NO_TELEMETRY':'1'}
        try:
            status=subprocess.run([node,str(cli),'preview',str(copy),'--status','--json'],cwd=index.STUDIO,env=env,capture_output=True,text=True,timeout=8)
            url=preview_url(status.stdout,copy) if status.returncode==0 else None
            if not url:
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                run=subprocess.run([node,str(cli),'preview',str(copy),'--background','--no-open','--json','--port',str(port)],cwd=index.STUDIO,env=env,capture_output=True,text=True,timeout=45)
                if run.returncode:raise ToolsError('HyperFrames could not open. Your working copy is saved; ask your editing chat to check the local setup.',503)
                url=preview_url(run.stdout,copy,port)
        except subprocess.TimeoutExpired:raise ToolsError('HyperFrames is taking longer to open. Your working copy is saved; ask your editing chat to open it.',503)
        if not url:raise ToolsError('The editor link was unavailable. Ask your editing chat to open the saved working copy.',503)
        return {'url':url,'working_copy':copy.relative_to(index.STUDIO).as_posix(),'artifact_id':a['id']}
    finally:OPEN_LOCK.release()
