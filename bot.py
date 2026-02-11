import asyncio
import psycopg2
import logging
import os
from aiohttp import web # Додаємо для Render
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# --- КОНФІГУРАЦІЯ ---
load_dotenv(dotenv_path="api.env")
API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

TEMPLATES = ["Ти мені подобаєшся! ❤️", "Дякую, що ти є! ✨", "З Днем Валентина! 💘"]

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (ФІКС ПОРТУ) ---
async def handle(request):
    return web.Response(text="Bot is alive!")

async def run_http_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render автоматично надає порт у змінній оточення PORT
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"HTTP server started on port {port}")

# --- БАЗА ДАНИХ ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS valentines (
        id SERIAL PRIMARY KEY, 
        sender_id BIGINT, 
        receiver_username TEXT, 
        content TEXT, 
        content_type TEXT,
        is_anonymous INTEGER)""")
    conn.commit()
    cursor.close()
    conn.close()

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

# --- ОБРОБНИКИ (POSTGRES) ---

@dp.message(F.text == "Моя пошта 📮", state="*")
async def check_mail(message: types.Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username.lower() if message.from_user.username else None
    if not username:
        await message.answer("❌ Встанови @username!")
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.content, v.content_type, v.is_anonymous, u.full_name, u.username 
        FROM valentines v LEFT JOIN users u ON v.sender_id = u.user_id
        WHERE v.receiver_username = %s
    """, (username,))
    mails = cursor.fetchall()
    
    if not mails:
        await message.answer("Твоя пошта порожня... ✨", reply_markup=get_main_kb())
    else:
        for content, c_type, anon, name, s_username in mails:
            sender_label = "Таємний шанувальник 👤" if anon else f"Від: {name} ✍️"
            builder = InlineKeyboardBuilder()
            if not anon and s_username:
                builder.button(text=f"Відповісти @{s_username}", callback_data=f"reply_{s_username}")
            
            if c_type == "sticker":
                await message.answer(f"<b>{sender_label}</b>:", parse_mode="HTML")
                await message.answer_sticker(content, reply_markup=builder.as_markup())
            else:
                await message.answer(f"<b>{sender_label}</b>:\n<tg-spoiler>{content}</tg-spoiler>", 
                                     parse_mode="HTML", reply_markup=builder.as_markup())
    cursor.close()
    conn.close()

@dp.callback_query(F.data.startswith("reply_"))
async def handle_reply(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.replace("reply_", "")
    await state.clear()
    await state.update_data(receiver=target)
    await state.set_state(SendValentine.waiting_for_message)
    await callback.message.answer(f"Пишемо відповідь для @{target}:")
    await callback.answer()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username.lower() if message.from_user.username else None
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, username, full_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username", 
                   (user_id, username, message.from_user.full_name))
    conn.commit()
    cursor.close()
    conn.close()
    await message.answer("❤️ Вітаємо в Пошті Амура ТНТУ!", reply_markup=get_main_kb())

# --- ЛОГІКА ВІДПРАВКИ ---

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
    await message.answer("Напиши текст або надішли стікер:")
    await state.set_state(SendValentine.waiting_for_message)

@dp.message(SendValentine.waiting_for_message)
async def process_content(message: types.Message, state: FSMContext):
    if message.text == "Моя пошта 📮":
        await check_mail(message, state)
        return
    c_type = "sticker" if message.sticker else "text"
    content = message.sticker.file_id if message.sticker else message.text
    await state.update_data(content=content, type=c_type)
    
    kb = ReplyKeyboardBuilder()
    kb.button(text="Анонімно 🔒")
    kb.button(text="Підписатися ✍️")
    await message.answer("Як надіслати?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_anon)

@dp.message(SendValentine.waiting_for_anon)
async def process_anon(message: types.Message, state: FSMContext):
    if message.text == "Моя пошта 📮":
        await check_mail(message, state)
        return
    is_anon = 1 if "Анонімно" in message.text else 0
    data = await state.get_data()
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO valentines (sender_id, receiver_username, content, content_type, is_anonymous) VALUES (%s, %s, %s, %s, %s)",
                   (message.from_user.id, data['receiver'], data['content'], data['type'], is_anon))
    
    cursor.execute("SELECT user_id FROM users WHERE username = %s", (data['receiver'],))
    receiver_data = cursor.fetchone()
    conn.commit()
    
    if receiver_data:
        try:
            await bot.send_message(receiver_data[0], "✨ Тобі прийшла нова валентинка! 📮\n💘")
        except: pass

    cursor.close()
    conn.close()
    await state.clear()
    await message.answer("✅ Доставлено!", reply_markup=get_main_kb())

async def main():
    init_db()
    # Запускаємо веб-сервер фоном
    await run_http_server()
    # Запускаємо бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())