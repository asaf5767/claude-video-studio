# Building and rendering the composition (HyperFrames)

Each version folder (`projects/<id>/versions/vNN/`, made by `scripts/new_version.py`) is one HyperFrames project: `index.html` plus everything it loads (`fonts/`, `gsap.min.js`, `media/`, the cut or base video). Keep every asset inside the folder with a relative path; nothing from the internet.

## Before the first composition

Read `examples/studio-check/index.html` (a working composition) and the installed CLI's own docs (`node_modules/hyperframes/README.md` and its docs folder) for the exact clip attributes of this version (pinned 0.9.16). Run `python "<studio>/scripts/hf.py" --help` once if you need the command list. If `node_modules/hyperframes` is missing, the studio was not fully set up: stop at this step, mark it `todo` ("צריך להשלים את ההתקנה") and tell the creator to run the setup again.

## Shape

- 1080×1920, 30 fps, `data-duration` = the length of the edit. One root element with `data-composition-id`, `data-start="0"`, `data-duration`, `data-width`, `data-height`; one paused GSAP timeline registered in `window.__timelines`.
- `<link rel="stylesheet" href="fonts/fonts.css">` and `<script src="gsap.min.js"></script>`. No `dir` attribute on `<html>`: put `dir="rtl"` on the text elements themselves.
- The footage is one muted `<video>` (with an `id`) covering the whole duration. Sound is mixed separately and muxed after the render (`docs/skills/sound.md`).
- Captions: paste the cues from `captions.json` into an inline `const CUES = [...]`, create one element per cue before building the timeline, and show/hide each with `tl.set` at its `start`/`end` (pop-ins with `fromTo` on scale/opacity). Text that changes over time is stacked elements swapped with `tl.set`, never GSAP `innerText`.
- Move things with `x`/`y`/`scale`/`opacity`, not `top`/`height`; use `fromTo` with absolute values; one tween at a time per element and property; every overlay fades out at its own end. End the timeline with `tl.to({}, {duration: 0.1}, <duration - 0.1>)`.
- Effects chosen on the Effects board: build each from its `instructions` in `effects/effects.json`, starting on the trigger word's time (`when`) found in the words file; without a trigger, put it where the look card or the beat calls for it. Budget about one big effect per 10 seconds, never two back to back; a plain cut is a valid choice.
- Never feed the composition a long full-frame video with transparency (HyperFrames stalls on it): composite a cut-out presenter with ffmpeg into one opaque base video first and use that.

## Check, render, mux

```bash
python "<studio>/scripts/hf.py" check "projects/<id>/versions/v01"
python "<studio>/scripts/hf.py" render "projects/<id>/versions/v01" --workers 1 --fps 30 --crf 18 --output "projects/<id>/versions/v01/renders/video-only.mp4"
python "<studio>/scripts/media.py" ffprobe -v error -show_entries stream=codec_name,pix_fmt,width,height:format=duration -of json "projects/<id>/versions/v01/renders/video-only.mp4"
python "<studio>/scripts/media.py" ffmpeg -nostdin -v error -n -i "projects/<id>/versions/v01/renders/video-only.mp4" -i "projects/<id>/versions/v01/mix.wav" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "projects/<id>/versions/v01/renders/draft.mp4"
```

Fix every `check` error before rendering. A render takes minutes (roughly 1-2 minutes per 10 seconds of video on a laptop): run it in the foreground with the Bash tool's `timeout` parameter set to `3600000` (one hour), never in the background, and mux only after it has finished. Render once per round, after the stills of a cheaper check look right. The delivered file is always H.264 yuv420p mp4 with AAC audio (Chrome on Windows cannot play HEVC): name it `renders/draft.mp4` for a storyboard round and `renders/final.mp4` for a video round. Confirm its duration matches the composition and look at a few frames before registering. Never render over an existing file (`-n`). If one exists in a version that is not registered yet (you are redoing this round's render after looking at the stills), render and mux under the next free suffix — `renders/video-only-2.mp4`, `renders/draft-2.mp4` or `final-2.mp4`, stills `storyboard/01-2.jpg` … — and register those (`docs/skills/review-loop.md`, "Redoing a step"). If the version is already registered, make a new version with `python "<studio>/scripts/new_version.py" "projects/<id>" --from vNN` instead.
