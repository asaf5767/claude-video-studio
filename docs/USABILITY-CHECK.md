# בדיקת שימושיות (Task 22)

מסמך זה הוא פרוטוקול הבדיקה האנושית שמשלימה את `scripts/smoke.py` (Task 22): הסקריפט מוכיח
שהצנרת עובדת (קוד אמיתי, בלי קלוד אמיתי ובלי רינדור HyperFrames); המסמך הזה מוכיח שאדם לא
טכני יכול להשתמש בסטודיו בעצמו, בלי עזרה.

## מה נחשב "הצלחה"

זרימה נחשבת מוצלחת אם בודק/ת לא טכני/ת עבר/ה אותה **מהתחלה ועד הסוף בלי עזרה** — בלי שהסברתם
לו/ה מה ללחוץ, בלי לפתור בעצמכם תקלה בדרך, ובלי להסביר הודעת שגיאה. אם נזקקתם להתערב (אפילו
הסבר קצר), זו לא הצלחה — זו חסימה שיש לתעד בטבלה למטה ולתקן במשימה נפרדת.

## שלוש הזרימות

### 1. מדבר למצלמה: צילום → שליחה לקלוד → סטוריבורד → הערה → MP4 סופי

1. "סרטון חדש" → "מדבר למצלמה" → עברית.
2. העלאת קליפ קצר (10–30 שניות).
3. מעבר על הבחירות (חיתוך / מראה / סאונד / סיום) ובחירה בכל שלב.
4. לחיצה על "שליחה לקלוד" — מעקב אחרי ההתקדמות שלב־אחר־שלב בעברית.
5. כשמופיע סטוריבורד: עיון בו, כתיבת הערה אחת (למשל "להאריך את הפתיחה"), ואישור הסטוריבורד.
6. סבב נוסף על ההערה, ואז אישור וסימון כסופי — הורדת ה-MP4 הסופי ובדיקה שהוא נפתח ומתנגן.

### 2. סרטון בלי פנים מהקלטת קול

1. "סרטון חדש" → "בלי פנים" → עברית.
2. העלאת הקלטת קול (קריינות) בלבד, בלי צילום.
3. בחירת מראה וסאונד, לחיצה על "שליחה לקלוד".
4. מעבר על הסטוריבורד (סצנות שנבנו בקוד, בלי הצילום של הבודק/ת) ואישורו.

### 3. סרטון השראה → כרטיס סגנון → שימוש בסרטון

1. "מציאת השראה" → הדבקת קישור לסרטון או גרירת קובץ וידאו.
2. "ללמוד את הסגנון" — מעקב אחרי שלבי הלמידה (צופה / מנתח / כותב כרטיס).
3. עיון בכרטיס הסגנון שנכתב, סימון "לשמור" על שורה אחת לפחות, ושמירה.
4. "להשתמש בסגנון הזה בסרטון חדש" → המשך זרימה 1 או 2 עם המראה הזה.

## טבלת חסימות (למלא עבור כל בודק/ת)

| בודק/ת | תאריך | מערכת הפעלה | זרימה | שלב שנתקע בו | מה קרה בדיוק (העתק/י את הטקסט, לא לתרגם) | נפתר? |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |
| | | | | | | |
| | | | | | | |

## פריטים בצ'קליסט הבית שלא ניתן להריץ כאן

נבדקו אוטומטית ב-`scripts/smoke.py` כל חלקי ה**לוגיקה** (`new_project`, `materials`,
`choices`, `claude_runner`, `cut.py`, `captions.py`, `register_version.py`,
`review_actions.py`) — אבל לא הדברים הבאים, שדורשים רשת, Node מותקן בפועל, או מכונה נקייה:

- **רינדור HyperFrames אמיתי** — הסביבה הזו חסומה מרשת ה-npm הציבורית (`node_modules`
  לא מותקן), כך שאין רינדור קומפוזיציה אמיתי כאן; `scripts/smoke.py --hebrew-only`
  מדלג על זה בכוונה (הסטוריבורד שלו נגזר ישירות מ-ffmpeg, לא מ-HyperFrames).
