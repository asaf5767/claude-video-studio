"""Has the studio's own code changed? Checked before and after every "Send to Claude" run (RULING R51).

The headless run may only write inside its job folder (claude_runner rules, scripts/jobscope.py,
scripts/media.py), but those are command-text and helper-level checks, not an operating-system
sandbox. This is the backstop: a baseline in logs/integrity.json records the sha256 of every
shipped file (release-files.txt) and the set of code files (*.py, *.pth, *.js, *.mjs) under
scripts/, style-library/ and the studio root, every file under .claude/, and every CLAUDE.md.
check() reports:
  - a shipped file that changed or disappeared,
  - a new code file in those places (a planted scripts/json.py would be imported by the next
    helper),
  - a Claude Code configuration file that the studio never ships and that a run could use to
    widen the next one (.claude/settings.json, .claude/settings.local.json, CLAUDE.local.md,
    .mcp.json) -- unless that exact file was already there when the baseline was written
    (the creator's own approvals from a setup chat).
The runner refuses to start (and marks a finished run failed) with the coded message
claude.studio-changed and the list of files. Nothing is ever deleted or restored here.

    python style-library/integrity.py --baseline   # after setup or a deliberate code change
    python style-library/integrity.py              # report (exit 1 when something changed)
"""
import hashlib
import importlib.machinery
import json
import os
import sys
import time
from pathlib import Path

import library
from atomic import atomic_write

# G6: everything Python can import (.py, .pyw, .pyc, .pyd and platform extension modules) plus
# .pth and JavaScript.
CODE_SUFFIXES = tuple(sorted(set(importlib.machinery.all_suffixes()) | {'.pth', '.js', '.mjs', '.cjs'}))
CODE_ROOTS = ('scripts', 'style-library', '.claude', 'node_modules/hyperframes')
# Generated or private places inside the code roots that are not code anyone ships. __pycache__
# is walked separately: only bytecode with no source beside it counts (Python writes the rest).
SKIP_DIRS = {'node_modules', 'runtime', '.venv', 'references', 'assets'}
# G6: the folders Claude runs work in; a Claude memory/settings file or Python code there would
# steer or run in a later session.
WORK_ROOTS = ('projects', 'references')
WORK_SUFFIXES = tuple(s for s in CODE_SUFFIXES if not s.endswith(('.js', '.mjs', '.cjs')))  # gsap.min.js is copied in
TRIPPED = 'logs/integrity-tripped.json'
GENERATED = {'style-library/dist/launch.js'}
MEMORY_FILES = {'CLAUDE.md', 'CLAUDE.local.md', 'AGENTS.md'}
CONFIG_FILES = ('.claude/settings.json', '.claude/settings.local.json', 'CLAUDE.local.md', '.mcp.json')


def _root(root):
    return Path(root) if root is not None else library.STUDIO


def _baseline_path(root):
    return _root(root) / 'logs' / 'integrity.json'


def _sha(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            sha.update(block)
    return sha.hexdigest()


def shipped(root=None):
    path = _root(root) / 'release-files.txt'
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.startswith('#')]


def _is_code(name):
    return name.lower().endswith(CODE_SUFFIXES)


def _orphan_bytecode(folder, name):
    """A __pycache__/<stem>.<tag>.pyc whose <stem>.py is gone: importable by nothing legitimate."""
    return name.endswith('.pyc') and not (Path(folder).parent / (name.split('.')[0] + '.py')).is_file()


def work_files(root=None):
    """G6: Claude memory/settings files and Python code inside projects/ and references/."""
    root = _root(root)
    found = set()
    for top in WORK_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for folder, dirs, files in os.walk(base):
            in_claude = '.claude' in Path(folder).relative_to(base).parts
            for name in files:
                if (in_claude or name.upper().startswith('CLAUDE') and name.lower().endswith('.md')
                        or name.upper() == 'AGENTS.MD' or name == '.mcp.json' or name.lower().endswith(WORK_SUFFIXES)):
                    found.add((Path(folder) / name).relative_to(root).as_posix())
    return sorted(found)


def code_files(root=None):
    root = _root(root)
    found = set()
    for item in root.iterdir():
        if item.is_file() and (_is_code(item.name) or item.name in MEMORY_FILES):
            found.add(item.name)
    for top in CODE_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for folder, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            bytecode = Path(folder).name == '__pycache__'
            for name in files:
                if bytecode:
                    if _orphan_bytecode(folder, name):
                        found.add((Path(folder) / name).relative_to(root).as_posix())
                    continue
                # Every file under .claude/ counts (a new skill, agent or command loads next run),
                # and so does a nested CLAUDE.md anywhere in the code roots.
                if top == '.claude' or _is_code(name) or name in MEMORY_FILES:
                    relative = (Path(folder) / name).relative_to(root).as_posix()
                    if relative not in GENERATED:
                        found.add(relative)
    return sorted(found)


