"""
בוט טלגרם לקטלוג מוצרים - חיפוש לפי שם מותג, לפי תמונה, או דפדוף בקטלוג.

איך זה עובד:
- הוספת מוצרים אפשרית בשתי דרכים (אפשר להשתמש בשתיהן ביחד):
    1. קבוצת "העלאת מוצרים" נפרדת - כל תמונה/סרטון (או כמה ביחד כ"אלבום",
       אפשר גם לערבב תמונות וסרטונים באותו אלבום) עם כיתוב תקין שנשלחת
       בקבוצה שמוגדרת ב-CATALOG_GROUP_ID נכנסת אוטומטית לקטלוג כמוצר אחד.
    2. הודעה פרטית לבוט מאדמין (מי שה-ID שלו ב-ADMIN_IDS) - אותו פורמט כיתוב.
  פורמט הכיתוב:
    מותג: שם המותג והדגם
    פרטים: (כל שורה הופכת לנקודה משלה)
    מידה 40-45
    צבע שחור
    מחיר: 199 ש"ח
    קישור: https://...

  אפשר לשלוח כמה תמונות/סרטונים ביחד (כ"אלבום" בטלגרם) עם כיתוב אחד - כולם
  יישמרו תחת אותו מוצר, וייחשלו יחד כאלבום גם כשהמוצר מוצג. הבוט אוסף את כל
  הפריטים של אותו אלבום (הם מגיעים כהודעות נפרדות מטלגרם) וממתין רגע קט
  (MEDIA_GROUP_DEBOUNCE_SECONDS) לפני שהוא שומר את המוצר. סרטונים לא נשמרים
  כקובץ מקומי (רק ה-file_id שטלגרם כבר מארח) - רק תמונות מורדות ומאוחסנות
  בפועל (לצורך חיפוש לפי תמונה ותצוגת הרשת).

- כל משתמש אחר (בצ'אט פרטי או בקבוצה אחרת, לא קבוצת ההעלאה) יכול:
    - לכתוב "חפש לי <מותג>" -> חיפוש מטושטש (fuzzy) שסובלני לטעויות הקלדה
      קטנות (אות חסרה/עודפת/מוחלפת), עם נרמול עברית: נעלי/נעליים = נעל, אותיות
      סופיות, כתיב מלא/חסר (פרדה = פראדה) וכינויי מותגים (ניקי = נייקי). כל מילה
      בשאילתה צריכה להתאים לכותרת. אם יש תוצאה אחת, מקבל מדיה+פרטים
      מלאים. אם יש כמה, מקבל רשת ממוספרת. בלי תוצאה - "לא מצאתי" + התראה לאדמין.
    - לכתוב שם מותג ישירות, בלי "חפש לי" (עד 3 מילים, למשל סתם "נייקי") ->
      אותו חיפוש מטושטש, אבל אם אין התאמה הבוט שותק (כדי לא להגיב "לא
      מצאתי" על כל הודעת צ'אט סתמית). כבוי בקבוצת ההעלאה עצמה.
    - לכתוב "קטלוג" (או /catalog) -> רשת דפדוף על כל המוצרים בקטלוג.
    - לשלוח תמונה -> אם ENABLE_IMAGE_SEARCH=false (ברירת מחדל: true), הבוט לא
      מנסה להתאים בכלל - מודיע למשתמש ומעביר את התמונה לקבוצת האדמין.
      אם מופעל, הבוט מחשב טביעת אצבע ויזואלית (perceptual hash) ומשווה
      לתמונות השמורות; אם לא נמצאה התאמה, גם זה נשלח לקבוצת האדמין.
    - לשלוח סרטון (בלי כיתוב, לא כאדמין) -> חיפוש לפי סרטון עדיין לא נתמך -
      הבוט מודיע ומעביר את הפנייה לקבוצת האדמין.

- /list -> אדמין בלבד: מציג את כל המוצרים בקטלוג (מזהה, מותג, מחיר, קישור).
- /stats -> אדמין בלבד: סה"כ מוצרים, פילוח לפי מותג ולפי סוג (category), ו-20 האחרונים שנוספו.
- /edit <id> -> אדמין בלבד: מתחיל עריכת מוצר קיים - שולחים תמונה/סרטון+כיתוב
  חדשים (כמו בהוספה) והם מחליפים את הישן. שדה שמשאירים ריק/לא כתוב נשאר כמו שהיה.
- /canceledit -> מבטל עריכה שהתחילה עם /edit.
- /delete <id> -> אדמין בלבד: מוחק מוצר מהקטלוג.
- /groupid -> מציג את מזהה הקבוצה הנוכחית (שימושי כדי להגדיר CATALOG_GROUP_ID
  או NOTIFY_GROUP_ID).
- שליחת קובץ .zip מאדמין בצ'אט פרטי (או בקבוצת ההעלאה) -> ייבוא מרובה של
  מוצרים מ-products.json + תיקיית images/ (ראה README, סעיף ייבוא ZIP).
  אופציונלי לצרף כיתוב /import; כל קובץ ZIP מאדמין עובד. מגבלת טלגרם: עד 20MB.

הערה לגבי אמינות: כל שגיאה בלתי צפויה נתפסת ע"י error handler גלובלי -
המשתמש תמיד יקבל הודעה שמשהו השתבש (במקום שקט מוחלט), והשגיאה המלאה
נכתבת ללוגים של השרת.
"""

import html
import io
import json
import logging
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import imagehash
from PIL import Image, ImageDraw, ImageFont, ImageOps
from rapidfuzz import fuzz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
# תיקיית שמירה לקטלוג/תמונות. ברירת מחדל - לצד הקוד עצמו (טוב להרצה מקומית).
# ב-Railway/Render מומלץ להצביע ל-Volume קבוע (למשל CATALOG_DIR=/data) כדי
# שהמוצרים לא יימחקו בכל Redeploy - ראה README, סעיף "אחסון קבוע".
DATA_DIR = Path(os.environ.get("CATALOG_DIR", str(BASE_DIR)))
IMAGES_DIR = DATA_DIR / "catalog_images"
CATALOG_FILE = DATA_DIR / "catalog.json"
FONT_PATH = BASE_DIR / "assets" / "DejaVuSans-Bold.ttf"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# אפשר כמה אדמינים, מופרדים בפסיק: "111111,222222"
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}
# מזהה הקבוצה שמיועדת להעלאת מוצרים (אופציונלי). כל תמונה עם כיתוב תקין
# שנשלחת שם תיכנס אוטומטית לקטלוג, מכל מי ששולח בקבוצה. השאר ריק כדי
# להשתמש רק בהעלאה פרטית מאדמין (ADMIN_IDS).
_catalog_group_raw = os.environ.get("CATALOG_GROUP_ID", "").strip()
CATALOG_GROUP_ID = int(_catalog_group_raw) if _catalog_group_raw else None

# קבוצת התראות לאדמין (אופציונלי) - כשמישהו מחפש ולא נמצאה התאמה (טקסט או
# תמונה), נשלחת לכאן הודעה עם פרטי המשתמש ומה שהוא חיפש/שלח, כדי שתוכל
# לפנות אליו ישירות. השאר ריק כדי לכבות את זה.
_notify_group_raw = os.environ.get("NOTIFY_GROUP_ID", "").strip()
NOTIFY_GROUP_ID = int(_notify_group_raw) if _notify_group_raw else None

# האם חיפוש לפי תמונה פעיל. כשזה False, שליחת תמונה (שאינה חלק מהוספה/עריכה
# ע"י אדמין) לא מנסה להתאים בקטלוג בכלל - היא רק מודיעה למשתמש ומעבירה
# את הפנייה לקבוצת ההתראות (NOTIFY_GROUP_ID) לטיפול ידני.
ENABLE_IMAGE_SEARCH = os.environ.get("ENABLE_IMAGE_SEARCH", "true").strip().lower() not in (
    "false",
    "0",
    "no",
)

# סף דמיון לתמונות. ככל שההפרש (hamming distance) קטן יותר - התמונות דומות יותר.
# 0 = זהה לגמרי, המקסימום התיאורטי הוא 64. הועלה מ-10 ל-16 (27/08) כדי לתת
# יותר סבלנות לזוויות/תאורה/רקע שונים - אם מתחילות להופיע התאמות שגויות
# (מוצר לא נכון), תוריד את המספר בחזרה; אם עדיין יותר מדי "לא נמצא", אפשר
# להעלות עוד קצת (בערך 20 זה כבר גבול סביר לפני שמתחילים לקבל שגיאות).
IMAGE_MATCH_THRESHOLD = 16

