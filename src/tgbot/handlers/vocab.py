import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..lang import detect_lang
from ..storage import add_vocab_word


async def handle_vocab_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """DM handler: Hebrew text → save raw token to vocab (no LLM)."""
    msg = update.message
    if not msg or not msg.text or msg.text.startswith("/"):
        return
    if update.effective_chat.type != "private":
        return
    if detect_lang(msg.text) != "he":
        await msg.reply_text(
            "Send me Hebrew words to save them. "
            "Or use /list to see saved words, /practice to quiz yourself."
        )
        return

    inserted = await add_vocab_word(msg.text, "", "")
    if inserted:
        await msg.reply_text(f"Saved: {msg.text}")
    else:
        await msg.reply_text(f"Already saved: {msg.text}")
