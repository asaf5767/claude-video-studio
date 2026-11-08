# Local tools

Website/registries: Python standard library, loopback server. Media probing/proxies/precise cuts/audio/assembly: FFmpeg/FFprobe. Contact sheets: Pillow. Motion/compositing: pinned HyperFrames and GSAP installed from package-lock.json. Word timing: local whisper.cpp (`python scripts/transcribe.py <media> <out.json> --language he|en`), a Hebrew (ivrit.ai) or English ggml model, on Windows and macOS. No private/global skill path is required.

Use `.venv/bin/python scripts/studio.py --help` on macOS/Linux (Windows uses .venv/Scripts/python.exe). Commands: new, ingest, prepare, assemble. Review metadata first. Assembly preserves originals, pads to fit, refuses HDR without explicit conversion, emits time map/script and rejects existing outputs. It does not automatically choose the best performances, design captions or mix music.

Use `python3 scripts/hf.py <command> ...` for the local renderer. It sets no-update/telemetry flags and fails clearly when npm dependencies are missing. Read the installed CLI help and current official composition docs before changing architecture: https://hyperframes.heygen.com/concepts/compositions . Timed media uses class clip and explicit starts/durations/media offsets; one paused timeline is registered by composition ID. Keep assets local and seek behavior deterministic. Use check, preview, render and inspect actual encoded frames. The sample is editable in examples/studio-check/index.html.

Source/rights ledger: origin, owner, permission, purpose and limitations. Epidemic Sound is an optional source to evaluate with the user's own coverage; no tracks/account coverage ship here. Record edited-time cues and listen for clipped words, masking and excessive repetition. No background music by default.

Run python3 scripts/setup.py --check for the capability report. It checks local prerequisites/packages and leaves browser/site/image-generation availability for the assistant to verify in chat. docs/CAPABILITIES.md explains fallbacks. Simple sound effects can be synthesized locally with code and FFmpeg; a commercial library is optional. Local availability does not prove audible quality.

## Pinned renderer maintenance

This release pins HyperFrames 0.9.16 and retains GSAP 3.14.2. Full media setup needs Node >=22.12.0. HyperFrames currently pins Undici 7.25.0 upstream; the scoped npm override selects patched Undici 7.30.2 within its 7.x line. Keep the override and package-lock.json together, audit after any dependency change and rerun local rendering/editor checks before removing or changing it. Do not run npm audit fix --force or an unpinned upgrade in an owner's studio.

Local check, render and the isolated editor handoff were exercised with synthetic sources; an app update does not rewrite accepted compositions or videos. The 0.9 distributed cloud protocol change is outside the default local workflow. Custom Lambda/Cloud Run owners must migrate their own optional stacks together with their SDK; this release does not deploy or validate cloud infrastructure.
