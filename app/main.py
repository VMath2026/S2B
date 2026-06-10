import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.commands import get_bot_commands
from app.bot.handlers import router
from app.config import settings
from app.db.init_db import ensure_database_schema
from app.db.seed import seed_db


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Add Telegram bot token to .env")

    if settings.init_database_on_start:
        ensure_database_schema()
        if settings.seed_database_on_start:
            seed_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(router)

    await bot.set_my_commands(get_bot_commands())

    print("Bot started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
