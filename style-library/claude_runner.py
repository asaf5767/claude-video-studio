"""Run Claude Code headless in the studio folder for one project or reference (Task 14).

The studio's "Send to Claude" button starts `claude -p "/<skill> <folder> Reply in <lang>."`
with `--permission-mode dontAsk` and a fixed tool allowlist (so the user's own default
permission mode cannot widen it), BASH_DEFAULT_TIMEOUT_MS=600000 / BASH_MAX_TIMEOUT_MS=3600000
in its environment (unless already set; long steps run in the foreground with the Bash timeout
parameter), cwd = the studio root, and stdout/stderr going to
logs/claude-<job>.log. Job records (with the child PID and its creation time) persist in
logs/jobs.json so a restarted server can still answer status(): a record left "running"
whose process is gone -- or whose PID now belongs to a different process -- becomes
"stopped", and is never killed. Progress steps come from <folder>/progress.json, written by
the skills themselves. Failures are classified into i18n message KEYS (claude.not-logged-in,
claude.limit, claude.failed); the UI translates them.

Never touches project files: a failed or cancelled run leaves every approved version as is.
"""
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import library
import project_index as index
from atomic import atomic_write
from library import STUDIO

_spec = importlib.util.spec_from_file_location('studio_tools', Path(__file__).resolve().parents[1] / 'scripts' / 'tools.py')
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

# Long steps (matte.py, a HyperFrames render) run in the foreground with the Bash tool's
# timeout parameter; these raise Claude Code's Bash limits for the child (unless already set).
BASH_TIMEOUTS = {'BASH_DEFAULT_TIMEOUT_MS': '600000', 'BASH_MAX_TIMEOUT_MS': '3600000'}
ALLOWED = ('Read,Glob,Grep,Edit,Write,Bash(ffmpeg:*),Bash(ffprobe:*),'
           'Bash(python scripts/*),Bash(python3 scripts/*),Bash(node node_modules/hyperframes/*)')
SKILL_BY_KIND = {'talking-head': 'talking-head', 'faceless': 'faceless-reel'}
LANGUAGE_NAME = {'he': 'Hebrew', 'en': 'English'}
STEP_STATES = ('done', 'running', 'todo')
ACTIVE = ('running', 'stopping')  # "stopping": cancel is still killing the process tree
JOB_ID = re.compile(r'^[0-9a-f]{32}$')
TAIL_BYTES = 16384
LOG_LINES, LOG_LINES_MAX = 40, 200  # support copy: default and largest line count
LOG_TAIL_BYTES = 262144  # stream-json lines can be long; 40 of them fit easily
LOG_LINE_CHARS = 500     # support copy: each line clipped to this many characters
CREATED_TOLERANCE = 2  # seconds between the recorded and the current creation time of a PID

LOCK = threading.RLock()
_PROCS = {}     # job -> Popen, for children started by this server process
_WATCHERS = {}  # job -> watcher thread

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _QUERY = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION


class RunnerError(Exception):
    """status: HTTP status. message_key: i18n key (or the bare 'claude-missing' / 'busy').
    details: extra reply fields -- 'busy' carries {"job": <running job>} so a reloaded page
    can re-attach to it (Task 13 fix round 1)."""
    def __init__(self, status, message_key, details=None):
        super().__init__(message_key)
        self.status = status
        self.message_key = message_key
        self.details = details or {}


def _logs():
    return STUDIO / 'logs'


def _load():
    """Read logs/jobs.json; a corrupt file is moved aside (never a permanent error)."""
    path = _logs() / 'jobs.json'
    if not path.exists():
        return {'jobs': {}}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or not isinstance(data.get('jobs'), dict) or
                not all(isinstance(r, dict) and r.get('job') == j for j, r in data['jobs'].items())):
            raise ValueError('Invalid job records')
        return data
    except ValueError:
        quarantine = path.with_name(f'jobs.corrupt-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}.json')
        os.replace(path, quarantine)
        print(json.dumps({'warning': 'claude-jobs-quarantined', 'file': 'logs/' + quarantine.name}),
              file=sys.stderr, flush=True)
        return {'jobs': {}}


