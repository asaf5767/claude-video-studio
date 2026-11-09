"""User-facing server messages as i18n keys (final review I2, round 2).

The feedback, script, writing and reference-note modules raise plain English sentences
(the Python tests and logs keep them). Every HTTP error answer goes through
serve.Handler.json_error, which calls code(): a known sentence becomes its i18n key
("server.<slug>"), so the UI shows it in the studio's language (I18N.server translates a
key answer). he.json/en.json carry the keys; test_server_messages keeps them complete.
"""
import re

# (English text exactly as raised or answered, Hebrew text). English UI text is the same
# sentence with "your assistant" / "your editing chat" / "chat" pointing at Claude.
MESSAGES = [
    # feedback.py
    ('Choose a registered project.', 'בחרו סרטון רשום.'),
    ('This project is no longer registered.', 'הסרטון הזה כבר לא רשום בסטודיו.'),
    ('The project folder needs a safe local path before saving feedback.', 'תיקיית הסרטון צריכה נתיב מקומי בטוח לפני שמירת הערות.'),
    ('The feedback file needs attention before adding more notes.', 'קובץ ההערות צריך בדיקה לפני שמוסיפים עוד הערות.'),
    ('The saved feedback needs repair. Existing notes were preserved.', 'ההערות השמורות צריכות תיקון. ההערות הקיימות נשמרו.'),
    ('The feedback links file needs attention. Your notes are preserved.', 'קובץ הקישורים להערות צריך בדיקה. ההערות שלכם נשמרו.'),
    ('Saved feedback links need repair. Your notes are preserved.', 'הקישורים השמורים להערות צריכים תיקון. ההערות שלכם נשמרו.'),
    ('This feedback link is unavailable.', 'הקישור להערות לא זמין.'),
    ('This saved feedback selection is unavailable. Your other notes are preserved.', 'בחירת ההערות השמורה לא זמינה. שאר ההערות שלכם נשמרו.'),
    ('This saved feedback selection needs repair. Your notes are preserved.', 'בחירת ההערות השמורה צריכה תיקון. ההערות שלכם נשמרו.'),
    ('Selected feedback was edited or deleted after copying. Review and copy again. Notes: ', 'הערות שנבחרו נערכו או נמחקו אחרי ההעתקה. עברו עליהן והעתיקו שוב.'),
    ('A previous save needs recovery before saving feedback.', 'שמירה קודמת צריכה שחזור לפני שמירת הערות.'),
    ('Choose a valid saved feedback selection.', 'בחרו בחירת הערות שמורה תקינה.'),
    ('Choose saved feedback notes first.', 'קודם בחרו הערות שמורות.'),
    ('Choose valid saved feedback notes.', 'בחרו הערות שמורות תקינות.'),
    ('This version is unavailable. Reopen the project before copying.', 'הגרסה הזו לא זמינה. פתחו מחדש את הסרטון לפני ההעתקה.'),
    ('The saved notes changed. Reopen this version, review the notes and copy again.', 'ההערות השמורות השתנו. פתחו שוב את הגרסה, עברו על ההערות והעתיקו שוב.'),
    ('This feedback link needs attention. Existing records were preserved.', 'הקישור להערות צריך בדיקה. הרשומות הקיימות נשמרו.'),
    ('Ask your assistant to archive old feedback links first.', 'קודם בקשו מקלוד להעביר לארכיון קישורי הערות ישנים.'),
    ('Use a valid feedback request.', 'בקשת ההערה לא תקינה.'),
    ('Use a valid save request.', 'בקשת השמירה לא תקינה.'),
    ('Write a note of up to 2,000 characters.', 'כתבו הערה של עד 2,000 תווים.'),
    ('This version is no longer registered. Refresh the project.', 'הגרסה הזו כבר לא רשומה. רעננו את הסרטון.'),
    ('This save request was already used for a different note.', 'בקשת השמירה הזו כבר שימשה להערה אחרת.'),
    ('Ask your assistant to archive completed feedback first.', 'קודם בקשו מקלוד להעביר לארכיון הערות שטופלו.'),
    ('This version has a missing file. Your note has not been discarded.', 'בגרסה הזו חסר קובץ. ההערה שלכם לא נמחקה.'),
    ('This version changed. Refresh its context before saving your note.', 'הגרסה השתנתה. רעננו אותה לפני שמירת ההערה.'),
    ('Choose a valid moment in the video.', 'בחרו רגע תקין בסרטון.'),
    ('Choose a valid storyboard scene or slide.', 'בחרו סצנה או שקופית תקינה מהסטוריבורד.'),
    ('This note applies to the whole document.', 'ההערה הזו חלה על כל המסמך.'),
    ('Ask your assistant to archive completed feedback before adding more.', 'בקשו מקלוד להעביר לארכיון הערות שטופלו לפני שמוסיפים עוד.'),
    ('Choose a valid feedback action.', 'בחרו פעולה תקינה על ההערה.'),
    ('Use a valid feedback change request.', 'בקשת שינוי ההערה לא תקינה.'),
    ('Choose a valid saved note and request.', 'בחרו הערה שמורה ובקשה תקינות.'),
    ('Refresh this note before changing it.', 'רעננו את ההערה לפני שמשנים אותה.'),
    ('This change request was already used for another action.', 'בקשת השינוי הזו כבר שימשה לפעולה אחרת.'),
    ('Use a new change request.', 'נסו שוב עם בקשה חדשה.'),
    ('This saved note is unavailable.', 'ההערה השמורה לא זמינה.'),
    ('This note changed in another window or editing chat. Refresh the notes before saving; your draft is preserved.',
     'ההערה השתנתה בחלון אחר או אצל קלוד. רעננו את ההערות לפני השמירה; הטיוטה שלכם נשמרה.'),
    ('This note was already deleted or restored. Refresh the notes.', 'ההערה כבר נמחקה או שוחזרה. רעננו את ההערות.'),
    ('Feedback history is full. Existing notes were preserved.', 'היסטוריית ההערות מלאה. ההערות הקיימות נשמרו.'),
    # project_script.py
    ('This script needs a safe project-local path. Existing files are preserved.', 'התסריט צריך נתיב בטוח בתוך תיקיית הסרטון. הקבצים הקיימים נשמרו.'),
    ('This script needs attention in your editing chat.', 'התסריט צריך בדיקה של קלוד.'),
    ('Your script history needs attention in chat. It is preserved.', 'היסטוריית התסריט צריכה בדיקה של קלוד. היא נשמרה.'),
    ('Saved scripts need repair. Your existing files are preserved.', 'התסריטים השמורים צריכים תיקון. הקבצים הקיימים שלכם נשמרו.'),
    ('That saved script version is unavailable.', 'גרסת התסריט השמורה לא זמינה.'),
    ('Use a valid project script request.', 'בקשת התסריט לא תקינה.'),
    ('Use a valid script save request.', 'בקשת שמירת התסריט לא תקינה.'),
    ('Enter a script up to 50,000 characters.', 'כתבו תסריט של עד 50,000 תווים.'),
    ('This save request was already used. Reload the saved script.', 'בקשת השמירה הזו כבר נוצלה. טענו מחדש את התסריט השמור.'),
    ('This script changed elsewhere. Reload the saved script; your draft is kept.', 'התסריט השתנה במקום אחר. טענו מחדש את התסריט השמור; הטיוטה שלכם נשמרת.'),
    ('Your script history is full. Ask your editing chat to archive it safely.', 'היסטוריית התסריט מלאה. בקשו מקלוד להעביר אותה לארכיון בבטחה.'),
    ('An earlier save needs recovery first.', 'קודם צריך לשחזר שמירה קודמת.'),
    ('The existing script is too long to version here. It is preserved.', 'התסריט הקיים ארוך מדי לשמירת גרסאות כאן. הוא נשמר.'),
    # scripting.py
    ('Use a shorter text value.', 'השתמשו בטקסט קצר יותר.'),
    ('Use a new request identity.', 'נסו שוב עם בקשה חדשה.'),
    ('Writing files need safe local paths. Existing files are preserved.', 'קובצי הכתיבה צריכים נתיבים מקומיים בטוחים. הקבצים הקיימים נשמרו.'),
    ('Writing history needs attention in chat. It is preserved.', 'היסטוריית הכתיבה צריכה בדיקה של קלוד. היא נשמרה.'),
    ('Writing history needs repair. It is preserved.', 'היסטוריית הכתיבה צריכה תיקון. היא נשמרה.'),
    ('The current writing version is unavailable. Existing history is preserved.', 'גרסת הכתיבה הנוכחית לא זמינה. ההיסטוריה הקיימת נשמרה.'),
    ('Reload the writing context before saving.', 'טענו מחדש את הכתיבה לפני השמירה.'),
    ('This request was already used for different writing context.', 'הבקשה הזו כבר שימשה לכתיבה אחרת.'),
    ('This writing context changed elsewhere. Reload it; your draft is kept.', 'הכתיבה השתנתה במקום אחר. טענו אותה מחדש; הטיוטה שלכם נשמרת.'),
    ('An earlier save needs recovery before continuing.', 'שמירה קודמת צריכה שחזור לפני שממשיכים.'),
    ('Writing history is full. Ask your editing chat to archive it safely.', 'היסטוריית הכתיבה מלאה. בקשו מקלוד להעביר אותה לארכיון בבטחה.'),
    ('Scripts belong to video projects.', 'תסריטים שייכים לסרטוני וידאו.'),
    ('The script brief needs repair. It is preserved.', 'תקציר התסריט צריך תיקון. הוא נשמר.'),
    ('Use a valid script brief request.', 'בקשת תקציר התסריט לא תקינה.'),
    ('The script changed. Save and reload the current script before marking it ready.', 'התסריט השתנה. שמרו וטענו מחדש את התסריט הנוכחי לפני שמסמנים אותו כמוכן.'),
    ('Use a valid script approval request.', 'בקשת אישור התסריט לא תקינה.'),
    ('The saved script changed. Reopen Script to review the current version.', 'התסריט השמור השתנה. פתחו שוב את התסריט כדי לעבור על הגרסה הנוכחית.'),
    ('The script approval changed. Reopen Script to review it.', 'אישור התסריט השתנה. פתחו שוב את התסריט כדי לבדוק אותו.'),
    ('Writing memory needs attention in chat. Existing memories are preserved.', 'זיכרון הכתיבה צריך בדיקה של קלוד. הזיכרונות הקיימים נשמרו.'),
    ('Keep up to 40 useful writing preferences.', 'שמרו עד 40 העדפות כתיבה שימושיות.'),
    ('Use a valid writing preference.', 'העדפת הכתיבה לא תקינה.'),
    ('Each preference needs its own identity, wording and source.', 'לכל העדפה צריך מזהה, ניסוח ומקור משלה.'),
    ('Use a valid forgotten memory date.', 'תאריך השכחה של הזיכרון לא תקין.'),
    ('Keep up to eight useful examples with each memory.', 'שמרו עד שמונה דוגמאות שימושיות לכל זיכרון.'),
    ('Save the wording, feedback and context for each writing example.', 'שמרו לכל דוגמת כתיבה את הניסוח, ההערה וההקשר.'),
    ('Each writing example needs its own identity and feedback.', 'לכל דוגמת כתיבה צריך מזהה והערה משלה.'),
    ('Keep the actual wording with the feedback.', 'שמרו את הניסוח המקורי יחד עם ההערה.'),
    ('Link writing examples to an exact project script.', 'קשרו את דוגמאות הכתיבה לתסריט מסוים של סרטון.'),
    ('Use a valid source project.', 'סרטון המקור לא תקין.'),
    ('Use a valid writing preference request.', 'בקשת העדפת הכתיבה לא תקינה.'),
    ('This writing request was already used for different text.', 'בקשת הכתיבה הזו כבר שימשה לטקסט אחר.'),
    ('Restore a forgotten memory explicitly before using it again.', 'שחזרו במפורש זיכרון שנשכח לפני שמשתמשים בו שוב.'),
    ('Use a valid writing memory request.', 'בקשת זיכרון הכתיבה לא תקינה.'),
    ('Use Forget to manage an existing memory.', 'כדי לנהל זיכרון קיים השתמשו ב„לשכוח“.'),
    ('This memory was forgotten. Restore it explicitly before changing it.', 'הזיכרון הזה נשכח. שחזרו אותו במפורש לפני שמשנים אותו.'),
    ('The example wording does not match its saved script.', 'ניסוח הדוגמה לא תואם לתסריט השמור שלה.'),
    ('Use a valid memory action.', 'הפעולה על הזיכרון לא תקינה.'),
    ('This memory action was already used for a different change.', 'הפעולה הזו על הזיכרון כבר שימשה לשינוי אחר.'),
    ('That writing memory is unavailable.', 'זיכרון הכתיבה הזה לא זמין.'),
    ('Writing memory changed. Copy a fresh correction request.', 'זיכרון הכתיבה השתנה. העתיקו בקשת תיקון חדשה.'),
    ('That writing memory is unavailable or forgotten.', 'זיכרון הכתיבה הזה לא זמין או שנשכח.'),
    ('Recall up to eight relevant writing examples.', 'אפשר להיזכר בעד שמונה דוגמאות כתיבה רלוונטיות.'),
    ('Openings belong to video scripts.', 'פתיחות שייכות לתסריטי וידאו.'),
    ('Use a valid opening set.', 'קבוצת הפתיחות לא תקינה.'),
    ('Choose an exact saved script for these openings.', 'בחרו תסריט שמור מסוים לפתיחות האלה.'),
    ('The opening must match complete paragraphs at the start of this exact script.', 'הפתיחה צריכה להתאים לפסקאות שלמות בתחילת התסריט הזה.'),
    ('Save two to six complete opening options.', 'שמרו בין שתיים לשש אפשרויות פתיחה שלמות.'),
    ('Use a valid opening option.', 'אפשרות הפתיחה לא תקינה.'),
    ('Each opening needs distinct text and its own identity.', 'לכל פתיחה צריך טקסט שונה ומזהה משלה.'),
    ('Use a shorter opening.', 'השתמשו בפתיחה קצרה יותר.'),
    ('Keep the original opening among the options.', 'השאירו את הפתיחה המקורית בין האפשרויות.'),
    ('Use a valid opening save request.', 'בקשת שמירת הפתיחות לא תקינה.'),
    ('Use a valid opening choice.', 'בחירת הפתיחה לא תקינה.'),
    ('That opening is unavailable. Reload the options; your script is kept.', 'הפתיחה הזו לא זמינה. טענו מחדש את האפשרויות; התסריט שלכם נשמר.'),
    ('The script or openings changed. Reload before choosing; your draft is kept.', 'התסריט או הפתיחות השתנו. טענו מחדש לפני הבחירה; הטיוטה שלכם נשמרת.'),
    ('This feedback belongs to a video script.', 'ההערה הזו שייכת לתסריט וידאו.'),
    ('Script feedback needs attention in chat. It is preserved.', 'ההערות על התסריט צריכות בדיקה של קלוד. הן נשמרו.'),
    ('Script feedback needs repair. It is preserved.', 'ההערות על התסריט צריכות תיקון. הן נשמרו.'),
    ('Saved script feedback changed. Its earlier records are preserved; ask your editing chat to reconcile it.',
     'ההערות השמורות על התסריט השתנו. הרשומות הקודמות נשמרו; בקשו מקלוד ליישב אותן.'),
    ('That copied feedback is unavailable. Copy it again from the studio.', 'ההערות שהועתקו לא זמינות. העתיקו אותן שוב מהסטודיו.'),
    ('That copied feedback no longer matches. Copy it again from the studio.', 'ההערות שהועתקו כבר לא תואמות. העתיקו אותן שוב מהסטודיו.'),
    ('Use a valid script feedback request.', 'בקשת ההערה על התסריט לא תקינה.'),
    ('Add feedback or a reference first.', 'קודם הוסיפו הערה או השראה.'),
    ('This feedback request was already used for different text. Your draft is kept.', 'בקשת ההערה הזו כבר שימשה לטקסט אחר. הטיוטה שלכם נשמרת.'),
    ('Script feedback history is full. Ask your editing chat to archive it safely.', 'היסטוריית ההערות על התסריט מלאה. בקשו מקלוד להעביר אותה לארכיון בבטחה.'),
    # reference_notes.py
    ('Reference notes need a safe local path before saving.', 'הערות ההשראה צריכות נתיב מקומי בטוח לפני השמירה.'),
    ('Reference notes need attention. Existing notes are preserved.', 'הערות ההשראה צריכות בדיקה. ההערות הקיימות נשמרו.'),
    ('Saved reference notes need repair. Existing notes are preserved.', 'הערות ההשראה השמורות צריכות תיקון. ההערות הקיימות נשמרו.'),
    ('Choose a saved reference.', 'בחרו השראה שמורה.'),
    ('Choose a valid technique example.', 'בחרו דוגמת טכניקה תקינה.'),
    ('Choose an exact technique example.', 'בחרו דוגמת טכניקה מסוימת.'),
    ('This reference is no longer available.', 'ההשראה הזו כבר לא זמינה.'),
    ('This example changed. Ask your assistant to recheck its source first.', 'הדוגמה הזו השתנתה. קודם בקשו מקלוד לבדוק שוב את המקור שלה.'),
    ('The reference source needs a safe local path.', 'מקור ההשראה צריך נתיב מקומי בטוח.'),
    ('This source is unavailable. Your notes are preserved.', 'המקור הזה לא זמין. ההערות שלכם נשמרו.'),
    ('The example source changed. Recheck its timing before using it.', 'מקור הדוגמה השתנה. בדקו שוב את התזמון לפני השימוש.'),
    ('Use a valid reference note request.', 'בקשת הערת ההשראה לא תקינה.'),
    ('Use a valid note save request.', 'בקשת שמירת ההערה לא תקינה.'),
    ('Use a valid earlier-note request.', 'הבקשה להערה קודמת לא תקינה.'),
    ('This save request already belongs to another note.', 'בקשת השמירה הזו כבר שייכת להערה אחרת.'),
    ('This source changed. Reopen it before saving; your draft is kept.', 'המקור השתנה. פתחו אותו שוב לפני השמירה; הטיוטה שלכם נשמרת.'),
    ('Choose a valid carousel slide.', 'בחרו שקופית קרוסלה תקינה.'),
    ('Choose a moment inside this video or exact example.', 'בחרו רגע בתוך הסרטון הזה או בתוך הדוגמה.'),
    ('This earlier-note request already belongs to another note.', 'הבקשה להערה קודמת כבר שייכת להערה אחרת.'),
    ('Ask your assistant to archive older reference notes first.', 'קודם בקשו מקלוד להעביר לארכיון הערות השראה ישנות.'),
    ('Reference notes need archiving before adding more.', 'צריך להעביר לארכיון הערות השראה לפני שמוסיפים עוד.'),
    ('Choose up to 60 exact references.', 'בחרו עד 60 השראות.'),
    ('Choose valid references and saved notes.', 'בחרו השראות והערות שמורות תקינות.'),
    ('The selected source or notes changed. Review them before copying.', 'המקור או ההערות שנבחרו השתנו. עברו עליהם לפני ההעתקה.'),
    ('Choose an exact carousel slide.', 'בחרו שקופית קרוסלה מסוימת.'),
    ('Choose each exact reference once.', 'בחרו כל השראה פעם אחת.'),
    ('Those notes belong to a different source, example or slide.', 'ההערות האלה שייכות למקור, לדוגמה או לשקופית אחרים.'),
    ('Text is too long.', 'הטקסט ארוך מדי.'),
    # serve.py answers on the same routes
    ('Use a valid writing request.', 'בקשת הכתיבה לא תקינה.'),
    ('Writing context could not be saved. Your existing files and draft are preserved.', 'לא הצלחנו לשמור את הכתיבה. הקבצים הקיימים והטיוטה שלכם נשמרו.'),
    ('Writing context is unavailable. Your existing files are preserved.', 'הכתיבה לא זמינה כרגע. הקבצים הקיימים שלכם נשמרו.'),
    ('The script could not be saved. Existing scripts and your draft are preserved.', 'לא הצלחנו לשמור את התסריט. התסריטים הקיימים והטיוטה שלכם נשמרו.'),
    ('Saved scripts are unavailable. Existing files are preserved.', 'התסריטים השמורים לא זמינים כרגע. הקבצים הקיימים נשמרו.'),
    ('Reference notes are unavailable. Existing notes and your draft are preserved.', 'הערות ההשראה לא זמינות כרגע. ההערות הקיימות והטיוטה שלכם נשמרו.'),
    ('Reference notes are unavailable. Existing notes are preserved.', 'הערות ההשראה לא זמינות כרגע. ההערות הקיימות נשמרו.'),
    ('Use a valid JSON feedback change.', 'בקשת שינוי ההערה לא תקינה.'),
    ('Feedback could not be changed. Existing notes and your draft are preserved.', 'לא הצלחנו לשנות את ההערה. ההערות הקיימות והטיוטה שלכם נשמרו.'),
    ('Use a valid JSON feedback selection.', 'בחירת ההערות לא תקינה.'),
    ('The feedback link could not be prepared. Your saved notes are preserved.', 'לא הצלחנו להכין את הקישור להערות. ההערות השמורות שלכם נשמרו.'),
    ('Use a valid JSON feedback request.', 'בקשת ההערה לא תקינה.'),
    ('Feedback could not be saved. Existing notes were preserved; try again.', 'לא הצלחנו לשמור את ההערה. ההערות הקיימות נשמרו; נסו שוב.'),
]

