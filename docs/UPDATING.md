# עדכון הסטודיו

הגרסה החדשה של הסטודיו היא תמיד הגרסה האחרונה בענף `main` של
https://github.com/asaf5767/claude-video-studio. אין גרסאות בטא ואין "releases" לבחור ביניהם.

הדרך הקלה: בסטודיו, בעמוד "עדכונים", לוחצים "העתקת בקשת העדכון", פותחים את Claude Code
בתיקיית הסטודיו ומדביקים. Claude עושה את השאר ושואל לפני כל התקנה.

מה Claude עושה בעדכון:

1. **מוריד את הקבצים החדשים.** אם הסטודיו הותקן עם git: `git pull` בתיקיית הסטודיו. אם זה לא
   מסתיים בצורה נקייה, הוא עוצר ומסביר. אף פעם לא `git reset`, `git clean` או מחיקה.
   אם הסטודיו הותקן מקובץ ZIP: מוריד את
   https://github.com/asaf5767/claude-video-studio/archive/refs/heads/main.zip ומעתיק את הקבצים
   שלו מעל התיקייה, בלי למחוק כלום ובלי לגעת במידע שלכם (הרשימה למטה).
2. **משלים מה שחדש** לפי `.claude/skills/setup-studio/SKILL.md`: מה שכבר מותקן מדלגים עליו,
   ועל כל התקנה חדשה הוא שואל קודם.
3. **מפעיל מחדש את הסטודיו**: `python style-library/start.py --restart --open`
   (ב-Mac: `python3`). זה עוצר רק את הסטודיו של התיקייה הזו ומפעיל אותו מחדש.
4. **מספר במילים פשוטות מה השתנה.** הוא לא מפרסם ולא מעלה שום דבר מהעבודה שלכם.

# Updating the studio

The newest version of the studio is always the latest `main` branch of
https://github.com/asaf5767/claude-video-studio. There are no betas or releases to choose between.

The easy way: on the studio's Updates page, press "Copy update request", open Claude Code in the
studio folder and paste it. Claude does the rest and asks before any install.

What the update does:

1. **Get the new files.** Installed with git: `git pull` in the studio folder. If that cannot
   finish cleanly, stop and explain. Never `git reset`, `git clean` or delete anything.
   Installed from a ZIP: download
   https://github.com/asaf5767/claude-video-studio/archive/refs/heads/main.zip and copy its files
   over the folder without deleting anything and without touching the owner's data (list below).
2. **Add what is new** by following `.claude/skills/setup-studio/SKILL.md`: what is installed is
   skipped, and every new install is asked about first.
3. **Restart the studio:** `python style-library/start.py --restart --open` (Mac: `python3`). It
   stops only this folder's own studio server (verified by its health answer and process id) and
   starts it again.
4. **Report in plain words what changed.** Never publish, push or upload the owner's work.

## The owner's data -- never overwrite, move or delete

These are all ignored by git (see `.gitignore`) and are never part of the ZIP, so a correct update
does not touch them:

- `projects/` and `references/` (except their `README.md`)
- `style-library/settings.json`, `style-library/catalog.json`, `style-library/projects.json`
- `style-library/reference-notes.json`, `style-library/writing-voice.json`
- `style-library/runtime/`, `style-library/references/`
- `style-library/dist/assets/posters/`, `style-library/dist/assets/techniques/`,
  `style-library/dist/assets/reference-previews/`, `style-library/dist/launch.js`
- `models/`, `bin/` (downloaded speech models and engine), `.env` (add-on keys), `logs/`
- `.claude/` except `.claude/skills/` (the owner's own Claude settings)
- `node_modules/`, `.venv/` (rebuilt by setup when needed)

## For assistants

- Before setup replaces dependencies it checks this installation's running HyperFrames previews
  and stops if one is open. Then ask the owner to save and close those previews, and run it again.
  Do not kill other work or bypass the check.
- Keep local changes: if `git pull` reports a conflict, stop and ask; never overwrite the owner's
  edits. A studio installed with `--studio-only` stays studio-only unless the owner asks for more.
- After the update, before restarting, run `python style-library/library.py validate` and
  `python style-library/project_index.py validate` against the real registries. Both must pass.
  Never move, rename or re-register the owner's media to fit a new layout.
- Updating the app never re-renders, approves or publishes a video.
- `scripts/check_install.py` (compare installed files with a published manifest) is not part of
  this flow; updates follow `main`, not numbered releases.
- Upstream history (Matt Paige's AI Video Studio betas) is in CHANGELOG.md.
