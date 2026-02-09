import asyncio
import sqlite3
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# --- КОНФІГУРАЦІЯ ---
load_dotenv(dotenv_path="api.env")
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    exit("Помилка: BOT_TOKEN не знайдено в api.env")

logging.basicConfig(level=logging.INFO)

TEMPLATES = [
    "Ти мені подобаєшся! ❤️",
    "Дякую, що ти є в моєму житті! ✨",
    "З Днем святого Валентина! 💘",
    "Ти — неймовірна людина! 🌟",
    "Давай вип'ємо кави разом? ☕"
]

# --- БАЗА ДАНИХ ---
def init_db():
    with sqlite3.connect("valentines_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)")
        cursor.execute("""CREATE TABLE IF NOT EXISTS valentines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            sender_id INTEGER, 
            receiver_username TEXT, 
            content TEXT, 
            content_type TEXT,
            is_anonymous INTEGER)""")
        
        # Перевірка структури (якщо база вже існувала)
        cursor.execute("PRAGMA table_info(valentines)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'content' not in columns:
            cursor.execute("ALTER TABLE valentines ADD COLUMN content TEXT")
        if 'content_type' not in columns:
            cursor.execute("ALTER TABLE valentines ADD COLUMN content_type TEXT")
        conn.commit()

class SendValentine(StatesGroup):
    waiting_for_receiver = State()
    waiting_for_message = State()
    waiting_for_anon = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def get_main_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Надіслати валентинку 💌")
    kb.button(text="Моя пошта 📮")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

# --- ОБРОБНИКИ ---

# 1. МОЯ ПОШТА (Інтерактивна з кнопкою відповіді)
@dp.message(F.text == "Моя пошта 📮")
async def check_mail(message: types.Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username.lower() if message.from_user.username else None
    
    if not username:
        await message.answer("❌ У тебе немає @username! Встанови його в налаштуваннях Telegram.")
        return

    with sqlite3.connect("valentines_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.content, v.content_type, v.is_anonymous, u.full_name, u.username 
            FROM valentines v LEFT JOIN users u ON v.sender_id = u.user_id
            WHERE v.receiver_username = ?
        """, (username,))
        mails = cursor.fetchall()

    if not mails:
        await message.answer("Твоя скринька поки порожня... ✨", reply_markup=get_main_kb())
    else:
        await message.answer(f"📬 Тобі прийшло {len(mails)} повідомлень:")
        for content, c_type, anon, name, s_username in mails:
            sender_label = "Таємний шанувальник 👤" if anon else f"Від: {name} ✍️"
            
            # Кнопка відповіді (тільки якщо не анонімно)
            reply_markup = None
            if not anon and s_username:
                builder = InlineKeyboardBuilder()
                builder.button(text=f"Відповісти @{s_username} 💌", callback_data=f"reply_{s_username}")
                reply_markup = builder.as_markup()

            if c_type == "sticker":
                await message.answer(f"<b>{sender_label}</b> надіслав тобі стікер:", parse_mode="HTML")
                await message.answer_sticker(content, reply_markup=reply_markup)
            else:
                protected_content = f"<b>{sender_label}</b>:\n<tg-spoiler>{content}</tg-spoiler>"
                await message.answer(protected_content, parse_mode="HTML", reply_markup=reply_markup)
        
        await message.answer("Це всі повідомлення на цей час!", reply_markup=get_main_kb())

# 2. ШВИДКА ВІДПОВІДЬ (Callback Query)
@dp.callback_query(F.data.startswith("reply_"))
async def handle_reply_button(callback: types.CallbackQuery, state: FSMContext):
    target_username = callback.data.replace("reply_", "")
    await state.clear()
    await state.update_data(receiver=target_username)
    await state.set_state(SendValentine.waiting_for_message)
    
    builder = InlineKeyboardBuilder()
    for i, text in enumerate(TEMPLATES):
        builder.button(text=text, callback_data=f"tmpl_{i}")
    builder.adjust(1)
    
    await callback.message.answer(
        f"✍️ Пишемо відповідь для @{target_username}:\nВведи текст, стікер або обери шаблон:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# 3. СТАРТ
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username.lower() if message.from_user.username else None
    with sqlite3.connect("valentines_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, username, message.from_user.full_name))
        conn.commit()
    await message.answer("❤️ Пошта Амура ТНТУ активована!", reply_markup=get_main_kb())

# 4. ЛОГІКА ВІДПРАВКИ
@dp.message(F.text == "Надіслати валентинку 💌")
async def start_sending(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введи @username отримувача:")
    await state.set_state(SendValentine.waiting_for_receiver)

@dp.message(SendValentine.waiting_for_receiver)
async def process_receiver(message: types.Message, state: FSMContext):
    if message.text == "Моя пошта 📮":
        await check_mail(message, state)
        return

    receiver = message.text.replace("@", "").lower().strip()
    await state.update_data(receiver=receiver)
    
    builder = InlineKeyboardBuilder()
    for i, text in enumerate(TEMPLATES):
        builder.button(text=text, callback_data=f"tmpl_{i}")
    builder.adjust(1)
    
    await message.answer("Напиши текст, надішли стікер або обери шаблон:", reply_markup=builder.as_markup())
    await state.set_state(SendValentine.waiting_for_message)

@dp.callback_query(F.data.startswith("tmpl_"), SendValentine.waiting_for_message)
async def process_template(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[1])
    await state.update_data(content=TEMPLATES[index], type="text")
    
    kb = ReplyKeyboardBuilder()
    kb.button(text="Анонімно 🔒")
    kb.button(text="Підписатися ✍️")
    await callback.message.answer("Як надіслати?", reply_markup=kb.as_markup(resize_keyboard=True, one_time_keyboard=True))
    await state.set_state(SendValentine.waiting_for_anon)

@dp.message(SendValentine.waiting_for_message)
async def process_content(message: types.Message, state: FSMContext):
    if message.text == "Моя пошта 📮":
        await check_mail(message, state)
        return

    if message.sticker:
        await state.update_data(content=message.sticker.file_id, type="sticker")
    else:
        await state.update_data(content=message.text, type="text")
        
    kb = ReplyKeyboardBuilder()
    kb.button(text="Анонімно 🔒")
    kb.button(text="Підписатися ✍️")
    await message.answer("Як надіслати повідомлення?", reply_markup=kb.as_markup(resize_keyboard=True, one_time_keyboard=True))
    await state.set_state(SendValentine.waiting_for_anon)

@dp.message(SendValentine.waiting_for_anon)
async def process_anon(message: types.Message, state: FSMContext):
    if message.text == "Моя пошта 📮":
        await check_mail(message, state)
        return

    if message.text not in ["Анонімно 🔒", "Підписатися ✍️"]:
        await message.answer("Будь ласка, натисни на кнопку!")
        return

    is_anon = 1 if "Анонімно" in message.text else 0
    data = await state.get_data()
    receiver_username = data['receiver']
    
    with sqlite3.connect("valentines_bot.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO valentines (sender_id, receiver_username, content, content_type, is_anonymous) VALUES (?, ?, ?, ?, ?)",
            (message.from_user.id, receiver_username, data['content'], data['type'], is_anon))
        
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (receiver_username,))
        receiver_data = cursor.fetchone()
        conn.commit()

    if receiver_data:
        try:
            await bot.send_message(receiver_data[0], "✨ <b>Тобі прийшла нова валентинка!</b>\nПеревір пошту 📮", parse_mode="HTML")
            await bot.send_message(receiver_data[0], "💘")
        except: pass

    await state.clear()
    await message.answer("✅ <b>Валентинку доставлено!</b>", parse_mode="HTML", reply_markup=get_main_kb())
    await message.answer("🚀")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())