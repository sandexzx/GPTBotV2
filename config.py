import os
from typing import Dict, List
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv(override=True)  # Принудительно перезагружаем переменные окружения

# Константы бота
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Максимальное количество токенов в ответе модели
DEFAULT_MAX_TOKENS = 4000

# Админы бота (только они могут использовать)
ADMIN_IDS = [165879072, 5237388776, 415595998]  # Замени своими ID

# Модели и цены (за миллион токенов)
MODELS: Dict[str, Dict[str, float]] = {
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# Курс конвертации
USD_TO_RUB = 107

# База данных
DB_URL = "sqlite:///openai_bot.db"  # SQLite для начала