def snapshot(root=None):
    root = _root(root)
    files = {}
    for name in shipped(root):
        target = root / name
        files[name] = _sha(target) if target.is_file() else None
    config = {name: _sha(root / name) for name in CONFIG_FILES if (root / name).is_file()}
    return {'schema_version': 1, 'created': time.time(), 'files': files, 'code': code_files(root), 'config': config,
            'work': work_files(root)}


def write_baseline(root=None):
    path = _baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = snapshot(root)
    atomic_write(path, (json.dumps(data, indent=2) + '\n').encode('utf-8'))
    (_root(root) / TRIPPED).unlink(missing_ok=True)  # an explicit re-baseline clears an earlier trip
    return data


def _release_check_passes(root):
    """The first-run rule: a missing baseline is created only from a tree check_release accepts."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location('integrity_export', Path(root) / 'scripts' / 'export_release.py')
        export = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(export)
        export.ROOT = Path(root)
        files = dict(export.sources())
        spec = importlib.util.spec_from_file_location('integrity_release', Path(root) / 'scripts' / 'check_release.py')
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        release.verify(files)
        return True
    except Exception:  # noqa: BLE001 -- any failure means "not a clean studio tree"
        return False


def changes(root=None):
    """The list of changed paths (empty when the studio is as the baseline recorded), or None
    when there is no baseline yet."""
    root = _root(root)
    try:
        base = json.loads(_baseline_path(root).read_text(encoding='utf-8'))
        if not isinstance(base, dict) or not isinstance(base.get('files'), dict):
            raise ValueError
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return ['logs/integrity.json']
    found = []
    for name, digest in base['files'].items():
        target = root / name
        now = _sha(target) if target.is_file() else None
        if now != digest:
            found.append(name)
    known = set(base.get('code') or [])
    found += [name for name in code_files(root) if name not in known]
    known_work = set(base.get('work') or [])
    found += [name for name in work_files(root) if name not in known_work]
    allowed = base.get('config') or {}
    for name in CONFIG_FILES:
        target = root / name
        if target.is_file() and allowed.get(name) != _sha(target):
            found.append(name)
    return sorted(set(found))


def diff(before, after):
    """Paths that differ between two snapshot()s (G5: the runner keeps the start snapshot in
    memory, so a run that also rewrites or deletes logs/integrity.json is still caught)."""
    found = [name for name in set(before['files']) | set(after['files'])
             if before['files'].get(name) != after['files'].get(name)]
    for key in ('code', 'work'):
        found += sorted(set(after.get(key) or []) ^ set(before.get(key) or []))
    found += [name for name in set(before['config']) | set(after['config'])
              if before['config'].get(name) != after['config'].get(name)]
    return sorted(set(found))


def trip(root, files):
    """Remember that a run changed the studio: every later start is refused until setup (or
    `--baseline`) records a new baseline on purpose. Never deletes anything."""
    path = _root(root) / TRIPPED
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, (json.dumps({'files': files, 'at': time.time()}, indent=2) + '\n').encode('utf-8'))


def check(root=None, first_run=True):
    """[] when a run may start; else the changed paths. G5: an earlier run that changed the
    studio blocks every start until a deliberate re-baseline. A missing baseline is written
    only on a first run (`first_run`: no job ever ran) and only from a tree that passes the
    release check; otherwise ['logs/integrity.json'] (run setup)."""
    root = _root(root)
    tripped = root / TRIPPED
    if tripped.is_file():
        try:
            files = json.loads(tripped.read_text(encoding='utf-8')).get('files') or []
        except (OSError, ValueError, AttributeError):
            files = []
        return sorted(set([TRIPPED] + [f for f in files if isinstance(f, str)]))
    found = changes(root)
    if found is None:
        if (not first_run or not _release_check_passes(root)
                or any((root / name).is_file() for name in CONFIG_FILES)):
            return ['logs/integrity.json']
        write_baseline(root)
        return []
    return found


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--baseline']:
        data = write_baseline()
        print(json.dumps({'ok': True, 'files': len(data['files']), 'code': len(data['code'])}))
        return 0
    found = changes()
    print(json.dumps({'ok': found == [], 'changed': found}, ensure_ascii=False))
    return 0 if found == [] else 1


if __name__ == '__main__':
    raise SystemExit(main())
