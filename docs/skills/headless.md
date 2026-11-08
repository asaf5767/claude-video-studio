# Running a project skill (shared rules)

The studio's "שליחה לקלוד" button runs Claude Code unattended with the prompt
`/<skill> projects/<id> Reply in Hebrew.`, `--permission-mode dontAsk` and a fixed tool list (`style-library/claude_runner.py`, `ALLOWED`). A creator can also paste the same request into a chat. Either way, work as if nobody is watching.

## Tools you have

| Need | Use |
| --- | --- |
| Read a file, look at a JPEG still | Read |
| Find files (instead of `ls`) | Glob |
| Search text | Grep |
| Create or change a text file (creates its folders too) | Write, Edit |
| Media | `ffmpeg …`, `ffprobe …` |
| Studio helpers | `python scripts/<helper>.py …` (on a Mac without `python`, the same command with `python3` works) |
| HyperFrames | `python scripts/hf.py …` (the pinned local CLI) |

Nothing else runs: no `cd`, `cp`, `mkdir`, `rm`, `npx`, `npm`, `pip`, `curl`, pipes or `&&`; Python only as `python scripts/…` (or `python3 scripts/…` on a Mac), never another script path. One command per Bash call, paths relative to the studio root, every path in double quotes (Hebrew names have spaces). ffmpeg cannot create folders: `scripts/new_version.py` makes `renders/`, `storyboard/` and `sfx/` in each version; for any other folder, Write a small notes file into it first. Copy a project file into a version with `python scripts/new_version.py … --copy`, or for media with `ffmpeg -i "<in>" -c copy "<out>"`. Slow commands (transcribing a long take, `matte.py`, a HyperFrames render) run in the foreground like every other command, with the Bash tool's `timeout` parameter set to `3600000` (one hour; the studio starts Claude Code with `BASH_MAX_TIMEOUT_MS=3600000`, and every other command gets 10 minutes by default). Never run a command in the background: the next step needs its output. A presenter look with a cut-out is meant for reels up to 3 minutes long: its cut-out step takes about 20 minutes per minute of video, so a longer video could pass the one-hour limit (reels are 15-90 seconds by design). Never write new files under `scripts/`, never edit the studio's own code, `style-library/*.json` registries, `settings.json` or `.env`.

## Coded answers that are not errors

- `transcribe.exists` — a transcript with that name is already there. Transcript names carry the media's hash, so it is current: **reuse the existing transcript** and go on (never `--force`, never re-transcribe it). Only a check you must redo (a second cut check after `cut.py --retry`) gets a new file name, such as `cut.check-2.json`.
- `register.final` — the creator marked this project final in the studio; nothing was written. See `docs/skills/review-loop.md`.

## Never stop to ask

The run is unattended: questions get no answer. Decide with the brief, `choices.json`, the material notes and the look card. When something is a guess, take the safe default and write the assumption into `STATUS.md` and your reply. If the run cannot continue (no footage, no voice recording, a missing tool), mark that step `todo` with a short reason and finish with a plain explanation of what the creator should do.

## Progress

Start with `python scripts/progress.py "<folder>/progress.json" --start <skill>` before anything else — before reading the project — so the studio shows the run at once (it ignores an older file). A step the skill adds later (talking-head's optional cut-out step) is inserted in its place the first time you report it. Before each step: `python scripts/progress.py "<folder>/progress.json" <key> running "<short detail>"`; after it: `… <key> done "<what came out>"`. A step that does not apply this round is still marked `done` with a reason ("אין שינוי בסבב הזה"). Details are one short line in the reply language, in plain words, never a path, code or error text.

## Language and tone

The request ends with `Reply in Hebrew.` or `Reply in English.`: that is the creator's interface language. Your reply, progress details, `STATUS.md` notes, storyboard titles and notes use it. Captions and on-screen text use the video's language (`video_language` in the project record, also stated in `brief.md`). No request line? Reply in the language of the brief.

The creator is not technical. The reply says, in a few short sentences: what you made, what to look at in the studio (open the project, the storyboard or the video), any assumption you made, and the next step. No file paths, commands, codes or English jargon in a Hebrew reply.

## Optional add-ons (voice and image)

Voice and image are optional add-ons, off by default (`docs/plan/addons-contract.md`). Read `style-library/settings.json` → `addons`. If `addons.voice.enabled` is true and `STUDIO_VOICE_KEY` is set in the studio's `.env`, you may use ElevenLabs for narration; otherwise the creator records the voice-over as usual. If `addons.image.enabled` is true and `STUDIO_IMAGE_KEY` is set, you may use the configured provider (OpenAI Images or Azure AI Foundry) for generated stills; otherwise build the visual in code. An add-on is used only through the studio's own client script, which reads the key itself: `scripts/addons_voice.py` (narration) and `scripts/addons_image.py` (stills). Check with Glob that the file exists; if it does, run it with `--help` first (for example `python scripts/addons_voice.py --help`) and follow its usage, writing its output under the project's `work/` folder; if it does not exist, take the no-add-on path and say so in that step's detail. Either add-on failing at runtime falls back to the no-add-on path — it never blocks the video. Check whether a key is set without seeing it: Grep the studio's `.env` for `^STUDIO_VOICE_KEY=.+` with the count output mode — never Read `.env`, and never print, log or write a key's value. Never require an add-on.

## Rights and privacy

Use only the creator's own materials (and anything marked "שלי / יש לי זכויות"). Outside footage, music and reference videos are inspiration only. Nothing is published, uploaded or sent anywhere.