# כמה מוצרים מוצגים ברשת דפדוף אחת (2x2, כמו בדוגמה שהתבקשה).
GRID_PAGE_SIZE = 4
GRID_CELL_PX = 320

# הפוטר הקבוע שמתווסף לכל תוצאת חיפוש (הזמנה, הסבר, ליווי, בוט ראשי וכו').
# עדכן את הטקסט/הקישורים/היוזרנים כאן במקום אחד אם הם משתנים.
RESULT_FOOTER_HTML = (
    "❓ איך מזמינים? על כל דגם בתמונה מופיע מספר / קוד. נכנסים לקישור, "
    "בוחרים ב- Flylinking את הקוד התואם למה שרציתם ומזמינים. "
    "אין צורך לשלוח הודעה למוכר!\n\n"
    "❓ סרטון הסבר איך להזמין דרך קישור מוסתר:\n"
    "https://t.me/ZoLinkisrael/28\n\n"
    "מי שמחפש דגם ספציפי מוזמן לשלוח אליי בפרטי @ZoLinkIL\n\n"
    "אנחנו מתווכים בלבד ולא הספקים או חברת השליחויות, ברגע שאתם מזמינים "
    "מהלינק אתם לקוחות של אותו האתר ואין לנו אחריות על אותן הזמנות.\n\n"
    "כמובן שהבוט עדיין פעיל למוצרים רגילים:\n"
    "@zolinkil_bot 👈"
)

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# מצב עריכה זמני (בזיכרון, לא נשמר בין הפעלות מחדש): user_id -> product_id
# שממתין לתמונה+כיתוב הבאים שאותו משתמש ישלח, כדי להחליף את המוצר.
PENDING_EDITS: dict[int, str] = {}

# תוצאות חיפוש/דפדוף פעילות (בזיכרון): session_id -> רשימת מזהי מוצרים,
# כדי שכפתורי הבחירה/הדפדוף (callback_data) יישארו קצרים.
SEARCH_SESSIONS: dict[str, list[str]] = {}

# מאגר זמני לאיסוף "אלבום" תמונות (media group) שנשלח כמה תמונות ביחד.
# טלגרם מספק כל תמונה כהודעה נפרדת עם אותו media_group_id, והכיתוב מגיע רק
# על אחת מהן - לכן אוספים לפי media_group_id וממתינים רגע (MEDIA_GROUP_DEBOUNCE_SECONDS)
# לפני שמעבדים את כולן ביחד כמוצר אחד עם כמה תמונות.
MEDIA_GROUP_BUFFERS: dict[str, dict] = {}
MEDIA_GROUP_DEBOUNCE_SECONDS = 1.5


