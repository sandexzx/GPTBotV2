from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.operations import get_or_create_user, create_chat, add_message, get_chat_messages, get_chat_stats, get_prompt_by_id
from services.openai_service import send_message_to_openai
from services.token_counter import calculate_cost, format_stats
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

     # Проверяем, есть ли выбранный промпт
    data = await state.get_data()
    selected_prompt_id = data.get("selected_prompt_id")

    print(f"Выбор модели {model}, выбранный промпт ID: {selected_prompt_id}")
    
    system_instruction = None
    if selected_prompt_id:
        # Добавляем проверку на существование промпта
        prompt = get_prompt_by_id(selected_prompt_id)
        if prompt:
            print(f"Применяем промпт {prompt.name} при создании чата")
            system_instruction = prompt.content
        else:
            print(f"Промпт с ID {selected_prompt_id} не найден при создании чата")
            await state.update_data(selected_prompt_id=None)

    # Обновляем состояние с системной инструкцией
    if system_instruction:
        await state.update_data(system_instruction=system_instruction)


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

    # Сообщение о начале чата
    message_text = f"Чат с моделью {model} начат!"
    if selected_prompt_id:
        prompt = get_prompt_by_id(selected_prompt_id)
        message_text += f"\n\n🔮 Промпт \"{prompt.name}\" применён к чату."
    message_text += "\n\nОтправь сообщение, и я передам его модели."
    
    
    await callback.message.edit_text(
        message_text,
        reply_markup=chat_keyboard() 
    )
    
    await state.set_state(ChatStates.waiting_for_message)
    print(f"Установлено состояние: ChatStates:waiting_for_message")
    await callback.answer()


@router.message(ChatStates.waiting_for_message)
async def process_message(message: Message, state: FSMContext):
    """Обработка сообщения в чате"""
    # Получаем данные из состояния
    data = await state.get_data()
    model = data.get("model")
    chat_id = data.get("chat_id")
    system_instruction = data.get("system_instruction")

    # Отладочная информация
    print(f"Модель: {model}, Chat ID: {chat_id}")
    print(f"Системная инструкция установлена: {'Да' if system_instruction else 'Нет'}")
    if system_instruction:
        print(f"Длина инструкции: {len(system_instruction)} символов")
    
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
    from services.token_counter import get_token_count
    user_tokens = get_token_count(message.text, model)  # Более точная оценка
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
        # ВОТ ГДЕ ПРОБЛЕМА! Нам нужно обновить предыдущую запись о токенах пользователя
        # с фактическими данными, которые пришли от API
        from database.models import Session, Message, Chat
        session = Session()
        # Получаем последнее сообщение пользователя и обновляем его токены
        last_user_message = session.query(Message).filter(
            Message.chat_id == chat_id, 
            Message.role == "user"
        ).order_by(Message.id.desc()).first()
        if last_user_message:
            # Вычисляем разницу между оценкой и реальным количеством
            tokens_diff = response["input_tokens"] - last_user_message.tokens
            cost_diff = calculate_cost(tokens_diff, model, True)
            
            # Обновляем запись сообщения
            last_user_message.tokens = response["input_tokens"]
            last_user_message.cost_usd = calculate_cost(response["input_tokens"], model, True)
            
            # Обновляем статистику чата
            chat = session.query(Chat).filter(Chat.id == chat_id).one()
            chat.tokens_input += tokens_diff
            chat.cost_usd += cost_diff
            
            # Обновляем статистику пользователя
            user = chat.user
            user.total_tokens_input += tokens_diff
            user.total_cost_usd += cost_diff
            
            session.commit()
        session.close()
        
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


@router.callback_query(F.data.startswith("use_prompt:"))
async def use_prompt_in_chat(callback: CallbackQuery, state: FSMContext):
    # Проверяем состояние
    current_state = await state.get_state()
    print(f"Применение промпта в чате, текущее состояние: {current_state}")
    
    """Применение промпта к текущему чату"""
    prompt_id = int(callback.data.split(":")[1])

    # Получаем промпт из БД
    from database.operations import get_prompt_by_id
    prompt = get_prompt_by_id(prompt_id)

    # Проверяем, находимся ли мы в чате
    if current_state is None or current_state != "ChatStates:waiting_for_message":
        # Перенаправляем на обработчик в prompts.py
        from handlers.prompts import redirect_use_prompt
        await redirect_use_prompt(callback, state)
        return
    
    if prompt:
        print(f"Применяем промпт {prompt.name} к чату")
        await state.update_data(system_instruction=prompt.content)
        await callback.message.edit_text(
            f"🔮 Промпт \"{prompt.name}\" успешно применен к текущему чату!\n"
            f"Теперь все сообщения будут обрабатываться согласно этому промпту.",
            reply_markup=chat_keyboard()
        )
    else:
        print(f"Промпт с ID {prompt_id} не найден")
        await callback.message.edit_text(
            "❌ Ошибка: Промпт не найден. Попробуйте выбрать другой.",
            reply_markup=chat_keyboard()
        )
    
    await callback.answer()