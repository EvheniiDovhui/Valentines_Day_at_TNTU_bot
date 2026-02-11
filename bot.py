import asyncio
import psycopg2
import logging
import os
import random
from aiohttp import web
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

# --- СТАНИ (FSM) ---
class SendValentine(StatesGroup):
    waiting_for_receiver = State()
    waiting_for_message = State()
    waiting_for_anon = State()

class ChatRoulette(StatesGroup):
    in_chat = State()

# --- ПЕРЕДБАЧЕННЯ ---
PREDICTIONS = [
    "Сьогодні ти зустрінеш свою долю в 2-му корпусі ТНТУ! ✨",
    "Твій таємний шанувальник поставить лайк на твій наступний сторіз. ❤️",
    "Амур каже: час надіслати валентинку тій самій людині... 😉",
    "Твоє кохання сильніше, ніж черга в їдальні ТНТУ! 🍕",
    "Сьогодні ідеальний день для кави з кимось особливим. ☕",
    "Хтось мріє отримати від тебе повідомлення прямо зараз. 💌",
    "Твій інтелект сьогодні — твоя найсексуальніша риса! 🧠🔥",
    "Сесія пройде легко, якщо в серці буде кохання! 📚❤️"
]

# --- БАЗА ДАНИХ (NEON / POSTGRESQL) ---
def get_db_connection():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Користувачі
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT)")
    # Валентинки
    cursor.execute("""CREATE TABLE IF NOT EXISTS valentines (
        id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_username TEXT, 
        content TEXT, content_type TEXT, is_anonymous INTEGER)""")
    # Чат-рулетка
    cursor.execute("CREATE TABLE IF NOT EXISTS active_chats (user1 BIGINT PRIMARY KEY, user2 BIGINT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS queue (user_id BIGINT PRIMARY KEY)")
    # Очистка тимчасових даних при перезапуску
    cursor.execute("DELETE FROM queue")
    cursor.execute("DELETE FROM active_chats")
    conn.commit()
    cursor.close()
    conn.close()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- КЛАВІАТУРИ ---
def get_main_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Надіслати валентинку 💌")
    kb.button(text="Моя пошта 📮")
    kb.button(text="Випадковий чат 🎲")
    kb.button(text="Передбачення Амура ✨")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Амур ТНТУ в мережі! ❤️")

async def run_http_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# --- ОБРОБНИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username.lower() if message.from_user.username else None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, username, full_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username", 
                   (user_id, username, message.from_user.full_name))
    conn.commit()
    cursor.close()
    conn.close()

    await message.answer(
        f"Привіт, {message.from_user.first_name}! 👋\n\n"
        "Вітаємо у **Пошті Амура ТНТУ**! 🏹\n"
        "Тут ти можеш надсилати валентинки, спілкуватися в анонімному чаті та отримувати передбачення.\n\n"
        "Обирай дію 👇", 
        parse_mode="Markdown", reply_markup=get_main_kb()
    )

