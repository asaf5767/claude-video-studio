# learn-style contract (Task 13 → Task 17)

The studio's "ללמוד את הסגנון" button runs `/learn-style references/<id>` through the Claude runner (`POST /claude-job {"reference": "<id>", "task": "learn-style"}`). Below is what the skill may and may not touch in `references/<id>/`.

| File | Owner | The skill |
| --- | --- | --- |
| `source.<ext>` (mp4/mov/webm/m4v) | the user's upload | reads it. If it is missing, uses the catalog entry's `source_url`. |
| `progress.json` | the skill | writes `[{"key": "watch"\|"analyze"\|"card", "state": "todo"\|"running"\|"done"}]` as it goes. |
| `style-card.md` | the skill and the user | writes it in the `looks/<id>/card.md` format: front matter with every `looks.REQUIRED_KEYS` key non-empty (`id, name_he, name_en, captions, titles, pace, transitions, graphics, music, sfx, hook, avoid`), one line per key, then a free-text body. |
| `style-card.json` | **the user only** | **never writes, moves or deletes it.** |

**The skill writes only style-card.md. It never writes style-card.json, and it must not change pinned keys.**

- `style-card.json` is `{"pinned": {key: value}}`. It holds the rows the user marked "לשמור" (keep), with the user's own values.
- When re-learning, keep each pinned key's line in `style-card.md` exactly as it is. You can read the pinned values from `style-card.json`.
- The studio enforces this anyway: `inspiration.card(id)` lays the pinned values over `style-card.md`, so a re-learn can never change a pinned row.
- A project whose look is `ref:<id>` follows `inspiration.card(id)["use"]`. That is the pinned rows when there are any, and otherwise the whole card.

Rule shown on every card, which the skill must follow: learn the technique, never copy the content. Do not reuse the creator's footage, words or logo.
