from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.operations import get_or_create_user, get_user_prompts, save_prompt, delete_prompt
from handlers.chat import ChatStates
from keyboards.keyboards import chat_keyboard, models_keyboard, prompts_keyboard, prompt_actions_keyboard, main_menu_keyboard

router = Router()


class PromptStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_content = State()
    editing_prompt = State()


@router.callback_query(F.data == "prompts")
async def show_prompts(callback: CallbackQuery, state: FSMContext):
    """Показать список промптов пользователя"""
    user_id = get_or_create_user(
        callback.from_user.id, 
        callback.from_user.username
    )
    
    prompts = get_user_prompts(user_id)
    
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
    
    user_id = get_or_create_user(message.from_user.id, message.from_user.username)
    
    # Сохраняем промпт
    prompt = save_prompt(user_id, prompt_name, message.text)
    
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
    
    # Получаем промпт из БД
    from database.operations import get_prompt_by_id
    prompt = get_prompt_by_id(prompt_id)
    
    if not prompt:
        await callback.message.edit_text(
            "❌ Промпт не найден. Возможно, он был удалён.",
            reply_markup=main_menu_keyboard()
        )
        await callback.answer()
        return
    
    # Подготавливаем превью содержимого (первые 100 символов)
    content_preview = prompt.content[:100] + "..." if len(prompt.content) > 100 else prompt.content
    
    await callback.message.edit_text(
        f"📄 Промпт: \"{prompt.name}\"\n\n"
        f"Содержимое:\n{content_preview}\n\n"
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

@router.callback_query(F.data.startswith("use_prompt:"))
async def redirect_use_prompt(callback: CallbackQuery, state: FSMContext):
    """Перенаправление запроса на использование промпта в чате"""
    # Получаем текущее состояние
    current_state = await state.get_state()
    print(f"Текущее состояние при нажатии на промпт: {current_state}")
    
    # Сохраняем ID промпта в состоянии для будущего использования
    prompt_id = int(callback.data.split(":")[1])
    
    # Проверяем промпт перед сохранением
    from database.operations import get_prompt_by_id
    prompt = get_prompt_by_id(prompt_id)
    if not prompt:
        await callback.message.edit_text(
            "❌ Ошибка: Промпт не найден. Попробуйте выбрать другой.",
            reply_markup=main_menu_keyboard()
        )
        await callback.answer()
        return
        
    print(f"Сохраняем промпт ID {prompt_id}: {prompt.name} для использования")
    
    # Очищаем состояние и сохраняем ID промпта
    await state.clear()
    await state.update_data(selected_prompt_id=prompt_id)
    
    # Проверяем, находимся ли мы в чате
    if current_state is not None and current_state == "ChatStates:waiting_for_message":
        # Если в чате, применяем промпт напрямую
        print(f"Применяем промпт к текущему чату")
        data = await state.get_data()
        chat_id = data.get("chat_id") 
        
        if chat_id:
            # Устанавливаем системную инструкцию
            await state.update_data(system_instruction=prompt.content)
            await callback.message.edit_text(
                f"🔮 Промпт \"{prompt.name}\" успешно применен к текущему чату!\n"
                f"Теперь все сообщения будут обрабатываться согласно этому промпту.",
                reply_markup=chat_keyboard()
            )
            await state.set_state(ChatStates.waiting_for_message)
        else:
            # Если нет chat_id, перенаправляем на выбор модели
            await callback.message.edit_text(
                f"Выбери модель для нового чата с промптом \"{prompt.name}\":",
                reply_markup=models_keyboard()
            )
    else:
        # Если не в чате, перенаправляем на выбор модели
        await callback.message.edit_text(
            f"Выбери модель для нового чата с промптом \"{prompt.name}\":",
            reply_markup=models_keyboard()
        )
    
    await callback.answer()