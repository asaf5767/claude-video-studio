# Add-ons contract for project skills (Task 21 → Task 17)

Task 21 (`style-library/addons.py`, `serve.py`'s `GET`/`POST /addons`) lets the owner
turn on two **optional** add-ons from the studio UI: voice (ElevenLabs) and image
(OpenAI Images or Azure AI Foundry). Both default to **off**, and the studio works
fully without either one. Task 17's three skills (`talking-head`, `faceless-reel`,
`learn-style`) are written after this task, so this section is the exact contract
their `SKILL.md` files must follow — Task 17's own failing test (`check_skills.py`)
should assert that each relevant SKILL.md states these rules, not just link here.

## What's on disk

- Settings: `style-library/settings.json`'s `addons` key —
  `{"voice": {"enabled": bool, "provider": "elevenlabs"|null}, "image": {"enabled": bool, "provider": "openai-images"|"foundry"|null}}`.
  A skill reads this file directly (it runs as Claude editing the project folder, not
  necessarily while the local server is running) rather than calling `GET /addons`.
- Keys: `.env` at the **studio root** (sibling of `style-library/`, not inside a
  project folder) — `STUDIO_VOICE_KEY` for voice, `STUDIO_IMAGE_KEY` for image. A
  skill that needs a key reads this file itself (same tiny `KEY=VALUE` format
  `addons.py` writes: one assignment per line, `#` comments and blank lines ignored)
  or relies on the key already being present in the process environment if the
  caller exported it. Either way: **never** read the key out of `settings.json` (it
  is never written there) and never echo, log, or write the key's value into
  `progress.json`, a commit message, or anything the skill prints to chat.
- Endpoint: `STUDIO_IMAGE_ENDPOINT`, also in `.env` at the studio root, next to
  `STUDIO_IMAGE_KEY` (new in this follow-up). Only meaningful when
  `addons.image.provider` is `"foundry"` — it's the Azure AI Foundry/Azure OpenAI
  resource's full deployment URL (e.g.
  `https://<resource>.openai.azure.com/openai/deployments/<deployment>`). It is not a
  secret the same way a key is, but it still lives only in `.env`, never in
  `settings.json`.

## What a skill must do

1. **Check `enabled` AND the key before ever calling a provider.** `enabled: true`
   with no `STUDIO_VOICE_KEY`/`STUDIO_IMAGE_KEY` present in `.env` means "the owner
   turned it on but hasn't pasted a key yet" — treat that exactly like disabled, not
   as an error.
2. **Voice, when `addons.voice.enabled` is true and `STUDIO_VOICE_KEY` is set:** the
   skill may call ElevenLabs (`provider` is always `"elevenlabs"`, the only
   supported voice provider) to synthesize the voice-over instead of asking the
   owner to record one. **Otherwise** (disabled, or no key yet): record the
   voice-over is the owner's job — the skill's `ingest`/`voice` progress step waits
   for (or transcribes) the owner's own recording, the same as if the add-on didn't
   exist. This is the fallback, not an error path; never block or fail a step for a
   missing voice add-on.
3. **Image, when `addons.image.enabled` is true and `STUDIO_IMAGE_KEY` is set:** the
   skill may call the configured `provider` (`"openai-images"` or `"foundry"`) to
   generate supplementary image assets (e.g. a still for a scene with no footage).
   **Otherwise:** build the visual in code — HyperFrames / the look's own
   `effects.json` primitives (Task 12) — exactly as today, no network image call.
4. **A provider call failing at runtime** (network error, quota, billing problem,
   bad key) is **not** a reason to fail the whole step: catch it, fall back to the
   no-add-on path for that scene/line, and record a short, key-free note in that
   step's `progress.json` `detail` (e.g. `"voice add-on unavailable, recorded
   narration used instead"`) so the owner can see what happened without digging
   through logs.
5. **Never make an add-on required.** No step may assert that `addons.voice` or
   `addons.image` is enabled before proceeding; the full pipeline (ingest through
   storyboard) must produce a finished video with both add-ons left at their
   default of disabled.
6. **Never pass the API key to Claude as visible text.** Scripts the skill shells
   out to should read `STUDIO_VOICE_KEY`/`STUDIO_IMAGE_KEY` from the environment or
   `.env` themselves; the skill's own instructions and chat output talk about
   *whether* a key is configured (`has_key`, from `GET /addons`, if the server
   happens to be running) and never its value.

## The clients (Task 21 follow-up)

Two stdlib-only CLIs do the actual provider calls described above; a skill shells out
to them rather than calling a provider itself. Both never make a network call when
the add-on is off (or on with no key yet) — they print a coded `{"ok": false, ...}`
JSON line and exit **3**, which a skill should treat exactly like "add-on unavailable,
use the fallback path", never as a failed step. A successful call prints
`{"ok": true, ...}` and exits 0.

**Voice** — `scripts/addons_voice.py`:

