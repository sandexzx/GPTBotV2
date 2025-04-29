from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database.operations import get_admin_stats
from config import ADMIN_IDS, USD_TO_RUB

router = Router()


@router.message(Command("admin"))
async def admin_command(message: Message):
    """Обработка админской команды"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    # Получаем статистику
    stats = get_admin_stats()
    
    # Форматируем статистику по пользователям
    users_text = "👤 Пользователи:\n\n"
    for user in stats["users"]:
        total_cost_rub = user["total_cost_usd"] * USD_TO_RUB
        users_text += (
            f"ID: {user['tg_id']}, @{user['username'] or 'Unknown'}\n"
            f"🗣️ Чатов: {user['chats_count']}\n"
            f"📝 Токенов: {user['total_tokens_input'] + user['total_tokens_output']} ({user['total_tokens_input']}⤵️/{user['total_tokens_output']}⤴️)\n"
            f"💰 Стоимость: {total_cost_rub:.2f}₽\n\n"
        )
    
    # Форматируем статистику по моделям
    models_text = "🤖 Модели:\n\n"
    for model_name, model_data in stats["models"].items():
        total_cost_rub = model_data["cost_usd"] * USD_TO_RUB
        models_text += (
            f"Модель: {model_name}\n"
            f"🗣️ Чатов: {model_data['chats_count']}\n"
            f"📝 Токенов: {model_data['tokens_input'] + model_data['tokens_output']} ({model_data['tokens_input']}⤵️/{model_data['tokens_output']}⤴️)\n"
            f"💰 Стоимость: {total_cost_rub:.2f}₽\n\n"
        )
    
    # Отправляем статистику
    await message.answer(users_text)
    await message.answer(models_text)