ASSISTANT = (('Ask your assistant', 'Ask Claude'), ('ask your editing chat', 'ask Claude'),
             ('Ask your editing chat', 'Ask Claude'), ('in your editing chat', 'by Claude'),
             ('in another window or editing chat', 'in another window or by Claude'), ('attention in chat', 'attention from Claude'))


def _slug(text):
    words = re.findall(r'[A-Za-z0-9]+', text.lower())[:8]
    return 'server.' + '-'.join(words)


def _english(text):
    for old, new in ASSISTANT:
        text = text.replace(old, new)
    return text.strip()


KEYS = {}      # English text -> key
STRINGS = {}   # key -> {'he': ..., 'en': ...}
for _en, _he in MESSAGES:
    _key = _slug(_en)
    while _key in STRINGS and STRINGS[_key]['source'] != _en:
        _key += '-2'
    KEYS[_en] = _key
    STRINGS[_key] = {'he': _he, 'en': _english(_en), 'source': _en}

_TOO_LONG = re.compile(r'^.{1,60} must be text of up to \d+ characters\.$')


def code(message):
    """The i18n key for a known server sentence, else the sentence itself (already a key, or
    a message from a module this table does not cover)."""
    if not isinstance(message, str):
        return message
    text = message.strip()
    if message in KEYS or text in KEYS:
        return KEYS.get(message) or KEYS[text]
    for source, key in KEYS.items():
        if source.endswith(': ') and message.startswith(source.rstrip()):  # a sentence followed by ids
            return key
    if _TOO_LONG.match(text):
        return KEYS['Text is too long.']
    import review_actions  # the shared storage errors (ReviewError) these routes also raise
    return review_actions.MESSAGE_KEYS.get(text, message)
