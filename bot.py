"""
בוט טלגרם לקטלוג מוצרים - חיפוש לפי שם מותג, לפי תמונה, או דפדוף בקטלוג.

איך זה עובד:
- הוספת מוצרים אפשרית בשתי דרכים (אפשר להשתמש בשתיהן ביחד):
    1. קבוצת "העלאת מוצרים" נפרדת - כל תמונה עם כיתוב תקין שנשלחת בקבוצה
       שמוגדרת ב-CATALOG_GROUP_ID נכנסת אוטומטית לקטלוג.
    2. הודעה פרטית לבוט מאדמין (מי שה-ID שלו ב-ADMIN_IDS) - אותו פורמט כיתוב.
  פורמט הכיתוב:
    מותג: שם המותג והדגם
    פרטים: (כל שורה הופכת לנקודה משלה)
    מידה 40-45
    צבע שחור
    מחיר: 199 ש"ח
    קישור: https://...

- כל משתמש אחר (בצ'אט פרטי או בקבוצה אחרת, לא קבוצת ההעלאה) יכול:
    - לכתוב "חפש לי <מותג>" -> חיפוש מפורש. אם יש תוצאה אחת, מקבל תמונה+פרטים
      מלאים. אם יש כמה, מקבל רשת ממוספרת. בלי תוצאה - "לא מצאתי" + התראה לאדמין.
    - לכתוב שם מותג ישירות, בלי "חפש לי" (למשל סתם "נייקי") -> אותו חיפוש,
      אבל אם אין התאמה הבוט שותק (כדי לא להגיב "לא מצאתי" על כל הודעת צ'אט
      סתמית). ההתנהגות הזו כבויה בקבוצת ההעלאה עצמה.
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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    '❓ סרטון הסבר איך להזמין דרך קישור מוסתר - '
    '<a href="https://t.me/ZoLinkisrael/28">לחצו כאן לצפייה</a>\n\n'
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


def describe_user(update: Update) -> str:
    """מחרוזת קצרה לזיהוי מי שלח את הפנייה, לשימוש בהתראות לאדמין."""
    user = update.effective_user
    name = user.full_name or "משתמש"
    handle = f"@{user.username}" if user.username else f"id:{user.id}"
    return f"{name} ({handle})"


async def notify_admin_group(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """שולח הודעת התראה לקבוצת האדמין, אם היא מוגדרת (NOTIFY_GROUP_ID)."""
    if NOTIFY_GROUP_ID is None:
        return
    try:
        await context.bot.send_message(chat_id=NOTIFY_GROUP_ID, text=text, disable_web_page_preview=True)
    except Exception:
        logger.exception("Failed to send admin notification")


async def notify_admin_group_photo(
    context: ContextTypes.DEFAULT_TYPE, file_id: str, caption: str
) -> None:
    """מעביר תמונה שהתקבלה לחיפוש (בלי שנמצאה התאמה/כשזיהוי תמונות כבוי) לקבוצת האדמין."""
    if NOTIFY_GROUP_ID is None:
        return
    try:
        await context.bot.send_photo(chat_id=NOTIFY_GROUP_ID, photo=file_id, caption=caption)
    except Exception:
        logger.exception("Failed to send admin photo notification")


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
    lines.append(f'🔗 קישור מוסתר - <a href="{link}">לחצו כאן להזמנה</a>')

    return "\n".join(lines)


async def send_product_detail(bot, chat_id: int, item: dict) -> None:
    """שולח תמונת מוצר + פרטים מעוצבים + הפוטר הקבוע. זה מה שהמשתמש בפועל רואה."""
    header = format_product_header(item)
    full_caption = f"{header}\n\n{RESULT_FOOTER_HTML}"
    image_path = DATA_DIR / item["image_path"] if item.get("image_path") else None
    has_image = image_path and image_path.exists()

    if has_image and len(full_caption) <= 1024:
        # הכל נכנס לכיתוב אחד יחד עם התמונה - הכי נקי.
        with open(image_path, "rb") as f:
            await bot.send_photo(
                chat_id=chat_id, photo=f, caption=full_caption, parse_mode=ParseMode.HTML
            )
        return

    # הכיתוב ארוך מדי בשביל תמונה אחת (מגבלת טלגרם 1024 תווים) - שולחים בנפרד.
    if has_image:
        with open(image_path, "rb") as f:
            await bot.send_photo(chat_id=chat_id, photo=f, caption=header, parse_mode=ParseMode.HTML)
        await bot.send_message(chat_id=chat_id, text=RESULT_FOOTER_HTML, parse_mode=ParseMode.HTML)
    else:
        # למקרה נדיר שהקובץ לא נמצא בדיסק - לפחות שולחים את הטקסט המלא.
        await bot.send_message(
            chat_id=chat_id,
            text=full_caption,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
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

        image_path = DATA_DIR / item["image_path"] if item.get("image_path") else None
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


async def handle_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מוסיף מוצר לקטלוג מתמונה עם כיתוב. הקריאה לפונקציה הזו כבר מניחה שהמקור מורשה
    (קבוצת ההעלאה, או אדמין בצ'אט פרטי) - הבדיקה נעשית ב-handle_photo_search."""
    caption = update.message.caption or ""
    fields = parse_caption(caption)

    if not fields["link"]:
        await update.message.reply_text(ADD_FORMAT_HELP)
        return

    photo = update.message.photo[-1]  # הגודל הכי גדול
    file = await context.bot.get_file(photo.file_id)

    product_id = str(uuid.uuid4())[:8]
    image_path = IMAGES_DIR / f"{product_id}.jpg"
    await file.download_to_drive(str(image_path))

    phash = str(imagehash.phash(Image.open(image_path)))

    catalog = load_catalog()
    catalog.append(
        {
            "id": product_id,
            "brand": fields["brand"],
            "details": fields["details"],
            "price": fields["price"],
            "link": fields["link"],
            "image_path": str(image_path.relative_to(DATA_DIR)),
            "phash": phash,
        }
    )
    save_catalog(catalog)

    await update.message.reply_text(
        f"✅ נוסף לקטלוג!\nמזהה: {product_id}\nמותג: {fields['brand'] or '—'}"
    )


