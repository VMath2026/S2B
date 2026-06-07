import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.commands import get_bot_commands
from app.bot.handlers import router
from app.config import settings


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Add Telegram bot token to .env")

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
