import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
load_dotenv()  # Загружаем переменные окружения из .env
from config import OPENAI_API_KEY, DEFAULT_MAX_TOKENS
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не установлен. Убедитесь, что файл .env создан и содержит правильный API ключ.")
from .token_counter import get_token_count, calculate_cost
import asyncio

import logging

logger = logging.getLogger('telegram_bot')

async def send_message_to_openai(
    model: str, 
    input_text: str, 
    messages: List[Dict[str, str]] = None,
    system_instruction: Optional[str] = None,
    max_tokens: Optional[int] = None,
    stream: bool = False
) -> Dict[str, Any]:
    """Отправить сообщение в OpenAI API и получить ответ"""

    # Инициализируем клиент здесь, чтобы быть уверенными, что переменные окружения загружены
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=30.0)

    # Если max_tokens не указан, используем значение по умолчанию из конфига
    if max_tokens is None:
        max_tokens = DEFAULT_MAX_TOKENS
    
    # Если нет истории сообщений, создаем новую
    if messages is None:
        messages = []
    
    # Формируем запрос в новом формате
    api_messages = []
    
    # Если есть системная инструкция, добавляем её как инструкцию для модели
    if system_instruction:
        api_messages.append({
            "role": "system",
            "content": system_instruction
        })
    
    # Добавляем историю сообщений
    for message in messages:
        api_messages.append(message)
    
    # Добавляем новый запрос пользователя, если его нет в истории
    if not messages or messages[-1]["role"] != "user" or messages[-1]["content"] != input_text:
        api_messages.append({"role": "user", "content": input_text})
    
    try:
        start_time = datetime.now()
        logger.info(f"🔄 Отправка запроса к OpenAI API с моделью {model} в {start_time.strftime('%H:%M:%S')}")
        logger.info(f"🧾 Содержимое запроса: {api_messages[-1]['content'][:50]}...")
        logger.info(f"📊 Количество сообщений в истории: {len(api_messages)}")
        if system_instruction:
            logger.info(f"🔮 Используется системная инструкция (промпт): {system_instruction[:50]}...")

        # Оценка токенов перед запросом
        from .token_counter import get_token_count
        estimated_input_tokens = 0
        for msg in api_messages:
            estimated_input_tokens += get_token_count(msg["content"], model)
        logger.info(f"📊 Примерная оценка токенов в запросе: {estimated_input_tokens}")

        # Отправляем запрос в API
        try:
            logger.info(f"⏱️ Начало запроса к OpenAI API")
            response = await client.chat.completions.create(
                model=model,
                messages=api_messages,
                max_tokens=max_tokens,
                stream=stream
            )
            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            logger.info(f"✅ Получен ответ от OpenAI API за {elapsed:.2f} сек.")
        except Exception as api_error:
            logger.error(f"⚠️ Ошибка при выполнении запроса к API: {str(api_error)}")
            raise  # Пробрасываем ошибку дальше для основного блока try/except

        if stream:
            # Для стриминга возвращаем сам стрим
            return {
                "success": True,
                "stream": response,
                "input_tokens": estimated_input_tokens
            }
        else:
            # Для обычного ответа возвращаем полный текст
            output_text = response.choices[0].message.content
            output_tokens = response.usage.completion_tokens
            output_cost = calculate_cost(output_tokens, model, is_input=False)
            
            return {
                "success": True,
                "output_text": output_text,
                "output_tokens": output_tokens,
                "output_cost": output_cost,
                "input_tokens": estimated_input_tokens
            }
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке запроса: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }