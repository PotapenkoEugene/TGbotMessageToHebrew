import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .storage import get_practice_word, get_distractors, update_practice_result, get_vocab_words

_CALLBACK_PREFIX = "quiz:"


async def cmd_practice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    words = await get_vocab_words(user_id)

    if len(words) < 2:
        await update.message.reply_text(
            "Need at least 2 saved words to practice. "
            "Send Hebrew words in DM to build your vocabulary."
        )
        return

    word = await get_practice_word(user_id)
    if word is None:
        await update.message.reply_text("No words to practice yet.")
        return

    distractors = await get_distractors(user_id, exclude_id=word.id, count=3)
    if not distractors:
        await update.message.reply_text("Need more words for multiple-choice. Keep adding!")
        return

    options = [word.translation] + [d.translation for d in distractors]
    random.shuffle(options)

    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"{_CALLBACK_PREFIX}{word.id}:{opt}:{word.translation}")]
        for opt in options
    ]
    await update.message.reply_text(
        f"What does this mean?\n\n{word.hebrew}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith(_CALLBACK_PREFIX):
        return

    _, word_id_str, chosen, correct_answer = data.split(":", 3)
    word_id = int(word_id_str)
    correct = chosen == correct_answer

    await update_practice_result(word_id, correct)

    if correct:
        await query.edit_message_text(f"Correct! {correct_answer}")
    else:
        await query.edit_message_text(f"Wrong. Answer: {correct_answer}")
