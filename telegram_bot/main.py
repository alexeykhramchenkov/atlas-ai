

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Allows running the file directly:
# PYTHONPATH=. .venv/bin/python telegram_bot/main.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.logger import logger
from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from telegram_bot.handlers import (
    handle_integration_callback,
    handle_message,
    start,
)


async def setup_bot_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Главное меню"),
        ]
    )


def get_bot_token() -> str:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env or export it before running the bot."
        )

    return token


def main() -> None:
    token = get_bot_token()

    app = Application.builder().token(token).post_init(setup_bot_commands).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_integration_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