def _save(data):
    _logs().mkdir(exist_ok=True)
    atomic_write(_logs() / 'jobs.json', (json.dumps(data, indent=2) + '\n').encode())


def _pid_alive(pid):
    """Raw liveness of a PID (no identity check -- see _same_process)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        handle = _kernel32.OpenProcess(_QUERY, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = wintypes.DWORD()
            return bool(_kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _proc_created(pid):
    """Creation time of the process now holding `pid` (seconds since the epoch), or None."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == 'nt':
        handle = _kernel32.OpenProcess(_QUERY, False, pid)
        if not handle:
            return None
        try:
            created, exited, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
            if not _kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                             ctypes.byref(kernel), ctypes.byref(user)):
                return None
            return created.value / 1e7 - 11644473600  # FILETIME (100 ns since 1601) -> Unix time
        finally:
            _kernel32.CloseHandle(handle)
    try:
        ps = shutil.which('ps') or '/bin/ps'
        out = subprocess.run([ps, '-o', 'lstart=', '-p', str(pid)], capture_output=True, text=True, timeout=5,
                             env={**os.environ, 'LC_ALL': 'C'}).stdout
        stamp = ' '.join(out.split())
        return time.mktime(time.strptime(stamp, '%a %b %d %H:%M:%S %Y')) if stamp else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _same_process(pid, created):
    """True only if `pid` is alive AND is the very process we recorded (same creation time)."""
    if not isinstance(created, (int, float)) or not _pid_alive(pid):
        return False
    actual = _proc_created(pid)
    return actual is not None and abs(actual - created) <= CREATED_TOLERANCE


def _running(record):
    """Whether an active record still has its own live process; marks it stopped if not."""
    if record.get('state') not in ACTIVE:
        return False
    if record['job'] in _PROCS:
        return True  # our own child: its watcher thread records the outcome
    if _same_process(record.get('pid'), record.get('created')):
        return True  # left by an earlier server run and verifiably still alive
    record['state'] = 'stopped'
    return False


def _target(project_id, task, ref_id):
    if task not in ('edit', 'learn-style'):
        raise RunnerError(400, 'claude.invalid-request')
    project = None
    if project_id is not None or task == 'edit':
        if not isinstance(project_id, str) or not index.TOKEN.fullmatch(project_id):
            raise RunnerError(404, 'claude.unknown-project')
        project = next((p for p in index.registry()['projects'] if p.get('id') == project_id), None)
        if project is None:
            raise RunnerError(404, 'claude.unknown-project')
    if task == 'edit':
        skill = SKILL_BY_KIND.get(project.get('kind'))
        if skill is None:
            raise RunnerError(409, 'claude.unknown-kind')
        return skill, 'projects/' + project_id
    if not isinstance(ref_id, str) or not index.TOKEN.fullmatch(ref_id) or ref_id not in library.entry_map():
        raise RunnerError(404, 'claude.unknown-reference')
    return 'learn-style', 'references/' + ref_id


