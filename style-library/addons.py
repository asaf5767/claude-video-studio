"""Optional voice and image add-ons (Task 21): off by default, never required.

Mirrors library.py's settings pattern: `enabled`/`provider` persist in settings.json
under the `addons` key, written atomically under the *same* lock library.py's own
`_save_setting()` uses (`library._SETTINGS_LOCK`, fix round 1 finding 3) -- so a
concurrent /ui-language, /ui-motion or /addons write can never interleave and lose
another's update to settings.json. The API key itself never touches settings.json --
it is written only to `.env` at the studio root (STUDIO_VOICE_KEY / STUDIO_IMAGE_KEY),
through a tiny stdlib KEY=VALUE parser (no third-party dotenv dependency) that edits
only the lines it owns and leaves the rest of a hand-edited `.env` (comments, blank
lines, unrelated variables, `export `/spacing quirks, line endings) untouched (fix
round 1, finding 1). GET /addons (see serve.py) calls `state()`, which never echoes
the key -- only `has_key: bool` -- so the key never round-trips back out over HTTP
once saved. An empty string for `key` in a POST body clears the stored key for that
add-on.
"""
import json
import os
import re
import time
from atomic import atomic_write
import library

PROVIDERS = {'voice': ('elevenlabs',), 'image': ('openai-images', 'foundry')}
ENV_KEY = {'voice': 'STUDIO_VOICE_KEY', 'image': 'STUDIO_IMAGE_KEY'}
KINDS = ('voice', 'image')
# Optional leading whitespace/`export ` before the key, and whitespace immediately
# around `=`, are formatting -- not value content -- so they're stripped the same way
# common .env conventions treat them. Everything else in group(2) (inner and trailing
# whitespace) is the value, kept exactly as written (fix round 1, finding 2: a value's
# own trailing spaces must survive a read/write round trip -- only the formatting
# immediately touching `=` is normalized away).
_ENV_LINE = re.compile(r'^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*)$')
_LINE_ENDINGS = ('\r\n', '\n', '\r')


class AddonsError(Exception):
    """status: HTTP status to answer with. message: plain-language text (this module
    has no i18n keys of its own; serve.py's addons routes answer in plain text the same
    way the existing /ui-language and /ui-motion routes do)."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _settings_path():
    return library.BASE / 'settings.json'


def _read_settings():
    try:
        settings = json.loads(_settings_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def _env_path():
    return library.STUDIO / '.env'


def _match_env_line(line):
    """`(key, value)` for a raw .env line (no trailing line ending) that assigns a
    variable, else `None` for a comment (`#`, after any leading whitespace) or a blank
    line. Only ever called with the terminator already removed -- nothing here strips
    anything else, so a value's own whitespace is returned exactly as written."""
    if not line.strip() or line.lstrip().startswith('#'):
        return None
    match = _ENV_LINE.match(line)
    return (match.group(1), match.group(2)) if match else None


def _read_env():
    """Tiny stdlib KEY=VALUE parser: one assignment per line (an optional leading
    `export` and spacing around `=` are both tolerated), `#` comments and blank lines
    ignored, no quoting/escaping support (the values this module writes -- API keys --
    never contain a newline, so none is needed)."""
    try:
        text = _env_path().read_text(encoding='utf-8')
    except OSError:
        return {}
    env = {}
    for line in text.splitlines():
        parsed = _match_env_line(line)
        if parsed:
            env[parsed[0]] = parsed[1]
    return env


def _line_ending(line):
    for ending in _LINE_ENDINGS:
        if line.endswith(ending):
            return ending
    return ''


def _apply_env_updates(text, updates):
    """Rewrite only the line(s) assigning a key in `updates` (`None` removes that
    line; otherwise it becomes the canonical `KEY=value`, keeping that line's own
    line ending but dropping any `export `/spacing quirks it had); append a new
    `KEY=value` line for any update whose key wasn't already present. Every other
    line -- comments, blanks, unrelated assignments -- is kept completely untouched,
    including its exact line ending, so saving an add-on key never reformats or
    reorders the rest of a hand-edited `.env` (fix round 1, finding 1).

    A key that (unusually) assigns more than once in the file is resolved to a single
    line: the *first* occurrence is the one rewritten (or kept, when clearing -- see
    below) in place; every later duplicate for that same key is dropped rather than
    also rewritten, so a save never leaves two conflicting lines for one variable
    (fix round 2, finding 1). Clearing a key already dropped every occurrence before
    this fix and keeps doing so."""
    lines = text.splitlines(keepends=True)
    seen = set()  # a key seen at least once, whether its first line was rewritten or dropped
    replaced = set()  # a key whose first occurrence has already been rewritten -- any
                       # further line for it this pass is a duplicate to drop, not rewrite again
    out = []
    last_ending = '\n'
    for line in lines:
        ending = _line_ending(line)
        if ending:
            last_ending = ending
        body = line[:len(line) - len(ending)] if ending else line
        parsed = _match_env_line(body)
        if parsed and parsed[0] in updates:
            key = parsed[0]
            seen.add(key)
            value = updates[key]
            if value is None or key in replaced:
                continue  # cleared, or a duplicate of a key already rewritten: drop this line
            replaced.add(key)
            out.append(f'{key}={value}{ending or last_ending}')
        else:
            out.append(line)
    pending = [(key, value) for key, value in updates.items() if value is not None and key not in seen]
    if pending:
        if out and not out[-1].endswith(_LINE_ENDINGS):
            out[-1] += last_ending
        for key, value in pending:
            out.append(f'{key}={value}{last_ending}')
    return ''.join(out)


