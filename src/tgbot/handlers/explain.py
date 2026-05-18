from telegram import Update
from telegram.ext import ContextTypes

from ..storage import get_bot_message, save_problem
from ..translator import translator


async def handle_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return

    reply = msg.reply_to_message
    if not reply or not reply.from_user:
        return
    if reply.from_user.id != context.bot.id:
        return

    stored = await get_bot_message(msg.chat_id, reply.message_id)
    if not stored:
        return

    original, translation = stored

    try:
        explanation = await translator.explain(original, translation, msg.text)
    except Exception as exc:
        context.application.logger.error('Explain error: %s', exc)
        return

    await msg.reply_text(explanation, do_quote=True)
    await save_problem(
        msg.chat_id,
        msg.from_user.id,
        original,
        translation,
        msg.text,
        explanation,
    )
