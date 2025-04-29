import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from config import OPENAI_API_KEY
from .token_counter import get_token_count, calculate_cost
import asyncio


client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=30.0)


async def send_message_to_openai(
    model: str, 
    input_text: str, 
    messages: List[Dict[str, str]] = None,
    system_instruction: Optional[str] = None
) -> Dict[str, Any]:
    """Отправить сообщение в OpenAI API и получить ответ"""
    import logging
    
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
        logging.info(f"🔄 Отправка запроса к OpenAI API с моделью {model}")
        logging.info(f"🧾 Содержимое запроса: {api_messages[-1]['content'][:50]}...")
        logging.info(f"📊 Количество сообщений в истории: {len(api_messages)}")

        # Отправляем запрос в API
        try:
            logging.info(f"⏱️ Начало запроса к OpenAI API")
            response = await client.chat.completions.create(
                model=model,
                messages=api_messages,
                max_tokens=4000
            )
            logging.info(f"✅ Получен ответ от OpenAI API")
        except Exception as api_error:
            logging.error(f"⚠️ Ошибка при выполнении запроса к API: {str(api_error)}")
            raise  # Пробрасываем ошибку дальше для основного блока try/except
        
        # Получим ответ модели
        output_text = response.choices[0].message.content
        
        # Считаем токены
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        
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
        logging.error(f"❌ Ошибка при запросе к OpenAI API: {str(e)}")
        import traceback
        logging.error(f"Детали ошибки: {traceback.format_exc()}")
        
        return {
            "success": False,
            "error": str(e),
            "input_tokens": get_token_count(input_text, model),
            "output_tokens": 0,
            "input_cost": calculate_cost(get_token_count(input_text, model), model, True),
            "output_cost": 0,
            "total_cost": calculate_cost(get_token_count(input_text, model), model, True),
        }