# אבטחה ופרטיות

הסטודיו רץ מקומית בלבד ומאזין רק לכתובת loopback,‏ 127.0.0.1; אין התחברות משתמשים, ואין להפעיל אותו מול חשיפה ציבורית — טאנל, פרוקסי הפוך או פתיחת חומת אש (שירות מתארח/צוותי דורש אימות, אחסון מדיה פרטי וסקירת פריסה נפרדים משלו). כל נקודת קצה שכותבת קבצים בודקת כותרת Host מקומית מדויקת, כותרת Origin מדויקת וכותרת X-Studio-Action; מדיה והערות רשומות מוגבלות לתיקיות projects/<slug> או references/<slug> בלבד (כולל בדיקות symlink וגבולות נתיב), וקבצים סטטיים מוגשים רק מתוך dist.

שני נתיבי ההעלאה המקומיים היחידים: PUT /materials (חומרי גלם, עד 8GB) ו-PUT /inspiration-file (סרטוני השראה, mp4/mov/webm/m4v בלבד, עד 1GB) — עם אותם שומרים, זרימה לקובץ זמני עם בדיקת Content-Length מדויקת, ומעבר למקום הסופי רק בהצלחה. אין API להרצת קוד שרירותי. פתיחת העורך (HyperFrames) דורשת POST מאובטח מפורש ומריצה כלי שורת-פקודה קבוע בלי shell; בקשת GET לעולם לא מריצה תהליכים. שליפת תמונת-נושא חיצונית (reference-preview) מקבלת HTTPS בלבד, דוחה כתובות DNS שאינן ציבוריות, ולעולם לא טוענת סקריפטים, embeds, עוגיות או וידאו.

אישורי סקירה שומרים מטא-דאטה בלבד (גרסה/hash נוכחיים ויומן היסטוריה) — זו לא הגנה מפני מחשב פרוץ או תהליך מקומי זדוני. מפתחות API וסודות אחרים נשמרים רק בקובץ .env המקומי — לעולם לא מחויבים ל-git ולעולם לא נשלחים לדפדפן; וכך גם העדפות כתיבה ותקצירי סקריפט — נתוני בעלים בלבד, לעולם לא נשלחים לשירות מודל חיצוני. לעולם אין להעלות קטלוגים אמיתיים, חומרי גלם, הערות, פרויקטים או credentials ל-git — יש להשתמש ב-release-files.txt והמייצא המפורש בלבד; ‎.gitignore‏ לבדו אינו ביקורת פרטיות.

כדי לדווח על חשש אבטחה, פתחו Issue בגיטהאב בפרויקט [asaf5767/claude-video-studio](https://github.com/asaf5767/claude-video-studio). אין לפרסם מדיה פרטית, פרויקטים אמיתיים, מפתחות או סודות ב-Issue פומבי.

# Security and privacy

The studio is local-only: it binds exclusively to the 127.0.0.1 loopback address, has no user login, and must never run behind a public tunnel, reverse proxy or opened firewall (a hosted/team service needs its own separate authentication, private media storage and deployment review). Every write endpoint checks an exact local Host header, an exact Origin header and an X-Studio-Action header; registered media and notes are confined to the projects/<slug> or references/<slug> directories only (including symlink and path-boundary checks), and static files are served from dist alone.

There are exactly two local upload routes: PUT /materials (raw footage, up to 8 GiB) and PUT /inspiration-file (reference videos, mp4/mov/webm/m4v only, up to 1 GiB) — both with the same guards, streamed to a temp file with an exact Content-Length check and moved into place only on success. There is no arbitrary-code API. Opening the editor (HyperFrames) requires an explicit guarded POST and runs a fixed local CLI without a shell; a GET request never launches a process. The external cover-image fetch (reference-preview) accepts HTTPS only, rejects non-public DNS results, and never loads scripts, embeds, cookies or video.

Review approvals record metadata only (the current version/hash and a history journal) — this is not protection against a compromised machine or a malicious local process. API keys and other secrets live only in the local .env file — never committed to git, never sent to the browser — and the same goes for writing preferences and script briefs: owner data only, never sent to an external model service. Never commit real catalogs, footage, notes, projects or credentials to git; use release-files.txt and the explicit exporter only — .gitignore alone is not a privacy audit.

To report a security concern, open an issue on GitHub at [asaf5767/claude-video-studio](https://github.com/asaf5767/claude-video-studio). Never post private media, real projects, keys or other secrets in a public issue.
