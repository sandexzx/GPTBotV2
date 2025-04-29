from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums.parse_mode import ParseMode
import logging
import time

from database.operations import get_or_create_user, create_chat, add_message, get_chat_messages, get_chat_stats, get_prompt_by_id
from services.openai_service import send_message_to_openai
from services.token_counter import calculate_cost, format_stats
from services.queue_manager import queue_manager
from keyboards.keyboards import chat_keyboard, models_keyboard, main_menu_keyboard
from config import MAIN_ADMIN_ID
from user_mapping import get_user_name

router = Router()


class ChatStates(StatesGroup):
    waiting_for_message = State()
    using_prompt = State()
    waiting_for_file = State()  # Новое состояние для ожидания файла


@router.callback_query(F.data.startswith("model:"))
async def select_model(callback: CallbackQuery, state: FSMContext):
    # Получаем модель из callback_data
    model = callback.data.split(":")[1]
    
    # Сохраняем выбранную модель в состоянии
    await state.update_data(model=model)

    # Проверяем, есть ли выбранный промпт
    data = await state.get_data()
    selected_prompt_id = data.get("selected_prompt_id")
    max_tokens = data.get("max_tokens", 4000)  # Получаем выбранное количество токенов или используем значение по умолчанию

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
    user_id = get_or_create_user(
        callback.from_user.id, 
        callback.from_user.username
    )
    
    # Создаем новый чат
    chat_id = create_chat(user_id, model)
    
    # Сохраняем ID чата в состоянии
    await state.update_data(chat_id=chat_id)

    # Сообщение о начале чата
    message_text = f"Чат с моделью {model} начат!"
    if selected_prompt_id:
        prompt = get_prompt_by_id(selected_prompt_id)
        message_text += f"\n\n🔮 Промпт \"{prompt.name}\" применён к чату."
    message_text += f"\n\n🔢 Лимит выходных токенов: {max_tokens}"
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
    # Проверяем, не находится ли пользователь уже в очереди
    if queue_manager.is_user_in_queue(message.from_user.id):
        await message.answer(
            "⏳ Ваш предыдущий запрос еще в очереди. Пожалуйста, дождитесь его обработки.",
            reply_markup=chat_keyboard()
        )
        return

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

    # Добавляем запрос в очередь
    position = await queue_manager.add_to_queue(message)

    # Отправляем уведомление о постановке в очередь
    if position > 1:
        await message.answer(
            f"⏳ Ваш запрос поставлен в очередь. Позиция: {position}\n"
            f"Вы получите уведомление, когда начнется обработка вашего запроса.",
            reply_markup=chat_keyboard()
        )

    # Обрабатываем очередь
    async for request in queue_manager.process_queue():
        # Получаем данные из состояния для текущего запроса
        current_data = await state.get_data()
        current_model = current_data.get("model")
        current_chat_id = current_data.get("chat_id")
        current_system_instruction = current_data.get("system_instruction")

        # Добавляем сообщение пользователя в БД
        from services.token_counter import get_token_count
        user_tokens = get_token_count(request['message'].text, current_model)
        user_cost = user_tokens * (current_data.get("model_rate_input", 0) / 1_000_000)
        add_message(current_chat_id, "user", request['message'].text, int(user_tokens), user_cost)

        # Получаем историю чата
        chat_messages = get_chat_messages(current_chat_id)

        # Отправляем уведомление главному админу
        if request['user_id'] != MAIN_ADMIN_ID:
            user_name = get_user_name(request['user_id']) or f"ID: {request['user_id']}"
            admin_notification = (
                f"🆕 Новый запрос от пользователя:\n"
                f"👤 {user_name}\n"
                f"📝 Текст: {request['message'].text}\n"
                f"🤖 Модель: {current_model}"
            )
            await request['bot'].send_message(MAIN_ADMIN_ID, admin_notification)

        try:
            # Отправляем запрос в OpenAI
            response = await send_message_to_openai(
                model=current_model,
                input_text=request['message'].text,
                messages=chat_messages,
                system_instruction=current_system_instruction,
                max_tokens=current_data.get("max_tokens", None),
                stream=True  # Включаем стриминг
            )

            if response["success"]:
                # Обновляем данные о токенах
                from database.operations import update_message_tokens
                update_message_tokens(
                    chat_id=current_chat_id,
                    is_user_message=True,
                    new_tokens=response["input_tokens"],
                    old_tokens=user_tokens,
                    model=current_model
                )

                # Создаем сообщение для редактирования
                bot_message = await request['message'].answer("⌛ Генерирую ответ...")
                full_response = ""
                output_tokens = 0
                last_update_length = 0
                use_file = False  # Флаг для переключения на отправку файлом
                last_update_time = 0  # Время последнего обновления
                update_interval = 1.0  # Уменьшаем интервал обновления
                min_length_for_streaming = 50  # Минимальная длина для начала стриминга
                initial_streaming_delay = 0.5  # Задержка перед первым обновлением для коротких ответов

                # Обрабатываем стрим
                async for chunk in response["stream"]:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        output_tokens += 1  # Примерная оценка токенов

                        current_time = time.time()
                        
                        # Для коротких ответов используем меньшую задержку
                        if len(full_response) < min_length_for_streaming:
                            if current_time - last_update_time >= initial_streaming_delay:
                                try:
                                    # Проверяем, что текст не пустой
                                    if full_response.strip():
                                        await bot_message.edit_text(full_response)
                                        last_update_time = current_time
                                    else:
                                        # Если текст пустой, просто пропускаем обновление
                                        continue
                                except Exception as e:
                                    logging.warning(f"Ошибка при обновлении короткого сообщения: {str(e)}")
                            continue

                        # Если сообщение стало слишком длинным, переключаемся на файл
                        if len(full_response) > 4000:  # Увеличиваем порог для переключения на файл
                            use_file = True
                            await bot_message.edit_text("📄 Ответ слишком длинный, отправляю файлом...")
                            continue

                        # Если используем файл, пропускаем обновления
                        if use_file:
                            continue

                        # Отправляем обновление только если прошло достаточно времени
                        if current_time - last_update_time >= update_interval:
                            try:
                                await bot_message.edit_text(full_response)
                                last_update_length = len(full_response)
                                last_update_time = current_time
                            except Exception as e:
                                if "Flood control" in str(e):
                                    # При ошибке flood control увеличиваем интервал
                                    update_interval = min(update_interval * 1.5, 5.0)
                                    logging.warning(f"Flood control detected, increasing interval to {update_interval}")
                                else:
                                    # При других ошибках переключаемся на файл
                                    use_file = True
                                    await bot_message.edit_text("📄 Ответ слишком длинный, отправляю файлом...")
                                    logging.warning(f"Ошибка при обновлении сообщения: {str(e)}")

                # Если использовали файл, отправляем его
                if use_file:
                    await send_chunked_message(request['message'], full_response, reply_markup=chat_keyboard())
                else:
                    # Обновляем финальный текст, если он не пустой
                    if full_response.strip():
                        try:
                            await bot_message.edit_text(full_response)
                        except Exception as e:
                            logging.error(f"Не удалось обновить финальное сообщение: {str(e)}")
                            # Если не удалось отредактировать, отправляем новое сообщение
                            await request['message'].answer(full_response)

                # Добавляем ответ ассистента в БД
                output_cost = calculate_cost(output_tokens, current_model, is_input=False)
                add_message(
                    current_chat_id,
                    "assistant",
                    full_response,
                    output_tokens,
                    output_cost
                )

                # Получаем статистику чата
                chat_stats = get_chat_stats(current_chat_id)

                # Форматируем статистику
                stats_text = format_stats(
                    response["input_tokens"],
                    output_tokens,
                    current_model,
                    chat_stats["tokens_input"],
                    chat_stats["tokens_output"]
                )

                # Отправляем статистику
                await request['message'].answer(
                    f"📊 Статистика:{stats_text}",
                    reply_markup=chat_keyboard()
                )
            else:
                # В случае ошибки отправляем сообщение пользователю
                await request['message'].answer(
                    "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.",
                    reply_markup=chat_keyboard()
                )
        except Exception as e:
            # В случае неожиданной ошибки
            await request['message'].answer(
                f"❌ Произошла непредвиденная ошибка: {str(e)}\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору.",
                reply_markup=chat_keyboard()
            )
            # Логируем ошибку
            logging.error(f"Error processing message: {str(e)}")


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

