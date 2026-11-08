# Rounds, versions and registering (talking-head, faceless-reel)

Matt's loop (`docs/WORKFLOW.md`): storyboard → review → edit → refine. The creator reviews in the studio; each "Send to Claude" is one round.

## Which round is this?

**First, a final project.** If the project's record in `style-library/projects.json` has `state: final` and its `review_decision.action` is not `reopen`, the creator approved it as final: **stop here**, before `new_version.py` or any building (`new_version.py` itself refuses with `register.final`). Mark every remaining step `todo` with a short reason in the reply language ("צריך ללחוץ על פתיחה מחדש בסטודיו") and tell the creator in plain words: if they want changes, press "פתיחה מחדש" on the project in the studio, then "שליחה לקלוד" again. Without open notes or a request for changes, the video is simply done: mark the steps `done` ("הסרטון כבר אושר כסופי") and say so.

Otherwise read the project's record in `style-library/projects.json` (Read only, never edit), `approval-state.json` (`current` is the latest studio decision) and `review-feedback.json` (notes whose `status` is `open` and that have no `deleted_at`).

| What you find | This round |
| --- | --- |
| No artifacts yet (`state: draft`) | **First storyboard**: the whole pipeline, then a storyboard version. |
| Open notes on the current storyboard, or it was reopened | **Storyboard refine**: a new version from the current one with the notes applied. |
| The storyboard was approved (`current.kind: storyboard`, `action: approve`) | **Final**: build the edit from the approved storyboard version, apply any open notes, render the video. |
| Open notes on the current video, or it was reopened after a final | **Video refine**: a new video version with the notes applied. |
| `state: final`, not reopened | Stop before building (above). |

The creator's own words in the request (anything after the folder, before `Reply in …`) come first.

## Never overwrite an approved version

Every round works in a new folder: `python scripts/new_version.py "projects/<id>"` (first round) or `python scripts/new_version.py "projects/<id>" --from v01` (refine or final, building on that version). It never reuses a folder, so the exact files the studio froze in `approval-state.json` (hashes of the approved version) stay as they are. Never write into an older `versions/vNN/`, never edit `approval-state.json`, never delete a render. Earlier work stays as history in the studio.

### What `--from` brings, and what you run again

`--from vNN` copies only the composition sources: `index.html`, `scenes.json` and `media/`. It never copies derived outputs — `cut.mp4`, `cut.words.json`, `cut.map.json`, `captions.json`, `words.fixed.json`, `mix.wav`, `sound-plan.json`, `matte/`, `base.mp4`, `renders/`, `storyboard/` — so every round makes its own and a note can never be lost under a stale file. Read the inputs you need from the earlier version (its `cut-request.json`, `words.fixed.json`, `sound-plan.json`) and Write them, with the notes applied, into the new folder. Then run the derived steps again in the new version, in order.

**Talking-head** (the cut and the cut-out live in the version):

