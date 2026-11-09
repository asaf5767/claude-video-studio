#!/usr/bin/env python3
"""Task 21 follow-up: the optional image add-on client (OpenAI Images or Azure AI
Foundry).

    python scripts/addons_image.py --prompt-file <utf8.txt> --out <file.png>
                                    [--size 1024x1536] [--n 1] [--model <id>]
                                    [--project <dir>] [--force] [--allow-cost]
    python scripts/addons_image.py --check     (ready? {"ok": true} or the coded reason; no call, no key shown)

The provider is whatever `style-library/addons.py`'s `state()` says for `image`
(`"openai-images"` or `"foundry"` -- see docs/plan/addons-contract.md); this script
never picks one itself.

openai-images: `POST https://api.openai.com/v1/images/generations` (docs:
https://developers.openai.com/api/reference/resources/images/methods/generate, fetched
2026-11-08) with model `"gpt-image-2.5-flare"` by default -- OpenAI's current default
image model as of this writing (`gpt-image-1` was retired 2026-10-23; see
https://developers.openai.com/api/docs/guides/image-prompting, fetched 2026-11-08).
GPT image models always return base64 (no `response_format` switch); `data[].b64_json`
is base64-decoded straight to PNG bytes.

foundry: Azure AI Foundry / Azure OpenAI's images REST route (docs:
https://learn.microsoft.com/azure/ai-foundry/openai/dall-e-quickstart, fetched
2026-11-08): `POST {STUDIO_IMAGE_ENDPOINT}/images/generations?api-version=2025-04-01-preview`,
auth header `Api-Key`. `STUDIO_IMAGE_ENDPOINT` (optional `.env` variable next to
`STUDIO_IMAGE_KEY` -- see docs/plan/addons-contract.md) holds the resource's full
deployment URL, e.g. `https://<resource>.openai.azure.com/openai/deployments/<deployment>`.
A `provider: "foundry"` add-on with no `STUDIO_IMAGE_ENDPOINT` set is a coded
`addons.no-endpoint` error -- the same fallback-not-error treatment as a missing key. The
endpoint must be https on an Azure OpenAI / AI Foundry host (`*.openai.azure.com`,
`*.services.ai.azure.com`, `*.cognitiveservices.azure.com`); anything else is a coded
`addons.bad-endpoint` before the key is sent anywhere (final review C1, defence in depth).

`--model` overrides the model id sent to either provider, else `STUDIO_IMAGE_MODEL`
(`.env` or the process environment) is used if set, else `gpt-image-2.5-flare` (fix
round 1, finding 4).

Only runs when image is enabled with a key (`addons_client.require_enabled`); anything
short of that prints `{"ok": false, "code": "addons.image-disabled", ...}` and exits 3,
so a calling skill falls back to building the visual in code. `--force` overwrites an
existing `--out` or numbered sibling (RULING R43, fix round 1: refused up front, before
any provider call, with coded `addons.exists` otherwise). The spending guard (more
than 4 images in one call, `--n`) is separately bypassed with `--allow-cost` --
`--force` does not bypass it. `--n 1` (the default) writes exactly `--out`; a larger
`--n` writes `--out`'s stem suffixed `-2`, `-3`, ... for the extra images, so a caller
always knows `--out` itself is produced.
"""
import argparse
import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)
import addons_client as client  # noqa: E402

DEFAULT_MODEL = 'gpt-image-2.5-flare'
MODEL_ENV_KEY = 'STUDIO_IMAGE_MODEL'
FOUNDRY_API_VERSION = '2025-04-01-preview'
ENDPOINT_ENV_KEY = 'STUDIO_IMAGE_ENDPOINT'
FOUNDRY_HOSTS = ('.openai.azure.com', '.services.ai.azure.com', '.cognitiveservices.azure.com')


def _decode_images(raw, n):
    try:
        doc = json.loads(raw.decode('utf-8'))
        items = doc['data']
        if not items:
            raise KeyError('data')
        return [base64.b64decode(item['b64_json']) for item in items[:n]]
    except (ValueError, KeyError, TypeError) as error:
        raise client.AddonsClientError('addons.bad-response', 'Provider response had no image data.') from error


def _openai_images(prompt, size, n, model, key):
    body = json.dumps({'model': model, 'prompt': prompt, 'size': size, 'n': n,
                        'output_format': 'png'}).encode('utf-8')
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    raw = client.http_request('https://api.openai.com/v1/images/generations', headers, body)
    return _decode_images(raw, n)