def _write_env(updates):
    """`updates`: `{ENV_VAR_NAME: new_value | None}` (`None` clears/removes that
    variable). Rewrites `.env` in place via `_apply_env_updates`, then enforces mode
    0o600 (fix round 1, finding 4) regardless of the file's previous mode -- unlike
    `atomic_write`'s normal "preserve the existing mode" behaviour (right for
    settings.json, wrong for a file holding API keys). Best-effort on Windows, where
    `os.chmod` cannot express POSIX permission bits.

    Reads with `newline=''` (universal-newline translation off) -- plain `read_text()`
    would silently turn every `\\r\\n` into `\\n` before `_apply_env_updates()` ever saw
    it, which is exactly the kind of reformatting fix round 1 (finding 1) said this must
    never do to a line it isn't touching."""
    path = _env_path()
    try:
        with path.open('r', encoding='utf-8', newline='') as handle:
            text = handle.read()
    except OSError:
        text = ''
    atomic_write(path, _apply_env_updates(text, updates).encode())
    _chmod_best_effort(path, 0o600)


def _chmod_best_effort(path, mode):
    """A few retries absorb a transient Windows file-lock (e.g. an AV scan briefly
    holding the file right after the `os.replace` inside `atomic_write`) -- genuinely
    unsupported POSIX bits on Windows fail the same way every time and are still
    swallowed after the retries, matching the "best effort on Windows" requirement."""
    for attempt in range(5):
        try:
            os.chmod(path, mode)
            return
        except OSError:
            if attempt == 4:
                return
            time.sleep(0.02)


def _entry(addons, kind):
    raw = addons.get(kind) if isinstance(addons.get(kind), dict) else {}
    provider = raw.get('provider') if raw.get('provider') in PROVIDERS[kind] else None
    enabled = bool(raw.get('enabled')) and provider is not None
    return {'enabled': enabled, 'provider': provider if enabled else None}


def state():
    """`{"voice": {"enabled": bool, "provider": "elevenlabs"|None, "has_key": bool},
    "image": {"enabled": bool, "provider": "openai-images"|"foundry"|None, "has_key": bool}}`.
    Defaults (a fresh studio, or anything unrecognized on disk): both disabled, no
    provider, no key. Never returns the key itself -- only whether one is saved."""
    settings = _read_settings()
    addons = settings.get('addons') if isinstance(settings.get('addons'), dict) else {}
    env = _read_env()
    out = {}
    for kind in KINDS:
        entry = _entry(addons, kind)
        entry['has_key'] = bool(env.get(ENV_KEY[kind], '').strip())
        out[kind] = entry
    return out


def _validate_patch(kind, patch):
    if not isinstance(patch, dict) or set(patch) - {'enabled', 'provider', 'key'}:
        raise AddonsError(400, 'Use a valid add-ons request.')
    enabled = patch.get('enabled')
    if not isinstance(enabled, bool):
        raise AddonsError(400, 'Use a valid add-ons request.')
    provider = patch.get('provider')
    if provider is not None and provider not in PROVIDERS[kind]:
        raise AddonsError(400, 'Choose a supported provider.')
    if enabled and provider is None:
        raise AddonsError(400, 'Choose a supported provider.')
    key = patch.get('key')
    if 'key' in patch and (not isinstance(key, str) or len(key) > 400 or any(ord(c) < 32 for c in key)):
        raise AddonsError(400, 'Use a valid add-ons request.')
    return {'enabled': enabled, 'provider': provider}, (key if 'key' in patch else None)


def save(body):
    """Patch one or both add-ons. `body`: `{"voice"?: {...}, "image"?: {...}}`, each an
    `{"enabled": bool, "provider": str|None, "key"?: str}` patch -- unmentioned add-ons
    (and an unmentioned `key`) are left exactly as they were. The whole read-modify-
    write of settings.json runs under `library._SETTINGS_LOCK` (fix round 1, finding
    3), the same lock `library.set_ui_language()`/`set_ui_motion()` use, so this can
    never race with either of those and silently drop a write. Returns the new
    `state()`."""
    if not isinstance(body, dict) or not body or set(body) - set(KINDS):
        raise AddonsError(400, 'Use a valid add-ons request.')
    settings_patch = {}
    key_patch = {}
    for kind in KINDS:
        if kind not in body:
            continue
        patch, key = _validate_patch(kind, body[kind])
        settings_patch[kind] = patch
        if key is not None:
            key_patch[kind] = key
    with library._SETTINGS_LOCK:
        try:
            settings = library.settings_for_update()  # a corrupt file is moved aside, not lost (M12)
        except OSError:
            raise AddonsError(503, 'Add-ons could not be saved.')
        addons = settings.get('addons') if isinstance(settings.get('addons'), dict) else {}
        for kind, patch in settings_patch.items():
            addons[kind] = patch
        settings['addons'] = addons
        try:
            atomic_write(_settings_path(), (json.dumps(settings, indent=2) + '\n').encode())
        except OSError:
            raise AddonsError(503, 'Add-ons could not be saved.')
        if key_patch:
            env_updates = {ENV_KEY[kind]: (None if key == '' else key) for kind, key in key_patch.items()}
            try:
                _write_env(env_updates)
            except OSError:
                raise AddonsError(503, 'Add-ons could not be saved.')
    return state()
