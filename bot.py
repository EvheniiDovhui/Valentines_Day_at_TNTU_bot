import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from database import init_db
from handlers import common, valentines, chat, games_handlers

# Завантаження налаштувань
load_dotenv(dotenv_path="api.env")
API_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db() # Створення таблиць
    
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()

    # Підключаємо всі роутери
    dp.include_router(common.router)
    dp.include_router(valentines.router)
    dp.include_router(chat.router)
    dp.include_router(games_handlers.router)

    print("🚀 Амур ТНТУ запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())