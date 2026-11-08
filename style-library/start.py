"""Start or reuse this gallery, without changing production preview processes.

--open     also open it in the default browser (the one-command way back into the studio).
--restart  stop this installation's own running studio server first (verified by its
           health answer: same root and same process id that this script recorded),
           then start a fresh one -- e.g. after setup installed new tools, so the server
           sees them. Never stops anything it cannot verify as ours."""
from pathlib import Path
import json,os,signal,sys,subprocess,socket,time,urllib.request,webbrowser
BASE=Path(__file__).resolve().parent;run=BASE/'runtime';run.mkdir(exist_ok=True);state=run/'server.json'
def write_launcher(url):
    # A double-clicked HTML file cannot fetch the gallery's API/media routes.
    # Keep its redirect aligned with the actual verified server, including a
    # fallback port, while preserving the requested view or exact reference.
    script='if(location.protocol === "file:"){location.replace('+json.dumps(url+'/')+' + location.search + location.hash);}\n'
    (BASE/'dist/launch.js').write_text(script, encoding='utf-8')
def open_browser(url):
    if '--open' in sys.argv[1:]:webbrowser.open(url+'/')
# A busy older server can answer slowly; never mistake it for "not running" (and start a second one).
LIVE_TIMEOUT=3
def message(key,**values):
    # Plain he/en text from scripts/setup_messages.py in the studio's saved language; English if unavailable.
    try:
        sys.path.insert(0,str(BASE.parent/'scripts'));import setup_messages
        try:lang=json.loads((BASE/'settings.json').read_text(encoding='utf-8')).get('language')
        except (OSError,ValueError,AttributeError):lang='he'
        return setup_messages.message(key,lang if lang in ('he','en') else 'he').format(**values)
    except ImportError:
        return 'The studio is already open and we could not confirm it is this folder\'s own, so we did not close it. It keeps running at {url}.'.format(**values)
def health(url,timeout):
    try:return json.load(urllib.request.urlopen(url+'/api/health',timeout=timeout))
    except Exception:return None
def stop(old):
    """Stop the recorded server only when it answers as this installation with the recorded pid."""
    info=health(old['url'],LIVE_TIMEOUT)
    if not info or info.get('root')!=str(BASE):return True  # nothing of ours is running there
    if info.get('pid')!=old.get('pid'):return False  # cannot prove it is the process we started
    try:os.kill(old['pid'],signal.SIGTERM)
    except OSError:return False
    for _ in range(50):
        if health(old['url'],.2) is None:return True
        time.sleep(.1)
    return False
def detach_options():
    # Keep the server running after the window/assistant session that started it closes.
    if os.name!='nt':return {'start_new_session':True}
    flags=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW
    return {'creationflags':flags|getattr(subprocess,'CREATE_BREAKAWAY_FROM_JOB',0),'fallback':flags}
def launch(command,log):
    options=detach_options();fallback=options.pop('fallback',None)
    try:return subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,**options)
    except OSError:
        if fallback is None:raise
        # The parent's job may forbid breaking away; start inside it rather than not at all.
        return subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=fallback)
if state.exists():
    try:old=json.loads(state.read_text(encoding='utf-8'))
    except ValueError:old=None
    if isinstance(old,dict) and old.get('url'):
        if '--restart' in sys.argv[1:]:
            # Not provably ours (e.g. started before servers reported their pid): leave it running.
            if not stop(old):
                for stream in (sys.stdout,sys.stderr):
                    try:stream.reconfigure(encoding='utf-8',errors='replace')
                    except (AttributeError,ValueError,OSError):pass
                raise SystemExit(message('start.restart-refused',url=old['url']))
        else:
            info=health(old['url'],LIVE_TIMEOUT)
            if info and info.get('root')==str(BASE):write_launcher(old['url']);print(json.dumps(old));open_browser(old['url']);sys.exit(0)
port=4870
while True:
    with socket.socket()as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:s.bind(('127.0.0.1',port));break
        except OSError:port+=1
log=(run/'server.log').open('a', encoding='utf-8')
process=launch([sys.executable,str(BASE/'serve.py'),'--port',str(port)],log)
url=f'http://127.0.0.1:{port}'
for _ in range(40):
    info=health(url,.3)
    if info and info.get('root')==str(BASE):break
    time.sleep(.1)
else:raise RuntimeError('Gallery did not become ready; see runtime/server.log.')
# The server's own pid (a Windows venv python.exe is a launcher with a different child pid).
result={'url':url,'pid':info.get('pid',process.pid),'root':str(BASE),'host':'127.0.0.1'};state.write_text(json.dumps(result,indent=2)+'\n', encoding='utf-8');write_launcher(url);print(json.dumps(result));open_browser(url)
