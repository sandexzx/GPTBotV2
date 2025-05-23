from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict

from config import MODELS, USD_TO_RUB


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Начать чат с AI", callback_data="new_chat")],
            [InlineKeyboardButton(text="📄 Мои промпты", callback_data="prompts")],
            [InlineKeyboardButton(text="📂 Загрузить промпт из файла", callback_data="load_prompt_file")],
            [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
        ]
    )
    return keyboard


def models_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора модели"""
    buttons = []
    
    for model_name, prices in MODELS.items():
        input_price = prices["input"]
        output_price = prices["output"]
        input_price_rub = input_price * USD_TO_RUB
        output_price_rub = output_price * USD_TO_RUB
        btn_text = f"{model_name} • ⤵️ {input_price_rub:.1f}₽/М • ⤴️ {output_price_rub:.1f}₽/М"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"model:{model_name}")])

    # Добавляем кнопки для настройки максимального количества токенов
    tokens_options = [4000, 8000, 12000, 16000]
    tokens_buttons = []
    for tokens in tokens_options:
        tokens_buttons.append(InlineKeyboardButton(
            text=f"🔢 {tokens} токенов", 
            callback_data=f"set_max_tokens:{tokens}"
        ))
    
    # Группируем кнопки токенов по 2 в ряд
    for i in range(0, len(tokens_options), 2):
        row = []
        for j in range(2):
            if i + j < len(tokens_options):
                tokens = tokens_options[i + j]
                row.append(InlineKeyboardButton(
                    text=f"🔢 {tokens} токенов", 
                    callback_data=f"set_max_tokens:{tokens}"
                ))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def chat_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура в чате"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
                InlineKeyboardButton(text="🔄 Новый чат", callback_data="new_chat")
            ]
        ]
    )
    return keyboard


def prompts_keyboard(prompts: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура управления промптами"""
    buttons = []
    
    for prompt in prompts:
        buttons.append([InlineKeyboardButton(
            text=f"📄 {prompt['name']}", 
            callback_data=f"prompt:{prompt['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="➕ Создать промпт", callback_data="create_prompt")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад в меню", callback_data="back_to_main")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def prompt_actions_keyboard(prompt_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий с промптом"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Использовать", callback_data=f"use_prompt:{prompt_id}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_prompt:{prompt_id}")
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_prompt:{prompt_id}"),
                InlineKeyboardButton(text="↩️ Назад", callback_data="prompts")
            ]
        ]
    )
    return keyboard