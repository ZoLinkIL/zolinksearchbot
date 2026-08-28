"""
בוט טלגרם לקטלוג מוצרים - חיפוש לפי שם מותג, לפי תמונה, או דפדוף בקטלוג.

איך זה עובד:
- הוספת מוצרים אפשרית בשתי דרכים (אפשר להשתמש בשתיהן ביחד):
    1. קבוצת "העלאת מוצרים" נפרדת - כל תמונה (או כמה תמונות ביחד כ"אלבום")
       עם כיתוב תקין שנשלחת בקבוצה שמוגדרת ב-CATALOG_GROUP_ID נכנסת
       אוטומטית לקטלוג כמוצר אחד.
    2. הודעה פרטית לבוט מאדמין (מי שה-ID שלו ב-ADMIN_IDS) - אותו פורמט כיתוב.
  פורמט הכיתוב:
    מותג: שם המותג והדגם
    פרטים: (כל שורה הופכת לנקודה משלה)
    מידה 40-45
    צבע שחור
    מחיר: 199 ש"ח
    קישור: https://...

  אפשר לשלוח כמה תמונות ביחד (כ"אלבום" בטלגרם) עם כיתוב אחד - כולן יישמרו
  תחת אותו מוצר, וייחשלו יחד כאלבום גם כשהמוצר מוצג. הבוט אוסף את כל
  התמונות של אותו אלבום (הן מגיעות כהודעות נפרדות מטלגרם) וממתין רגע קט
  (MEDIA_GROUP_DEBOUNCE_SECONDS) לפני שהוא שומר את המוצר.

- כל משתמש אחר (בצ'אט פרטי או בקבוצה אחרת, לא קבוצת ההעלאה) יכול:
    - לכתוב "חפש לי <מותג>" -> חיפוש מטושטש (fuzzy) שסובלני לטעויות הקלדה
      קטנות (אות חסרה/עודפת/מוחלפת). אם יש תוצאה אחת, מקבל תמונה+פרטים
      מלאים. אם יש כמה, מקבל רשת ממוספרת. בלי תוצאה - "לא מצאתי" + התראה לאדמין.
    - לכתוב שם מותג ישירות, בלי "חפש לי" (עד 3 מילים, למשל סתם "נייקי") ->
      אותו חיפוש מטושטש, אבל אם אין התאמה הבוט שותק (כדי לא להגיב "לא
      מצאתי" על כל הודעת צ'אט סתמית). כבוי בקבוצת ההעלאה עצמה.
    - לכתוב "קטלוג" (או /catalog) -> רשת דפדוף על כל המוצרים בקטלוג.
    - לשלוח תמונה -> אם ENABLE_IMAGE_SEARCH=false (ברירת מחדל: true), הבוט לא
      מנסה להתאים בכלל - מודיע למשתמש ומעביר את התמונה לקבוצת האדמין.
      אם מופעל, הבוט מחשב טביעת אצבע ויזואלית (perceptual hash) ומשווה
      לתמונות השמורות; אם לא נמצאה התאמה, גם זה נשלח לקבוצת האדמין.

- /list -> אדמין בלבד: מציג את כל המוצרים בקטלוג (מזהה, מותג, מחיר, קישור).
- /edit <id> -> אדמין בלבד: מתחיל עריכת מוצר קיים - שולחים תמונה+כיתוב חדשים
  (כמו בהוספה) והם מחליפים את הישן. שדה שמשאירים ריק/לא כתוב נשאר כמו שהיה.
- /canceledit -> מבטל עריכה שהתחילה עם /edit.
- /delete <id> -> אדמין בלבד: מוחק מוצר מהקטלוג.
- /groupid -> מציג את מזהה הקבוצה הנוכחית (שימושי כדי להגדיר CATALOG_GROUP_ID
  או NOTIFY_GROUP_ID).

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
from pathlib import Path

import imagehash
from PIL import Image, ImageDraw, ImageFont, ImageOps
from rapidfuzz import fuzz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
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


# סף התאמה מטושטשת לחיפוש טקסט (0-100, ככל שגבוה יותר - דורש התאמה מדויקת
# יותר). 80 סובלני לטעויות הקלדה קלות (אות חסרה/עודפת) בלי לתפוס מילים
# מקריות מהודעות צ'אט סתמיות. אם מתחילות להופיע התאמות שגויות, העלה את
# המספר; אם חיפושים סבירים לא נמצאים, הורד אותו מעט.
FUZZY_MATCH_THRESHOLD = 80


def search_catalog(query: str, catalog: list[dict]) -> list[dict]:
    """חיפוש מטושטש (fuzzy) של query מול שם המותג של כל מוצר - סובלני לטעויות
    הקלדה קטנות. מחזיר את המוצרים התואמים, מהניקוד הגבוה לנמוך."""
    query = (query or "").strip().lower()
    if not query:
        return []

    scored: list[tuple[float, dict]] = []
    for item in catalog:
        brand = (item.get("brand") or "").strip().lower()
        if not brand:
            continue
        score = max(fuzz.partial_ratio(query, brand), fuzz.token_sort_ratio(query, brand))
        if score >= FUZZY_MATCH_THRESHOLD:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


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
    "כדי להוסיף מוצר, שלח תמונה עם כיתוב בפורמט:\n\n"
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
    """שולח תמונות מוצר (אחת או כמה כאלבום) + פרטים מעוצבים + הפוטר הקבוע."""
    header = format_product_header(item)
    full_caption = f"{header}\n\n{RESULT_FOOTER_HTML}"

    paths = [DATA_DIR / p for p in item_image_paths(item)]
    paths = [p for p in paths if p.exists()][:10]  # מגבלת טלגרם: עד 10 תמונות באלבום

    if not paths:
        # אין אף תמונה שמורה בדיסק - לפחות שולחים את הטקסט המלא.
        await bot.send_message(
            chat_id=chat_id, text=full_caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        return

    if len(paths) == 1:
        if len(full_caption) <= 1024:
            with open(paths[0], "rb") as f:
                await bot.send_photo(
                    chat_id=chat_id, photo=f, caption=full_caption, parse_mode=ParseMode.HTML
                )
            return
        # הכיתוב ארוך מדי בשביל תמונה אחת (מגבלת טלגרם 1024 תווים) - שולחים בנפרד.
        with open(paths[0], "rb") as f:
            await bot.send_photo(chat_id=chat_id, photo=f, caption=header, parse_mode=ParseMode.HTML)
        await bot.send_message(chat_id=chat_id, text=RESULT_FOOTER_HTML, parse_mode=ParseMode.HTML)
        return

    # כמה תמונות - שולחים כאלבום. הכיתוב (אם נכנס במגבלה) יושב על התמונה הראשונה בלבד.
    caption_for_album = full_caption if len(full_caption) <= 1024 else None
    open_files = [open(p, "rb") for p in paths]
    try:
        media = [
            InputMediaPhoto(media=f, caption=caption_for_album, parse_mode=ParseMode.HTML)
            if i == 0 and caption_for_album
            else InputMediaPhoto(media=f)
            for i, f in enumerate(open_files)
        ]
        await bot.send_media_group(chat_id=chat_id, media=media)
    finally:
        for f in open_files:
            f.close()

    if caption_for_album is None:
        # הכיתוב לא נכנס לתמונה - שולחים אותו כהודעת טקסט נפרדת אחרי האלבום.
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
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, caption: str, file_ids: list[str]
) -> None:
    """מוסיף מוצר לקטלוג מתמונה אחת או כמה (אלבום) + כיתוב. הקריאה לפונקציה הזו
    כבר מניחה שהמקור מורשה (קבוצת ההעלאה, או אדמין בצ'אט פרטי)."""
    fields = parse_caption(caption or "")

    if not fields["link"]:
        await context.bot.send_message(chat_id=chat_id, text=ADD_FORMAT_HELP)
        return

    product_id = str(uuid.uuid4())[:8]
    image_paths: list[str] = []
    phashes: list[str] = []
    for idx, file_id in enumerate(file_ids):
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
        }
    )
    save_catalog(catalog)

    photo_count_note = f" ({len(image_paths)} תמונות)" if len(image_paths) > 1 else ""
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ נוסף לקטלוג!{photo_count_note}\nמזהה: {product_id}\nמותג: {fields['brand'] or '—'}",
    )