| Note is about | Change in the new version | Then run again |
| --- | --- | --- |
| The spoken cut: a line to drop or keep, a retake, length, pauses | `cut-request.json` | cut + cut check, matte (if the look uses it; recomputed, the cut changed), captions, sound; update the times in `index.html`; render |
| Caption text, a misheard word, caption style or size | `words.fixed.json`, the `captions.py` options | cut (same request), matte (`--reuse-from` the previous version's `matte/`), captions, sound, render |
| Graphics, titles, effects, B-roll | `index.html` | cut (same request), matte (`--reuse-from`), captions, sound, render |
| Sound effects or music | `sound-plan.json` | cut (same request), matte (`--reuse-from`), captions, sound, render |
| None (final round after the storyboard was approved) | — | cut (same request), matte (`--reuse-from`), captions, sound, render `final.mp4` |

**Faceless reel** (no cut and no cut-out; the voice is in `media/`, its transcript stays in `work/transcripts/`):

| Note is about | Change in the new version | Then run again |
| --- | --- | --- |
| Caption text, a misheard word, caption style or size | `words.fixed.json`, the `captions.py` options | captions, sound, render |
| A scene's visual, titles, effects | `scenes.json`, `index.html` | captions, sound, render |
| Sound effects or music | `sound-plan.json` | captions, sound, render |
| The voice-over | a new voice file in `media/` (`--copy`) | transcribe the new file, captions, the scenes' times in `scenes.json` / `index.html`, sound, render |
| None (final round after the storyboard was approved) | — | captions, sound, render `final.mp4` |

Re-running a step with the same inputs gives the same result (the cut is frame-exact and byte-identical for the same request), so an unchanged step costs time, never quality. The slow one is reused rather than redone: `python scripts/matte.py` with `--reuse-from "projects/<id>/versions/<previous>/matte"` copies the previous version's cut-out when it was made from exactly this cut (same file hash, same model) and recomputes it otherwise. A step you re-ran unchanged is marked `done` with "כמו בגרסה הקודמת" (or "same as the previous version").

### Redoing a step before the version is registered

`cut.py` and `captions.py` never overwrite a file the studio already shows. Inside the round you are building, before `register_version.py` has run, a step can be redone in the same folder: when the cut check finds a missing word, fix `cut-request.json` and run the same `cut.py` command again with `--retry`, then check it into a new file name (`cut.check-2.json`, then `cut.check-3.json`; never reuse the first check, `transcribe.exists` would hand you the old one). The same `--retry` redoes `captions.py`. A render (and the files made from it) is redone under the next free suffix instead, because ffmpeg and the renderer never overwrite (`-n`): `renders/video-only-2.mp4`, `renders/draft-2.mp4` (or `final-2.mp4`), stills `storyboard/01-2.jpg` …, and those are the paths you register — the same rule as `--retry`: only while nothing from the version is registered. None of this uses up a version number. A version is registered once `register_version.py` has run for it (its files then appear in the project's record; `cut.py` / `captions.py` say "the studio shows it"): from then on nothing in it is redone — make a new version with `--from vNN`.

## Storyboard

A storyboard is real frames of the edit, not a description: render the draft (see `docs/skills/composition.md`), then pull one JPEG still per beat — the hook, every title or effect, every scene change, the call to action — usually 6-12 frames:

```bash
ffmpeg -nostdin -v error -n -ss 2.40 -i "projects/<id>/versions/v01/renders/draft.mp4" -frames:v 1 -vf scale=540:-2 -q:v 3 "projects/<id>/versions/v01/storyboard/03.jpg"
```

Look at every still with Read before registering: captions readable and inside the frame, nothing over the eyes or mouth, no empty or black frame, Hebrew letters in the right order. Fix and re-render if not. Then write `versions/vNN/storyboard/frames.json`: `[{"path": "versions/v01/storyboard/01.jpg", "title": "<beat, 2-5 words>", "note": "<what happens: words, caption, effect, sound>"}]` in the reply language.

## Register (never approves)

```bash
python scripts/register_version.py "projects/<id>" --version V01 --kind storyboard --frames "versions/v01/storyboard/frames.json" --preview "versions/v01/renders/draft.mp4" --cut "versions/v01/cut.mp4" --summary "<one sentence>" --next-step "<what the creator does now>" --lang he
python scripts/register_version.py "projects/<id>" --version V02 --kind final --video "versions/v02/renders/final.mp4" --poster "versions/v02/storyboard/poster.jpg" --summary "<one sentence>" --next-step "<what the creator does now>" --lang he
```

`--cut` is talking-head only. A final video needs `--poster`: one JPEG frame of `final.mp4` that shows the video well (the hook frame, about 1 s in), made with the same ffmpeg still command into `versions/vNN/storyboard/poster.jpg`; the studio uses it when the creator marks the video final. `--lang` is the reply language. It keeps the studio's own record fields (the next "Send to Claude" needs `kind`), keeps every earlier version and every decision the creator saved in the studio exactly as they are (it calls `scripts/register.py project --append-version`), adds the new version and makes it current. It works the same before and after an approval, and never approves anything. If it answers:

- `register.exists` — that version is already registered: you skipped `new_version.py`. Make a new version.
- `register.final` (from `register_version.py` or `new_version.py`) — the creator approved this project as final in the studio. Nothing was written, and nothing can be added until they press "פתיחה מחדש" ("Reopen") on the project in the studio. Keep the files you made, mark the step `todo` ("צריך ללחוץ על פתיחה מחדש בסטודיו"), and tell the creator in plain words: press "פתיחה מחדש" in the studio, then "שליחה לקלוד" again. Never try another way around it.
- `register.failed` — a file is missing or the record could not be updated; nothing changed. Fix the named file and run it again. Never edit `style-library/projects.json` or `approval-state.json` by hand, and never use `register.py --replace` on a project the creator has reviewed (it refuses records with saved decisions).

## A final video

Once the creator presses "Approve & mark final" the project's `state` is `final`; `scripts/new_version.py` and `scripts/register.py --append-version` both refuse (`register.final`) — appending would silently undo their approval. The creator reopens it with "פתיחה מחדש" / "Reopen" in the studio; after that (`review_decision.action` is `reopen`) the next round is an ordinary video refine.

## Notes and handoff

After a refine round, mark each note you applied as AGENTS.md describes ("Saved review feedback"): keep its text and ID, set `status` to `applied` and add the new version to `applied_in`; leave notes you could not apply `open` and say why. Update `STATUS.md` (current version, what changed, assumptions, next step) and append the round to `review-notes.md`, both in the reply language. Record each version's exact commands in `versions/vNN/README.md` so another chat can rebuild it.
