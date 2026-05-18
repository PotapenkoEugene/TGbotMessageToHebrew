from telegram import Message, Update
from telegram.ext import ContextTypes

from ..config import config
from ..lang import detect_lang, extract_hebrew_words, route
from ..storage import is_chat_enabled, save_bot_message, upsert_vocab_seen
from ..translator import translator


def _has_url_or_media(msg: Message) -> bool:
    if msg.photo or msg.document or msg.sticker or msg.animation or msg.video:
        return True
    if msg.entities:
        for e in msg.entities:
            if e.type in ("url", "text_link"):
                return True
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.from_user and msg.from_user.is_bot:
        return
    if msg.text.startswith('/'):
        return

    if not await is_chat_enabled(msg.chat_id):
        return

    # Always collect Hebrew words regardless of translation skip
    for word in extract_hebrew_words(msg.text):
        await upsert_vocab_seen(word)

    # Skip translation for media, links, single words, or long messages
    if _has_url_or_media(msg):
        return
    word_count = len(msg.text.split())
    if word_count <= 1 or word_count >= config.word_threshold:
        return

    src = detect_lang(msg.text)
    pair = route(src)
    if pair is None:
        return
    _, tgt = pair

    try:
        if tgt == "he":
            he, pron = await translator.translate_to_hebrew(msg.text)
            reply_text = f"{he}\n{pron}"
        else:
            reply_text = await translator.translate_to_russian(msg.text)
    except Exception as exc:
        context.application.logger.error('Translation error: %s', exc)
        return

    sent = await msg.reply_text(reply_text, do_quote=True)
    await save_bot_message(msg.chat_id, sent.message_id, msg.text, reply_text)
