from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.operations import get_or_create_user, create_chat, add_message, get_chat_messages, get_chat_stats
from services.openai_service import send_message_to_openai
from services.token_counter import format_stats
from keyboards.keyboards import chat_keyboard, models_keyboard, main_menu_keyboard

router = Router()


class ChatStates(StatesGroup):
    waiting_for_message = State()
    using_prompt = State()


@router.callback_query(F.data.startswith("model:"))
async def select_model(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора модели"""
    model = callback.data.split(":")[1]
    
    # Сохраняем выбранную модель в состоянии
    await state.update_data(model=model)

    # Добавляем ставки модели в состояние
    from config import MODELS
    model_rates = MODELS.get(model, {"input": 0, "output": 0})
    await state.update_data(
        model_rate_input=model_rates["input"],
        model_rate_output=model_rates["output"]
    )
    
    # Получаем или создаем пользователя
    user = get_or_create_user(
        callback.from_user.id, 
        callback.from_user.username
    )
    
    # Создаем новый чат
    chat_id = create_chat(user.id, model)
    
    # Сохраняем ID чата в состоянии
    await state.update_data(chat_id=chat_id)
    
    await callback.message.edit_text(
        f"Чат с моделью {model} начат!\n\n"
        f"Отправь сообщение, и я передам его модели.",
        reply_markup=chat_keyboard()
    )
    
    await state.set_state(ChatStates.waiting_for_message)
    await callback.answer()


@router.message(ChatStates.waiting_for_message)
async def process_message(message: Message, state: FSMContext):
    """Обработка сообщения в чате"""
    # Получаем данные из состояния
    data = await state.get_data()
    model = data.get("model")
    chat_id = data.get("chat_id")
    system_instruction = data.get("system_instruction")
    
    # Проверяем наличие chat_id
    if not chat_id:
        await message.answer(
            "Произошла ошибка. Пожалуйста, начните новый чат.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Показываем статус "печатает..."
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    # Добавляем сообщение пользователя в БД
    user_tokens = len(message.text.split()) * 1.3  # Примерная оценка токенов
    user_cost = user_tokens * (data.get("model_rate_input", 0) / 1_000_000)
    add_message(chat_id, "user", message.text, int(user_tokens), user_cost)
    
    # Получаем историю чата
    chat_messages = get_chat_messages(chat_id)
    
    # Отправляем запрос в OpenAI
    response = await send_message_to_openai(
        model=model,
        input_text=message.text,
        messages=chat_messages,
        system_instruction=system_instruction
    )
    
    if response["success"]:
        # Добавляем ответ ассистента в БД
        add_message(
            chat_id,
            "assistant",
            response["output_text"],
            response["output_tokens"],
            response["output_cost"]
        )
        
        # Получаем статистику чата
        chat_stats = get_chat_stats(chat_id)
        
        # Форматируем статистику
        stats_text = format_stats(
            response["input_tokens"],
            response["output_tokens"],
            model,
            chat_stats["tokens_input"],
            chat_stats["tokens_output"]
        )
        
        # Отправляем ответ с статистикой
        await message.answer(
            f"{response['output_text']}{stats_text}",
            reply_markup=chat_keyboard()
        )
    else:
        # В случае ошибки
        await message.answer(
            f"❌ Произошла ошибка: {response['error']}\n\n"
            f"Попробуйте еще раз или выберите другую модель.",
            reply_markup=chat_keyboard()
        )


@router.callback_query(F.data.startswith("use_prompt:"), ChatStates.waiting_for_message)
async def use_prompt_in_chat(callback: CallbackQuery, state: FSMContext):
    """Применение промпта к текущему чату"""
    prompt_id = int(callback.data.split(":")[1])
    
    # Здесь нужно получить промпт из БД
    # И установить его как системную инструкцию для чата
    
    # Пример (нужно доработать):
    # prompt = get_prompt(prompt_id)
    # await state.update_data(system_instruction=prompt.content)
    
    await callback.message.edit_text(
        "Промпт успешно применен к текущему чату!\n"
        "Теперь все сообщения будут обрабатываться согласно этому промпту.",
        reply_markup=chat_keyboard()
    )
    await callback.answer()