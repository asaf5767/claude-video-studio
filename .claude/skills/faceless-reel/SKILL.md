---
name: faceless-reel
description: Use when the studio sends "/faceless-reel projects/<id>" (the "שליחה לקלוד" button or a pasted request) to turn a creator's voice-over into a vertical reel without their face, with motion graphics, captions and sound, or to apply their review notes to a faceless project's storyboard or video.
---

# Faceless reel (בלי פנים)

The creator's voice over a new visual every few seconds: 1080×1920, one idea per scene, each scene built in code (type, shapes, diagrams, counters) or from their own images and clips, captions in the video's language, light sound. The creator is not technical and is not watching: follow `docs/skills/headless.md` for tools, language, progress and add-ons. Rounds, versions and registering: `docs/skills/review-loop.md`. Run the helpers as `python scripts/…`; on a Mac without `python`, the same command with `python3` works.

Progress steps: `voice` → `transcribe` → `scenes` → `captions` → `sound` → `storyboard`

## 0. Start, then read the project

First of all, before reading anything: `python scripts/progress.py "projects/<id>/progress.json" --start faceless-reel` (the studio shows the run at once). Then read `projects/<id>/`: `brief.md` (choices block in the video's language), `choices.json` (`look`, `sound`, `sfx`, `captions`, `length`, `extra`, `effects: [{effect, when}]`; `cut` and `presenter` do not apply), `materials.json` (tags and the creator's notes), `STATUS.md`, the round's state (review-loop: a project marked final and not reopened stops right here). The look: a built-in id → `looks/<id>/card.md`; `ref:<id>` → `references/<id>/style-card.json` is authoritative for values (its `pinned` rows are the creator's exact values and win), `references/<id>/style-card.md` for the prose and the unpinned rows; no pins → the whole card; none → Collage (`looks/collage/card.md`). Chosen effects: their `instructions` in `effects/effects.json` (skip a missing id or file and say so).

## 1. voice

`python scripts/prepare_media.py "projects/<id>"` first: it makes H.264 SDR mp4 copies of every video (iPhone HEVC, `.mov` and HLG/HDR included, tone-mapped to SDR BT.709), 48 kHz wav copies of every audio file and jpg/png stills, all under `work/media/` (`media.json` lists them). Never use a file from `materials/` directly.

The voice-over is the item tagged `voice` ("קריינות" in the materials tag menu). None tagged? Uploaded audio starts as `music`, so look among the audio items and any video tagged `raw`: prefer a note or file name that says voice/קול/קריינות/הקלטה/narration; otherwise the speech recording is the one that transcribes into real sentences in step 2 (music gives few or no words). Several takes of the same text: keep the last complete one. No recording at all → see the add-ons below; without them mark `voice` `todo` ("צריך הקלטת קול") and tell the creator to upload their voice recording in the materials and send again.

## 2. transcribe

`python scripts/transcribe.py "projects/<id>/work/media/<voice>.wav" "projects/<id>/work/transcripts/<voice>.json" --language he` (`en` for an English video). An existing transcript for that file name is current: `transcribe.exists` means "reuse the existing transcript" (not an error) — use it, never re-transcribe it. Setup errors (`transcribe.no-engine`, `transcribe.model-missing`) → `todo` and ask the creator to run setup again.

## 3. scenes

Make the round's folder: `python scripts/new_version.py "projects/<id>" --copy "work/media/<voice>.wav"` (plus any images or clips you will show; later rounds `--from vNN`, which brings `index.html`, `scenes.json` and `media/` but none of the captions, mix or renders: run those steps again, see review-loop). Plan `versions/vNN/scenes.json`, one scene per idea, 2.5-4 s each (faster or slower per the look's pace), every scene anchored to its first word's time: `[{"start", "end", "words", "label", "visual", "why"}]`.

- **One idea, one object.** Each scene shows the thing the sentence says, as one central visual: a number becomes a counter or a big figure, a list becomes items arriving one by one, a comparison becomes two sides, a process becomes steps with arrows, a tool becomes a simple icon-like drawing. If you cannot name the object, use a short bold phrase instead, never a stock-photo feeling.
- **Hook on frame 1.** The first scene's visual is already on screen at 0 s and states the promise; something moves about every second; the last scene lands the call to action.
- **The creator's own material wins.** An image or clip whose note matches a line goes in that scene ("when I say X" → the time of X). Never invent screenshots or product UI and present them as real.
- **One recurring element** (a counter, a progress bar, a shape that changes with the story) ties the scenes together; label each scene in 1-5 words when the look uses titles.

Then build `versions/vNN/index.html` (`docs/skills/composition.md`): background, palette and motion from the look card, the voice as the length (`data-duration` = voice length + 0.3 s), the chosen effects on their trigger words, scene changes that never leave a dead frame. Run `python scripts/hf.py check "projects/<id>/versions/v01"` and fix every error.

## 4. captions

`docs/skills/captions.md`: correct mishearings into `words.fixed.json`, then `python scripts/captions.py` on the voice transcript with the look's mode. RTL, one line ≤ 28 characters, Latin words and numbers isolated in `<bdi dir="ltr">`, the bundled fonts (Secular One, Heebo, Suez One, Karantina, Bellefair) as the card says, placed where they never cover the scene's main object.

## 5. sound

`docs/skills/sound.md`: a small sound per visual event when `sfx` is on (a pop as an item lands, a whoosh on a scene change, a tick on a counter), the creator's music only if they uploaded one and chose music, voice on top, -16 LUFS into `versions/vNN/mix.wav`, plan in `sound-plan.json`.

## 6. storyboard

Render and mux to H.264 `renders/draft.mp4`, pull one JPEG still per scene, look at them, write `frames.json` (scene label as title, what the viewer sees and hears as note), register `--kind storyboard --preview` (review-loop). In the **final** round render `renders/final.mp4` from the approved storyboard's version (plus open notes), pull a JPEG `poster.jpg` from it and register `--kind final --poster`. Update `STATUS.md` and `review-notes.md` and reply in plain words.

## Optional add-ons

Voice and image are optional add-ons, off by default (`style-library/settings.json` → `addons`). If `addons.voice.enabled` is true and `STUDIO_VOICE_KEY` is set in `.env`, you may use ElevenLabs for narration through `python scripts/addons_voice.py` when that file exists (run it with `--help` first); otherwise the creator records the voice-over themselves as usual. If `addons.image.enabled` is true and `STUDIO_IMAGE_KEY` is set, you may use the configured provider (OpenAI Images or Azure AI Foundry) for generated stills through `python scripts/addons_image.py` when that file exists; otherwise build the visual in code. Either add-on failing at runtime falls back to the no-add-on path and is noted in that step's detail — it never blocks the video, it is never required, and a key's value is never read or shown (details in `docs/skills/headless.md`).

## Common mistakes

| Mistake | Instead |
| --- | --- |
| Using the uploaded `.m4a`/`.mov`/HEVC file directly | Only `work/media/` files from `prepare_media.py` |
| Treating the music file as the voice (both are tagged `music`) | Notes first, then the file that transcribes into sentences |
| Writing into an existing `versions/vNN/` | `new_version.py` every round; approved files are frozen in `approval-state.json` |
| The same layout every scene, or a scene that only repeats the sentence as text | A new object per idea; text only when the beat is the word |
| "AI" or "38" flipping sides in a caption or label | Cue `html` as is; wrap hand-written Latin/number runs in `<bdi dir="ltr">` |
| Asking the creator a question mid-run | Decide, note the assumption in `STATUS.md` and the reply |
