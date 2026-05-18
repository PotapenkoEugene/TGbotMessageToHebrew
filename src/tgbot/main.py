import asyncio
import logging

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from .config import config
from .storage import init_db
from .translator import translator
from .handlers.translate import handle_message
from .handlers.explain import handle_explain
from .handlers.commands import cmd_start, cmd_help, cmd_on, cmd_off, cmd_list, cmd_stats
from .handlers.vocab import handle_vocab_dm
from .practice import cmd_practice, handle_quiz_callback

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app) -> None:
    await init_db()
    await translator.start()
    logger.info("DB initialized, translator ready (model: %s)", config.claude_model)


async def post_shutdown(app) -> None:
    await translator.stop()


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("practice", cmd_practice))

    # Reply-to-bot explain: must come before translate/vocab handlers
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY & ~filters.COMMAND,
            handle_explain,
        )
    )

    # DM vocab handler: Hebrew text in private chat (non-reply)
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.REPLY & ~filters.COMMAND,
            handle_vocab_dm,
        )
    )

    # Group/channel message translator (non-command, non-reply text)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.REPLY & ~filters.ChatType.PRIVATE,
            handle_message,
        )
    )

    # Quiz answer callbacks
    app.add_handler(CallbackQueryHandler(handle_quiz_callback, pattern=r"^quiz:"))

    logger.info("Starting bot (model: %s)", config.claude_model)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
