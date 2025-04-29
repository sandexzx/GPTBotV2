import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
load_dotenv()  # Загружаем переменные окружения из .env
from config import OPENAI_API_KEY
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
    system_instruction: Optional[str] = None
) -> Dict[str, Any]:
    """Отправить сообщение в OpenAI API и получить ответ"""

    # Инициализируем клиент здесь, чтобы быть уверенными, что переменные окружения загружены
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=30.0)
    
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
        logger.info(f"🔄 Отправка запроса к OpenAI API с моделью {model}")
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
                max_tokens=4000
            )
            logger.info(f"✅ Получен ответ от OpenAI API")
        except Exception as api_error:
            logger.error(f"⚠️ Ошибка при выполнении запроса к API: {str(api_error)}")
            raise  # Пробрасываем ошибку дальше для основного блока try/except
        
        # Получим ответ модели
        output_text = response.choices[0].message.content
        
        # Считаем токены
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        # Логируем точное количество токенов для отладки
        logger.info(f"📊 Точное количество токенов запроса: {input_tokens}")
        logger.info(f"📊 Точное количество токенов ответа: {output_tokens}")
       
        
        # Считаем стоимость
        input_cost = calculate_cost(input_tokens, model, True)
        output_cost = calculate_cost(output_tokens, model, False)
        
        return {
            "success": True,
            "output_text": output_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": input_cost + output_cost,
        }
    
    except Exception as e:
        logger.error(f"❌ Ошибка при запросе к OpenAI API: {str(e)}")
        import traceback
        logger.error(f"Детали ошибки: {traceback.format_exc()}")

        # Оценка токенов при ошибке
        estimated_tokens = 0
        for msg in api_messages:
            estimated_tokens += get_token_count(msg["content"], model)
         
        
        return {
            "success": False,
            "error": str(e),
            "input_tokens": estimated_tokens,
            "output_tokens": 0,
            "input_cost": calculate_cost(estimated_tokens, model, True),
            "output_cost": 0,
            "total_cost": calculate_cost(estimated_tokens, model, True),
        }