def foundry_endpoint():
    """The configured Foundry endpoint, checked: https on an Azure OpenAI / AI Foundry host."""
    endpoint = (client.addons._read_env().get(ENDPOINT_ENV_KEY) or '').strip()
    if not endpoint:
        raise client.AddonsClientError('addons.no-endpoint', 'STUDIO_IMAGE_ENDPOINT is not set in .env.')
    try:
        parts = urlsplit(endpoint)
        host = (parts.hostname or '').lower()
        port = parts.port
    except ValueError:
        host, port = '', None
    if (parts.scheme != 'https' or port not in (None, 443) or parts.username or parts.password or
            not host.endswith(FOUNDRY_HOSTS) or parts.query or parts.fragment):
        raise client.AddonsClientError('addons.bad-endpoint',
                                       'STUDIO_IMAGE_ENDPOINT must be an https Azure OpenAI / AI Foundry address.')
    return endpoint


def _foundry_images(prompt, size, n, model, key):
    endpoint = foundry_endpoint()
    url = endpoint.rstrip('/') + f'/images/generations?api-version={FOUNDRY_API_VERSION}'
    body = json.dumps({'model': model, 'prompt': prompt, 'size': size, 'n': n,
                        'output_format': 'png'}).encode('utf-8')
    headers = {'Api-Key': key, 'Content-Type': 'application/json'}
    raw = client.http_request(url, headers, body)
    return _decode_images(raw, n)


PROVIDERS = {'openai-images': _openai_images, 'foundry': _foundry_images}


def _output_paths(out, count):
    if count <= 1:
        return [out]
    return [out.with_name(f'{out.stem}-{i}{out.suffix}') if i > 1 else out for i in range(1, count + 1)]


def generate(prompt, out, size='1024x1536', n=1, model=None, project=None, force=False, allow_cost=False):
    """Write `prompt`'s generated image(s) to `out` (and, for `n > 1`, numbered
    siblings) and return `(paths, total_bytes)`. Raises `AddonsClientError` for every
    fallback/failure case -- disabled, no key, no endpoint, output already exists,
    too many images, HTTP error, network error, bad response -- never lets one
    through as a crash."""
    client.use_project(project)
    # Fix round 1, finding (minor): require_enabled runs before the spending guard
    # and the overwrite check, so a disabled/no-key add-on is always the reported
    # reason when it's the real one.
    provider, key = client.require_enabled('image')
    out = Path(out)
    paths = _output_paths(out, n)  # computed from the *requested* n, before any call
    client.check_overwrite(paths, force)
    client.guard_image_count(n, allow_cost)
    model_id = client.resolved_model(model, MODEL_ENV_KEY, DEFAULT_MODEL)
    images = PROVIDERS[provider](prompt, size, n, model_id, key)
    paths = paths[:len(images)]
    for path, data in zip(paths, images):
        client.write_output(path, data)
    return paths, sum(len(data) for data in images)


def check(project=None):
    """`{"ok": true, "provider"}` when a generation could run now (enabled, key set, a valid
    Foundry endpoint); raises the same coded error generate() would. Never shows the key."""
    client.use_project(project)
    provider, _ = client.require_enabled('image')
    if provider == 'foundry':
        foundry_endpoint()
    return {'ok': True, 'provider': provider}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='only report whether the add-on is ready (no call)')
    parser.add_argument('--prompt-file', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--size', default='1024x1536')
    parser.add_argument('--n', type=int, default=1, help='images to request in this one call (default 1)')
    parser.add_argument('--model', default=None, help=f'provider model id (default {MODEL_ENV_KEY} or {DEFAULT_MODEL!r})')
    parser.add_argument('--project', default=None, help='studio root to use instead of this checkout')
    parser.add_argument('--force', action='store_true', help='overwrite an existing --out or numbered sibling')
    parser.add_argument('--allow-cost', action='store_true', help='bypass the 4-images-per-call spending guard')
    args = parser.parse_args(argv)
    if jobscope.active() and args.project is not None:
        print(json.dumps({'ok': False, 'code': jobscope.CODE, 'message': '--project is not available in a studio run'}))
        return 2
    if (code := jobscope.refuse(args.prompt_file) or jobscope.refuse(args.out, write=True)) is not None:
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
    if args.prompt_file is None or args.out is None:
        parser.error('--prompt-file and --out are required')

    try:
        prompt = args.prompt_file.read_text(encoding='utf-8')
    except UnicodeDecodeError as error:
        print(json.dumps({'ok': False, 'code': 'addons.bad-input', 'message': f'{args.prompt_file} is not valid UTF-8: {error}'}))
        return 3
    except OSError as error:
        print(json.dumps({'ok': False, 'code': 'addons.bad-input', 'message': str(error)}))
        return 3

    try:
        paths, total_bytes = generate(prompt, args.out, args.size, args.n, model=args.model, project=args.project,
                                       force=args.force, allow_cost=args.allow_cost)
    except client.AddonsClientError as error:
        return client.emit_failure(error)

    out_field = str(paths[0]) if len(paths) == 1 else [str(p) for p in paths]
    print(json.dumps({'ok': True, 'out': out_field, 'bytes': total_bytes}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
