import asyncio
import logging

from aiohttp import ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, TELEGRAM_REQUEST_TIMEOUT_SEC
from db import SQLiteStorage, init_db
from handlers import router

logging.basicConfig(level=logging.INFO)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Create .env from .env.example and fill secrets.")
    await init_db()

    tg_timeout = ClientTimeout(
        total=TELEGRAM_REQUEST_TIMEOUT_SEC,
        connect=60,
        sock_read=TELEGRAM_REQUEST_TIMEOUT_SEC,
    )
    session = AiohttpSession(timeout=tg_timeout)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=SQLiteStorage())

    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())