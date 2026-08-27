"""
בוט טלגרם לקטלוג מוצרים - חיפוש לפי שם מותג או לפי תמונה.

איך זה עובד:
- אדמין (המשתמש שה-ID שלו מוגדר ב-ADMIN_IDS) שולח תמונה עם כיתוב בפורמט:
    מותג: שם המותג
    שם: שם המוצר (אופציונלי)
    קישור: https://...
  והבוט מוסיף את זה לקטלוג.

- כל משתמש אחר יכול:
    - לכתוב "חפש לי <מותג>" -> הבוט מחפש התאמה טקסטואלית בקטלוג.
    - לשלוח תמונה -> הבוט מחשב טביעת אצבע ויזואלית (perceptual hash)
      ומשווה לתמונות השמורות, ומחזיר את ההתאמה הכי קרובה אם יש כזו.

- /list -> אדמין בלבד: מציג את כל המוצרים בקטלוג.
- /delete <id> -> אדמין בלבד: מוחק מוצר מהקטלוג.
"""

import json
import logging
import os
import re
import uuid
from pathlib import Path

import imagehash
from PIL import Image
from telegram import Update
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

# סף דמיון לתמונות. ככל שההפרש (hamming distance) קטן יותר - התמונות דומות יותר.
# 0 = זהה לגמרי. בערך עד 10 עדיין נחשב "אותו מוצר" בפועל (זווית/תאורה שונה קלות).
IMAGE_MATCH_THRESHOLD = 10

IMAGES_DIR.mkdir(parents=True, exist_ok=True)


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


def parse_caption(caption: str) -> dict:
    """מפרסר כיתוב בפורמט 'מותג: X\nשם: Y\nקישור: Z' לדיקט."""
    fields = {"brand": "", "name": "", "link": ""}
    patterns = {
        "brand": r"מותג\s*:\s*(.+)",
        "name": r"שם\s*:\s*(.+)",
        "link": r"קישור\s*:\s*(\S+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, caption)
        if match:
            fields[key] = match.group(1).strip()
    return fields


async def handle_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """אדמין שולח תמונה עם כיתוב -> מוסיף מוצר לקטלוג."""
    user = update.effective_user
    if not is_admin(user.id):
        return  # שקט - לא אדמין, ננסה לזהות תמונה בהמשך ב-handle_photo_search במקום

    caption = update.message.caption or ""
    fields = parse_caption(caption)

    if not fields["link"]:
        await update.message.reply_text(
            "כדי להוסיף מוצר, שלח תמונה עם כיתוב בפורמט:\n\n"
            "מותג: שם המותג\n"
            "שם: שם המוצר (אופציונלי)\n"
            "קישור: https://...\n\n"
            'לחיפוש - תכתוב "חפש לי <מותג>" או פשוט תשלח תמונה.'
        )
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
            "name": fields["name"],
            "link": fields["link"],
            "image_path": str(image_path.relative_to(BASE_DIR)),
            "phash": phash,
        }
    )
    save_catalog(catalog)

    await update.message.reply_text(
        f"✅ נוסף לקטלוג!\nמזהה: {product_id}\nמותג: {fields['brand'] or '—'}\nשם: {fields['name'] or '—'}"
    )


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בהודעת טקסט - מזהה 'חפש לי <משהו>' ומחפש בקטלוג."""
    text = update.message.text or ""
    match = re.match(r"^\s*חפש\s*לי\s+(.+)", text)
    if not match:
        return

    query = match.group(1).strip().lower()
    catalog = load_catalog()

    results = [
        item
        for item in catalog
        if query in item.get("brand", "").lower() or query in item.get("name", "").lower()
    ]

    if not results:
        await update.message.reply_text(f'לא מצאתי מוצר שמתאים ל"{query}" 🤷')
        return

    for item in results[:5]:
        caption = f"{item.get('brand', '')} {item.get('name', '')}".strip()
        await update.message.reply_text(f"{caption}\n{item['link']}")


async def handle_photo_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """אם ההודעה עם תמונה היא לא של אדמין שמוסיף מוצר - מנסה למצוא התאמה בקטלוג."""
    user = update.effective_user
    caption = update.message.caption or ""

    # אם זה אדמין ששלח כיתוב תקין - זו הוספת מוצר, לא חיפוש
    if is_admin(user.id) and parse_caption(caption).get("link"):
        await handle_add_product(update, context)
        return

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
            caption_out = f"{best_match.get('brand', '')} {best_match.get('name', '')}".strip()
            await update.message.reply_text(f"מצאתי! ✅\n{caption_out}\n{best_match['link']}")
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
    lines = [
        f"{item['id']} | {item.get('brand', '—')} | {item.get('name', '—')}" for item in catalog
    ]
    # טלגרם מגביל אורך הודעה - נחלק לצ'אנקים אם צריך
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await update.message.reply_text(text[i : i + 3500])


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


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "היי! 👋\n"
        'כדי לחפש מוצר - תכתוב "חפש לי <מותג>" או פשוט תשלח תמונה של המוצר.'
    )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("חסר BOT_TOKEN - הגדר משתנה סביבה BOT_TOKEN עם הטוקן מ-BotFather")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("list", handle_list))
    app.add_handler(CommandHandler("delete", handle_delete))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