def user_mention_html(update: Update) -> str:
    """קישור HTML שאפשר ללחוץ עליו כדי לפתוח את הפרופיל של השולח - עובד גם
    אם אין לו @username. משמש בהתראות לאדמין כדי "לתייג" ולהגיע אליו ישירות."""
    user = update.effective_user
    name = html.escape(user.full_name or "משתמש")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def notify_admin_group(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """שולח הודעת התראה לקבוצת האדמין, אם היא מוגדרת (NOTIFY_GROUP_ID).
    text יכול להכיל HTML (למשל תיוג לחיץ מ-user_mention_html)."""
    if NOTIFY_GROUP_ID is None:
        return
    try:
        await context.bot.send_message(
            chat_id=NOTIFY_GROUP_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Failed to send admin notification")


async def notify_admin_group_photo(
    context: ContextTypes.DEFAULT_TYPE, file_id: str, caption: str
) -> None:
    """מעביר תמונה שהתקבלה לחיפוש (בלי שנמצאה התאמה/כשזיהוי תמונות כבוי) לקבוצת האדמין.
    caption יכול להכיל HTML (למשל תיוג לחיץ מ-user_mention_html)."""
    if NOTIFY_GROUP_ID is None:
        return
    try:
        await context.bot.send_photo(
            chat_id=NOTIFY_GROUP_ID, photo=file_id, caption=caption, parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.exception("Failed to send admin photo notification")


# סף התאמה לחיפוש טקסט (0-100). כל מילה בשאילתה צריכה להתאים למילה בכותרת המוצר
# בציון הזה לפחות (אחרי נרמול עברית - ראה normalize_search_text). 80 סובלני לטעויות
# הקלדה קלות (אות חסרה/עודפת) בלי לתפוס מילים מקריות מהודעות צ'אט סתמיות.
FUZZY_MATCH_THRESHOLD = 80

# ---------------------------------------------------------------------------
# נרמול עברית לחיפוש (בזמן חיפוש - חל גם על כותרות שכבר בקטלוג):
#  - אותיות סופיות (ך ם ן ף ץ -> כ מ נ פ צ), ניקוד, גרש/גרשיים (ג'ורדן = גורדן)
#  - נטיות של מילות סוג: נעלי/נעליים -> נעל, שעוני/שעונים -> שעון, כפכפים -> כפכף ...
#  - כתיב מלא/חסר: השוואה גם בלי אמות קריאה א/ו/י (פרדה = פראדה)
#  - טבלת כינויים למותגים נפוצים (נייקי/ניקי, אדידס/אדידאס, ניו בלנס/ניו באלאנס ...)
# ---------------------------------------------------------------------------

_FINALS = str.maketrans("ךםןףץ", "כמנפצ")
_NIQQUD_RE = re.compile(r"[\u0591-\u05C7]")
_GERESH_RE = re.compile(r"[\u05F3\u05F4'`\u2018\u2019\"\u201C\u201D]")
_TOKEN_SPLIT_RE = re.compile(r"[^0-9a-z\u05D0-\u05EA]+")
_HE_DIGIT_BOUNDARY_RE = re.compile(r"(?<=[\u05D0-\u05EA])(?=\d)|(?<=\d)(?=[\u05D0-\u05EA])")

# גזעי מילות סוג (אחרי המרת אותיות סופיות): גזע + סיומת נטייה -> גזע
_HE_STEMS = (
    "נעל", "שעונ", "צעיפ", "תיק", "כפכפ", "סנדל", "מגפ", "כובע", "ארנק", "חגור", "חולצ",
    "מעיל", "מכנס", "גרב", "משקפ", "ילד", "בגד",
)
_HE_SUFFIXES = tuple(s.translate(_FINALS) for s in ("", "י", "ים", "יים", "ות", "ה", "ת"))
_HE_PREFIXES = ("ה", "ל", "ו", "ב", "וה", "לה", "מ")

# כינויים: כל הצורות בקבוצה מנורמלות לצורה הראשונה. ביטויים של כמה מילים מוחלפים כביטוי.
_ALIAS_GROUPS = (
    ("נייקי", "ניקי", "נייק", "נאיקי", "נייקיי"),
    ("אדידס", "אדידאס", "אדידאז", "אדידז"),
    ("ג'ורדן", "גורדן", "ג'ורדאן", "ג׳ורדן", "ג'ורדנ"),
    ("ניו בלנס", "ניו באלאנס", "ניו באלנס", "ניו בלאנס", "ניובלנס", "ניובאלאנס"),
    ("גוצ'י", "גוצי", "גוצ׳י", "גוצ'צי", "גוצצי"),
    ("פראדה", "פרדה", "פראדא", "פרדא"),
    ("לואי ויטון", "לואי וויטון", "לויי ויטון", "לויי וויטון", "לוי ויטון", "לואיס ויטון", "לואי ויטאן"),
    ("לואי", "לויי"),
    ("אסיקס", "אסיקאס", "אסיקס'"),
    ("יזי", "איזי", "ייזי"),
    ("הוקה", "הוקא", "הוקה וואן וואן"),
    ("בלנסיאגה", "בלנסיאגא", "בלנציאגה", "בלנסיאג'ה"),
    ("שאנל", "שנל", "שאנאל"),
    ("דיור", "דיאור"),
    ("ז'יבנשי", "גיבנשי", "זיבנשי", "ג'יבנשי"),
    ("סמבה", "סמבא", "סאמבה"),
    ("גאזל", "גזל", "גאזאל"),
    ("ספציאל", "ספזיאל", "ספשל"),
)


def _norm_word(word: str) -> str:
    """אותיות קטנות, בלי ניקוד/גרשים, אותיות סופיות -> רגילות."""
    word = _NIQQUD_RE.sub("", word.lower())
    word = _GERESH_RE.sub("", word)
    return word.translate(_FINALS)


def _build_alias_map() -> tuple[list[tuple[str, str]], dict[str, str]]:
    phrases: list[tuple[str, str]] = []
    words: dict[str, str] = {}
    for group in _ALIAS_GROUPS:
        canon = " ".join(_norm_word(w) for w in group[0].split())
        for variant in group:
            v = " ".join(_norm_word(w) for w in variant.split())
            if " " in v:
                phrases.append((v, canon))
            else:
                words[v] = canon
    phrases.sort(key=lambda p: -len(p[0]))  # ביטוי ארוך קודם
    return phrases, words


_ALIAS_PHRASES, _ALIAS_WORDS = _build_alias_map()


def _stem_word(word: str) -> str:
    """נעליים/נעלי/הנעליים -> נעל ; שעונים -> שעונ ; כפכפים -> כפכפ (רק למילות סוג מוכרות)."""
    for prefix in ("",) + _HE_PREFIXES:
        if prefix and not word.startswith(prefix):
            continue
        rest = word[len(prefix):]
        for stem in _HE_STEMS:
            if rest.startswith(stem) and rest[len(stem):] in _HE_SUFFIXES:
                return stem
    return word


def _skeleton(word: str) -> str:
    """כתיב חסר: בלי א/ו/י אחרי האות הראשונה (פראדה -> פרדה, נייקי -> נק)."""
    if not word or not ("\u05D0" <= word[0] <= "\u05EA"):
        return word
    return word[0] + re.sub("[אוי]", "", word[1:])


def normalize_search_text(text: str) -> list[str]:
    """מחזיר רשימת מילים מנורמלות (כינויים + גזעים) לחיפוש."""
    words = [_norm_word(w) for w in (text or "").split()]
    s = " " + " ".join(w for w in words if w) + " "
    s = _HE_DIGIT_BOUNDARY_RE.sub(" ", s)
    tokens = [t for t in _TOKEN_SPLIT_RE.split(s) if t]
    s = " " + " ".join(tokens) + " "
    for variant, canon in _ALIAS_PHRASES:
        s = s.replace(f" {variant} ", f" {canon} ")
    out = []
    for t in s.split():
        t = _ALIAS_WORDS.get(t, t)
        out.append(_stem_word(t))
    return out


# מילים שלא נושאות משמעות בחיפוש (מתעלמים מהן בשאילתה)
_QUERY_STOPWORDS = {
    _norm_word(w)
    for w in (
        "של", "את", "לי", "יש", "בבקשה", "מחפש", "מחפשת", "רוצה", "צריך", "צריכה", "עם", "גם", "the", "a", "of",
        "היי", "הי", "שלום", "אהלן", "תודה", "מה", "קורה",
    )
}


def _token_score(q: str, t: str) -> float:
    if q == t:
        return 100.0
    qs, ts = _skeleton(q), _skeleton(t)
    if len(qs) >= 2 and qs == ts:
        return 95.0
    if t.startswith(q) and (len(q) >= 4 or (len(q) >= 2 and q.isdigit())):
        return 90.0  # התחלת מילה: "נייק" -> "נייקי", "1906" -> "1906r"
    if len(q) >= 4 and len(t) >= 3:
        score = fuzz.ratio(q, t)
        if "\u05D0" <= q[0] <= "\u05EA" and min(len(qs), len(ts)) >= 2 and fuzz.ratio(qs, ts) < 70:
            return 0.0  # שלד העיצורים שונה מדי ("נייקי" מול "נייבי")
        return score
    return 0.0


from functools import lru_cache  # noqa: E402


@lru_cache(maxsize=4096)
def _title_tokens(title: str) -> tuple[str, ...]:
    toks = normalize_search_text(title)
    # גם צירופים של שתי מילים צמודות ("air force" -> "airforce", "ניו בלנס" -> "ניובלנס")
    pairs = [a + b for a, b in zip(toks, toks[1:])]
    return tuple(dict.fromkeys(toks + pairs))


def search_score(query: str, title: str) -> float:
    """ציון 0-100: כל מילה בשאילתה חייבת להתאים למילה כלשהי בכותרת (הציון = ההתאמה החלשה ביותר)."""
    q_tokens = [t for t in normalize_search_text(query) if t not in _QUERY_STOPWORDS]
    if not q_tokens:
        return 0.0
    t_tokens = _title_tokens(title or "")
    if not t_tokens:
        return 0.0
    worst = 100.0
    for q in q_tokens:
        best = max(_token_score(q, t) for t in t_tokens)
        worst = min(worst, best)
        if worst < FUZZY_MATCH_THRESHOLD:
            return worst
    return worst


def search_catalog(query: str, catalog: list[dict]) -> list[dict]:
    """חיפוש טקסט סובלני מול כותרת המוצר (שדה brand): נרמול עברית (נטיות, אותיות סופיות,
    כתיב מלא/חסר, כינויי מותגים) + התאמה מטושטשת לכל מילה. מחזיר מהציון הגבוה לנמוך."""
    query = (query or "").strip()
    if not query:
        return []

    q_lower = query.lower()
    scored: list[tuple[float, float, dict]] = []
    for item in catalog:
        brand = (item.get("brand") or "").strip()
        if not brand:
            continue
        score = search_score(query, brand)
        if score >= FUZZY_MATCH_THRESHOLD:
            # שובר שוויון: דמיון גולמי לכל הכותרת
            scored.append((score, fuzz.partial_ratio(q_lower, brand.lower()), item))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item for _, _, item in scored]


# ---------------------------------------------------------------------------
# קטגוריה (סוג מוצר) - נגזרת ממילות מפתח בכותרת. אותם כללים כמו ב-make_package.py
# (product_type). מוצרים ישנים בלי שדה category מקבלים אותה בזמן תצוגה.
# ---------------------------------------------------------------------------

_CATEGORY_RULES: list[tuple[str, str]] = [
    (r"\bwatch(es)?\b|(?<![א-ת])שעונ", "שעונים"),
    (r"\bscarf|\bscarves\b|(?<![א-ת])צעיפ", "צעיפים"),
    (r"\bwallet|\bcard ?holder|(?<![א-ת])ארנק|\bbag\b|\bbags\b|backpack|\btote\b|\bclutch\b|(?<![א-ת])תיק", "תיקים וארנקים"),
    (r"\bbelt\b|(?<![א-ת])חגור|sunglass|(?<![א-ת])משקפי|\bcap\b|\bhat\b|beanie|(?<![א-ת])כובע", "אביזרים"),
    (r"hoodie|(?<![א-ת])קפוצ'?ונ|t-?shirt|\btee\b|(?<![א-ת])חולצ|\bjacket\b|\bcoat\b|(?<![א-ת])מעיל|\bpants\b|\bshorts\b"
     r"|\bjeans\b|(?<![א-ת])מכנס|tracksuit|(?<![א-ת])אימונית|\bsocks?\b|(?<![א-ת])גרב", "ביגוד"),
    (r"sandal|(?<![א-ת])סנדל|slide|flip-?flop|\bthong\b|slipper|mule|adilette|\bclogs?\b|(?<![א-ת])כפכפ|(?<![א-ת])מיול"
     r"|(?<![א-ת])סלייד|(?<![א-ת])אדילט", "כפכפים וסנדלים"),
    (r"\bboots?\b|(?<![א-ת])מגפ", "מגפיים"),
    (r"mercurial|\bf50\b|predator|phantom|tiempo|\bcopa\b|\b(fg|ag|sg|tf)\b|football|soccer|(?<![א-ת])כדורגל", "נעלי כדורגל"),
    (r"loafer|oxford|derby|(?<![א-ת])לואפר|(?<![א-ת])מוקסינ", "נעליים אלגנטיות"),
]
_KIDS_RE = re.compile(r"\bkids?\b|\bchildren\b|\btoddler\b|\b(gs|ps|td)\b|ילדים|לילדים|ילדות")
_FOOTWEAR_CATEGORIES = {"סניקרס", "כפכפים וסנדלים", "מגפיים", "נעלי כדורגל", "נעליים אלגנטיות"}


def derive_category(title: str) -> str:
    text = (title or "").lower().translate(_FINALS)
    category = "סניקרס"
    for rx, cat in _CATEGORY_RULES:
        if re.search(rx, text):
            category = cat
            break
    if category in _FOOTWEAR_CATEGORIES and _KIDS_RE.search(text):
        category = "ילדים"
    return category


def item_category(item: dict) -> str:
    return item.get("category") or derive_category(item.get("brand") or "")


def item_brand_name(item: dict) -> str:
    """שם המותג מהכותרת ('Nike | Nike Dunk | ...' -> 'Nike')."""
    title = (item.get("brand") or "").strip()
    first = title.split("|")[0].strip() if "|" in title else (title.split()[0] if title else "")
    return first or "—"


def now_iso() -> str:
    """זמן נוכחי ב-UTC בפורמט ISO (עם אזור זמן)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def item_image_paths(item: dict) -> list[str]:
    """מחזיר את רשימת נתיבי התמונות של מוצר (תומך גם במוצרים ישנים עם image_path יחיד)."""
    if item.get("image_paths"):
        return item["image_paths"]
    if item.get("image_path"):
        return [item["image_path"]]
    return []


def item_phashes(item: dict) -> list[str]:
    """מחזיר את רשימת טביעות האצבע של מוצר (תומך גם במוצרים ישנים עם phash יחיד)."""
    if item.get("phashes"):
        return item["phashes"]
    if item.get("phash"):
        return [item["phash"]]
    return []


def item_video_file_ids(item: dict) -> list[str]:
    """מחזיר את רשימת ה-file_id של הסרטונים של מוצר (אם יש)."""
    return item.get("video_file_ids") or []


def load_catalog() -> list[dict]:
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog: list[dict]) -> None:
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


def is_admin(user_id: int) -> bool:
    # אם לא הוגדר שום אדמין - כולם נחשבים אדמין (נוח לבדיקה ראשונית, מומלץ להגדיר ADMIN_IDS בפועל)
    return not ADMIN_IDS or user_id in ADMIN_IDS


def is_catalog_group(chat_id: int) -> bool:
    return CATALOG_GROUP_ID is not None and chat_id == CATALOG_GROUP_ID


def parse_caption(caption: str) -> dict:
    """מפרסר כיתוב בפורמט 'מותג: X\nפרטים: ...\nמחיר: Y\nקישור: Z' לדיקט.
    'פרטים' יכול להכיל כמה שורות - כל שורה לא ריקה הופכת לנקודה נפרדת."""
    fields = {"brand": "", "details": [], "price": "", "link": ""}

    brand_match = re.search(r"מותג\s*:\s*(.+)", caption)
    if brand_match:
        fields["brand"] = brand_match.group(1).strip()

    details_match = re.search(
        r"פרטים\s*:\s*(.+?)(?=\n\s*(?:מחיר|קישור)\s*:|\Z)", caption, re.DOTALL
    )
    if details_match:
        raw_lines = details_match.group(1).splitlines()
        fields["details"] = [
            re.sub(r"^[-•*]\s*", "", line).strip() for line in raw_lines if line.strip()
        ]

    price_match = re.search(r"מחיר\s*:\s*(.+?)(?=\n\s*קישור\s*:|\Z)", caption, re.DOTALL)
    if price_match:
        fields["price"] = price_match.group(1).strip()

    link_match = re.search(r"קישור\s*:\s*(\S+)", caption)
    if link_match:
        fields["link"] = link_match.group(1).strip()

    return fields


ADD_FORMAT_HELP = (
    "כדי להוסיף מוצר, שלח תמונה ו/או סרטון (אפשר גם כמה ביחד) עם כיתוב בפורמט:\n\n"
    "מותג: שם המותג והדגם\n"
    "פרטים:\n"
    "מידה 40-45\n"
    "צבע שחור\n"
    'מחיר: 199 ש"ח\n'
    "קישור: https://...\n\n"
    'לחיפוש - תכתוב "חפש לי <מותג>", "קטלוג" לדפדוף בהכל, או שלח תמונה.'
)

# הודעה שמוצגת כשחיפוש (טקסט מפורש או תמונה) לא הניב תוצאה - זמנית, כל עוד
# הקטלוג עדיין קטן/בבנייה. אפשר לשנות את הניסוח כאן במקום אחד.
NOT_FOUND_MESSAGE = (
    "🛠️ הבוט עדיין בבנייה ומרחיב את הקטלוג כל הזמן - עדיין לא מצאנו את מה שחיפשת.\n"
    "נחזור אליך בפרטי בהקדם עם מה שביקשת! 🙏"
)


# ---------------------------------------------------------------------------
# בניית הודעת/תמונת תוצאה למוצר בודד
# ---------------------------------------------------------------------------


def format_product_header(item: dict) -> str:
    """כותרת + פרטים + מחיר + קישור מוסתר (בלי הפוטר הקבוע) - ה-caption של התמונה."""
    lines = [f"⭐️ <b>{html.escape(item.get('brand', ''))}</b>"]

    details = item.get("details") or []
    if details:
        lines.append("")
        lines.extend(f"✅ {html.escape(d)}" for d in details)

    if item.get("price"):
        lines.append("")
        lines.append(f"🔥 מחיר: {html.escape(item['price'])}")

    lines.append("")
    link = html.escape(item["link"], quote=True)
    lines.append(f"🔗 לקישור המוסתר:\n{link}")

    return "\n".join(lines)


async def send_product_detail(bot, chat_id: int, item: dict) -> None:
    """שולח מדיה של מוצר (תמונות ו/או סרטונים, אחד או כמה כאלבום) + פרטים + פוטר."""
    header = format_product_header(item)
    full_caption = f"{header}\n\n{RESULT_FOOTER_HTML}"

    photo_paths = [DATA_DIR / p for p in item_image_paths(item)]
    photo_paths = [p for p in photo_paths if p.exists()]
    video_file_ids = item_video_file_ids(item)

    total = len(photo_paths) + len(video_file_ids)

    if total == 0:
        # אין אף מדיה שמורה - לפחות שולחים את הטקסט המלא.
        await bot.send_message(
            chat_id=chat_id, text=full_caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        return

    if total == 1:
        caption_fits = len(full_caption) <= 1024
        if photo_paths:
            with open(photo_paths[0], "rb") as f:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=full_caption if caption_fits else header,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await bot.send_video(
                chat_id=chat_id,
                video=video_file_ids[0],
                caption=full_caption if caption_fits else header,
                parse_mode=ParseMode.HTML,
            )
        if not caption_fits:
            # הכיתוב ארוך מדי בשביל תמונה/סרטון אחד (מגבלת טלגרם 1024 תווים) - שולחים בנפרד.
            await bot.send_message(chat_id=chat_id, text=RESULT_FOOTER_HTML, parse_mode=ParseMode.HTML)
        return

    # כמה קבצי מדיה (תמונות ו/או סרטונים) - שולחים כאלבום אחד. מגבלת טלגרם:
    # עד 10 פריטים באלבום, והכיתוב (אם נכנס במגבלה) יושב על הפריט הראשון בלבד.
    photo_paths = photo_paths[:10]
    video_file_ids = video_file_ids[: max(0, 10 - len(photo_paths))]
    caption_for_album = full_caption if len(full_caption) <= 1024 else None

    open_files = [open(p, "rb") for p in photo_paths]
    try:
        media: list = []
        for i, f in enumerate(open_files):
            if i == 0 and caption_for_album:
                media.append(InputMediaPhoto(media=f, caption=caption_for_album, parse_mode=ParseMode.HTML))
            else:
                media.append(InputMediaPhoto(media=f))
        for j, video_file_id in enumerate(video_file_ids):
            if not open_files and j == 0 and caption_for_album:
                media.append(
                    InputMediaVideo(media=video_file_id, caption=caption_for_album, parse_mode=ParseMode.HTML)
                )
            else:
                media.append(InputMediaVideo(media=video_file_id))

        await bot.send_media_group(chat_id=chat_id, media=media)
    finally:
        for f in open_files:
            f.close()

    if caption_for_album is None:
        # הכיתוב לא נכנס - שולחים אותו כהודעת טקסט נפרדת אחרי האלבום.
        await bot.send_message(
            chat_id=chat_id, text=full_caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )


# ---------------------------------------------------------------------------
# רשת דפדוף ממוספרת (2x2 עם כפתורים) - לחיפושים עם כמה תוצאות, ולדפדוף בקטלוג
# ---------------------------------------------------------------------------


def build_grid_image(items: list[dict]) -> io.BytesIO:
    """מרכיב תמונה אחת עם עד 4 תמונות מוצר, כל אחת עם תגית מספר אדומה."""
    n = len(items)
    cols = 1 if n == 1 else 2
    rows = 1 if n <= 2 else 2

    canvas = Image.new("RGB", (cols * GRID_CELL_PX, rows * GRID_CELL_PX), "white")
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype(str(FONT_PATH), 56) if FONT_PATH.exists() else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    for idx, item in enumerate(items):
        col, row = idx % cols, idx // cols
        x0, y0 = col * GRID_CELL_PX, row * GRID_CELL_PX

        image_path = DATA_DIR / item_image_paths(item)[0] if item_image_paths(item) else None
        if image_path and image_path.exists():
            with Image.open(image_path) as img:
                fitted = ImageOps.fit(img.convert("RGB"), (GRID_CELL_PX, GRID_CELL_PX))
                canvas.paste(fitted, (x0, y0))
        else:
            draw.rectangle([x0, y0, x0 + GRID_CELL_PX, y0 + GRID_CELL_PX], fill=(230, 230, 230))

        # תגית מספר אדומה בפינה השמאלית-עליונה של כל תא
        cx, cy, r = x0 + 44, y0 + 44, 40
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(214, 39, 55), outline="white", width=5)
        text = str(idx + 1)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, fill="white", font=font)

    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=88)
    buffer.seek(0)
    buffer.name = "grid.jpg"
    return buffer


async def send_grid_page(context: ContextTypes.DEFAULT_TYPE, chat_id: int, session_id: str, page: int) -> None:
    session = SEARCH_SESSIONS.get(session_id)
    if not session:
        await context.bot.send_message(chat_id=chat_id, text="התוצאות האלה כבר לא זמינות, נסה לחפש שוב 🙏")
        return

    start = page * GRID_PAGE_SIZE
    page_ids = session[start : start + GRID_PAGE_SIZE]
    if not page_ids:
        await context.bot.send_message(chat_id=chat_id, text="אין עוד תוצאות להציג.")
        return

    catalog_by_id = {p["id"]: p for p in load_catalog()}
    items = [catalog_by_id[pid] for pid in page_ids if pid in catalog_by_id]
    if not items:
        await context.bot.send_message(chat_id=chat_id, text="אין עוד תוצאות להציג.")
        return

    image_buffer = build_grid_image(items)

    number_row = [
        InlineKeyboardButton(str(i + 1), callback_data=f"sel|{session_id}|{start + i}")
        for i in range(len(items))
    ]
    keyboard_rows = [number_row]
    if start + GRID_PAGE_SIZE < len(session):
        keyboard_rows.append(
            [InlineKeyboardButton("עוד דגמים / צבעים 🔍", callback_data=f"pg|{session_id}|{page + 1}")]
        )

    await context.bot.send_photo(
        chat_id=chat_id,
        photo=image_buffer,
        caption=(
            "🔍 מצאתי כמה דגמים שמתאימים!\n"
            "בחרו את המספר של הדגם שאהבתם ונשלח לכם את כל הפרטים + קישור ההזמנה 👇"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


async def handle_grid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = (query.data or "").split("|")
    if len(parts) != 3:
        return
    action, session_id, arg = parts

    if action == "sel":
        session = SEARCH_SESSIONS.get(session_id)
        if not session:
            await context.bot.send_message(
                chat_id=query.message.chat.id, text="התוצאות האלה כבר לא זמינות, נסה לחפש שוב 🙏"
            )
            return
        idx = int(arg)
        if idx >= len(session):
            return
        item = next((p for p in load_catalog() if p["id"] == session[idx]), None)
        if not item:
            await context.bot.send_message(chat_id=query.message.chat.id, text="המוצר הזה כבר לא קיים בקטלוג.")
            return
        await send_product_detail(context.bot, query.message.chat.id, item)

    elif action == "pg":
        await send_grid_page(context, query.message.chat.id, session_id, int(arg))


# ---------------------------------------------------------------------------
# הוספה ועריכה של מוצרים
# ---------------------------------------------------------------------------


async def save_new_product(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    caption: str,
    photo_file_ids: list[str],
    video_file_ids: list[str],
) -> None:
    """מוסיף מוצר לקטלוג מתמונות ו/או סרטונים (אחד או כמה כאלבום) + כיתוב.
    הקריאה לפונקציה הזו כבר מניחה שהמקור מורשה (קבוצת ההעלאה, או אדמין בצ'אט פרטי)."""
    fields = parse_caption(caption or "")

    if not fields["link"]:
        await context.bot.send_message(chat_id=chat_id, text=ADD_FORMAT_HELP)
        return

    product_id = str(uuid.uuid4())[:8]
    image_paths: list[str] = []
    phashes: list[str] = []
    for idx, file_id in enumerate(photo_file_ids):
        file = await context.bot.get_file(file_id)
        path = IMAGES_DIR / f"{product_id}_{idx}.jpg"
        await file.download_to_drive(str(path))
        image_paths.append(str(path.relative_to(DATA_DIR)))
        phashes.append(str(imagehash.phash(Image.open(path))))

    catalog = load_catalog()
    catalog.append(
        {
            "id": product_id,
            "brand": fields["brand"],
            "details": fields["details"],
            "price": fields["price"],
            "link": fields["link"],
            "image_paths": image_paths,
            "phashes": phashes,
            "video_file_ids": list(video_file_ids),
            "category": derive_category(fields["brand"]),
            "added_at": now_iso(),
        }
    )
    save_catalog(catalog)

    media_note_parts = []
    if len(image_paths) > 1:
        media_note_parts.append(f"{len(image_paths)} תמונות")
    if len(video_file_ids) == 1:
        media_note_parts.append("סרטון")
    elif len(video_file_ids) > 1:
        media_note_parts.append(f"{len(video_file_ids)} סרטונים")
    media_note = f" ({', '.join(media_note_parts)})" if media_note_parts else ""

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ נוסף לקטלוג!{media_note}\nמזהה: {product_id}\nמותג: {fields['brand'] or '—'}",
    )


async def apply_edit(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    product_id: str,
    caption: str,
    photo_file_ids: list[str],
    video_file_ids: list[str],
) -> None:
    """מחליף שדות/מדיה של מוצר קיים. שדה ריק בכיתוב החדש משאיר את הערך הישן."""
    catalog = load_catalog()
    idx = next((i for i, p in enumerate(catalog) if p["id"] == product_id), None)
    if idx is None:
        await context.bot.send_message(
            chat_id=chat_id, text=f"המוצר {product_id} כבר לא קיים בקטלוג - העריכה בוטלה."
        )
        return

    item = catalog[idx]
    fields = parse_caption(caption or "")

    # מנקים את קבצי התמונה הישנים לפני שכותבים את החדשים, כדי לא להשאיר יתומים.
    # (סרטונים לא נשמרים כקובץ מקומי - רק file_id - אז אין מה לנקות עבורם.)
    for old_path in item_image_paths(item):
        (DATA_DIR / old_path).unlink(missing_ok=True)

    image_paths: list[str] = []
    phashes: list[str] = []
    for i, file_id in enumerate(photo_file_ids):
        file = await context.bot.get_file(file_id)
        path = IMAGES_DIR / f"{product_id}_{i}.jpg"
        await file.download_to_drive(str(path))
        image_paths.append(str(path.relative_to(DATA_DIR)))
        phashes.append(str(imagehash.phash(Image.open(path))))

    item["brand"] = fields["brand"] or item.get("brand", "")
    item["details"] = fields["details"] or item.get("details", [])
    item["price"] = fields["price"] or item.get("price", "")
    item["link"] = fields["link"] or item.get("link", "")
    item["image_paths"] = image_paths
    item["phashes"] = phashes
    item["video_file_ids"] = list(video_file_ids)
    item.pop("image_path", None)  # מיגרציה מהסכמה הישנה (תמונה יחידה)
    item.pop("phash", None)

    catalog[idx] = item
    save_catalog(catalog)

    media_note_parts = []
    if len(image_paths) > 1:
        media_note_parts.append(f"{len(image_paths)} תמונות")
    if len(video_file_ids) == 1:
        media_note_parts.append("סרטון")
    elif len(video_file_ids) > 1:
        media_note_parts.append(f"{len(video_file_ids)} סרטונים")
    media_note = f" ({', '.join(media_note_parts)})" if media_note_parts else ""

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✏️ מוצר {product_id} עודכן!{media_note}\nמותג: {item['brand'] or '—'}",
    )


# ---------------------------------------------------------------------------
# ייבוא מרובה מקובץ ZIP
# ---------------------------------------------------------------------------

# מגבלת גודל לא-דחוס כוללת לתוכן ה-ZIP (הגנה מפני zip-bomb).
MAX_ZIP_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
# מגבלת הורדה של טלגרם לקבצים דרך הבוט.
TELEGRAM_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


def _is_safe_zip_member(name: str) -> bool:
    """ודא שנתיב בתוך ה-ZIP לא בורח מהתיקייה (zip-slip): בלי absolute / .. """
    if not name or name.endswith("/"):
        return False
    # נרמול ל־/ גם אם נוצר ב־Windows
    norm = name.replace("\\", "/")
    if norm.startswith("/") or norm.startswith("../") or "/../" in f"/{norm}/":
        return False
    parts = Path(norm).parts
    if any(p == ".." or p.startswith("..") for p in parts):
        return False
    if Path(norm).is_absolute():
        return False
    return True


def import_zip_into_catalog(zip_path) -> dict:
    """מייבא מוצרים מקובץ ZIP בפורמט: products.json בשורש + תיקיית images/.

    כל אובייקט ב-products.json: source_id, brand, details, price, link, images
    (נתיבים יחסיים בתוך ה-ZIP, בסדר תצוגה). אם כבר קיים מוצר עם אותו
    source_id — מעדכנים אותו (בלי כפילות); אחרת יוצרים מזהה קצר חדש.

    מחזיר dict: {added, updated, skipped: [{source_id, reason}, ...]}
    פונקציה סינכרונית טהורה (בלי טלגרם) — נוחה לבדיקות offline.
    """
    zip_path = Path(zip_path)
    summary: dict = {"added": 0, "updated": 0, "skipped": []}

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"ה-ZIP גדול מדי אחרי חילוץ "
                f"({total_uncompressed // (1024 * 1024)}MB, מקסימום "
                f"{MAX_ZIP_UNCOMPRESSED_BYTES // (1024 * 1024)}MB)"
            )

        # מפתחות שמות בנרמול ל־/
        name_map = {info.filename.replace("\\", "/"): info.filename for info in infos}
        if "products.json" not in name_map:
            raise ValueError("חסר products.json בשורש קובץ ה-ZIP")

        raw = zf.read(name_map["products.json"])
        try:
            products = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"products.json לא תקין: {exc}") from exc
        if not isinstance(products, list):
            raise ValueError("products.json חייב להכיל רשימה (list) של מוצרים")

        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        catalog = load_catalog()

        for entry in products:
            if not isinstance(entry, dict):
                summary["skipped"].append({"source_id": "", "reason": "רשומה לא תקינה (לא אובייקט)"})
                continue

            source_id = str(entry.get("source_id") or "").strip()
            link = str(entry.get("link") or "").strip()
            images = entry.get("images") or []
            if not isinstance(images, list):
                images = []

            if not link:
                summary["skipped"].append({"source_id": source_id, "reason": "חסר קישור (link)"})
                continue
            if not images:
                summary["skipped"].append({"source_id": source_id, "reason": "חסרות תמונות (images)"})
                continue

            # בדיקת נתיבי תמונות לפני כתיבה
            resolved_members: list[str] = []
            bad_image = False
            for rel in images:
                rel_s = str(rel).replace("\\", "/")
                while rel_s.startswith("./"):
                    rel_s = rel_s[2:]
                if not _is_safe_zip_member(rel_s):
                    summary["skipped"].append(
                        {"source_id": source_id, "reason": f"נתיב תמונה לא בטוח: {rel}"}
                    )
                    bad_image = True
                    break
                if rel_s not in name_map:
                    summary["skipped"].append(
                        {"source_id": source_id, "reason": f"תמונה חסרה ב-ZIP: {rel_s}"}
                    )
                    bad_image = True
                    break
                resolved_members.append(name_map[rel_s])
            if bad_image:
                continue

            existing_idx = next(
                (i for i, p in enumerate(catalog) if source_id and p.get("source_id") == source_id),
                None,
            )
            if existing_idx is not None:
                product_id = catalog[existing_idx]["id"]
                for old_path in item_image_paths(catalog[existing_idx]):
                    (DATA_DIR / old_path).unlink(missing_ok=True)
                is_update = True
            else:
                product_id = str(uuid.uuid4())[:8]
                is_update = False

            image_paths: list[str] = []
            phashes: list[str] = []
            try:
                for idx, member_name in enumerate(resolved_members):
                    data = zf.read(member_name)
                    with Image.open(io.BytesIO(data)) as im:
                        rgb = im.convert("RGB")
                        out_path = IMAGES_DIR / f"{product_id}_{idx}.jpg"
                        rgb.save(out_path, "JPEG", quality=92)
                    image_paths.append(str(out_path.relative_to(DATA_DIR)))
                    phashes.append(str(imagehash.phash(Image.open(out_path))))
            except Exception as exc:
                # ניקוי חלקי אם נכשל באמצע
                for p in image_paths:
                    (DATA_DIR / p).unlink(missing_ok=True)
                summary["skipped"].append(
                    {"source_id": source_id, "reason": f"שגיאה בפתיחת/שמירת תמונה: {exc}"}
                )
                continue

            brand = str(entry.get("brand") or "").strip()
            details = entry.get("details") or []
            if not isinstance(details, list):
                details = [str(details)] if details else []
            details = [str(d).strip() for d in details if str(d).strip()]
            price = str(entry.get("price") or "").strip()

            category = str(entry.get("category") or "").strip() or derive_category(brand)
            # added_at: זמן ההוספה הראשונה - נשמר גם כשמוצר קיים מתעדכן בייבוא חוזר
            added_at = (catalog[existing_idx].get("added_at") if existing_idx is not None else None) or now_iso()

            item = {
                "id": product_id,
                "source_id": source_id,
                "brand": brand,
                "details": details,
                "price": price,
                "link": link,
                "image_paths": image_paths,
                "phashes": phashes,
                "video_file_ids": [],
                "category": category,
                "added_at": added_at,
            }
            if existing_idx is not None:
                item["updated_at"] = now_iso()
            # ניקוי שדות ישנים אם היו
            if existing_idx is not None:
                item.pop("image_path", None)
                catalog[existing_idx] = item
                # גם אם נשארו מפתחות ישנים — דורסים את הרשומה
                summary["updated"] += 1
            else:
                catalog.append(item)
                summary["added"] += 1

        save_catalog(catalog)

    return summary


