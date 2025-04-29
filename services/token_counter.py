import tiktoken
from typing import Dict, Any, List, Union

from config import MODELS, USD_TO_RUB


def get_token_count(text: str, model: str = "gpt-4.1") -> int:
    """Подсчёт токенов в тексте"""
    try:
        encoder = tiktoken.encoding_for_model(model)
        tokens = len(encoder.encode(text))
        return tokens
    except Exception:
        # Если модель не поддерживается tiktoken, используем приблизительный подсчёт
        return int(len(text) / 4)  # В среднем 1 токен ≈ 4 символа


def calculate_cost(tokens: int, model: str, is_input: bool = True) -> float:
    """Рассчитать стоимость токенов в USD"""
    rate_key = "input" if is_input else "output"
    rate = MODELS.get(model, {}).get(rate_key, 0)
    
    # Цена за миллион токенов -> цена за токен
    cost = (rate / 1_000_000) * tokens
    return cost


def format_stats(tokens_input: int, tokens_output: int, 
               model: str, total_input: int = 0, total_output: int = 0) -> str:
    """Форматировать статистику для отображения пользователю"""
    
    # Расчет стоимости в рублях (без долларов)
    cost_input_usd = calculate_cost(tokens_input, model, True)
    cost_output_usd = calculate_cost(tokens_output, model, False)
    
    cost_input_rub = cost_input_usd * USD_TO_RUB
    cost_output_rub = cost_output_usd * USD_TO_RUB
    total_cost_rub = cost_input_rub + cost_output_rub
    
    # Стоимость всего чата в рублях
    total_cost_input_usd = calculate_cost(total_input, model, True)
    total_cost_output_usd = calculate_cost(total_output, model, False)
    
    total_cost_input_rub = total_cost_input_usd * USD_TO_RUB
    total_cost_output_rub = total_cost_output_usd * USD_TO_RUB
    chat_total_cost_rub = total_cost_input_rub + total_cost_output_rub
    
    stats = (
        f"\n\n📊 Текущий запрос: {tokens_input + tokens_output} токенов ({tokens_input}⤵️/{tokens_output}⤴️) • {total_cost_rub:.2f}₽"
        f"\n💰 Весь чат: {total_input + total_output} токенов • {chat_total_cost_rub:.2f}₽"
    )
    
    return stats