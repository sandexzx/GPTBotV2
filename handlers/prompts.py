from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.operations import get_or_create_user, get_user_prompts, save_prompt, delete_prompt
from keyboards.keyboards import prompts_keyboard, prompt_actions_keyboard, main_menu_keyboard

router = Router()


class PromptStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_content = State()
    editing_prompt = State()


@router.callback_query(F.data == "prompts")
async def show_prompts(callback: CallbackQuery, state: FSMContext):
    """Показать список промптов пользователя"""
    user = get_or_create_user(
        callback.from_user.id, 
        callback.from_user.username
    )
    
    prompts = get_user_prompts(user.id)
    
    if not prompts:
        await callback.message.edit_text(
            "У тебя пока нет сохраненных промптов.\n\n"
            "Промпты - это предустановленные инструкции для AI модели, "
            "которые можно сохранить и использовать в новых чатах.",
            reply_markup=prompts_keyboard([])
        )
    else:
        prompts_data = [{"id": p.id, "name": p.name} for p in prompts]
        await callback.message.edit_text(
            "Твои сохраненные промпты:",
            reply_markup=prompts_keyboard(prompts_data)
        )
    
    await callback.answer()


@router.callback_query(F.data == "create_prompt")
async def create_prompt_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания промпта"""
    await callback.message.edit_text(
        "Создание нового промпта.\n\n"
        "Как назовем этот промпт? Введи название:",
    )
    await state.set_state(PromptStates.waiting_for_name)
    await callback.answer()


@router.message(PromptStates.waiting_for_name)
async def process_prompt_name(message: Message, state: FSMContext):
    """Обработка имени промпта"""
    await state.update_data(prompt_name=message.text)
    
    await message.answer(
        "Отлично! Теперь введи содержимое промпта:\n\n"
        "Это инструкция, которая будет отправляться модели перед твоими сообщениями. "
        "Например: \"Отвечай как Шекспир\" или \"Ты эксперт по Python\"."
    )
    await state.set_state(PromptStates.waiting_for_content)


@router.message(PromptStates.waiting_for_content)
async def process_prompt_content(message: Message, state: FSMContext):
    """Обработка содержимого промпта"""
    data = await state.get_data()
    prompt_name = data.get("prompt_name")
    
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    
    # Сохраняем промпт
    prompt = save_prompt(user.id, prompt_name, message.text)
    
    await message.answer(
        f"✅ Промпт \"{prompt_name}\" успешно сохранен!\n\n"
        f"Теперь ты можешь использовать его в чатах.",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()


@router.callback_query(F.data.startswith("prompt:"))
async def show_prompt_actions(callback: CallbackQuery, state: FSMContext):
    """Показать действия с промптом"""
    prompt_id = int(callback.data.split(":")[1])
    
    # Сохраняем ID промпта в состоянии
    await state.update_data(prompt_id=prompt_id)
    
    # В реальном коде здесь нужно получить промпт из БД
    # И показать его название и начало содержимого
    
    await callback.message.edit_text(
        f"Промпт #{prompt_id}\n\n"
        f"Выбери действие:",
        reply_markup=prompt_actions_keyboard(prompt_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_prompt:"))
async def delete_prompt_action(callback: CallbackQuery, state: FSMContext):
    """Удаление промпта"""
    prompt_id = int(callback.data.split(":")[1])
    
    # Удаляем промпт
    success = delete_prompt(prompt_id)
    
    if success:
        await callback.message.edit_text(
            "✅ Промпт успешно удален!",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось удалить промпт.",
            reply_markup=main_menu_keyboard()
        )
    
    await callback.answer()