def start(project_id, task, ref_id=None):
    skill, target = _target(project_id, task, ref_id)
    try:
        claude = tools.resolve('claude')
    except tools.ToolMissing:
        raise RunnerError(409, 'claude-missing') from None
    prompt = f'/{skill} {target} Reply in {LANGUAGE_NAME[library.ui_language()]}.'
    # --allowedTools is variadic, so it stays last.
    command = [claude, '-p', prompt, '--output-format', 'stream-json', '--verbose',
               '--permission-mode', 'dontAsk', '--allowedTools', ALLOWED]
    with LOCK:
        data = _load()
        busy = [r for r in data['jobs'].values() if r.get('target') == target and _running(r)]
        if busy:
            _save(data)
            raise RunnerError(409, 'busy', {'job': busy[0]['job']})
        job = uuid.uuid4().hex
        _logs().mkdir(exist_ok=True)
        options = {}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            options['start_new_session'] = True
        started = time.time()
        with open(_logs() / f'claude-{job}.log', 'wb') as log:
            proc = subprocess.Popen(command, cwd=STUDIO, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, env={**BASH_TIMEOUTS, **os.environ}, **options)
        _PROCS[job] = proc
        # Safe to read now: until we wait() on the child (POSIX) / while Popen holds its handle
        # (Windows), its PID cannot be reused.
        data['jobs'][job] = {'job': job, 'task': task, 'project': project_id, 'reference': ref_id,
                             'target': target, 'pid': proc.pid, 'created': _proc_created(proc.pid),
                             'state': 'running', 'message_key': None, 'exit_code': None, 'started': started}
        _save(data)
        watcher = threading.Thread(target=_watch, args=(job, proc), daemon=True)
        _WATCHERS[job] = watcher
        watcher.start()
    return {'job': job}


def _tail(job):
    try:
        with open(_logs() / f'claude-{job}.log', 'rb') as log:
            log.seek(0, os.SEEK_END)
            offset = max(0, log.tell() - TAIL_BYTES)
            log.seek(offset)
            data = log.read()
    except OSError:
        return ''
    if offset:
        data = data.partition(b'\n')[2]  # drop the partial first line
    return data.decode('utf-8', 'replace')


def _outcome(tail):
    """(is_error, failure text) from the log tail.

    stream-json ends with a {"type":"result"} event whose is_error marks a failed run even on
    exit 0. The failure text is that event's error text plus any non-JSON (stderr) lines; only
    when neither exists does it fall back to the whole tail -- so assistant chatter that merely
    mentions "rate limit" cannot misclassify a failure."""
    result, plain = None, []
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            plain.append(line)
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            result = event
    is_error = bool(result and result.get('is_error'))
    parts = []
    if is_error:
        parts = [str(result.get(key)) for key in ('subtype', 'result', 'error', 'errors') if result.get(key)]
    text = '\n'.join(parts + plain)
    return is_error, text if text.strip() else tail


def classify(text):
    lowered = text.lower()
    if any(s in lowered for s in ('/login', 'not logged in', 'invalid api key', 'authentication_error',
                                  'oauth token has expired', 'please log in')):
        return 'claude.not-logged-in'
    if any(s in lowered for s in ('usage limit', 'rate limit', 'rate_limit', 'limit reached',
                                  'credit balance is too low', 'quota')):
        return 'claude.limit'
    return 'claude.failed'


def _watch(job, proc):
    code = proc.wait()
    is_error, text = _outcome(_tail(job))
    with LOCK:
        try:
            data = _load()
            record = data['jobs'].get(job)
            if record is not None:
                record['exit_code'] = code
                if record['state'] == 'running':
                    if code == 0 and not is_error:
                        record['state'] = 'done'
                    else:
                        record['state'], record['message_key'] = 'failed', classify(text)
                elif record['state'] == 'stopping':
                    record['state'] = 'stopped'
                _save(data)
        except (OSError, ValueError):
            pass
        finally:
            _PROCS.pop(job, None)


def _record(job):
    if not isinstance(job, str) or not JOB_ID.fullmatch(job):
        raise RunnerError(404, 'claude.unknown-job')
    data = _load()
    record = data['jobs'].get(job)
    if record is None:
        raise RunnerError(404, 'claude.unknown-job')
    return data, record


def _steps(record):
    path = STUDIO / record['target'] / 'progress.json'
    try:
        if path.stat().st_mtime < record.get('started', 0) - 2:
            return []  # left over from an earlier run
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    steps = []
    for step in raw if isinstance(raw, list) else []:
        if isinstance(step, dict) and isinstance(step.get('key'), str) and step.get('state') in STEP_STATES:
            clean = {'key': step['key'], 'state': step['state']}
            if isinstance(step.get('detail'), str):
                clean['detail'] = step['detail']
            steps.append(clean)
    return steps