async def send_chunked_message(message: Message, text: str, reply_markup=None, parse_mode=None):
    """Отправляет длинный текст частями, если он превышает лимит Telegram"""
    MAX_LENGTH = 4096  # Максимальная длина сообщения в Telegram

    # Если текст короче максимальной длины, просто отправляем его
    if len(text) <= MAX_LENGTH:
        return await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    
    # Если текст длиннее, отправляем его как файл
    import tempfile
    import os
    from datetime import datetime
    from aiogram.types import FSInputFile
    
    # Создаем имя файла с временной меткой
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"response_{timestamp}.txt"
    
    try:
        # Создаем временный файл с сохранением форматирования
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            # Добавляем заголовок с информацией о времени
            temp_file.write(f"Ответ сгенерирован: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            temp_file.write("=" * 50 + "\n\n")
            
            # Записываем сам текст
            temp_file.write(text)
            temp_file_path = temp_file.name
        
        # Отправляем файл
        input_file = FSInputFile(temp_file_path, filename=filename)
        await message.answer_document(
            document=input_file,
            caption="📄 Ответ слишком длинный, отправляю файлом",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке файла: {str(e)}")
        # В случае ошибки пытаемся отправить текст частями
        try:
            chunks = [text[i:i+MAX_LENGTH] for i in range(0, len(text), MAX_LENGTH)]
            for i, chunk in enumerate(chunks, 1):
                await message.answer(
                    f"Часть {i}/{len(chunks)}:\n\n{chunk}",
                    reply_markup=reply_markup if i == len(chunks) else None,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logging.error(f"Ошибка при отправке текста частями: {str(e)}")
            await message.answer(
                "❌ Произошла ошибка при отправке ответа. Пожалуйста, попробуйте позже.",
                reply_markup=reply_markup
            )
    finally:
        # Удаляем временный файл
        try:
            if 'temp_file_path' in locals():
                os.unlink(temp_file_path)
        except Exception as e:
            logging.warning(f"Не удалось удалить временный файл: {str(e)}")

@router.callback_query(F.data.startswith("set_max_tokens:"))
async def set_max_tokens(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора максимального количества токенов"""
    max_tokens = int(callback.data.split(":")[1])
    
    # Сохраняем выбранное значение в состоянии
    await state.update_data(max_tokens=max_tokens)
    
    await callback.message.edit_text(
        f"✅ Установлен лимит в {max_tokens} токенов для ответа.\n\n"
        "Теперь выберите модель для чата:",
        reply_markup=models_keyboard()
    )
    
    await callback.answer()

@router.callback_query(F.data == "load_prompt_file")
async def load_prompt_file(callback: CallbackQuery, state: FSMContext):
    """Обработка запроса на загрузку файла с промптом"""
    await callback.message.edit_text(
        "📂 Отправьте текстовый файл (.txt) с промптом.\n\n"
        "Файл должен содержать текст промпта, который будет использоваться для чата.",
        reply_markup=chat_keyboard()
    )
    await state.set_state(ChatStates.waiting_for_file)
    await callback.answer()

@router.message(ChatStates.waiting_for_file, F.document)
async def process_prompt_file(message: Message, state: FSMContext):
    """Обработка загруженного файла с промптом"""
    # Проверяем, что файл имеет расширение .txt
    if not message.document.file_name.endswith('.txt'):
        await message.answer(
            "❌ Ошибка: Файл должен иметь расширение .txt\n"
            "Пожалуйста, отправьте текстовый файл.",
            reply_markup=chat_keyboard()
        )
        return

    try:
        # Получаем файл
        file = await message.bot.get_file(message.document.file_id)
        file_path = file.file_path
        
        # Скачиваем файл
        file_content = await message.bot.download_file(file_path)
        prompt_text = file_content.read().decode('utf-8')
        
        # Сохраняем промпт в состоянии
        await state.update_data(system_instruction=prompt_text)
        
        # Получаем данные о модели
        data = await state.get_data()
        model = data.get("model")
        
        if model:
            # Если модель уже выбрана, сразу начинаем чат
            await message.answer(
                "✅ Промпт успешно загружен!\n\n"
                "Отправьте сообщение, и я передам его модели.",
                reply_markup=chat_keyboard()
            )
            await state.set_state(ChatStates.waiting_for_message)
        else:
            # Если модель не выбрана, предлагаем выбрать
            await message.answer(
                "✅ Промпт успешно загружен!\n\n"
                "Теперь выберите модель для чата:",
                reply_markup=models_keyboard()
            )
            
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при обработке файла: {str(e)}\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=chat_keyboard()
        )
        await state.set_state(ChatStates.waiting_for_file)