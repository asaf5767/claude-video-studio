# התקנה ידנית

הדרך הקלה היא [ההודעה האחת מ-README](README.md#התקנה-בהודעה-אחת): Claude Code עושה את כל זה בשבילכם
לפי הסקיל `.claude/skills/setup-studio/SKILL.md`. כאן אותם צעדים, למי שרוצה לעשות אותם לבד
(או ל-Claude, אם הסקיל לא זמין). כל הפקודות רצות בתוך תיקיית הסטודיו.
ב-Windows כותבים `python`, וב-Mac `python3`.

1. **מורידים את הסטודיו.** `git clone https://github.com/asaf5767/claude-video-studio` לתיקייה שתבחרו
   (למשל `claude-video-studio` בתיקיית הבית, התיקייה עם שם המשתמש שלכם). בלי git: מורידים את
   https://github.com/asaf5767/claude-video-studio/archive/refs/heads/main.zip, פותחים את הקובץ
   (לחיצה כפולה, או לחיצה ימנית ו"חילוץ הכול" ב-Windows) ומעבירים את התיקייה שבתוכו למקום שבחרתם.
2. **Python 3.11 ומעלה** (התוכנה שמריצה את הסטודיו). בודקים: `python --version`.
   ב-Mac מתקינים קודם את Homebrew (כלי ההתקנה של Mac) מהאתר https://brew.sh, ואז `brew install python@3.13`.
   ב-Windows: `winget install --id Python.Python.3.13 -e --scope user`. אם `python` לא עובד, נסו `py -3`.
3. **בודקים מה חסר:** `python scripts/setup.py --check`. התשובה בעברית ומסבירה כל דבר חסר.
4. **מתקינים:** `python scripts/setup.py`. ההתקנה שואלת לפני כל כלי ולפני כל הורדה גדולה (עונים כ או ל):
   Node.js (מרכיב את הסרטונים), FFmpeg (חותך ומחבר וידאו), מנוע הדיבור ומודל הדיבור בעברית
   (1.6GB, בשביל הכתוביות), ובאופן לא חובה גם מודל לאנגלית והסרת רקע.
   אפשר להריץ שוב בכל זמן: מה שכבר מותקן מדלגים עליו, והסרטונים וההגדרות שלכם נשמרים.
5. **פותחים את הסטודיו:** `python style-library/start.py --open`. הדפדפן נפתח על הסטודיו
   (בדרך כלל http://127.0.0.1:4870). בפעם הבאה מספיק לפתוח את Claude Code בתיקייה ולכתוב "תפתח לי את הסטודיו".

אם רשת העבודה חוסמת הורדות (קורה עם VPN או רשת ארגונית), ההתקנה תגיד את זה בעברית.
נסו מרשת אחרת, למשל בבית, והריצו שוב את אותה פקודה.

# Manual setup

The easy way is [the one message in the README](README.en.md#install-with-one-message): Claude Code
does all of this for you following the `.claude/skills/setup-studio/SKILL.md` skill. These are the
same steps for doing it yourself (or for Claude, when the skill is not available). Run every
command inside the studio folder. On Windows type `python`; on a Mac, `python3`.

1. **Get the studio.** `git clone https://github.com/asaf5767/claude-video-studio` into a folder of
   your choice (for example `claude-video-studio` in your home folder). No git? Download
   https://github.com/asaf5767/claude-video-studio/archive/refs/heads/main.zip, open it (double-click,
   or right-click and "Extract All" on Windows) and move the folder inside to where you want it.
2. **Python 3.11 or newer** (it runs the studio). Check with `python --version`.
   Mac: install Homebrew (the Mac installer) from https://brew.sh first, then `brew install python@3.13`.
   Windows: `winget install --id Python.Python.3.13 -e --scope user`. If `python` does not work, try `py -3`.
3. **See what is missing:** `python scripts/setup.py --check --lang en`.
4. **Install:** `python scripts/setup.py --lang en`. It asks before each tool and each big download
   (answer y or n): Node.js (assembles the videos), FFmpeg (cuts and joins video), the speech engine
   and the Hebrew speech model (1.6GB, for captions), and optionally an English model and
   background removal. Re-running is safe: what is installed is skipped, and your videos and
   settings are kept.
5. **Open the studio:** `python style-library/start.py --open`. Your browser opens the studio
   (usually http://127.0.0.1:4870). Next time, open Claude Code in the folder and write
   "Open the studio for me".

If a work network blocks downloads (common with a VPN or a company network), setup says so in
plain words. Try another network, such as your home network, and run the same command again.

## For assistants and developers

- `scripts/setup.py` flags: `--check` (report only), `--json` (machine-readable report),
  `--studio-only` (the home base without media tools), `--lang he|en`, `--yes` (answer yes to
  everything) and `--yes-to node,ffmpeg,whisper-cpp,model-he,model-en,matting` (pre-answer yes to
  exactly these, after asking the owner in chat; anything not listed is still asked, which without
  a terminal means no). setup.py never changes your shell profile; system tools are installed only
  with winget (Windows) or Homebrew (Mac) after a yes. With the owner's OK, the setup-studio skill
  adds Homebrew's one `brew shellenv` line to `~/.zprofile` (once) so a new Terminal finds it.
  setup.py and the studio server also look in Homebrew's folders and reload the saved Windows PATH
  themselves, so tools installed a moment ago are found without reopening anything.
- `python style-library/start.py --open` opens the studio; `--restart` stops this folder's own
  studio server (verified by its health answer and process id) and starts a fresh one.
- Setup creates `.venv`, installs hash-pinned Python packages, runs `npm ci` from the lock,
  downloads HyperFrames' render browser, copies GSAP into the synthetic sample, and creates empty
  personal catalogs/settings only when they are missing. Speech models go to `models/`, the
  Windows speech engine to `bin/whisper/`; both are SHA-256 verified (see `studio.config.json`).
- Checks:

  ```sh
  python -m unittest discover -s style-library -p 'test_*.py' -q
  node scripts/run_node_tests.mjs
  python style-library/project_index.py validate
  python style-library/library.py validate
  python scripts/smoke.py
  ```

  Smoke builds a small synthetic source, makes a two-cut assembly and checks a rendered animation.
  It does not judge real footage, captions or artistic quality.
- `start.py` prints the address it uses; if another studio is running it picks another free port.
  Keep the service local. Use the printed HTTP address, not the HTML file.
- Renderer failure: run `python scripts/hf.py doctor --json` and inspect the output. Do not
  upgrade the pinned renderer or disable security checks just to get a pass.
- Updating an existing studio: keep working in its folder and see docs/UPDATING.md. Never extract
  a fresh copy over a used folder or replace populated registries with the empty examples; your
  projects, references, notes and settings must survive. Running HyperFrames previews of this
  installation pause a full setup re-run until they are closed.
- Claude Code reads CLAUDE.md and AGENTS.md here. No account credentials or private global skills
  are bundled.