```
python scripts/addons_voice.py --text-file <utf8.txt> --out <file.mp3> [--voice <id>] [--model <id>] [--project <dir>] [--force] [--allow-cost]
```

Calls ElevenLabs (`model_id` `eleven_multilingual_v2` by default, which supports
Hebrew) when `addons.voice.enabled` and `STUDIO_VOICE_KEY` is set; `--voice` overrides
the default voice id. On success prints `{"ok": true, "out": "<file.mp3>", "chars": <int>}`.

**Image** — `scripts/addons_image.py`:

```
python scripts/addons_image.py --prompt-file <utf8.txt> --out <file.png> [--size 1024x1536] [--n 1] [--model <id>] [--project <dir>] [--force] [--allow-cost]
```

Calls whichever provider `addons.image.provider` names (`openai-images` or
`foundry`) when `addons.image.enabled` and `STUDIO_IMAGE_KEY` is set. `--n > 1`
requests that many images in one call and writes `--out`'s stem suffixed `-2`, `-3`,
... for the extras (`--out` itself always holds the first). On success prints
`{"ok": true, "out": "<file.png>" | ["<file.png>", ...], "bytes": <int>}`.

`provider: "foundry"` additionally needs a **new** `.env` variable,
`STUDIO_IMAGE_ENDPOINT` — the Azure resource's full deployment URL, e.g.
`https://<resource>.openai.azure.com/openai/deployments/<deployment>`. It lives next
to `STUDIO_IMAGE_KEY` at the studio root, read the same key-free way; a `foundry` add-on
with no endpoint configured is treated like a missing key (fallback, not an error:
`addons.no-endpoint`).

**Model id (fix round 1, finding 4).** Both scripts default their provider's model id
(`eleven_multilingual_v2` for voice, `gpt-image-2.5-flare` for image) but accept
`--model <id>` to override it; absent `--model`, `STUDIO_VOICE_MODEL` /
`STUDIO_IMAGE_MODEL` is read the same key-free way as the API key (`.env`, or the
process environment) and used if set.

**`--force` vs. `--allow-cost` (RULING R43, fix round 1).** `--force` has one meaning
everywhere in these two scripts: overwrite an existing output. An existing `--out` (or
any numbered sibling for `--n > 1`) is refused up front — before any provider call —
with coded `addons.exists`, unless `--force` is passed. The spending guard (a
`--text-file` over 5,000 characters, or `--n` over 4 images) is a *separate* concern
with its own flag, `--allow-cost`: refused with `addons.text-too-long` /
`addons.too-many-images` unless `--allow-cost` is passed. `--force` does **not**
bypass the spending guard, and `--allow-cost` does **not** bypass the overwrite
check — a skill that wants both passes both flags.

Coded `code` values a skill may see: `addons.voice-disabled` / `addons.image-disabled`
(off, or on with no key yet — fall back silently), `addons.no-endpoint` (foundry, no
`STUDIO_IMAGE_ENDPOINT` — same fallback), `addons.exists` (`--out` or a numbered
sibling already exists — pass `--force` to overwrite, or choose a new path),
`addons.bad-endpoint` (a non-HTTPS endpoint was refused before any request — this
should never happen with the documented providers; it means `STUDIO_IMAGE_ENDPOINT` or
similar was misconfigured), `addons.http-<status>` (the provider answered with a
non-2xx status — fall back, note the status in `progress.json`'s `detail`, never the
key), `addons.network` (could not reach the provider — fall back),
`addons.text-too-long` / `addons.too-many-images` (the spending guard — pass
`--allow-cost` to override, never `--force`), `addons.bad-response` (an unexpected or
oversized provider reply), `addons.bad-input` (an unreadable, or non-UTF-8,
`--text-file`/`--prompt-file`). None of these is ever a reason to fail the step — rule
4 above still applies: catch the non-zero exit, fall back, record a short key-free
`detail`.

Sources consulted for the provider calls (fetched 2026-11-08): ElevenLabs text-to-speech
convert (https://elevenlabs.io/docs/api-reference/text-to-speech/convert) and its model
language table (https://elevenlabs.io/docs/overview/models); OpenAI's image generation
reference (https://developers.openai.com/api/reference/resources/images/methods/generate)
and image-prompting guide (https://developers.openai.com/api/docs/guides/image-prompting);
Azure AI Foundry's image quickstart
(https://learn.microsoft.com/azure/ai-foundry/openai/dall-e-quickstart).

Suggested phrasing for each `SKILL.md` (one short paragraph, per the brief): *"Voice
and image are optional add-ons, off by default. If `addons.voice.enabled` is true and
`STUDIO_VOICE_KEY` is set in `.env`, you may use ElevenLabs for narration; otherwise
record the voice-over yourself as usual. If `addons.image.enabled` is true and
`STUDIO_IMAGE_KEY` is set, you may use the configured provider (OpenAI Images or
Azure AI Foundry) for generated stills; otherwise build the visual in code. Either
add-on failing at runtime falls back to the no-add-on path — it never blocks the
video."*
