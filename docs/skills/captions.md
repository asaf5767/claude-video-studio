# Captions and on-screen text

Skip captions only when `choices.json` has `"captions": false` (mark the step `done`, "בלי כתוביות לפי הבחירה").

## Words first

Captions come from the word timings of the edit (`cut.words.json` in a talking-head version, the voice transcript in a faceless one). Whisper mishears names and English terms: read the words against the brief and the creator's script, and when something is wrong write `versions/vNN/words.fixed.json` (same times, corrected text) and build from that. English terms, product names and numbers go in their own letters and digits ("AI", "Claude Code", "38"), never transliterated ("איי איי"). Keep what the creator actually said; never invent words.

## Build the cues

```bash
python scripts/captions.py "projects/<id>/versions/v01/cut.words.json" "projects/<id>/versions/v01/captions.json" --lang he --mode word --duration 31.4
```

`--lang` is the video language; `--duration` is the edit's length (the cut's `cut.map.json` duration, or the voice length) so no caption outlasts the video. `--mode word` (one word, or two quick short words, at a time) for energetic looks (Headline, Collage); `--mode line` for calm ones (Soft, Signature) and as the default. `--lines 2` only when the look card asks for two lines. Each cue has `start`/`end` (seconds), `lines`, `html` and per-word `html` with times.

## Rules (all looks)

- **RTL, bidi-safe.** A Hebrew caption element has `dir="rtl"` and `lang="he"`; English has `dir="ltr"`. Use each cue's `html` exactly: every run of Latin words or numbers is already wrapped in one `<bdi dir="ltr">` isolate (a Hebrew prefix like "ה-" stays outside), so "AI חוסך 38 שניות" never reorders. Any on-screen text you write by hand (titles, labels, counters) follows the same rule: wrap Latin/number runs in `<bdi dir="ltr">`. Never put `dir` on `<html>` (HyperFrames renders a black video).
- **One line, at most 28 characters** (`captions.py` enforces it; a cue with `too_long: true` is a single long word: shrink its font for that cue, never split the word).
- **Fonts: the studio's bundled set only**, from the version's `fonts/fonts.css`: Secular One or Heebo (800-900) for captions, Suez One for a warmer caption, Karantina or Secular One for big titles, Bellefair for calm serif titles. Follow the look card's choice; at most two families per video.
- **Readable on any footage**: white or the look's light color with a dark shadow or a soft dark chip behind; key words (numbers, the term being taught, the hook word) may use the look's accent color and run about 1.2× bigger.
- **Placement**: never over the eyes or mouth, never under the bottom 300 px (app buttons and the post text) or the right 160 px (like/comment buttons), never on top of a title or effect that says the same words. When a title or hero word is on screen, hide the caption for that moment, except the hook line, which is always captioned.
- **Timing**: show a cue from its `start` to its `end`; never shift captions off the word times. Strip nothing else from the words.

## Titles and labels

Titles name the beat in 1-4 words (never the whole sentence the creator is saying). Write them in the video language, check the Hebrew spelling, and keep them in the top or middle third away from the face.