async def apply_edit(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    product_id: str,
    caption: str,
    file_ids: list[str],
) -> None:
    """מחליף שדות/תמונות של מוצר קיים. שדה ריק בכיתוב החדש משאיר את הערך הישן."""
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
    for old_path in item_image_paths(item):
        (DATA_DIR / old_path).unlink(missing_ok=True)

    image_paths: list[str] = []
    phashes: list[str] = []
    for i, file_id in enumerate(file_ids):
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
    item.pop("image_path", None)  # מיגרציה מהסכמה הישנה (תמונה יחידה)
    item.pop("phash", None)

    catalog[idx] = item
    save_catalog(catalog)

    photo_count_note = f" ({len(image_paths)} תמונות)" if len(image_paths) > 1 else ""
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✏️ מוצר {product_id} עודכן!{photo_count_note}\nמותג: {item['brand'] or '—'}",
    )


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


async def route_incoming_photos(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    caption: str,
    file_ids: list[str],
    mention_html: str,
) -> None:
    """הלוגיקה המשותפת לניתוב תמונה/אלבום תמונות שהתקבל: עריכה ממתינה / הוספה
    לקטלוג / חיפוש לפי תמונה. עובדת גם עבור תמונה בודדת מיידית וגם עבור אלבום
    שנאסף במאגר הזמני ומעובד אחרי דיליי קצר (ראה handle_photo_search)."""
    has_valid_caption = bool(parse_caption(caption or "").get("link"))

    # 0. יש עריכה ממתינה למשתמש הזה (מ-/edit) -> תמיד עדיפות ראשונה
    pending_product_id = PENDING_EDITS.pop(user_id, None)
    if pending_product_id is not None:
        await apply_edit(context, chat_id, pending_product_id, caption, file_ids)
        return

    # 1. הודעה בקבוצת ההעלאה המיועדת -> תמיד ניסיון הוספה (לא תלוי מי שלח)
    if is_catalog_group(chat_id):
        if has_valid_caption:
            await save_new_product(context, chat_id, caption, file_ids)
        else:
            await context.bot.send_message(chat_id=chat_id, text=ADD_FORMAT_HELP)
        return

    # 2. אדמין בצ'אט פרטי עם כיתוב תקין -> הוספה (השיטה הישנה, עדיין נתמכת)
    if is_admin(user_id) and has_valid_caption:
        await save_new_product(context, chat_id, caption, file_ids)
        return

    # 3. חיפוש לפי תמונה - משתמשים תמיד רק בתמונה הראשונה מהאלבום (אם נשלחו כמה)
    first_file_id = file_ids[0]

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
    """נקרא אחרי דיליי קצר מאז התמונה האחרונה של אלבום - מעבד את כל האלבום ביחד."""
    media_group_id = context.job.data
    buf = MEDIA_GROUP_BUFFERS.pop(media_group_id, None)
    if not buf:
        return
    await route_incoming_photos(
        context, buf["chat_id"], buf["user_id"], buf["caption"], buf["file_ids"], buf["mention_html"]
    )