async def handle_edit_product(
    update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: str
) -> None:
    """מחליף שדות/תמונה של מוצר קיים. שדה ריק בכיתוב החדש משאיר את הערך הישן."""
    catalog = load_catalog()
    idx = next((i for i, p in enumerate(catalog) if p["id"] == product_id), None)
    if idx is None:
        await update.message.reply_text(
            f"המוצר {product_id} כבר לא קיים בקטלוג - העריכה בוטלה."
        )
        return

    item = catalog[idx]
    fields = parse_caption(update.message.caption or "")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_path = IMAGES_DIR / f"{product_id}.jpg"
    await file.download_to_drive(str(image_path))

    item["brand"] = fields["brand"] or item.get("brand", "")
    item["details"] = fields["details"] or item.get("details", [])
    item["price"] = fields["price"] or item.get("price", "")
    item["link"] = fields["link"] or item.get("link", "")
    item["phash"] = str(imagehash.phash(Image.open(image_path)))
    item["image_path"] = str(image_path.relative_to(DATA_DIR))

    catalog[idx] = item
    save_catalog(catalog)

    await update.message.reply_text(f"✏️ מוצר {product_id} עודכן!\nמותג: {item['brand'] or '—'}")


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
        query = explicit_match.group(1).strip().lower()
        results = [item for item in catalog if query in item.get("brand", "").lower()]
        if not results:
            await update.message.reply_text(f'לא מצאתי מוצר שמתאים ל"{query}" 🤷')
            await notify_admin_group(
                context, f"🔎 חיפוש ללא תוצאה\nמאת: {describe_user(update)}\nחיפש: \"{query}\""
            )
            return
        await start_browse(update, context, results)
        return

    # חיפוש משתמע - טקסט חופשי שלא מתחיל ב"חפש לי". לא פעיל בקבוצת ההעלאה
    # (שם טקסט חופשי הוא לרוב שיחה בין אדמינים, לא בקשת חיפוש של לקוח).
    if is_catalog_group(update.effective_chat.id):
        return

    query = text.strip().lower()
    results = [item for item in catalog if query in item.get("brand", "").lower()]
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


async def handle_photo_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מנתב תמונה נכנסת: עריכה ממתינה / הוספה לקטלוג / חיפוש לפי תמונה."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    caption = update.message.caption or ""
    has_valid_caption = bool(parse_caption(caption).get("link"))

    # 0. יש עריכה ממתינה למשתמש הזה (מ-/edit) -> תמיד עדיפות ראשונה
    pending_product_id = PENDING_EDITS.pop(user.id, None)
    if pending_product_id is not None:
        await handle_edit_product(update, context, pending_product_id)
        return

    # 1. הודעה בקבוצת ההעלאה המיועדת -> תמיד ניסיון הוספה (לא תלוי מי שלח)
    if is_catalog_group(chat_id):
        if has_valid_caption:
            await handle_add_product(update, context)
        else:
            await update.message.reply_text(ADD_FORMAT_HELP)
        return

    # 2. אדמין בצ'אט פרטי עם כיתוב תקין -> הוספה (השיטה הישנה, עדיין נתמכת)
    if is_admin(user.id) and has_valid_caption:
        await handle_add_product(update, context)
        return

    # 3. חיפוש לפי תמונה - אם כבוי (ENABLE_IMAGE_SEARCH=false), לא מנסים להתאים
    # בכלל: מודיעים למשתמש ומעבירים את התמונה לקבוצת האדמין לטיפול ידני.
    photo = update.message.photo[-1]

    if not ENABLE_IMAGE_SEARCH:
        await update.message.reply_text(
            "🔍 חיפוש לפי תמונה כרגע לא זמין.\n"
            'תכתבו לי מה אתם מחפשים (למשל "חפש לי נייקי") ואשמח לעזור - '
            "או שנחזור אליכם ישירות בקרוב 🙏"
        )
        await notify_admin_group_photo(
            context,
            photo.file_id,
            f"📸 בקשת חיפוש לפי תמונה (זיהוי תמונות כבוי)\nמאת: {describe_user(update)}",
        )
        return

    catalog = load_catalog()
    if not catalog:
        await update.message.reply_text("הקטלוג עדיין ריק, אין מה לחפש בו כרגע.")
        return

    file = await context.bot.get_file(photo.file_id)

    tmp_path = IMAGES_DIR / f"_search_{uuid.uuid4().hex[:8]}.jpg"
    await file.download_to_drive(str(tmp_path))

    try:
        query_hash = imagehash.phash(Image.open(tmp_path))

        best_match = None
        best_distance = None
        for item in catalog:
            item_hash = imagehash.hex_to_hash(item["phash"])
            distance = query_hash - item_hash
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = item

        if best_match and best_distance <= IMAGE_MATCH_THRESHOLD:
            await send_product_detail(context.bot, chat_id, best_match)
        else:
            await update.message.reply_text("לא הצלחתי למצוא התאמה מספיק טובה לתמונה הזו 🤔")
            await notify_admin_group_photo(
                context, photo.file_id, f"🔎 חיפוש לפי תמונה ללא תוצאה\nמאת: {describe_user(update)}"
            )
    finally:
        tmp_path.unlink(missing_ok=True)


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
    image_path = DATA_DIR / removed["image_path"]
    image_path.unlink(missing_ok=True)

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