def format_import_summary(summary: dict) -> str:
    """בונה הודעת סיכום בעברית לייבוא ZIP."""
    lines = [
        "📦 ייבוא ZIP הסתיים",
        f"✅ נוספו: {summary.get('added', 0)}",
        f"✏️ עודכנו: {summary.get('updated', 0)}",
    ]
    skipped = summary.get("skipped") or []
    lines.append(f"⏭️ דולגו: {len(skipped)}")
    for s in skipped[:20]:
        sid = s.get("source_id") or "—"
        reason = s.get("reason") or "—"
        lines.append(f"  • {sid}: {reason}")
    if len(skipped) > 20:
        lines.append(f"  … ועוד {len(skipped) - 20}")
    lines.append("")
    lines.append(
        f"⚠️ שימו לב: טלגרם מאפשר הורדת קבצים לבוט עד "
        f"{TELEGRAM_MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB בלבד. "
        "אם ה-ZIP גדול יותר — פצלו אותו (למשל עם make_package.py)."
    )
    return "\n".join(lines)


async def handle_zip_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ייבוא מרובה מקובץ ZIP: אדמין בצ'אט פרטי, או כל שליחה בקבוצת ההעלאה.
    כיתוב /import אופציונלי — כל מסמך .zip מורשה עובר ייבוא."""
    message = update.message
    if not message or not message.document:
        return

    chat = update.effective_chat
    user = update.effective_user
    in_private_admin = chat.type == "private" and is_admin(user.id)
    in_catalog_group = is_catalog_group(chat.id)
    if not (in_private_admin or in_catalog_group):
        return

    doc = message.document
    if doc.file_size and doc.file_size > TELEGRAM_MAX_DOWNLOAD_BYTES:
        await message.reply_text(
            f"הקובץ גדול מדי ({doc.file_size // (1024 * 1024)}MB). "
            f"טלגרם מאפשר לבוט להוריד עד {TELEGRAM_MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB בלבד — "
            "פצלו את ה-ZIP לקבצים קטנים יותר ושלחו שוב."
        )
        return

    status_msg = await message.reply_text("📦 קולט את קובץ ה-ZIP ומייבא מוצרים...")
    tmp_path = IMAGES_DIR / f"_import_{uuid.uuid4().hex[:8]}.zip"
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(str(tmp_path))
        summary = import_zip_into_catalog(tmp_path)
        await status_msg.edit_text(format_import_summary(summary))
    except ValueError as exc:
        await status_msg.edit_text(f"❌ הייבוא נכשל: {exc}")
    except Exception:
        logger.exception("ZIP import failed")
        await status_msg.edit_text(
            "❌ הייבוא נכשל בגלל תקלה לא צפויה. בדקו את הלוגים / את מבנה ה-ZIP."
        )
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# חיפוש (טקסט/תמונה) ודפדוף בקטלוג
# ---------------------------------------------------------------------------


CATALOG_TRIGGER_WORDS = {"קטלוג", "קטלוג מלא", "תראה הכל", "תראו הכל", "כל המוצרים"}


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בהודעת טקסט:
    - 'קטלוג' -> דפדוף בהכל.
    - 'חפש לי X' -> חיפוש מפורש. בלי תוצאה: מגיב "לא מצאתי" + מתריע לאדמין.
    - כל טקסט אחר (לא בקבוצת ההעלאה) -> מנסה להתאים כשם מותג ישירות (בלי
      צורך לכתוב "חפש לי"). אם לא נמצאה התאמה - שקט, כדי לא "לתקוע" תגובת
      שגיאה על כל הודעת צ'אט סתמית שלא הייתה כוונתה בכלל לחפש מוצר.
    """
    text = (update.message.text or "").strip()
    if not text:
        return

    if text in CATALOG_TRIGGER_WORDS:
        await start_browse(update, context, load_catalog())
        return

    catalog = load_catalog()

    explicit_match = re.match(r"^\s*חפש\s*לי\s+(.+)", text)
    if explicit_match:
        query = explicit_match.group(1).strip()
        results = search_catalog(query, catalog)
        if not results:
            await update.message.reply_text(NOT_FOUND_MESSAGE)
            await notify_admin_group(
                context,
                f"🔎 חיפוש ללא תוצאה\nמאת: {user_mention_html(update)}\nחיפש: \"{html.escape(query)}\"",
            )
            return
        await start_browse(update, context, results)
        return

    # חיפוש משתמע - טקסט חופשי שלא מתחיל ב"חפש לי". לא פעיל בקבוצת ההעלאה
    # (שם טקסט חופשי הוא לרוב שיחה בין אדמינים, לא בקשת חיפוש של לקוח).
    if is_catalog_group(update.effective_chat.id):
        return

    # רק לטקסט קצר (עד 3 מילים) - משפטים ארוכים כנראה שיחה רגילה, לא שם מוצר.
    if len(text.split()) > 3:
        return

    results = search_catalog(text, catalog)
    if results:
        await start_browse(update, context, results)
    # אין תוצאה -> שקט בכוונה (ראה docstring למעלה)


