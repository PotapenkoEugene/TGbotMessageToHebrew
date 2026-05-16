from telegram import Update
from telegram.ext import ContextTypes

from ..lang import detect_lang
from ..storage import add_vocab_word
from ..translator import translator


async def handle_vocab_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """DM handler: Hebrew text → save to vocab with translation + transliteration."""
    msg = update.message
    if not msg or not msg.text or msg.text.startswith("/"):
        return
    if update.effective_chat.type != "private":
        return
    if detect_lang(msg.text) != "he":
        # Not Hebrew — ignore in DM (translate handler won't run in DM when this runs)
        await msg.reply_text(
            "Send me Hebrew words to save them. "
            "Or use /list to see saved words, /practice to quiz yourself."
        )
        return

    await msg.reply_text("Looking up...")
    try:
        info = await translator.translate_and_transliterate(msg.text)
    except Exception as exc:
        context.application.logger.error("Vocab lookup error: %s", exc)
        await msg.reply_text("Translation failed. Check Ollama connection.")
        return

    translation = info.get("translation", "")
    transliteration = info.get("transliteration", "")

    inserted = await add_vocab_word(
        update.effective_user.id,
        msg.text,
        translation,
        transliteration,
    )

    if inserted:
        await msg.reply_text(
            f"Saved!\n{msg.text} — {translation} ({transliteration})"
        )
    else:
        await msg.reply_text(
            f"Already in your vocabulary:\n{msg.text} — {translation} ({transliteration})"
        )
