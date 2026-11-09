"""Run Claude Code headless in the studio folder for one project or reference (Task 14).

The studio's "Send to Claude" button starts `claude -p "/<skill> <folder> Reply in <lang>."`
with `--permission-mode dontAsk` (so the user's own default permission mode cannot widen it),
`--settings {"disableAllHooks":true}` and least-privilege rules built per job (RULINGS R48, R51;
allowed_rules / denied_rules): edits only inside the job's own folder, Bash only for that
skill's named helper scripts (ffmpeg/ffprobe only through scripts/media.py), and no reading of
`.env`. STUDIO_JOB_DIR in the child's environment names the job folder; every helper and
media.py refuse any path outside it (scripts/jobscope.py). integrity.check() runs before the
start and after the end: a changed studio (code, shipped files, Claude settings) refuses the
run or marks it failed with claude.studio-changed. Its environment is the server's minus the parent
Claude Code session's variables (child_env), with BASH_DEFAULT_TIMEOUT_MS=600000 /
BASH_MAX_TIMEOUT_MS=3600000 (unless already set; long steps run in the foreground with the Bash
timeout parameter) and UTF-8 Python output; cwd = the studio root, and stdout/stderr going to
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

import integrity
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
# Helper output is JSON with Hebrew in it; a Windows pipe would otherwise use the ANSI code page.
UTF8_ENV = {'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}

# --- Least privilege (RULING R48). Rule syntax: https://code.claude.com/docs/en/permissions ---
# Bash: one rule per helper (and per HyperFrames subcommand), each for `python` and `python3`
# (R39: a Mac may have only python3). `Bash(x:*)` == `Bash(x *)`: the space is part of the
# rule, so `python scripts/cut.py/../../x.py` does not match; a compound command must match
# part by part. scripts/check_skills.py reads MEDIA_COMMANDS/PYTHONS/HELPERS (literal tuples).
# R51: no raw ffmpeg/ffprobe -- they could write or print any file; scripts/media.py checks
# every option and path first.
MEDIA_COMMANDS = ()
PYTHONS = ('python', 'python3')
HELPERS = {
    'edit': ('scripts/progress.py', 'scripts/prepare_media.py', 'scripts/transcribe.py', 'scripts/new_version.py',
             'scripts/cut.py', 'scripts/captions.py', 'scripts/matte.py', 'scripts/register_version.py',
             'scripts/hf.py check', 'scripts/hf.py render', 'scripts/hf.py --help',
             'scripts/addons_voice.py', 'scripts/addons_image.py',
             'scripts/media.py ffmpeg', 'scripts/media.py ffprobe'),
    # R53: learn-style reads another creator's content, so it gets no shell at all.
    'learn-style': (),
}
# Secrets live only in .env (settings.json holds no keys). Per the docs a Read deny rule also
# blocks Grep and Glob (Grep(path)/Glob(path) rules are accepted but never matched), the
# Edit/Write tools on that path, and Bash file commands naming it (cat, head, tail, sed). A bare
# file name matches at any depth under the working directory. The pattern is gitignore syntax
# and case-sensitive while NTFS/APFS are not, and Windows trims a trailing dot or space and
# opens `name::$DATA` streams: `.[eE][nN][vV]*` also covers `.ENV`, `.env `, `.env::$DATA`.
SECRET_RULES = ('Read(.env)', 'Read(.env.*)', 'Read(.[eE][nN][vV]*)', 'Edit(.env)', 'Edit(.env.*)',
                'Edit(.[eE][nN][vV]*)')
# Defence in depth for Bash, which the docs say is matched on the command text only (not a
# security boundary): the docs' read-only commands run unprompted in every mode, including
# dontAsk, and accept unquoted globs (`cat .e*` never names .env), so every file- or
# environment-printing one is denied outright (the skills use Read, Grep and Glob instead), as
# are the commands that could change STUDIO_JOB_DIR (allow rules never match past an unknown
# `VAR=` assignment) and raw ffmpeg/ffprobe. No skill command matches any of these
# (test_claude_runner checks every command the skills show).
FILE_PRINTERS = ('cat', 'head', 'tail', 'less', 'more', 'sed', 'awk', 'strings', 'od', 'xxd', 'hexdump', 'base64',
                 'sort', 'uniq', 'diff', 'cmp', 'comm', 'tac', 'nl', 'rev', 'tr', 'fold', 'paste', 'column',
                 'grep', 'egrep', 'fgrep', 'rg', 'git', 'env', 'printenv', 'export', 'declare', 'unset',
                 'ffmpeg', 'ffprobe')
BASH_DENY = tuple(f'Bash({name}:*)' for name in FILE_PRINTERS) + ('Bash(set)', 'Bash(*$*)', 'Bash(*`*)',
                                                                   # B1: no changing folder (no skill needs it)
                                                                   'Bash(cd)', 'Bash(cd *)', 'Bash(pushd *)', 'Bash(popd*)')
# --settings is the documented "inline JSON string" form (code.claude.com/docs/en/cli-reference):
# above user/project/local settings, so a planted .claude/settings.local.json cannot add hooks.
# B2: auto memory off too (`autoMemoryEnabled`, code.claude.com/docs/en/memory): a run must not
# write notes outside its folder that a later session would load.
SESSION_SETTINGS = '{"disableAllHooks":true,"autoMemoryEnabled":false}'
# R53 / G4: built-in tools per job (`--tools`, code.claude.com/docs/en/cli-reference) and only the
# project's own settings (`--setting-sources project`: the creator's user and local allow-lists
# never widen a run; sign-in is not a setting, so it still works).
TOOLS = {'edit': 'Read,Glob,Grep,Edit,Write,Bash', 'learn-style': 'Read,Glob,Grep,Write'}
# G1 belt: code-like and Claude-configuration files Claude may never create inside a job folder
# (the composition is index.html with inline script; gsap.min.js and fonts are copied by a helper).
NO_WRITE_IN_JOB = ('**/*.py', '**/*.pyw', '**/*.pyc', '**/*.pyd', '**/*.pth', '**/*.js', '**/*.mjs', '**/*.cjs',
                   '**/*.bat', '**/*.cmd', '**/*.exe', '**/*.com', '**/*.ps1', '**/*.vbs', '**/*.wsf',
                   '**/scripts/**', '**/CLAUDE*.md', '**/AGENTS.md', '**/.claude/**', '**/.mcp.json')
# Studio-owned files inside the job folder that the skill only reads (helpers/the server write them).
# look.json: the look values the studio copies from a reference's checked card (concern 3).
OWNED = {'edit': ('approval-state.json', 'look.json'), 'learn-style': ('style-card.json',)}
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
_SNAPSHOTS = {}  # job -> integrity snapshot taken just before the child started

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


def _project(project_id):
    found = index.registered_project(project_id, folder=False)
    if found is None:
        raise RunnerError(404, 'claude.unknown-project')
    return found[0]


def _reference(ref_id):
    if not isinstance(ref_id, str) or not index.TOKEN.fullmatch(ref_id) or ref_id not in library.entry_map():
        raise RunnerError(404, 'claude.unknown-reference')
    return 'references/' + ref_id


def _target(project_id, task, ref_id):
    if task not in ('edit', 'learn-style'):
        raise RunnerError(400, 'claude.invalid-request')
    project = None
    if project_id is not None or task == 'edit':
        project = _project(project_id)
    if task == 'edit':
        skill = SKILL_BY_KIND.get(project.get('kind'))
        if skill is None:
            raise RunnerError(409, 'claude.unknown-kind')
        return skill, 'projects/' + project_id
    return 'learn-style', _reference(ref_id)


def studio_path(root=None):
    """The studio root as the skills write it in a command: absolute, forward slashes."""
    return Path(root if root is not None else STUDIO).resolve().as_posix()


def bash_prefixes(task, root=None):
    """The command prefixes Bash may run for `task`. G1: every helper by its ABSOLUTE path in
    double quotes (`python "<studio>/scripts/progress.py" …`), so a helper of the same relative
    name inside the job folder (`cd projects/x && python scripts/progress.py`) never matches."""
    base = studio_path(root)
    prefixes = []
    for helper in HELPERS[task]:
        script, _, rest = helper.partition(' ')
        for python in PYTHONS:
            prefixes.append(f'{python} "{base}/{script}"' + (f' {rest}' if rest else ''))
    return list(MEDIA_COMMANDS) + prefixes


def allowed_rules(task, target, root=None):
    """--allowedTools for an edit job. Reads: the studio folder (the working directory; in
    dontAsk mode a read outside it is denied). Edit, which also governs Write: only the job's
    own folder `target`, relative to the working directory."""
    return ['Read(./**)', f'Edit(./{target}/**)'] + [f'Bash({prefix} *)' for prefix in bash_prefixes(task, root)]


def denied_rules(task, target):
    """--disallowedTools for an edit job (a deny rule wins over every allow rule)."""
    # Concern 3: an edit run never reads another creator's reference folder; the look values it
    # needs are in its own look.json, written by the studio.
    return (list(SECRET_RULES) + ['Read(./references/**)'] + [f'Edit(./{target}/{name})' for name in OWNED[task]] +
            [f'Edit(./{target}/{pattern})' for pattern in NO_WRITE_IN_JOB] + list(BASH_DENY))


# A studio opened from a Claude chat inherits that session's variables (CLAUDECODE=1,
# CLAUDE_CODE_SESSION_ID, CLAUDE_CODE_CHILD_SESSION, ...): the child would refuse to start or
# run as the parent's nested session. Of CLAUDE_CODE_* keep only what selects or authenticates a
# provider and what Claude Code needs to run (Git Bash on Windows); ANTHROPIC_*,
# CLAUDE_CONFIG_DIR, HOME/USERPROFILE/PATH and the rest pass unchanged.
KEEP_CLAUDE_CODE = ('CLAUDE_CODE_USE_', 'CLAUDE_CODE_SKIP_', 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_CLIENT_',
                    'CLAUDE_CODE_API_KEY_HELPER_TTL_MS', 'CLAUDE_CODE_AWS_CHAIN_RESOLVE_TIMEOUT_MS',
                    'CLAUDE_CODE_GIT_BASH_PATH')
DROP_ENV = ('CLAUDECODE', 'CLAUDE_PID', 'CLAUDE_PROJECT_DIR', 'CLAUDE_ENV_FILE', 'STUDIO_VOICE_KEY', 'STUDIO_IMAGE_KEY',
            'STUDIO_JOB_DIR')
# Not CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: Claude Code 2.1.228 then forces the permission mode back
# to "default" (it warns so at startup). Instead every Bash command containing `$` or a backtick
# is denied (BASH_DENY), so a command cannot expand a credential variable at all.


def _write_look(project_id):
    """Concern 3: copy the chosen reference look's checked values into projects/<id>/look.json."""
    import inspiration  # local: inspiration imports project_index, which imports this module's peers
    root = STUDIO / 'projects' / project_id
    try:
        look = json.loads((root / 'choices.json').read_text(encoding='utf-8')).get('look')
    except (OSError, ValueError, AttributeError):
        look = None
    try:
        inspiration.write_look(root, look)
    except (OSError, inspiration.InspirationError):
        pass  # the skill then follows the built-in default look


