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
    "Твій таємний шанувальник поставив лайк на твій наступний сторіз. ❤️",
    "Амур каже: час надіслати валентинку тій самій людині... 😉",
    "Твоє кохання сильніше, ніж черга в їдальні ТНТУ! 🍕",
    "Сьогодні ідеальний день для кави з кимось особливим. ☕",
    "Хтось мріє отримати від тебе повідомлення прямо зараз. 💌",
    "Твій інтелект сьогодні — твоя найкраща риса! 🧠🔥",
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
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS valentines (
        id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_username TEXT, 
        content TEXT, content_type TEXT, is_anonymous INTEGER)""")
    cursor.execute("CREATE TABLE IF NOT EXISTS active_chats (user1 BIGINT PRIMARY KEY, user2 BIGINT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS queue (user_id BIGINT PRIMARY KEY)")
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
        "Обирай дію 👇", 
        parse_mode="Markdown", reply_markup=get_main_kb()
    )

# --- ЧАТ РУЛЕТКА ---
@dp.message(F.text == "Випадковий чат 🎲")
async def start_roulette(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM queue WHERE user_id != %s LIMIT 1", (user_id,))
    partner = cursor.fetchone()

    if partner:
        partner_id = partner[0]
        cursor.execute("DELETE FROM queue WHERE user_id = %s", (partner_id,))
        cursor.execute("INSERT INTO active_chats (user1, user2) VALUES (%s, %s)", (user_id, partner_id))
        conn.commit()
        await state.set_state(ChatRoulette.in_chat); await state.update_data(partner_id=partner_id)
        p_state = dp.fsm.get_context(bot, user_id=partner_id, chat_id=partner_id)
        await p_state.set_state(ChatRoulette.in_chat); await p_state.update_data(partner_id=user_id)
        msg = "💎 Пару знайдено! Напиши /stop для виходу."
        await message.answer(msg, reply_markup=ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True))
        await bot.send_message(partner_id, msg, reply_markup=ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True))
    else:
        cursor.execute("INSERT INTO queue (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        conn.commit()
        await message.answer("Шукаю пару... 🔍", reply_markup=ReplyKeyboardBuilder().button(text="Скасувати пошук ❌").as_markup(resize_keyboard=True))
    cursor.close(); conn.close()

@dp.message(ChatRoulette.in_chat, F.text == "/stop")
async def stop_chat(message: types.Message, state: FSMContext):
    data = await state.get_data(); p_id = data.get("partner_id")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM active_chats WHERE user1 = %s OR user2 = %s", (message.from_user.id, message.from_user.id))
    conn.commit(); cursor.close(); conn.close()
    await state.clear(); await message.answer("Чат завершено ❤️", reply_markup=get_main_kb())
    if p_id:
        p_state = dp.fsm.get_context(bot, user_id=p_id, chat_id=p_id)
        await p_state.clear()
        try: await bot.send_message(p_id, "Співрозмовник вийшов. ✨", reply_markup=get_main_kb())
        except: pass

@dp.message(ChatRoulette.in_chat)
async def chat_messages(message: types.Message, state: FSMContext):
    data = await state.get_data(); p_id = data.get("partner_id")
    if p_id:
        try:
            if message.text: await bot.send_message(p_id, f"👤: {message.text}")
            elif message.sticker: await bot.send_sticker(p_id, message.sticker.file_id)
        except: pass

@dp.message(F.text == "Скасувати пошук ❌")
async def cancel_search(message: types.Message):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM queue WHERE user_id = %s", (message.from_user.id,))
    conn.commit(); cursor.close(); conn.close()
    await message.answer("Скасовано.", reply_markup=get_main_kb())

# --- ВАЛЕНТИНКИ ТА MATCH СИСТЕМА ---
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
    s_id = message.from_user.id
    s_un = message.from_user.username.lower() if message.from_user.username else None
    r_un = data['receiver']

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO valentines (sender_id, receiver_username, content, content_type, is_anonymous) VALUES (%s, %s, %s, %s, %s)",
                   (s_id, r_un, data['content'], data['type'], is_anon))
    
    # ПЕРЕВІРКА НА MATCH
    cursor.execute("SELECT sender_id FROM valentines WHERE sender_id = (SELECT user_id FROM users WHERE username = %s LIMIT 1) AND receiver_username = %s LIMIT 1", (r_un, s_un))
    match = cursor.fetchone()
    cursor.execute("SELECT user_id FROM users WHERE username = %s", (r_un,))
    rec_data = cursor.fetchone()
    conn.commit()

    if match and rec_data and s_un:
        m_msg = f"🔥 **IT'S A MATCH!** ❤️\n\nВи з @{r_un} обмінялися валентинками! Це взаємно! 😍"
        await message.answer(m_msg, parse_mode="Markdown")
        try: await bot.send_message(rec_data[0], f"🔥 **IT'S A MATCH!** ❤️\n\nКористувач @{s_un} теж надіслав тобі валентинку!", parse_mode="Markdown")
        except: pass
    elif rec_data:
        try: await bot.send_message(rec_data[0], "💘 Тобі прийшла нова валентинка! Перевір пошту 📮")
        except: pass
        await message.answer("🚀 Доставлено!", reply_markup=get_main_kb())
    
    cursor.close(); conn.close(); await state.clear()

# --- ІНШЕ ТА АДМІН СТАТИСТИКА ---
@dp.message(F.text == "Передбачення Амура ✨")
async def get_prediction(message: types.Message):
    await message.answer(f"🔮 **Твоє передбачення:**\n\n_{random.choice(PREDICTIONS)}_", parse_mode="Markdown")

@dp.message(F.text == "Моя пошта 📮")
async def check_mail(message: types.Message, state: FSMContext):
    un = message.from_user.username.lower() if message.from_user.username else None
    if not un: await message.answer("❌ Встанови @username!"); return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT v.content, v.content_type, v.is_anonymous, u.full_name, u.username FROM valentines v LEFT JOIN users u ON v.sender_id = u.user_id WHERE v.receiver_username = %s", (un,))
    mails = cursor.fetchall()
    if not mails: await message.answer("Пошта порожня... ✨")
    else:
        for ct, tp, an, nm, sun in mails:
            lb = "🎭 Таємний шанувальник" if an else f"✍️ Від: {nm}"
            kb = InlineKeyboardBuilder()
            if not an and sun: kb.button(text="Відповісти 💌", callback_data=f"reply_{sun}")
            if tp == "sticker": await message.answer_sticker(ct, reply_markup=kb.as_markup())
            else: await message.answer(f"<b>{lb}</b>:\n<tg-spoiler>{ct}</tg-spoiler>", parse_mode="HTML", reply_markup=kb.as_markup())
    cursor.close(); conn.close()

@dp.message(Command("admin_stats"))
async def get_admin_stats(message: types.Message):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users"); u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM valentines"); v = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM queue"); q = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM active_chats"); a = cursor.fetchone()[0]
    cursor.close(); conn.close()
    await message.answer(f"📊 **Статистика:**\n👥 Юзерів: {u}\n💌 Валентинок: {v}\n🔍 В черзі: {q}\n💬 Пар у чаті: {a}", parse_mode="Markdown")

async def main():
    init_db(); await run_http_server(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())