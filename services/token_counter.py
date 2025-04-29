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
    
    # Текущий запрос/ответ
    cost_input_usd = calculate_cost(tokens_input, model, True)
    cost_output_usd = calculate_cost(tokens_output, model, False)
    
    cost_input_rub = cost_input_usd * USD_TO_RUB
    cost_output_rub = cost_output_usd * USD_TO_RUB
    
    # Текущий чат (всего)
    total_cost_input_usd = calculate_cost(total_input, model, True)
    total_cost_output_usd = calculate_cost(total_output, model, False)
    
    total_cost_input_rub = total_cost_input_usd * USD_TO_RUB
    total_cost_output_rub = total_cost_output_usd * USD_TO_RUB
    
    stats = (
        f"\nТекущий запрос/ответ: {tokens_input} (${cost_input_usd:.6f}/{cost_input_rub:.2f}₽)/"
        f"{tokens_output} (${cost_output_usd:.6f}/{cost_output_rub:.2f}₽) токенов.\n"
        f"Текущий чат запрос/ответ: {total_input} (${total_cost_input_usd:.6f}/{total_cost_input_rub:.2f}₽)/"
        f"{total_output} (${total_cost_output_usd:.6f}/{total_cost_output_rub:.2f}₽) токенов."
    )
    
    return stats