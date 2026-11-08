---
name: setup-studio
description: Use when someone asks to set up, install, repair, update or open the video studio — "תתקין את הסטודיו", "תפתח לי את הסטודיו", "הסטודיו לא נפתח", "set up the studio", "open the studio", or /setup-studio. Installs only what is missing, asks before each install, explains in plain Hebrew and ends with the studio open in the browser. Safe to re-run.
---

# Set up and open the studio

The person you are helping is not technical. Speak plain Hebrew (English only if they write
in English), in the second person plural like the studio itself, one short message per step.
No jargon: if a word like "Python" or "FFmpeg" must appear, say in the same sentence what it does.

## Rules

- **Ask before every install or big download**, one item at a time, and wait for a clear yes.
  Say what it is, why the studio needs it, and the size/time. A "no" is fine: say in one
  sentence what will not work without it, and continue.
- **Never show errors, logs or tracebacks.** If something fails, say in one sentence what did
  not work and what it means, then offer: "רוצים שאנסה שוב, או להעתיק פרטים בשביל מי שעוזר לכם?"
  Only if they ask to copy details, show the technical output in one fenced block, nothing else.
- Run every command from the studio folder (the one with `style-library/` and `scripts/`). If this
  session was not opened there, start each command with `cd "<studio folder>" && `.
- **Python command (`PY` below):** the first that works and says 3.11 or newer. Mac: `python3`,
  then `python3.13`. Windows: `python --version`, then `py -3 --version`, then the full path to `python.exe` in the
  `Programs\Python\Python313` folder inside the user's AppData\Local folder (only if that file exists).
  A Microsoft Store window or an empty answer means that one is not real Python; try the next.
- On Windows, every winget question ends with: "ההתקנה מאשרת את תנאי השימוש החינמיים שלו."
- Never publish, push or upload anything. Re-running is safe: say "כבר מותקן" for what is there.
- Long commands (step 6) run in the background; meanwhile give a one-line update every few
  minutes ("מורידים את מודל הדיבור בעברית, זה החלק הארוך").

**Only opening?** If `style-library/settings.json` exists, setup was done before: run
`PY scripts/setup.py --check --json`, then go to step 7. If something is missing, open the studio
anyway and add one sentence on what is missing, offering to finish it now.

## 1. Which computer

Windows or Mac (from your environment). Anything else: say the studio is built for Windows and
Mac, and that you can still try.

## 2. The installer helper (first, because everything else installs through it)

- Windows: `winget --version`. If missing, say: "חסר כלי ההתקנה של Windows. פתחו את Microsoft
  Store, חפשו App Installer, לחצו 'קבלה' או 'עדכון', וכתבו לי 'סיימתי'."
- Mac: `brew --version` (also try `/opt/homebrew/bin/brew --version`, then `/usr/local/bin/brew --version`).
  If missing, explain: "Homebrew הוא כלי ההתקנה של Mac. הוא צריך את הסיסמה של המחשב, לכן את
  הצעד הזה עושים אתם: פתחו את Terminal (Command+רווח, כותבים Terminal, Enter), הדביקו את השורה
  שאשלח ולחצו Enter. כשהוא מבקש סיסמה, הקלידו את סיסמת המחשב (היא לא תופיע על המסך) ולחצו
  Enter; אחר כך, כשהוא מבקש, לחצו Enter שוב. כשזה נגמר, כתבו לי 'סיימתי'." (In English: "When it
  asks for a password, type your computer's password (it will not show on screen) and press Enter;
  then, when it asks, press Enter again.") Then send exactly the line from https://brew.sh:
  `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- Mac, Homebrew installed but `brew` alone is not found: ask "כדי שהמחשב ימצא את Homebrew גם בפעם
  הבאה, אוסיף שורה אחת לקובץ ההגדרות שלכם. בסדר?" On yes, with `B` = `/opt/homebrew/bin/brew` if it
  exists, else `/usr/local/bin/brew`:
  `grep -qs 'brew shellenv' ~/.zprofile || echo 'eval "$(B shellenv)"' >> ~/.zprofile`
  and start each later command in this session with `eval "$(B shellenv)";`.

## 3. Python (the engine that runs the studio)

Find `PY` (see Rules). If none works, ask: "חסר Python, התוכנה שמריצה את הסטודיו עצמו. הורדה של
כ-30MB, דקה-שתיים. להתקין?"
- Windows: `winget install --id Python.Python.3.13 -e --scope user --source winget --accept-source-agreements --accept-package-agreements`
  (the user-scope installer already adds Python to PATH), then find `PY` again: the full path works right away.
- Mac: `brew install python@3.13`, then `PY` is `python3.13`.

## 4. See what is missing

Run `PY scripts/setup.py --check --json` (a non-zero exit only means something is missing). Read
`tools` (node, npm, ffmpeg, ffprobe), `node_supported` and `renderer`. Then check:
- speech engine: Windows `bin/whisper/whisper-cli.exe`; Mac `command -v whisper-cli`
- speech models: `models/ggml-ivrit-ai-large-v3-turbo.bin` (Hebrew), `models/ggml-base.en.bin` (English)
- background removal: `~/.cache/hyperframes/background-removal/models/u2net_human_seg.onnx`
- `claude --version`. If missing: "חסר הכלי שדרכו הסטודיו שולח עבודה לקלוד. בלי זה, 'שליחה לקלוד'
  תציע להעתיק את הבקשה לצ'אט במקום. להתקין? (כמה דקות)". On yes, the official installer:
  Mac `curl -fsSL https://claude.ai/install.sh | bash`; Windows
  `powershell -NoProfile -Command "irm https://claude.ai/install.ps1 | iex"`.