async def start_browse(update: Update, context: ContextTypes.DEFAULT_TYPE, items: list[dict]) -> None:
    """מתחיל דפדוף על רשימת מוצרים: תמונה בודדת+פרטים אם יש אחת, אחרת רשת ממוספרת."""
    if not items:
        await update.message.reply_text("הקטלוג ריק כרגע.")
        return

    if len(items) == 1:
        await send_product_detail(context.bot, update.effective_chat.id, items[0])
        return

    session_id = uuid.uuid4().hex[:8]
    SEARCH_SESSIONS[session_id] = [item["id"] for item in items]
    await send_grid_page(context, update.effective_chat.id, session_id, 0)


async def handle_catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_browse(update, context, load_catalog())


async def route_incoming_media(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    caption: str,
    photo_file_ids: list[str],
    video_file_ids: list[str],
    mention_html: str,
) -> None:
    """הלוגיקה המשותפת לניתוב תמונה/סרטון/אלבום מעורב שהתקבל: עריכה ממתינה /
    הוספה לקטלוג / חיפוש לפי תמונה. עובדת גם עבור מדיה בודדת מיידית וגם עבור
    אלבום שנאסף במאגר הזמני ומעובד אחרי דיליי קצר (ראה handle_media_message)."""
    has_valid_caption = bool(parse_caption(caption or "").get("link"))

    # 0. יש עריכה ממתינה למשתמש הזה (מ-/edit) -> תמיד עדיפות ראשונה
    pending_product_id = PENDING_EDITS.pop(user_id, None)
    if pending_product_id is not None:
        await apply_edit(context, chat_id, pending_product_id, caption, photo_file_ids, video_file_ids)
        return

    # 1. הודעה בקבוצת ההעלאה המיועדת -> תמיד ניסיון הוספה (לא תלוי מי שלח)
    if is_catalog_group(chat_id):
        if has_valid_caption:
            await save_new_product(context, chat_id, caption, photo_file_ids, video_file_ids)
        else:
            await context.bot.send_message(chat_id=chat_id, text=ADD_FORMAT_HELP)
        return

    # 2. אדמין בצ'אט פרטי עם כיתוב תקין -> הוספה (השיטה הישנה, עדיין נתמכת)
    if is_admin(user_id) and has_valid_caption:
        await save_new_product(context, chat_id, caption, photo_file_ids, video_file_ids)
        return

    # 3. חיפוש - רק לפי תמונה (סרטון לא נתמך לחיפוש). אם נשלח רק סרטון בלי
    # תמונה, אין מה להשוות - מעבירים ישירות לקבוצת האדמין כמו במקרה "כבוי".
    if not photo_file_ids:
        if video_file_ids:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🔍 חיפוש לפי סרטון עדיין לא נתמך.\n"
                    'תכתבו לי מה אתם מחפשים (למשל "חפש לי נייקי") או שלחו תמונה - ואשמח לעזור 🙏'
                ),
            )
            await notify_admin_group(
                context, f"🎥 התקבל סרטון לחיפוש (לא נתמך)\nמאת: {mention_html}"
            )
        return

    first_file_id = photo_file_ids[0]

    if not ENABLE_IMAGE_SEARCH:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🔍 חיפוש לפי תמונה כרגע לא זמין.\n"
                'תכתבו לי מה אתם מחפשים (למשל "חפש לי נייקי") ואשמח לעזור - '
                "או שנחזור אליכם ישירות בקרוב 🙏"
            ),
        )
        await notify_admin_group_photo(
            context, first_file_id, f"📸 בקשת חיפוש לפי תמונה (זיהוי תמונות כבוי)\nמאת: {mention_html}"
        )
        return

    catalog = load_catalog()
    if not catalog:
        await context.bot.send_message(chat_id=chat_id, text="הקטלוג עדיין ריק, אין מה לחפש בו כרגע.")
        return

    file = await context.bot.get_file(first_file_id)
    tmp_path = IMAGES_DIR / f"_search_{uuid.uuid4().hex[:8]}.jpg"
    await file.download_to_drive(str(tmp_path))

    try:
        query_hash = imagehash.phash(Image.open(tmp_path))

        best_match = None
        best_distance = None
        for item in catalog:
            for phash_hex in item_phashes(item):
                distance = query_hash - imagehash.hex_to_hash(phash_hex)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_match = item

        if best_match and best_distance <= IMAGE_MATCH_THRESHOLD:
            await send_product_detail(context.bot, chat_id, best_match)
        else:
            await context.bot.send_message(chat_id=chat_id, text=NOT_FOUND_MESSAGE)
            await notify_admin_group_photo(
                context, first_file_id, f"🔎 חיפוש לפי תמונה ללא תוצאה\nמאת: {mention_html}"
            )
    finally:
        tmp_path.unlink(missing_ok=True)


