import random # Додано для вибору випадкового передбачення
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from database import get_db_connection
from keyboards import get_main_kb
from states import Registration
from config import PREDICTIONS # Додано імпорт списку передбачень
import os

router = Router()
BOT_ACTIVE = True  # Твій перемикач сезону

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if not BOT_ACTIVE:
        await message.answer(
            "👋 <b>Дякуємо!</b>\n\nПошта Амура ТНТУ завершила роботу. Зустрінемось у 2027! ❤️",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    user_id = message.from_user.id
    un = message.from_user.username.lower() if message.from_user.username else None
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT gender FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        kb = ReplyKeyboardBuilder()
        kb.button(text="Я Хлопець 👨")
        kb.button(text="Я Дівчина 👩")
        await message.answer(f"Привіт, {message.from_user.first_name}! 👋\n\nОберіть свою стать:", 
                             reply_markup=kb.as_markup(resize_keyboard=True))
        await state.set_state(Registration.waiting_for_gender)
    else:
        cursor.execute("UPDATE users SET username = %s WHERE user_id = %s", (un, user_id))
        conn.commit()
        await message.answer("З поверненням до ТНТУ! ❤️", reply_markup=get_main_kb())
    cursor.close(); conn.close()

@router.message(Registration.waiting_for_gender)
async def process_gender(message: types.Message, state: FSMContext):
    gender = "male" if "Хлопець" in message.text else "female"
    user_id = message.from_user.id
    un = message.from_user.username.lower() if message.from_user.username else None
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, username, full_name, gender) VALUES (%s, %s, %s, %s) "
                   "ON CONFLICT (user_id) DO UPDATE SET gender = EXCLUDED.gender",
                   (user_id, un, message.from_user.full_name, gender))
    conn.commit(); cursor.close(); conn.close()
    await state.clear()
    await message.answer("Тепер ти в базі Амура! 👇", reply_markup=get_main_kb())

# --- ОБРОБНИК ПЕРЕДБАЧЕНЬ ---
@router.message(F.text == "Передбачення Амура ✨")
async def get_prediction(message: types.Message):
    # Вибираємо рандомну фразу зі списку в config.py
    prediction = random.choice(PREDICTIONS)
    res = f"🔮 <b>Твоє передбачення на сьогодні:</b>\n\n<i>{prediction}</i>"
    await message.answer(res, parse_mode="HTML")

# --- ОБРОБНИК СТАТИСТИКИ ---
@router.message(F.text == "Статистика 📈")
async def show_stats(message: types.Message):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM valentines")
    v = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM queue")
    q = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM active_chats")
    a = cursor.fetchone()[0]
    cursor.close(); conn.close()
    
    stats_text = (
        "📊 <b>Статистика Амура ТНТУ:</b>\n\n"
        f"👥 Всього користувачів: {u}\n"
        f"💌 Надіслано валентинок: {v}\n"
        "──────────────────\n"
        f"🔍 Зараз шукають пару: {q}\n"
        f"💬 Активних чатів: {a}\n\n"
        "Приєднуйся до спілкування! ❤️"
    )
    await message.answer(stats_text, parse_mode="HTML")