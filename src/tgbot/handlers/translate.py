from telegram import Update
from telegram.ext import ContextTypes

from ..lang import detect_lang, route
from ..storage import is_chat_enabled
from ..translator import translator


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return
    # Ignore bots and commands
    if msg.from_user and msg.from_user.is_bot:
        return
    if msg.text.startswith('/'):
        return

    chat_id = msg.chat_id
    if not await is_chat_enabled(chat_id):
        return

    src_lang = detect_lang(msg.text)
    pair = route(src_lang)
    if pair is None:
        return

    src, tgt = pair
    try:
        translation = await translator.translate(msg.text, src, tgt)
    except Exception as exc:
        context.application.logger.error('Translation error: %s', exc)
        return

    await msg.reply_text(translation, do_quote=True)