## 5. Ask about each missing piece

Ask one at a time, in this order. Remember each yes by its name (right column).

| What | Say (one sentence + size) | Name |
|---|---|---|
| Node.js | "Node.js, התוכנה שמרכיבה את הסרטונים. כ-30MB." | `node` |
| FFmpeg (ffprobe comes with it) | "FFmpeg, התוכנה שחותכת ומחברת את הווידאו. כ-200MB." | `ffmpeg` |
| Studio packages | "החבילות של הסטודיו ודפדפן קטן לציור הסרטונים. הכול בתוך תיקיית הסטודיו, ולא נוגע בדפדפן שלכם. כ-500MB." | (none) |
| Speech engine | "מנוע הדיבור, שהופך את מה שאמרתם לכתוביות. קטן, כמה MB." | `whisper-cpp` |
| Hebrew speech model | "מודל הדיבור בעברית, כדי שהכתוביות יבינו עברית. 1.6GB, בין כמה דקות לחצי שעה לפי האינטרנט." | `model-he` |
| English speech model | "מודל דיבור באנגלית, רק לסרטונים באנגלית. כ-150MB, לא חובה." | `model-en` |
| Background removal | "הסרת רקע, רק למראות כמו 'מסך ירוק'. כ-380MB, לא חובה." | `matting` |

**No to Node.js, FFmpeg or the studio packages:** say plainly "בלי זה אי אפשר לערוך סרטונים, רק
לפתוח את הסטודיו ולעיין בו. אפשר להשלים בכל רגע עם /setup-studio." Do not ask the remaining
questions (their yes would be lost), and in step 6 run `PY scripts/setup.py --studio-only --lang he`.
Node.js present but `node_supported` is false: ask to update it (Windows
`winget upgrade --id OpenJS.NodeJS.LTS -e --source winget --accept-source-agreements --accept-package-agreements`,
Mac `brew upgrade node`).

## 6. Install

Before starting on Windows, say: "אם Windows שואל 'לאפשר לאפליקציה לבצע שינויים?', לחצו כן."
Run in the background, with exactly the names they said yes to:

`PY scripts/setup.py --lang he --yes-to node,ffmpeg,whisper-cpp,model-he`

(`--lang en` if you are speaking English.) Anything not named is skipped.
Setup prints short Hebrew lines; retell them in your own words, never paste them.

When it stops early:
- "לא הצלחנו להתחבר למחסן החבילות" → the network blocks downloads (common at work or on a VPN).
  Suggest a home network or turning the VPN off for a moment, then run the same command again.
- "Node 22.12.0 or newer" → offer the Node.js update from step 5.
- "running HyperFrames previews" → ask them to close open video previews, then run it again.
- A tool was installed but is still "not found" → say: "כמעט סיימנו. סגרו את Claude Code, פתחו
  אותו שוב בתיקיית הסטודיו וכתבו /setup-studio. מה שכבר הותקן יידלג."

## 7. Open the studio

If anything was installed in this session: `PY style-library/start.py --restart --open` (it
restarts only this folder's own studio, so it sees the new tools). Otherwise:
`PY style-library/start.py --open`. If `--restart` refuses (it says the studio is already open,
with its address), keep using that studio: open the browser at the address it gave, and say:
"הסטודיו כבר היה פתוח, אז פתחתי אותו כמו שהוא. מה שהתקנו עכשיו ייכנס לפעולה אחרי ההפעלה הבאה של המחשב."
Otherwise it prints a line with `"url"` (usually
`http://127.0.0.1:4870`) and opens the browser. If no browser opened: Windows `start <url>`,
Mac `open <url>`. The studio keeps running in the background after the command ends.

Then say, with the real folder path:
"הסטודיו פתוח בדפדפן! בעמוד הראשון יש הסבר קצר איך עושים סרטון ראשון.
בפעם הבאה: פותחים את Claude Code בתיקייה <folder> וכותבים 'תפתח לי את הסטודיו'."

If they declined something, add one sentence on what is still missing and that they can
write /setup-studio any time to finish it.
