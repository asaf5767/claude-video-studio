"""Shared plumbing for the optional voice/image add-on CLIs (Task 21 follow-up).

`scripts/addons_voice.py` and `scripts/addons_image.py` both import this module. It
never talks to a provider itself -- it only:

1. Reads the add-on's `enabled`/`provider` state and API key exactly the way
   `style-library/addons.py` does, by importing that module (and `library`) instead of
   re-implementing settings/`.env` parsing a second time. `use_project()` lets a caller
   point those two modules' `BASE`/`STUDIO` at a different studio root for one process
   (the CLI's own `--project`, or a test's temp fixture).
2. Wraps `urllib.request` with an HTTPS-only check, a timeout, and coded errors that
   never carry a provider's response body (which could, in principle, echo request
   details) -- only the HTTP status code is ever surfaced.
3. Writes a provider's output file atomically with `style-library/atomic.py`'s
   `atomic_write` -- refusing an existing `--out` (or numbered sibling) unless
   `--force` (RULING R43, fix round 1: `--force` keeps one house meaning everywhere,
   "overwrite existing output"; the spending guard below has its own, differently
   named, bypass flag).
4. Enforces the spending guard from the Task 21 follow-up brief: refuse text over
   5,000 characters, or more than 4 images in one call, unless `--allow-cost`.

Coded errors (`AddonsClientError.code`):
- `addons.<kind>-disabled` -- the add-on is off, on with no provider, or on with no key
  yet in `.env`. docs/plan/addons-contract.md treats all three exactly alike: this is
  the normal fallback path for a calling skill, never an error to show the owner.
- `addons.no-endpoint` -- image add-on, provider "foundry", no `STUDIO_IMAGE_ENDPOINT`.
- `addons.exists` -- `--out` (or a numbered sibling) already exists; pass `--force`.
- `addons.bad-endpoint` -- a non-HTTPS add-on endpoint (refused before any request).
- `addons.http-<status>` -- the provider answered with a non-2xx HTTP status.
- `addons.network` -- DNS/connection/timeout reaching the provider.
- `addons.text-too-long` / `addons.too-many-images` -- the spending guard
  (`--allow-cost` bypasses it; `--force` does not).
- `addons.bad-response` -- a 2xx response that doesn't contain the image/audio data
  expected, or exceeds `MAX_RESPONSE_BYTES`.
- `addons.bad-input` -- `--text-file`/`--prompt-file` could not be read as UTF-8 text.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent

for _path in (str(SCRIPTS_DIR), str(ROOT / 'style-library')):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import addons  # style-library/addons.py -- state(), ENV_KEY, _read_env()  # noqa: E402
import library  # style-library/library.py -- BASE/STUDIO roots  # noqa: E402
from atomic import atomic_write  # style-library/atomic.py  # noqa: E402

MAX_TEXT_CHARS = 5000
MAX_IMAGES_PER_CALL = 4
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
TIMEOUT_SECONDS = 60


class AddonsClientError(Exception):
    """A coded, key-free, user-facing add-on failure (never a raw traceback)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def use_project(project):
    """Point `library.STUDIO`/`library.BASE` (and so `addons.py`'s settings/.env reads)
    at `project` instead of this checkout's own studio root. A no-op when `project` is
    None -- the normal case, where `library`'s own module-level defaults already point
    at this checkout. Tests should prefer patching `library.BASE`/`STUDIO` themselves
    (as `style-library/test_addons.py` does) over calling this, since it mutates the
    shared `library` module in place for the rest of the process."""
    if project is None:
        return
    studio = Path(project).resolve()
    library.STUDIO = studio
    library.BASE = studio / 'style-library'


def addon_state(kind):
    return addons.state()[kind]


def require_enabled(kind):
    """`(provider, key)` once `kind` ("voice"|"image") is enabled with a provider AND a
    non-empty key is present in `.env`. Raises `AddonsClientError('addons.<kind>-
    disabled', ...)` for anything short of that -- off, on with no provider, or on with
    no key yet -- since the contract (docs/plan/addons-contract.md) treats all three as
    the fallback path, never an error."""
    entry = addon_state(kind)
    if not entry['enabled'] or not entry['provider']:
        raise AddonsClientError(f'addons.{kind}-disabled', f'{kind} add-on is disabled.')
    env = addons._read_env()
    key = env.get(addons.ENV_KEY[kind], '').strip()
    if not key:
        raise AddonsClientError(f'addons.{kind}-disabled', f'{kind} add-on has no key configured yet.')
    return entry['provider'], key


def guard_text_length(text, allow_cost):
    if not allow_cost and len(text) > MAX_TEXT_CHARS:
        raise AddonsClientError(
            'addons.text-too-long',
            f'Text is {len(text)} characters (limit {MAX_TEXT_CHARS}). Use --allow-cost to override.')


def guard_image_count(n, allow_cost):
    if not allow_cost and n > MAX_IMAGES_PER_CALL:
        raise AddonsClientError(
            'addons.too-many-images',
            f'{n} images requested (limit {MAX_IMAGES_PER_CALL} per call). Use --allow-cost to override.')


def check_overwrite(paths, force):
    """Refuse (coded `addons.exists`) when any of `paths` already exists, unless
    `force` -- checked up front, before any provider call is made, so a caller never
    pays for a generation it can't then save (RULING R43)."""
    if force:
        return
    for path in paths:
        path = Path(path)
        if path.exists():
            raise AddonsClientError('addons.exists', f'{path} already exists. Use --force to overwrite.')


def resolved_model(cli_value, env_key, default):
    """`--model` wins; else `env_key` read from `.env` (the same key-free reader
    `require_enabled` uses) or the process environment; else `default`."""
    if cli_value:
        return cli_value
    from_env_file = addons._read_env().get(env_key, '')
    value = (from_env_file or os.environ.get(env_key, '')).strip()
    return value or default


def http_request(url, headers, body, method='POST'):
    """POST (or `method`) `body` (bytes) to `url`, returning the raw response bytes.
    HTTPS only. `headers`' own values (an Authorization/xi-api-key/Api-Key the caller
    built with the provider key) are sent on the wire but never logged, and never
    included in a raised message -- only the response *status code* is ever surfaced;
    the body of an error response is not, since it is the provider's own text and not
    ours to guarantee is key-free. The response is capped at `MAX_RESPONSE_BYTES` --
    an unbounded `.read()` let a misbehaving or malicious endpoint exhaust memory."""
    if not url.startswith('https://'):
        raise AddonsClientError('addons.bad-endpoint', 'Refusing a non-HTTPS add-on endpoint.')
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise AddonsClientError(f'addons.http-{error.code}', f'Provider request failed (HTTP {error.code}).') from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise AddonsClientError('addons.network', 'Could not reach the provider (network error).') from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise AddonsClientError('addons.bad-response', f'Provider response exceeded {MAX_RESPONSE_BYTES} bytes.')
    return data


def write_output(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, data)


def emit_failure(error):
    """Print the coded `{"ok": false, "code", "message"}` JSON line a calling skill
    reads to decide to fall back, and return the CLI exit code (3) for it."""
    print(json.dumps({'ok': False, 'code': error.code, 'message': error.message}, ensure_ascii=False))
    return 3