async def process_media_group_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """נקרא אחרי דיליי קצר מאז הפריט האחרון של אלבום - מעבד את כל האלבום ביחד."""
    media_group_id = context.job.data
    buf = MEDIA_GROUP_BUFFERS.pop(media_group_id, None)
    if not buf:
        return
    await route_incoming_media(
        context,
        buf["chat_id"],
        buf["user_id"],
        buf["caption"],
        buf["photo_file_ids"],
        buf["video_file_ids"],
        buf["mention_html"],
    )


async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בתמונה/סרטון נכנס. אם הוא חלק מאלבום (media_group_id), אוספים אותו
    במאגר זמני וממתינים רגע לשאר הפריטים של אותו אלבום לפני עיבוד; אחרת
    מעבדים מיד (ראה route_incoming_media לניתוב בפועל)."""
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    caption = message.caption or ""
    mention_html = user_mention_html(update)

    photo_file_id = message.photo[-1].file_id if message.photo else None
    video_file_id = message.video.file_id if message.video else None

    media_group_id = message.media_group_id
    if media_group_id:
        buf = MEDIA_GROUP_BUFFERS.setdefault(
            media_group_id,
            {
                "photo_file_ids": [],
                "video_file_ids": [],
                "caption": "",
                "chat_id": chat_id,
                "user_id": user_id,
                "mention_html": mention_html,
            },
        )
        if photo_file_id:
            buf["photo_file_ids"].append(photo_file_id)
        if video_file_id:
            buf["video_file_ids"].append(video_file_id)
        if caption:
            buf["caption"] = caption

        # דוחים (debounce) את העיבוד בכל פעם שמגיע עוד פריט מאותו אלבום,
        # כדי לוודא שכל התמונות/הסרטונים נאספו לפני שממשיכים.
        if context.job_queue is not None:
            for job in context.job_queue.get_jobs_by_name(media_group_id):
                job.schedule_removal()
            context.job_queue.run_once(
                process_media_group_job, when=MEDIA_GROUP_DEBOUNCE_SECONDS, data=media_group_id, name=media_group_id
            )
        else:
            # גיבוי נדיר: אם JobQueue לא זמין (חסרה תלות apscheduler) - מעבדים
            # מיד את מה שיש עד כה במקום לא להגיב בכלל.
            logger.warning("JobQueue not available - processing media group immediately without debounce")
            await route_incoming_media(
                context, chat_id, user_id, buf["caption"], buf["photo_file_ids"], buf["video_file_ids"], mention_html
            )
            MEDIA_GROUP_BUFFERS.pop(media_group_id, None)
        return

    await route_incoming_media(
        context,
        chat_id,
        user_id,
        caption,
        [photo_file_id] if photo_file_id else [],
        [video_file_id] if video_file_id else [],
        mention_html,
    )


# ---------------------------------------------------------------------------
# פקודות ניהול
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# /stats - סטטיסטיקות קטלוג (אדמין בלבד)
# ---------------------------------------------------------------------------

STATS_MAIN_BRANDS = ("Nike", "Adidas", "Asics", "New Balance", "Hoka", "Yeezy")
STATS_RECENT_COUNT = 20


def _display_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(os.environ.get("BOT_TIMEZONE", "Asia/Jerusalem"))
    except Exception:
        return None


def format_added_at(value: str | None) -> str:
    if not value:
        return "תאריך לא ידוע"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = _display_tz()
    if tz is not None:
        dt = dt.astimezone(tz)
    return dt.strftime("%d/%m/%Y %H:%M")


def format_stats(catalog: list[dict]) -> str:
    """בונה את הודעת /stats: סה"כ, פילוח לפי מותג ולפי סוג, ואחרונים שנוספו."""
    total = len(catalog)
    lines = ["📊 סטטיסטיקות קטלוג", f"סה\"כ מוצרים: {total}"]
    if not catalog:
        return "\n".join(lines)

    brand_counts: dict[str, int] = {}
    for item in catalog:
        b = item_brand_name(item)
        key = next((m for m in STATS_MAIN_BRANDS if m.lower() == b.lower()), b)
        brand_counts[key] = brand_counts.get(key, 0) + 1
    lines += ["", "🏷️ לפי מותג:"]
    for b in sorted((b for b in STATS_MAIN_BRANDS if brand_counts.get(b)), key=lambda b: -brand_counts[b]):
        lines.append(f"• {b}: {brand_counts[b]}")
    others = sorted(((b, c) for b, c in brand_counts.items() if b not in STATS_MAIN_BRANDS), key=lambda x: (-x[1], x[0]))
    if others:
        lines.append(f"• מותגים אחרים: {sum(c for _, c in others)} ({', '.join(f'{b} {c}' for b, c in others)})")

    cat_counts: dict[str, int] = {}
    for item in catalog:
        c = item_category(item)
        cat_counts[c] = cat_counts.get(c, 0) + 1
    lines += ["", "👟 לפי סוג:"]
    for c, n in sorted(cat_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"• {c}: {n}")

    # אחרונים שנוספו: לפי added_at (מוצרים ישנים בלי תאריך - בסוף, לפי סדר הקטלוג)
    indexed = list(enumerate(catalog))
    indexed.sort(key=lambda p: (p[1].get("added_at") or "", p[0]), reverse=True)
    recent = indexed[:STATS_RECENT_COUNT]
    lines += ["", f"🆕 {len(recent)} המוצרים האחרונים שנוספו:"]
    for _, item in recent:
        lines.append(f"• {format_added_at(item.get('added_at'))} | {item.get('brand') or '—'} ({item.get('id')})")
    return "\n".join(lines)


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    text = format_stats(load_catalog())
    # טלגרם מגביל אורך הודעה - נחלק לצ'אנקים לפי שורות
    chunk = ""
    for line in text.split("\n"):
        if len(chunk) + len(line) + 1 > 3500:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await update.message.reply_text(chunk)


