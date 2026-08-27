# בוט חיפוש מוצרים בטלגרם

בוט שמאפשר לך להעלות מוצרים (תמונה + קישור), ולמשתמשים לחפש אותם
לפי שם מותג ("חפש לי נייקי") או לפי שליחת תמונה דומה.

## שלב 1: יצירת הבוט בטלגרם

1. פתח שיחה עם [@BotFather](https://t.me/BotFather) בטלגרם.
2. שלח `/newbot` ועקוב אחר ההוראות (שם + username).
3. תקבל **טוקן** בפורמט כזה: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`. שמור אותו.
4. כדי לדעת מה ה-ID שלך (בשביל ADMIN_IDS) — פתח שיחה עם [@userinfobot](https://t.me/userinfobot) והוא יגיד לך.

## שלב 2: הרצה מקומית (לבדיקה)

```bash
pip install -r requirements.txt
export BOT_TOKEN="הטוקן_שקיבלת_מ-BotFather"
export ADMIN_IDS="123456789"   # ה-ID שלך, אפשר כמה מופרדים בפסיק
python bot.py
```

הבוט ירוץ כל עוד המחשב שלך פתוח והתהליך רץ (polling).

## שלב 3: הוספת מוצרים

שלח לבוט **תמונה** עם כיתוב (caption) בפורמט הזה:

```
מותג: נייקי
שם: נעלי ריצה אייר מקס
קישור: https://example.com/product123
```

(שורת "שם" אופציונלית — אפשר בלי).

## שלב 4: שימוש (מכל משתמש)

- `חפש לי נייקי` — חיפוש טקסטואלי לפי מותג/שם.
- שליחת תמונה — הבוט ישווה אותה לתמונות בקטלוג ויחזיר את הקישור המתאים.
- `/list` — (אדמין בלבד) רשימת כל המוצרים בקטלוג.
- `/delete <מזהה>` — (אדמין בלבד) מחיקת מוצר.

## שלב 5: העלאה לאחסון קבוע (24/7)

הבוט צריך לרוץ תמיד ברקע כדי לענות בזמן אמת. שתי אפשרויות מומלצות:

### Railway (הכי פשוט)

1. העלה את התיקייה הזו ל-repo חדש ב-GitHub.
2. היכנס ל-[railway.app](https://railway.app), התחבר עם GitHub, ותבחר "Deploy from GitHub repo".
3. ב-Settings → Variables, הוסף:
   - `BOT_TOKEN` = הטוקן שלך
   - `ADMIN_IDS` = ה-ID שלך
4. Railway יריץ אוטומטית `python bot.py` (וודא ש-Start Command מוגדר כך, או הוסף `Procfile` עם `worker: python bot.py`).

### Render

דומה ל-Railway: "New Background Worker" → מחברים ל-GitHub repo → מגדירים משתני סביבה `BOT_TOKEN` ו-`ADMIN_IDS` → Build Command: `pip install -r requirements.txt` → Start Command: `python bot.py`.

**חשוב:** בשתי האפשרויות, קובצי הקטלוג (`catalog.json` + `catalog_images/`) נשמרים על הדיסק של השרת. אם השרת מתאפס (redeploy), הם עלולים להימחק — אם זה קריטי, כדאי בהמשך לעבור לאחסון קבוע כמו S3 או מסד נתונים חיצוני. לכמות מוצרים סבירה (עשרות-מאות) זה לא דחוף.

## מבנה הקבצים

```
telegram-product-bot/
├── bot.py              # הקוד הראשי
├── requirements.txt
├── catalog.json         # נוצר אוטומטית - מסד הנתונים של המוצרים
└── catalog_images/      # נוצר אוטומטית - התמונות שהועלו
```
