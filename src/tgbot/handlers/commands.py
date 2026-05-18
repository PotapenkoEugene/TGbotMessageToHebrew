from telegram import Update, ChatMember
from telegram.ext import ContextTypes

from ..storage import set_chat_enabled, get_vocab_words


async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return False
    if chat.type == "private":
        return True
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! I translate messages in this chat:\n"
        "• Russian/English → Hebrew\n"
        "• Hebrew → Russian\n\n"
        "Commands:\n"
        "/on — enable translation\n"
        "/off — disable translation\n"
        "/list — show your saved Hebrew words\n"
        "/practice — quiz yourself\n"
        "/stats — see your practice stats\n"
        "/help — this message\n\n"
        "Send me a Hebrew word in DM to save it to your vocabulary."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update, context):
        await update.message.reply_text("Only admins can change this setting.")
        return
    await set_chat_enabled(update.effective_chat.id, True)
    await update.message.reply_text("Translation enabled.")


async def cmd_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update, context):
        await update.message.reply_text("Only admins can change this setting.")
        return
    await set_chat_enabled(update.effective_chat.id, False)
    await update.message.reply_text("Translation disabled.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    words = await get_vocab_words()
    if not words:
        await update.message.reply_text(
            "No saved words yet. Send me Hebrew words in DM to add them."
        )
        return
    lines = [
        f"{w.hebrew} — {w.translation} ({w.transliteration}) ×{w.frequency}"
        for w in words
    ]
    text = f"Words ({len(words)}):\n\n" + "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n…"
    await update.message.reply_text(text)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    words = await get_vocab_words()
    if not words:
        await update.message.reply_text("No words yet.")
        return
    total = len(words)
    correct = sum(w.correct_count for w in words)
    wrong = sum(w.wrong_count for w in words)
    practiced = sum(1 for w in words if w.last_practiced)
    await update.message.reply_text(
        f"Vocabulary stats:\n"
        f"Total words: {total}\n"
        f"Practiced: {practiced}\n"
        f"Correct answers: {correct}\n"
        f"Wrong answers: {wrong}"
    )
