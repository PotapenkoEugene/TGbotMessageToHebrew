import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..format import build_explain_table, build_grammar_reply
from ..lang import detect_lang
from ..storage import get_bot_message, save_problem
from ..translator import translator

log = logging.getLogger(__name__)


async def handle_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return

    trigger = msg.text.strip().rstrip('!.?…').strip().lower()
    if trigger != 'объясни':
        return

    reply = msg.reply_to_message
    if not reply:
        return

    # Route: bot translation → per-word explain; Hebrew user message → grammar check.
    stored = await get_bot_message(msg.chat_id, reply.message_id)
    if stored:
        original, translation = stored
        try:
            payload = await translator.explain(original, translation)
            rendered = build_explain_table(payload)
        except Exception as exc:
            log.error('Explain error: %s', exc)
            return
        await msg.reply_text(rendered, parse_mode='HTML', do_quote=True)
        await save_problem(
            msg.chat_id,
            msg.from_user.id,
            original,
            translation,
            msg.text,
            rendered,
        )
    elif reply.text and detect_lang(reply.text) == 'he':
        try:
            payload = await translator.grammar_check(reply.text)
            rendered = build_grammar_reply(payload)
        except Exception as exc:
            log.error('Grammar check error: %s', exc)
            return
        await msg.reply_text(rendered, parse_mode='HTML', do_quote=True)
    # else: not a bot message and not Hebrew — ignore silently