async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    catalog = load_catalog()
    if not catalog:
        await update.message.reply_text("הקטלוג ריק.")
        return

    blocks = []
    for item in catalog:
        price_part = f" | {item['price']}" if item.get("price") else ""
        blocks.append(
            f"{item['id']} | {item.get('brand', '—')}{price_part}\n{item.get('link', '—')}"
        )
    text = "\n\n".join(blocks) + "\n\nלעריכה: /edit <מזהה>\nלמחיקה: /delete <מזהה>"

    # טלגרם מגביל אורך הודעה - נחלק לצ'אנקים אם צריך
    for i in range(0, len(text), 3500):
        await update.message.reply_text(text[i : i + 3500])


async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("שימוש: /edit <מזהה מוצר>\nלרשימת מזהים: /list")
        return

    product_id = context.args[0]
    catalog = load_catalog()
    item = next((p for p in catalog if p["id"] == product_id), None)
    if not item:
        await update.message.reply_text(f"לא נמצא מוצר עם מזהה {product_id}")
        return

    PENDING_EDITS[update.effective_user.id] = product_id
    await update.message.reply_text(
        f"עורך את מוצר {product_id} ({item.get('brand') or '—'}).\n\n"
        "עכשיו שלח תמונה/סרטון חדשים עם כיתוב באותו פורמט (מותג/פרטים/מחיר/קישור). "
        "שדה שתשאיר ריק יישאר כמו שהיה. לביטול: /canceledit"
    )