def child_env(environ=None, job_dir=None):
    """The environment for `claude -p`: the server's own minus the parent session's variables
    (and any add-on key a user exported: the add-on clients read keys from .env themselves),
    plus STUDIO_JOB_DIR=<job_dir> (absolute)."""
    environ = os.environ if environ is None else environ
    env = {}
    for name, value in environ.items():
        upper = name.upper()  # Windows variable names are case-insensitive
        if upper in DROP_ENV or (upper.startswith('CLAUDE_CODE_') and not upper.startswith(KEEP_CLAUDE_CODE)):
            continue
        env[name] = value
    for name, value in BASH_TIMEOUTS.items():
        env.setdefault(name, value)
    env.update(UTF8_ENV)
    # B1: on Windows a bare program name is otherwise looked up in the current folder first.
    env['NoDefaultCurrentDirectoryInExePath'] = '1'
    # B2: no auto memory (code.claude.com/docs/en/memory).
    env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] = '1'
    # Helpers never read bytecode from the studio's own __pycache__ folders (a planted .pyc there
    # would run instead of the reviewed source); theirs goes to logs/pycache.
    env['PYTHONPYCACHEPREFIX'] = str(Path(STUDIO).resolve() / 'logs' / 'pycache')
    if job_dir is not None:
        env['STUDIO_JOB_DIR'] = str(Path(job_dir).resolve())
    return env