async def handle_photo_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מטפל בתמונה נכנסת. אם היא חלק מאלבום (media_group_id), אוספים אותה
    במאגר זמני וממתינים רגע לשאר התמונות של אותו אלבום לפני עיבוד; אחרת
    מעבדים מיד (ראה route_incoming_photos לניתוב בפועל)."""
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    caption = message.caption or ""
    file_id = message.photo[-1].file_id
    mention_html = user_mention_html(update)

    media_group_id = message.media_group_id
    if media_group_id:
        buf = MEDIA_GROUP_BUFFERS.setdefault(
            media_group_id,
            {"file_ids": [], "caption": "", "chat_id": chat_id, "user_id": user_id, "mention_html": mention_html},
        )
        buf["file_ids"].append(file_id)
        if caption:
            buf["caption"] = caption

        # דוחים (debounce) את העיבוד בכל פעם שמגיעה עוד תמונה מאותו אלבום,
        # כדי לוודא שכל התמונות נאספו לפני שממשיכים.
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
            await route_incoming_photos(context, chat_id, user_id, buf["caption"], buf["file_ids"], mention_html)
            MEDIA_GROUP_BUFFERS.pop(media_group_id, None)
        return

    await route_incoming_photos(context, chat_id, user_id, caption, [file_id], mention_html)


# ---------------------------------------------------------------------------
# פקודות ניהול
# ---------------------------------------------------------------------------


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
        "עכשיו שלח תמונה חדשה עם כיתוב באותו פורמט (מותג/פרטים/מחיר/קישור). "
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
    app.add_handler(CommandHandler("edit", handle_edit))
    app.add_handler(CommandHandler("canceledit", handle_cancel_edit))
    app.add_handler(CommandHandler("delete", handle_delete))
    app.add_handler(CommandHandler("groupid", handle_groupid))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))
    app.add_handler(CallbackQueryHandler(handle_grid_callback))
    app.add_error_handler(handle_error)

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