async def handle_cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if PENDING_EDITS.pop(update.effective_user.id, None) is not None:
        await update.message.reply_text("העריכה בוטלה.")
    else:
        await update.message.reply_text("אין עריכה פעילה לביטול.")


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("שימוש: /delete <מזהה מוצר>")
        return

    product_id = context.args[0]
    catalog = load_catalog()
    new_catalog = [item for item in catalog if item["id"] != product_id]

    if len(new_catalog) == len(catalog):
        await update.message.reply_text(f"לא נמצא מוצר עם מזהה {product_id}")
        return

    removed = next(item for item in catalog if item["id"] == product_id)
    for path in item_image_paths(removed):
        (DATA_DIR / path).unlink(missing_ok=True)

    save_catalog(new_catalog)
    await update.message.reply_text(f"🗑️ נמחק מוצר {product_id}")


async def handle_groupid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await update.message.reply_text(f"מזהה הצ'אט הזה: {chat.id}")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "היי! 👋\n"
        'כדי לחפש מוצר - תכתוב "חפש לי <מותג>", "קטלוג" לדפדוף בהכל, או שלח תמונה של המוצר.'
    )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """נתפס בכל שגיאה שלא טופלה - כותב ללוג ומודיע למשתמש במקום שקט מוחלט."""
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😕 קרתה תקלה בעיבוד ההודעה. נסה שוב - ואם זה חוזר, תבדוק את הלוגים בשרת."
            )
        except Exception:
            pass


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("חסר BOT_TOKEN - הגדר משתנה סביבה BOT_TOKEN עם הטוקן מ-BotFather")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("catalog", handle_catalog_command))
    app.add_handler(CommandHandler("list", handle_list))
    app.add_handler(CommandHandler("stats", handle_stats))
    app.add_handler(CommandHandler("edit", handle_edit))
    app.add_handler(CommandHandler("canceledit", handle_cancel_edit))
    app.add_handler(CommandHandler("delete", handle_delete))
    app.add_handler(CommandHandler("groupid", handle_groupid))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media_message))
    app.add_handler(MessageHandler(filters.Document.ZIP, handle_zip_import))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))
    app.add_handler(CallbackQueryHandler(handle_grid_callback))
    app.add_error_handler(handle_error)

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
