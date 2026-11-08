"""Plain-language setup messages. Hebrew by default; English available with --lang en
or the studio's saved UI language (style-library/settings.json "language").

Every key below MUST exist in both language tables with the same set of keys --
`style-library/test_setup_messages.py::test_messages_exist_in_both_languages` enforces
this. Add a key to both dicts together, never to just one.
"""

MESSAGES = {
    'he': {
        'setup.checking': 'בודקים מה חסר במחשב הזה...',
        'setup.nothing-missing': 'הכל כבר מותקן.',
        'setup.missing-tool.node': 'Node.js חסר — זה הכלי שמריץ את התוכנה שמרכיבה את הסרטונים. להתקין עכשיו? (כ/ל)',
        'setup.missing-tool.ffmpeg': 'FFmpeg חסר — זה הכלי שחותך ומעבד וידאו. להתקין עכשיו? (כ/ל)',
        'setup.missing-tool.whisper-cpp': 'מנוע הדיבור whisper.cpp חסר — הוא הופך הקלטה לכתוביות. להתקין עכשיו? (כ/ל)',
        'setup.missing-tool.generic': '{tool} חסר. להתקין עכשיו? (כ/ל)',
        'setup.consent-yes': 'כ',
        'setup.installing': 'מתקינים {tool}...',
        'setup.install-ok': '{tool} הותקן בהצלחה.',
        'setup.install-failed': 'התקנת {tool} נכשלה. אפשר לנסות שוב, או להתקין באופן ידני.',
        'setup.install-skipped': 'דילגנו על התקנת {tool}. אפשר להריץ את ההתקנה בעצמך בהמשך ולהריץ את הבדיקה הזו שוב.',
        'setup.need-winget': 'לא מצאנו את winget (כלי ההתקנה של Windows). התקינו אותו מחנות Microsoft תחת השם "App Installer", ואז הריצו את הבדיקה הזו שוב.',
        'setup.need-brew': 'לא מצאנו את Homebrew (כלי ההתקנה של Mac). התקינו אותו מהכתובת brew.sh, ואז הריצו את הבדיקה הזו שוב.',
        'setup.prerequisites-missing': 'התקינו קודם את הכלים האלה: {tools}. ראו SETUP.md; לא בוצעה שום התקנה גלובלית.',
        'setup.insecure-url': 'הכתובת להורדה אינה מאובטחת (לא https) — לא ממשיכים. בדקו את ההגדרה ב-studio.config.json.',
        'setup.matting-consent': 'הורדת רקע אוטומטית (למראות כמו "ירוק" או "רקע חדש") דורשת עוד הורדה, כ-380MB עבור מודל "{model}" וספריית ריצה. זה לא נדרש להמשך העבודה — להוריד עכשיו? (כ/ל)',
        'setup.matting-skipped': 'דילגנו על הורדת הסרת הרקע. אפשר להמשיך לעבוד בלעדיה; מראות שדורשים אותה יוצעו רק אחרי שתורידו אותה.',
        'setup.matting-installing-runtime': 'מתקינים את ספריית הריצה להסרת רקע (onnxruntime-node)...',
        'setup.matting-downloading': 'מורידים את מודל הסרת הרקע "{model}"...',
        'setup.matting-ok': 'מודל הסרת הרקע "{model}" מוכן.',
        'setup.matting-checksum-mismatch': 'הקובץ שהתקבל למודל הסרת הרקע "{model}" לא תואם לצפוי. ננסה להוריד אותו שוב בפעם אחרת; שום דבר לא נפגם.',
        'setup.npm-blocked': 'לא הצלחנו להתחבר למחסן החבילות של npm. זה קורה הרבה ברשתות עבודה או עם VPN/פרוקסי. ננסו: רשת אחרת (למשל רשת הבית), כיבוי זמני של VPN, או מתן הרשאה לתוכנית ברשת הארגונית. אין שגיאה טכנית להעתיק — פשוט לנסות שוב כשתתחברו לרשת אחרת.',
        'setup.model-pending': 'מודל השפה "{model}" עדיין לא מוכן להורדה — זה יוגדר בהמשך, אין צורך לעשות דבר כרגע.',
        'setup.model-consent': 'להוריד את מודל השפה "{model}"? (כ/ל)',
        'setup.model-downloading': 'מורידים את מודל השפה "{model}"...',
        'setup.model-ok': 'מודל השפה "{model}" מוכן.',
        'setup.model-checksum-mismatch': 'הקובץ שהתקבל עבור "{model}" לא תואם לצפוי. ננסה להוריד אותו שוב בפעם אחרת; שום דבר לא נפגם.',
        'setup.model-skipped': 'דילגנו על הורדת מודל השפה "{model}".',
        'setup.whisper-download': 'מורידים את מנוע הדיבור whisper.cpp...',
        'setup.whisper-ok': 'מנוע הדיבור מוכן.',
        'setup.registry-retry': 'כשהרשת תהיה פתוחה, הריצו שוב: python scripts/setup.py',
        'setup.done': 'הכול מוכן! פותחים את הסטודיו...',
        'setup.studio-only-done': 'הבסיס של הסטודיו מוכן (בלי כלי מדיה). פותחים אותו עם: {hint}',
        'setup.studio-ready-yes': 'מוכן לעבודה בסיסית.',
        'setup.studio-ready-no': 'עדיין לא מוכן לעבודה בסיסית.',
        'setup.media-ready-yes': 'מוכן לעריכת מדיה מלאה.',
        'setup.media-ready-no': 'עדיין לא מוכן לעריכת מדיה מלאה — ראו למעלה מה חסר.',
        'start.restart-refused': 'הסטודיו כבר פתוח, ולא הצלחנו לוודא שזה הסטודיו של התיקייה הזו, אז לא סגרנו אותו. הוא ממשיך לעבוד בכתובת {url}.',
    },
    'en': {
        'setup.checking': 'Checking what is missing on this computer...',
        'setup.nothing-missing': 'Everything is already installed.',
        'setup.missing-tool.node': 'Node.js is missing — it runs the program that assembles your videos. Install it now? (y/n)',
        'setup.missing-tool.ffmpeg': 'FFmpeg is missing — it cuts and processes video. Install it now? (y/n)',
        'setup.missing-tool.whisper-cpp': 'The whisper.cpp speech engine is missing — it turns a recording into captions. Install it now? (y/n)',
        'setup.missing-tool.generic': '{tool} is missing. Install it now? (y/n)',
        'setup.consent-yes': 'y',
        'setup.installing': 'Installing {tool}...',
        'setup.install-ok': '{tool} installed successfully.',
        'setup.install-failed': 'Installing {tool} failed. Try again, or install it yourself.',
        'setup.install-skipped': 'Skipped installing {tool}. You can install it yourself later and run this check again.',
        'setup.need-winget': 'We could not find winget (Windows\' installer). Install it from the Microsoft Store as "App Installer", then run this check again.',
        'setup.need-brew': 'We could not find Homebrew (the Mac installer). Install it from brew.sh, then run this check again.',
        'setup.prerequisites-missing': 'Install these prerequisites first: {tools}. See SETUP.md; no global installs were attempted.',
        'setup.insecure-url': 'The download address is not secure (not https) -- not continuing. Check the studio.config.json setting.',
        'setup.matting-consent': 'Automatic background removal (for looks like "green screen" or "new background") needs another download, about 380MB for the "{model}" model and a runtime library. It is not required for anything else -- download it now? (y/n)',
        'setup.matting-skipped': 'Skipped the background-removal download. You can keep working without it; looks that need it will only be offered once it is downloaded.',
        'setup.matting-installing-runtime': 'Installing the background-removal runtime (onnxruntime-node)...',
        'setup.matting-downloading': 'Downloading the "{model}" background-removal model...',
        'setup.matting-ok': 'The "{model}" background-removal model is ready.',
        'setup.matting-checksum-mismatch': 'The file received for the "{model}" background-removal model did not match what was expected. We will try again another time; nothing was damaged.',
        'setup.npm-blocked': 'We could not reach the npm package registry. This is common on work networks or with a VPN/proxy. Try: a different network (e.g. your home network), turning off a VPN for a moment, or asking IT to allow this on the work network. There is no technical error to copy -- just try again on a different network.',
        'setup.model-pending': 'The "{model}" language model is not ready to download yet — it will be configured later, nothing to do right now.',
        'setup.model-consent': 'Download the "{model}" language model now? (y/n)',
        'setup.model-downloading': 'Downloading the "{model}" language model...',
        'setup.model-ok': 'The "{model}" language model is ready.',
        'setup.model-checksum-mismatch': 'The file received for "{model}" did not match what was expected. We will try again another time; nothing was damaged.',
        'setup.model-skipped': 'Skipped downloading the "{model}" language model.',
        'setup.whisper-download': 'Downloading the whisper.cpp speech engine...',
        'setup.whisper-ok': 'The speech engine is ready.',
        'setup.registry-retry': 'Once the network is open, run again: python scripts/setup.py',
        'setup.done': 'Everything is ready! Opening the studio...',
        'setup.studio-only-done': 'The studio home base is ready (no media tools). Open it with: {hint}',
        'setup.studio-ready-yes': 'Ready for the home base.',
        'setup.studio-ready-no': 'Not ready for the home base yet.',
        'setup.media-ready-yes': 'Ready for full media editing.',
        'setup.media-ready-no': 'Not ready for full media editing yet — see what is missing above.',
        'start.restart-refused': 'The studio is already open and we could not confirm it is this folder\'s own, so we did not close it. It keeps running at {url}.',
    },
}


def message(key, lang):
    """Return the plain-language text for `key` in `lang`, falling back to Hebrew for an
    unrecognized language and to the raw key when the key itself does not exist."""
    table = MESSAGES.get(lang) or MESSAGES['he']
    return table.get(key, MESSAGES['he'].get(key, key))
