from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.keyboards import main_menu_keyboard, models_keyboard
from config import ADMIN_IDS

router = Router()


class MainMenuStates(StatesGroup):
    waiting_for_action = State()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    # Проверяем, может ли пользователь использовать бота
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Извините, этот бот доступен только для авторизованных пользователей.")
        return
    
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Это бот для взаимодействия с моделями OpenAI.\n"
        f"Выбери действие 👇",
        reply_markup=main_menu_keyboard()
    )
    await state.set_state(MainMenuStates.waiting_for_action)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработка команды /help"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    help_text = (
        "🤖 *OpenAI Proxy Bot* 🤖\n\n"
        "Команды:\n"
        "/start - Запустить бота\n"
        "/help - Показать эту справку\n\n"
        "Этот бот позволяет взаимодействовать с моделями OpenAI, "
        "сохранять промпты для многократного использования и отслеживать расходы."
    )
    await message.answer(help_text, parse_mode="Markdown")


@router.callback_query(F.data == "about")
async def about_bot(callback: CallbackQuery):
    """Информация о боте"""
    about_text = (
        "🤖 *OpenAI Proxy Bot* 🤖\n\n"
        "Бот позволяет взаимодействовать с разными моделями OpenAI и вести учёт расходов.\n\n"
        "Доступные функции:\n"
        "• 💬 Чат с разными моделями OpenAI\n"
        "• 📄 Сохранение и использование своих промптов\n"
        "• 📊 Отслеживание расходов и использования токенов\n\n"
        "Разработчик: @username"
    )
    await callback.message.edit_text(about_text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возвращение в главное меню"""
    await callback.message.edit_text(
        "Выбери действие 👇",
        reply_markup=main_menu_keyboard()
    )
    await state.set_state(MainMenuStates.waiting_for_action)
    await callback.answer()


@router.callback_query(F.data == "new_chat")
async def new_chat(callback: CallbackQuery, state: FSMContext):
    """Начало нового чата - выбор модели"""
    await callback.message.edit_text(
        "Выбери модель для чата:\n\n"
        "Стоимость указана за 1 миллион токенов.",
        reply_markup=models_keyboard()
    )
    await callback.answer()