- **רינדור `sample.mp4`** לכל מראה מובנה (`looks/{soft,collage,signature,headline}`) —
  כיום יש רק `sample.jpg` placeholder בכל תיקייה.
- **שלושה תצוגות-מקדימות של אפקטים** שחסרות מ-Task 12 (`effects/effects.json`).
- **התקנה על מכונה נקייה** לפי `docs/plan/clean-machine-test.md` (Windows ו-Mac בלי
  Node/FFmpeg על ה-PATH).
- **מפגש שימושיות אמיתי** עם 2–3 עוקבים/עוקבות: הרצת שלוש הזרימות למעלה בעצמם, מילוי
  הטבלה, ותיקון חסימות במשימות נפרדות.

---

# Usability check (Task 22)

This document is the human-testing protocol that complements `scripts/smoke.py` (Task
22): the script proves the pipeline works (real library code, no real Claude, no
HyperFrames render); this document proves a non-technical person can use the studio
on their own, without help.

## What counts as "success"

A flow counts as successful only if a non-technical tester gets through it **start to
finish without help** — without you explaining what to click, fixing something for
them along the way, or interpreting an error message. If you had to step in (even a
short explanation), that is not success — log it as a blocker in the table below and
fix it as a separate task.

## The three flows

### 1. Talking-head take → Send to Claude (שליחה לקלוד) → storyboard → note → final MP4

1. "New video" ("סרטון חדש") → "Talking head" ("מדבר למצלמה") → Hebrew.
2. Upload a short clip (10-30 seconds).
3. Go through the choices (Cut / Look / Sound / Finish) and pick one at each step.
4. Press "Send to Claude" ("שליחה לקלוד") — watch the step-by-step progress in Hebrew.
5. When a storyboard appears: review it, write one note (e.g. "make the opening
   longer"), and approve the storyboard.
6. Another round on that note, then approve & mark final — download the final MP4
   and confirm it opens and plays.

### 2. Faceless reel from a voice recording

1. "New video" → "Faceless" ("בלי פנים") → Hebrew.
2. Upload only a voice recording (narration), no footage.
3. Pick a look and sound, press "Send to Claude".
4. Review the storyboard (scenes built in code, with no footage of the tester) and
   approve it.

### 3. Inspiration reel → style card → used in a video

1. "Find inspiration" ("מציאת השראה") → paste a video link or drop a video file.
2. "Learn the style" ("ללמוד את הסגנון") — watch the learning steps (watch / analyze /
   write the card).
3. Review the written style card, check "keep" ("לשמור") on at least one row, and save.
4. "Use this style in a new video" ("להשתמש בסגנון הזה בסרטון חדש") → continue flow 1
   or 2 with that look.

## Blocker log (fill in per tester)

| Tester | Date | OS | Flow | Step where stuck | Exactly what happened (copy the text, don't translate) | Resolved? |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |
| | | | | | | |
| | | | | | | |

## Home checklist items that can't run here

`scripts/smoke.py` covers every **logic** piece automatically (`new_project`,
`materials`, `choices`, `claude_runner`, `cut.py`, `captions.py`,
`register_version.py`, `review_actions.py`) — but not the following, which need
network, Node actually installed, or a clean machine:

- **A real HyperFrames render** — this environment is blocked from the public npm
  registry (`node_modules` is not installed), so no real composition render happens
  here; `scripts/smoke.py --hebrew-only` deliberately skips it (its storyboard still
  comes straight from ffmpeg, not from a HyperFrames render).
- **Rendering `sample.mp4`** for each built-in look (`looks/{soft,collage,signature,
  headline}`) — each folder currently only has a placeholder `sample.jpg`.
- **Three effect previews** missing from Task 12 (`effects/effects.json`).
- **Clean-machine install** per `docs/plan/clean-machine-test.md` (Windows and Mac
  with no Node/FFmpeg on PATH).
- **A real usability session** with 2-3 followers: running the three flows above
  themselves, filling in the table, and fixing blockers as separate follow-up tasks.
