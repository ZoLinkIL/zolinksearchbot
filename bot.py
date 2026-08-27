"""
בוט טלגרם לקטלוג מוצרים - חיפוש לפי שם מותג או לפי תמונה.

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
    - לכתוב "חפש לי <מותג>" -> הבוט מחפש התאמה טקסטואלית בקטלוג.
    - לשלוח תמונה -> הבוט מחשב טביעת אצבע ויזואלית (perceptual hash)
      ומשווה לתמונות השמורות, ומחזיר את ההתאמה הכי קרובה אם יש כזו.
  התוצאה חוזרת מעוצבת (⭐️ מותג, ✅ פרטים, 🔥 מחיר, 🔗 קישור מוסתר) + פוטר קבוע.

- /list -> אדמין בלבד: מציג את כל המוצרים בקטלוג (מזהה, מותג, מחיר, קישור).
- /edit <id> -> אדמין בלבד: מתחיל עריכת מוצר קיים - שולחים תמונה+כיתוב חדשים
  (כמו בהוספה) והם מחליפים את הישן. שדה שמשאירים ריק/לא כתוב נשאר כמו שהיה.
- /canceledit -> מבטל עריכה שהתחילה עם /edit.
- /delete <id> -> אדמין בלבד: מוחק מוצר מהקטלוג.
- /groupid -> מציג את מזהה הקבוצה הנוכחית (שימושי כדי להגדיר CATALOG_GROUP_ID).

הערה לגבי אמינות: כל שגיאה בלתי צפויה נתפסת ע"י error handler גלובלי -
המשתמש תמיד יקבל הודעה שמשהו השתבש (במקום שקט מוחלט), והשגיאה המלאה
נכתבת ללוגים של השרת.
"""

import html
import json
import logging
import os
import re
import uuid
from pathlib import Path

import imagehash
from PIL import Image
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
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
IMAGES_DIR = BASE_DIR / "catalog_images"
CATALOG_FILE = BASE_DIR / "catalog.json"

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

# סף דמיון לתמונות. ככל שההפרש (hamming distance) קטן יותר - התמונות דומות יותר.
# 0 = זהה לגמרי. בערך עד 10 עדיין נחשב "אותו מוצר" בפועל (זווית/תאורה שונה קלות).
IMAGE_MATCH_THRESHOLD = 10

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
    'לחיפוש - תכתוב "חפש לי <מותג>" או פשוט תשלח תמונה.'
)


def format_product_message(item: dict) -> str:
    """בונה את הודעת התוצאה המעוצבת: כותרת + פרטים + מחיר + קישור מוסתר + פוטר קבוע."""
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

    lines.append("")
    lines.append(RESULT_FOOTER_HTML)

    return "\n".join(lines)


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
            "image_path": str(image_path.relative_to(BASE_DIR)),
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
    item["image_path"] = str(image_path.relative_to(BASE_DIR))

    catalog[idx] = item
    save_catalog(catalog)

    await update.message.reply_text(f"✏️ מוצר {product_id} עודכן!\nמותג: {item['brand'] or '—'}")


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בהודעת טקסט - מזהה 'חפש לי <משהו>' ומחפש בקטלוג."""
    text = update.message.text or ""
    match = re.match(r"^\s*חפש\s*לי\s+(.+)", text)
    if not match:
        return

    query = match.group(1).strip().lower()
    catalog = load_catalog()

    results = [item for item in catalog if query in item.get("brand", "").lower()]

    if not results:
        await update.message.reply_text(f'לא מצאתי מוצר שמתאים ל"{query}" 🤷')
        return

    for item in results[:5]:
        await update.message.reply_text(
            format_product_message(item),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def handle_photo_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """מנתב תמונה נכנסת: עריכה ממתינה / הוספה לקטלוג / חיפוש."""
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

    # 3. כל מקרה אחר -> חיפוש לפי התמונה
    catalog = load_catalog()
    if not catalog:
        await update.message.reply_text("הקטלוג עדיין ריק, אין מה לחפש בו כרגע.")
        return

    photo = update.message.photo[-1]
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
            await update.message.reply_text(
                format_product_message(best_match),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        else:
            await update.message.reply_text("לא הצלחתי למצוא התאמה מספיק טובה לתמונה הזו 🤔")
    finally:
        tmp_path.unlink(missing_ok=True)


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
    image_path = BASE_DIR / removed["image_path"]
    image_path.unlink(missing_ok=True)

    save_catalog(new_catalog)
    await update.message.reply_text(f"🗑️ נמחק מוצר {product_id}")


async def handle_groupid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await update.message.reply_text(f"מזהה הצ'אט הזה: {chat.id}")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "היי! 👋\n"
        'כדי לחפש מוצר - תכתוב "חפש לי <מותג>" או פשוט תשלח תמונה של המוצר.'
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
    app.add_handler(CommandHandler("list", handle_list))
    app.add_handler(CommandHandler("edit", handle_edit))
    app.add_handler(CommandHandler("canceledit", handle_cancel_edit))
    app.add_handler(CommandHandler("delete", handle_delete))
    app.add_handler(CommandHandler("groupid", handle_groupid))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))
    app.add_error_handler(handle_error)

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
