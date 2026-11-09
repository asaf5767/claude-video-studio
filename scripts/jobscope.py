"""Confine a helper's path arguments to the folder one "Send to Claude" job may change (RULING R51).

The studio's runner starts Claude Code with STUDIO_JOB_DIR=<the job's folder, absolute>
(projects/<id> or references/<id>); the model cannot change or unset it (Bash rules never
match past an unknown assignment, and env/export/unset are denied). Every path a helper
reads or writes during such a run goes through confine(): the resolved path (symlinks and
junctions followed) must stay inside that folder -- or, for reads that allow it, inside the
studio's read-only asset folders -- and may not name a `.env*` file, an NTFS stream
(`name:stream`), a Windows device name or a name Windows would silently trim (trailing dot
or space). A refusal is the coded error `job.outside-folder` (exit 2).

Without STUDIO_JOB_DIR (a creator running a helper from their own chat) nothing changes.
"""
import json
import os
from pathlib import Path, PureWindowsPath
import sys

ENV = 'STUDIO_JOB_DIR'
CODE = 'job.outside-folder'
ROOT = Path(__file__).resolve().parents[1]
# Studio folders a run may read media from but never write to (looks' samples, effects demos, ...).
READ_ONLY = ('looks', 'effects', 'templates', 'style-library/dist/assets')
DEVICES = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} | {f'COM{d}' for d in '123456789'} | {f'LPT{d}' for d in '123456789'}
CASELESS = os.name == 'nt' or sys.platform == 'darwin'  # NTFS and default APFS ignore case
# G8: studio-owned records inside a job folder that only the studio writes; no helper output may
# replace them (approval decisions, the creator's pinned card rows, materials and choices, notes).
PROTECTED = {'approval-state.json', 'style-card.json', 'materials.json', 'choices.json', 'review-feedback.json',
             'review-feedback-links.json', 'look.json'}


class JobScopeError(Exception):
    code = CODE


def job_dir():
    value = os.environ.get(ENV)
    return Path(value).resolve() if value else None


def _key(path):
    text = os.path.normpath(str(path))
    return text.casefold() if CASELESS else text


def _inside(path, folder):
    path, folder = _key(path), _key(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _components(path):
    raw = str(path)
    parts = PureWindowsPath(raw).parts if os.name == 'nt' else Path(raw).parts
    anchor = PureWindowsPath(raw).anchor if os.name == 'nt' else Path(raw).anchor
    return [p for p in parts if p != anchor]


def _plain(path):
    """Refuse the spellings that would let one name mean another file."""
    for part in _components(path):
        if part == '..':
            raise JobScopeError(f'{path}: ".." is not allowed in a studio run')
        if ':' in part:
            raise JobScopeError(f'{path}: a ":" stream or device name is not allowed')
        if part not in ('.',) and (part.endswith(' ') or part.endswith('.')):
            raise JobScopeError(f'{path}: a name ending in a dot or space is not allowed')
        if part.split('.')[0].upper().rstrip(' ') in DEVICES:
            raise JobScopeError(f'{path}: a device name is not allowed')
        if part.casefold().startswith('.env'):
            raise JobScopeError(f'{path}: .env files are never read or written in a studio run')


def confine(path, *, new=False, exists=False, read=False, write=False):
    """Return `path` unchanged when this run may use it; raise JobScopeError otherwise.

    new: an output that must not exist yet. exists: an input that must exist. read: an input
    that may also come from the studio's read-only asset folders. write: an output, which may
    never be one of the studio-owned records (PROTECTED)."""
    folder = job_dir()
    if folder is None:
        return path
    if path is None:
        return path
    _plain(path)
    resolved = Path(path).resolve()  # follows symlinks and junctions that exist
    if resolved.name.casefold().startswith('.env'):
        raise JobScopeError(f'{path}: .env files are never read or written in a studio run')
    roots = [folder] + ([ROOT / name for name in READ_ONLY] if read else [])
    if not any(_inside(resolved, root.resolve()) for root in roots):
        raise JobScopeError(f'{path} is outside the folder this run may use ({_relative(folder)})')
    if write and resolved.name.casefold() in PROTECTED:
        raise JobScopeError(f'{path}: the studio keeps this file itself; write a different file')
    if new and resolved.exists():
        raise JobScopeError(f'{path} already exists; write a new file')
    if exists and not resolved.exists():
        raise JobScopeError(f'{path} does not exist')
    return path


def _relative(folder):
    try:
        return folder.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(folder)


def refuse(*paths, **options):
    """For a helper's main(): None when every path is allowed, else print the coded error as one
    JSON line and return the exit code 2."""
    try:
        for path in paths:
            if path is not None:
                confine(path, **options)
    except JobScopeError as error:
        print(json.dumps({'ok': False, 'code': CODE, 'message': str(error)}, ensure_ascii=False))
        return 2
    return None


def active():
    return job_dir() is not None
