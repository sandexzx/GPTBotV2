import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from database.models import create_tables

from config import TOKEN, OPENAI_API_KEY
from handlers import setup_routers

import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def main():
    """Основная функция запуска бота"""
    # Проверка наличия токенов
    if not TOKEN:
        logging.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения BOT_TOKEN не установлена")
        return
    
    if not OPENAI_API_KEY:
        logging.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения OPENAI_API_KEY не установлена")
        return

    # Инициализация бота и диспетчера
    from aiogram.client.default import DefaultBotProperties
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключаем роутеры
    dp.include_router(setup_routers())
    
    # Создаем таблицы в БД (если они не существуют)
    create_tables()
    
    # Запускаем бота
    logging.info("🚀 Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())