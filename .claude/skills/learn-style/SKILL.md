---
name: learn-style
description: Use when the studio sends "/learn-style references/<id>" (the "ללמוד את הסגנון" button or a pasted request) to watch an inspiration video a creator saved and write or refresh its style card, the editable look their own videos can follow.
---

# Learn a style (ללמוד סגנון)

Watch the creator's inspiration video and describe *how* it is made — pace, captions, titles, transitions, graphics, sound, hook — as a style card in the same format as the built-in looks, so the talking-head and faceless skills can build that look with the creator's own material. The creator is not technical and is not watching: follow `docs/skills/headless.md` for tools, language and progress (the reply language is also the card's language). Run the helpers as `python scripts/…`; on a Mac without `python`, the same command with `python3` works.

**Technique only.** Learn the technique, never copy the content: never reuse the reference's footage, frames, words or script lines, logo, handle, watermark or music — not in the card, not in any project. Frames you extract stay in `references/<id>/analysis/` for your own viewing.

Progress steps: `watch` → `analyze` → `card`

Start, before reading anything else: `python scripts/progress.py "references/<id>/progress.json" --start learn-style`.

**Each run is a learn round with its own folder.** The creator can press the button again to re-learn the same video, and ffmpeg never overwrites (`-n`), so never write into an earlier round's folder: Glob `references/<id>/analysis/r*/notes.md`; this run's folder is the next free `references/<id>/analysis/rNN/` (`r01` on the first run, then `r02`, …). All of this round's files (notes, contact sheets, hook frame, words) go there.

## 1. watch

`python scripts/progress.py "references/<id>/progress.json" watch running "צופים בסרטון"` (in the reply language). Find the video with Glob `references/<id>/source.*`. No file (only a link in `style-library/catalog.json`): this unattended run cannot download, so mark `watch` `todo` ("צריך את קובץ הסרטון") and tell the creator to drop the video file on the inspiration card and press the button again. With the file:

1. Write `references/<id>/analysis/r01/notes.md` (this round's folder; a heading is enough, it creates the folder ffmpeg writes into).
2. Measure:

```bash
ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate:format=duration -of json "references/<id>/source.mp4"
ffmpeg -nostdin -hide_banner -i "references/<id>/source.mp4" -vf "select='gt(scene,0.3)',showinfo" -an -f null -
ffmpeg -nostdin -v error -n -i "references/<id>/source.mp4" -vf "fps=2,scale=216:-2,tile=5x4" -q:v 4 "references/<id>/analysis/r01/sheet-%02d.jpg"
ffmpeg -nostdin -v error -n -ss 0.5 -i "references/<id>/source.mp4" -frames:v 1 -vf scale=540:-2 -q:v 3 "references/<id>/analysis/r01/hook.jpg"
ffmpeg -nostdin -hide_banner -i "references/<id>/source.mp4" -vn -af ebur128 -f null -
```

The `showinfo` lines' `pts_time` values are the cuts (shot list); each contact sheet shows 10 seconds at two frames per second. Look at every sheet and the hook frame with Read, plus a few full-size frames where captions or titles are on screen. HEVC/HDR sources decode fine for viewing. If the video has speech, `python scripts/transcribe.py "references/<id>/source.mp4" "references/<id>/analysis/r01/words.json" --language he` (or `en`) measures speaking pace and caption timing; those words are for timing only. (Use the round's folder in every path above: `r02` on a second run, and so on.)

`… watch done "<n> שוטים, <seconds> שניות"`.

## 2. analyze

`python scripts/progress.py "references/<id>/progress.json" analyze running "מנתחים את הסגנון"`. In this round's `analysis/rNN/notes.md` record what you measured (length, number of shots, average shot length, cuts per 10 s, words per second, words per caption, loudness) and what you saw for each card key: caption look (size, weight, case, color, outline or box, position, word-by-word or lines, how they enter), titles, pace, transitions and zooms, graphics (stickers, arrows, B-roll, frames, color), music energy and SFX on cuts, and how the first two seconds hook. Say what you could not tell (e.g. silent sound, too-small text). Then `… analyze done`.

## 3. card

`… card running`. Read `references/<id>/style-card.json` if it exists: it is authoritative — `pinned` holds rows the creator chose to keep, with their own exact values. Write `references/<id>/style-card.md` in the `looks/<id>/card.md` format (read `looks/headline/card.md` as the example):

- front matter: `id` (this reference's id), `name_he`, `name_en` (a short name for the *style*, never the creator's name or handle), then `captions`, `titles`, `pace`, `transitions`, `graphics`, `music`, `sfx`, `hook`, `avoid` — each exactly one non-empty line, concrete enough to build (sizes, positions, seconds, eases, hex colors);
- fonts named from the studio's bundled set only (Secular One, Heebo, Suez One, Karantina, Bellefair: map a bold sans to Secular One or Heebo, a condensed display face to Karantina, a serif to Bellefair or Suez One); Hebrew captions stay right-to-left, one line of at most 28 characters;
- every pinned key's line exactly the creator's pinned value — you never change a pinned row and you never write, move or delete `style-card.json`;
- a body of practical notes: when this look fits, how to apply it to someone else's footage, what to avoid.

`python scripts/check_card.py "references/<id>"` must print `"ok": true`; fix the card until it does. Then `… card done` and reply: what makes this style recognizable in two or three plain sentences, that the card can be edited and rows pinned in the studio, and that new videos can pick it as their look.

## Common mistakes

| Mistake | Instead |
| --- | --- |
| Quoting the reference's lines, or naming the card after the creator | Describe technique; name the style |
| A vague card ("dynamic captions") | Measured, buildable values: size, position, timing, color |
| Changing a pinned row, or writing `style-card.json` | Pinned rows copied exactly; only `style-card.md` is written |
| Inventing what you could not see or hear | Say it in the notes and keep the card line general |
| Fonts the studio does not ship | Map to the bundled five |