def status(job):
    with LOCK:
        data, record = _record(job)
        if record.get('state') in ACTIVE and not _running(record):
            _save(data)
        state = 'running' if record['state'] == 'stopping' else record['state']
        return {'job': record['job'], 'state': state, 'steps': _steps(record),
                'message_key': record.get('message_key'), 'started': record.get('started')}


def latest(project_id=None, ref_id=None):
    """Status of the newest job for one project (or one reference), or {"job": None}.

    Task 15: the project page asks this on load so a running job's progress survives a
    page reload. Exactly one of project_id / ref_id; both are checked like start() does."""
    if (project_id is None) == (ref_id is None):
        raise RunnerError(400, 'claude.invalid-request')
    if project_id is not None:
        if (not isinstance(project_id, str) or not index.TOKEN.fullmatch(project_id) or
                not any(p.get('id') == project_id for p in index.registry()['projects'])):
            raise RunnerError(404, 'claude.unknown-project')
        target = 'projects/' + project_id
    else:
        if not isinstance(ref_id, str) or not index.TOKEN.fullmatch(ref_id) or ref_id not in library.entry_map():
            raise RunnerError(404, 'claude.unknown-reference')
        target = 'references/' + ref_id
    with LOCK:
        records = [r for r in _load()['jobs'].values() if r.get('target') == target]
        if not records:
            return {'job': None}
        newest = max(records, key=lambda r: r.get('started') if isinstance(r.get('started'), (int, float)) else 0)
        return status(newest['job'])


def log_tail(job, lines=LOG_LINES):
    """The last `lines` lines of logs/claude-<job>.log, for the UI's quiet "copy details for
    support" link. The job must be a known record (so the path is never caller-built) and
    the count is a plain int in 1..LOG_LINES_MAX."""
    if type(lines) is not int or not 1 <= lines <= LOG_LINES_MAX:
        raise RunnerError(400, 'claude.invalid-request')
    with LOCK:
        _record(job)
    try:
        with open(_logs() / f'claude-{job}.log', 'rb') as log:
            log.seek(0, os.SEEK_END)
            offset = max(0, log.tell() - LOG_TAIL_BYTES)
            log.seek(offset)
            data = log.read()
    except OSError:
        return ''
    if offset:
        data = data.partition(b'\n')[2]  # drop the partial first line
    rows = data.decode('utf-8', 'replace').splitlines()[-lines:]
    # One stream-json event (a whole file read back by a tool) can be huge: clip each line.
    return '\n'.join(row if len(row) <= LOG_LINE_CHARS else row[:LOG_LINE_CHARS] + '…' for row in rows)


def _kill_tree(pid):
    if os.name == 'nt':
        taskkill = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
        subprocess.run([str(taskkill), '/T', '/F', '/PID', str(pid)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.killpg(pid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.1)


def cancel(job):
    """Stop a job's process tree. The record stays "stopping" (still busy) until the process is
    gone, then becomes "stopped". A PID that can't be verified as ours is never killed."""
    with LOCK:
        data, record = _record(job)
        if not _running(record) or record['state'] == 'stopping':
            _save(data)
            return None
        record['state'], record['message_key'] = 'stopping', None
        _save(data)
        pid, created, proc = record['pid'], record.get('created'), _PROCS.get(job)
    try:
        if proc is not None:
            if proc.poll() is None:
                _kill_tree(pid)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        elif _same_process(pid, created):
            _kill_tree(pid)
    finally:
        with LOCK:
            data = _load()
            record = data['jobs'].get(job)
            if record is not None and record['state'] == 'stopping':
                record['state'] = 'stopped'
                _save(data)
    return None