def command_for(claude, skill, task, target, language, root=None):
    """The exact argv of an edit job's Claude run (learn-style: learn_command)."""
    prompt = f'/{skill} {target} Studio folder: "{studio_path(root)}". Reply in {LANGUAGE_NAME[language]}.'
    # Both rule flags are variadic (one rule per argument, the documented form), so they come
    # after the prompt and each list ends at the next flag. --strict-mcp-config: no MCP servers.
    return [claude, '-p', prompt, '--output-format', 'stream-json', '--verbose',
            '--permission-mode', 'dontAsk', '--strict-mcp-config', '--setting-sources', 'project',
            '--settings', SESSION_SETTINGS, '--tools', TOOLS[task],
            '--disallowedTools', *denied_rules(task, target),
            '--allowedTools', *allowed_rules(task, target, root)]


LEARN_SKILL = Path(__file__).resolve().parents[1] / '.claude' / 'skills' / 'learn-style' / 'SKILL.md'


def learn_instructions(ref_id, round_name, language):
    """The instructions file learn_job.py writes into the round folder: the learn-style skill
    (without front matter) under a header naming this run. A one-line prompt points at it, so
    no long multi-line argument has to pass through a Windows .cmd shim."""
    body = LEARN_SKILL.read_text(encoding='utf-8')
    if body.startswith('---'):
        body = body.split('\n---', 1)[1].lstrip('-').lstrip('\n')
    return (f'# This run\n\nReference: `{ref_id}`. Your working folder is this reference\'s folder. This round\'s '
            f'analysis: `analysis/{round_name}/`. You have no shell and cannot run commands; read with Read, Glob '
            f'and Grep, and write only `style-card.md`. Reply in {LANGUAGE_NAME[language]}.\n\n{body}')


