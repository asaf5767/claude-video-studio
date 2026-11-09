#!/usr/bin/env python3
"""Task 21 follow-up: the optional voice add-on client (ElevenLabs).

    python scripts/addons_voice.py --text-file <utf8.txt> --out <file.mp3>
                                    [--voice <id>] [--model <id>] [--project <dir>]
                                    [--force] [--allow-cost]
    python scripts/addons_voice.py --check     (ready? {"ok": true} or the coded reason; no call, no key shown)

Calls ElevenLabs' text-to-speech REST API --
`POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
(docs: https://elevenlabs.io/docs/api-reference/text-to-speech/convert, fetched
2026-11-08) with `model_id` `"eleven_multilingual_v2"` by default, ElevenLabs'
documented multilingual model; it supports Hebrew among its 29 languages (see
https://elevenlabs.io/docs/overview/models / https://elevenlabs.io/docs/help-center/
other/what-languages-do-you-support, both fetched 2026-11-08). `--model` overrides
the model id, else `STUDIO_VOICE_MODEL` (`.env` or the process environment) is used
if set (fix round 1, finding 4). The returned MP3 bytes are written to `--out`
atomically (temp file + `os.replace`, via `style-library/atomic.py`).

Only runs when `style-library/addons.py`'s `state()` says voice is enabled with
provider `"elevenlabs"` AND `STUDIO_VOICE_KEY` is set in `.env` (see
docs/plan/addons-contract.md). Anything short of that -- disabled, or enabled with no
key yet -- is the normal fallback path, not an error: the CLI prints
`{"ok": false, "code": "addons.voice-disabled", "message": ...}` and exits 3, so a
calling skill falls back to "record your own voice-over" instead of treating this as a
failure. `--force` overwrites an existing `--out` (RULING R43, fix round 1: refused
with coded `addons.exists` otherwise); the spending guard (text over 5,000
characters) is separately bypassed with `--allow-cost` -- `--force` does not bypass
it. A non-2xx response from ElevenLabs (bad key, rate limit, quota/billing) becomes a
coded `addons.http-<status>` error with only the status code in the message -- never
the response body -- so the key can never leak into a log, a chat transcript, or
`progress.json`.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)
import addons_client as client  # noqa: E402

# ElevenLabs' public "Rachel" demo voice; any owner-chosen voice id overrides this.
DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM'
DEFAULT_MODEL_ID = 'eleven_multilingual_v2'
MODEL_ENV_KEY = 'STUDIO_VOICE_MODEL'


def synthesize(text, out, voice_id=DEFAULT_VOICE_ID, model=None, project=None, force=False, allow_cost=False):
    """Write `text`'s ElevenLabs narration to `out` (MP3) and return the audio's byte
    length. Raises `AddonsClientError` for every fallback/failure case -- disabled, no
    key, output already exists, too long, HTTP error, network error -- never lets one
    through as a crash."""
    client.use_project(project)
    # Fix round 1, finding (minor): require_enabled runs before the spending guard
    # and the overwrite check, so a disabled/no-key add-on is always the reported
    # reason when it's the real one, never masked by an unrelated guard failing first.
    _, key = client.require_enabled('voice')
    client.check_overwrite([out], force)
    client.guard_text_length(text, allow_cost)
    model_id = client.resolved_model(model, MODEL_ENV_KEY, DEFAULT_MODEL_ID)
    body = json.dumps({'text': text, 'model_id': model_id}).encode('utf-8')
    headers = {'xi-api-key': key, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'}
    url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}'
    audio = client.http_request(url, headers, body)
    client.write_output(out, audio)
    return len(audio)


def check(project=None):
    """`{"ok": true, "provider"}` when narration could run now; raises the same coded error
    synthesize() would. Never shows the key."""
    client.use_project(project)
    provider, _ = client.require_enabled('voice')
    return {'ok': True, 'provider': provider}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='only report whether the add-on is ready (no call)')
    parser.add_argument('--text-file', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--voice', default=DEFAULT_VOICE_ID)
    parser.add_argument('--model', default=None, help=f'ElevenLabs model id (default {MODEL_ENV_KEY} or {DEFAULT_MODEL_ID!r})')
    parser.add_argument('--project', default=None, help='studio root to use instead of this checkout')
    parser.add_argument('--force', action='store_true', help='overwrite an existing --out')
    parser.add_argument('--allow-cost', action='store_true', help='bypass the 5,000 character spending guard')
    args = parser.parse_args(argv)
    if jobscope.active() and args.project is not None:
        print(json.dumps({'ok': False, 'code': jobscope.CODE, 'message': '--project is not available in a studio run'}))
        return 2
    if (code := jobscope.refuse(args.text_file) or jobscope.refuse(args.out, write=True)) is not None:
        return code
    if jobscope.active() and (args.allow_cost or getattr(args, 'n', 1) != 1):
        # G10: a studio run never lifts the spending guard or asks for several images.
        print(json.dumps({'ok': False, 'code': jobscope.CODE, 'message': '--allow-cost and --n are not available in a studio run'}))
        return 2
    if args.check:
        try:
            print(json.dumps(check(args.project)))
        except client.AddonsClientError as error:
            return client.emit_failure(error)
        return 0
    if args.text_file is None or args.out is None:
        parser.error('--text-file and --out are required')

    try:
        text = args.text_file.read_text(encoding='utf-8')
    except UnicodeDecodeError as error:
        print(json.dumps({'ok': False, 'code': 'addons.bad-input', 'message': f'{args.text_file} is not valid UTF-8: {error}'}))
        return 3
    except OSError as error:
        print(json.dumps({'ok': False, 'code': 'addons.bad-input', 'message': str(error)}))
        return 3

    try:
        synthesize(text, args.out, args.voice, model=args.model, project=args.project,
                   force=args.force, allow_cost=args.allow_cost)
    except client.AddonsClientError as error:
        return client.emit_failure(error)

    print(json.dumps({'ok': True, 'out': str(args.out), 'chars': len(text)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