# --- ЛОГІКА ЧАТ-РУЛЕТКИ (ВАУ-ФІЧА) ---
@dp.message(F.text == "Випадковий чат 🎲")
async def start_roulette(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()

    # Шукаємо вільну людину
    cursor.execute("SELECT user_id FROM queue WHERE user_id != %s LIMIT 1", (user_id,))
    partner = cursor.fetchone()

    if partner:
        partner_id = partner[0]
        cursor.execute("DELETE FROM queue WHERE user_id = %s", (partner_id,))
        cursor.execute("INSERT INTO active_chats (user1, user2) VALUES (%s, %s)", (user_id, partner_id))
        conn.commit()
        
        await state.set_state(ChatRoulette.in_chat)
        await state.update_data(partner_id=partner_id)
        
        partner_state = dp.fsm.get_context(bot, user_id=partner_id, chat_id=partner_id)
        await partner_state.set_state(ChatRoulette.in_chat)
        await partner_state.update_data(partner_id=user_id)

        msg = "💎 Пару знайдено! Ви спілкуєтесь анонімно.\nНапиши /stop щоб вийти."
        await message.answer(msg, reply_markup=ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True))
        await bot.send_message(partner_id, msg, reply_markup=ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True))
    else:
        cursor.execute("INSERT INTO queue (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()
        await message.answer("Шукаю тобі пару... 🔍", reply_markup=ReplyKeyboardBuilder().button(text="Скасувати пошук ❌").as_markup(resize_keyboard=True))
    
    cursor.close()
    conn.close()

@dp.message(ChatRoulette.in_chat, Command("stop"))
@dp.message(ChatRoulette.in_chat, F.text == "/stop")
async def stop_chat(message: types.Message, state: FSMContext):
    data = await state.get_data()
    partner_id = data.get("partner_id")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_chats WHERE user1 = %s OR user2 = %s", (message.from_user.id, message.from_user.id))
    conn.commit()
    cursor.close()
    conn.close()

    await state.clear()
    await message.answer("Чат завершено ❤️", reply_markup=get_main_kb())
    
    if partner_id:
        p_state = dp.fsm.get_context(bot, user_id=partner_id, chat_id=partner_id)
        await p_state.clear()
        try:
            await bot.send_message(partner_id, "Співрозмовник завершив чат. ✨", reply_markup=get_main_kb())
        except: pass

@dp.message(ChatRoulette.in_chat)
async def chat_messages(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_id = data.get("partner_id")
    if p_id:
        try:
            if message.text: await bot.send_message(p_id, f"👤: {message.text}")
            elif message.sticker: await bot.send_sticker(p_id, message.sticker.file_id)
        except: await message.answer("Не вдалося надіслати.")

@dp.message(F.text == "Скасувати пошук ❌")
async def cancel_search(message: types.Message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM queue WHERE user_id = %s", (message.from_user.id,))
    conn.commit()
    cursor.close()
    conn.close()
    await message.answer("Пошук скасовано.", reply_markup=get_main_kb())

# --- ВАЛЕНТИНКИ ТА ІНШЕ ---
@dp.message(F.text == "Передбачення Амура ✨")
async def get_prediction(message: types.Message):
    await message.answer(f"🔮 **Твоє передбачення:**\n\n_{random.choice(PREDICTIONS)}_", parse_mode="Markdown")

@dp.message(F.text == "Моя пошта 📮")
async def check_mail(message: types.Message, state: FSMContext):
    username = message.from_user.username.lower() if message.from_user.username else None
    if not username:
        await message.answer("❌ Встанови @username в налаштуваннях!")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.content, v.content_type, v.is_anonymous, u.full_name, u.username 
        FROM valentines v LEFT JOIN users u ON v.sender_id = u.user_id
        WHERE v.receiver_username = %s
    """, (username,))
    mails = cursor.fetchall()
    
    if not mails:
        await message.answer("Пошта порожня... ✨", reply_markup=get_main_kb())
    else:
        for content, c_type, anon, name, s_username in mails:
            label = "🎭 Таємний шанувальник" if anon else f"✍️ Від: {name}"
            kb = InlineKeyboardBuilder()
            if not anon and s_username: kb.button(text="Відповісти 💌", callback_data=f"reply_{s_username}")
            
            if c_type == "sticker":
                await message.answer(f"<b>{label}</b>:", parse_mode="HTML")
                await message.answer_sticker(content, reply_markup=kb.as_markup())
            else:
                await message.answer(f"<b>{label}</b>:\n<tg-spoiler>{content}</tg-spoiler>", parse_mode="HTML", reply_markup=kb.as_markup())
    cursor.close()
    conn.close()

@dp.message(F.text == "Надіслати валентинку 💌")
async def start_val(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📝 Введи **@username** отримувача:", parse_mode="Markdown")
    await state.set_state(SendValentine.waiting_for_receiver)

@dp.message(SendValentine.waiting_for_receiver)
async def process_rec(message: types.Message, state: FSMContext):
    if message.text in ["Моя пошта 📮", "Випадковий чат 🎲"]: return
    await state.update_data(receiver=message.text.replace("@", "").lower().strip())
    await message.answer("Напиши текст або надішли стікер:")
    await state.set_state(SendValentine.waiting_for_message)

@dp.message(SendValentine.waiting_for_message)
async def process_msg(message: types.Message, state: FSMContext):
    c_type = "sticker" if message.sticker else "text"
    content = message.sticker.file_id if message.sticker else message.text
    await state.update_data(content=content, type=c_type)
    kb = ReplyKeyboardBuilder().button(text="Анонімно 🔒").button(text="Підписатися ✍️")
    await message.answer("Як надіслати?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_anon)

@dp.message(SendValentine.waiting_for_anon)
async def process_fin(message: types.Message, state: FSMContext):
    is_anon = 1 if "Анонімно" in message.text else 0
    data = await state.get_data()
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO valentines (sender_id, receiver_username, content, content_type, is_anonymous) VALUES (%s, %s, %s, %s, %s)",
                   (message.from_user.id, data['receiver'], data['content'], data['type'], is_anon))
    cursor.execute("SELECT user_id FROM users WHERE username = %s", (data['receiver'],))
    rec = cursor.fetchone()
    conn.commit(); cursor.close(); conn.close()
    if rec:
        try: await bot.send_message(rec[0], "💘 Тобі прийшла валентинка! Перевір пошту 📮")
        except: pass
    await state.clear()
    await message.answer("🚀 Доставлено!", reply_markup=get_main_kb())

@dp.message(Command("stats"))
async def get_stats(message: types.Message):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM valentines"); v = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users"); u = cursor.fetchone()[0]
    cursor.close(); conn.close()
    await message.answer(f"📊 ❤️ Валентинок: {v} | 👥 Студентів: {u}")

async def main():
    init_db()
    await run_http_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())