def learn_command(claude, ref_id, round_name, language):
    """The exact argv of a learn-style Claude run (R53). cwd: references/<id>/ (learn_job.py).
    No Bash: `--tools Read,Glob,Grep,Write`, and the only writable file is style-card.md."""
    prompt = (f'Follow analysis/{round_name}/instructions.md to write this reference\'s style card. '
              f'Reply in {LANGUAGE_NAME[language]}.')
    return [claude, '-p', prompt, '--output-format', 'stream-json', '--verbose',
            '--permission-mode', 'dontAsk', '--strict-mcp-config', '--setting-sources', 'project',
            '--settings', SESSION_SETTINGS, '--tools', TOOLS['learn-style'],
            '--disallowedTools', *SECRET_RULES, 'Edit(./style-card.json)', 'Bash',
            '--allowedTools', 'Read(./**)', 'Edit(./style-card.md)']


def start(project_id, task, ref_id=None):
    skill, target = _target(project_id, task, ref_id)
    try:
        claude = tools.resolve('claude')
    except tools.ToolMissing:
        raise RunnerError(409, 'claude-missing') from None
    language = library.ui_language()
    if task == 'edit':
        _write_look(project_id)
    if task == 'learn-style':
        # R53: the server analyses first, then a shell-less Claude run (learn_job.py drives both).
        command = [sys.executable, str(Path(__file__).resolve().parent / 'learn_job.py'), str(STUDIO), ref_id, language]
    else:
        command = command_for(claude, skill, task, target, language)
    with LOCK:
        data = _load()
        busy = [r for r in data['jobs'].values() if r.get('target') == target and _running(r)]
        if busy:
            _save(data)
            raise RunnerError(409, 'busy', {'job': busy[0]['job']})
        # G5: a missing baseline is recreated only before the very first run.
        changed = integrity.check(STUDIO, first_run=not data['jobs'])
        if changed:
            raise RunnerError(409, 'claude.studio-changed', {'files': changed})
        before = integrity.snapshot(STUDIO)
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
                                    stderr=subprocess.STDOUT, env=child_env(job_dir=STUDIO / target), **options)
        _PROCS[job] = proc
        _SNAPSHOTS[job] = before  # G5: kept in memory; the run cannot rewrite it
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
    for marker, key in STUDIO_RESULTS.items():  # learn_job.py's own outcomes
        if marker in lowered:
            return key
    if any(s in lowered for s in ('/login', 'not logged in', 'invalid api key', 'authentication_error',
                                  'oauth token has expired', 'please log in')):
        return 'claude.not-logged-in'
    if any(s in lowered for s in ('usage limit', 'rate limit', 'rate_limit', 'limit reached',
                                  'credit balance is too low', 'quota')):
        return 'claude.limit'
    return 'claude.failed'


STUDIO_RESULTS = {'studio.no-source': 'claude.no-source', 'studio.unreadable': 'claude.unreadable-source',
                  'studio.card-invalid': 'claude.card-invalid'}


def _watch(job, proc):
    code = proc.wait()
    is_error, text = _outcome(_tail(job))
    try:
        before = _SNAPSHOTS.pop(job, None)
        changed = integrity.diff(before, integrity.snapshot(STUDIO)) if before is not None else []
        against_baseline = integrity.changes(STUDIO)
        changed = sorted(set(changed) | set(against_baseline if against_baseline is not None else ['logs/integrity.json']))
        if changed:
            integrity.trip(STUDIO, changed)  # every later start is refused until a deliberate re-baseline
    except OSError:
        changed = ['logs/integrity.json']
    with LOCK:
        try:
            data = _load()
            record = data['jobs'].get(job)
            if record is not None:
                record['exit_code'] = code
                if changed:
                    # The run changed the studio itself: never "done", whatever it reported.
                    record['state'], record['message_key'], record['changed'] = 'failed', 'claude.studio-changed', changed
                elif record['state'] == 'running':
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
        result = {'job': record['job'], 'state': state, 'steps': _steps(record),
                  'message_key': record.get('message_key'), 'started': record.get('started')}
        if record.get('changed'):
            result['changed'] = record['changed']
        return result


def latest(project_id=None, ref_id=None):
    """Status of the newest job for one project (or one reference), or {"job": None}.

    Task 15: the project page asks this on load so a running job's progress survives a
    page reload. Exactly one of project_id / ref_id; both are checked like start() does."""
    if (project_id is None) == (ref_id is None):
        raise RunnerError(400, 'claude.invalid-request')
    if project_id is not None:
        _project(project_id)
        target = 'projects/' + project_id
    else:
        target = _reference(ref_id)
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
