import asyncio
import psycopg2
import logging
import os
import random
import re
from aiohttp import web
from dotenv import load_dotenv

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError

# Імпорт наших модулів
from config import PREDICTIONS
from utils import censor_text

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# --- КОНФІГУРАЦІЯ ---
load_dotenv(dotenv_path="api.env")
API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_ME_ID = os.getenv("TELEGRAM_ME_ID")
logging.basicConfig(level=logging.INFO)

# --- СТАНИ (FSM) ---
class Registration(StatesGroup):
    waiting_for_gender = State()

class SendValentine(StatesGroup):
    waiting_for_receiver = State()
    waiting_for_message = State()
    waiting_for_anon = State()

class ChatRoulette(StatesGroup):
    choosing_target = State()
    in_chat = State()

# --- БАЗА ДАНИХ ---
def get_db_connection():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)

def init_db():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT, gender TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS valentines (
        id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_username TEXT, 
        content TEXT, content_type TEXT, is_anonymous INTEGER)""")
    cursor.execute("CREATE TABLE IF NOT EXISTS active_chats (user1 BIGINT PRIMARY KEY, user2 BIGINT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS queue (user_id BIGINT PRIMARY KEY, gender TEXT, search_gender TEXT)")
    
    cursor.execute("DELETE FROM queue")
    cursor.execute("DELETE FROM active_chats")
    conn.commit(); cursor.close(); conn.close()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
BOT_ACTIVE = False  # Постав False, якщо хочеш вимкнути бота

def get_main_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Надіслати валентинку 💌")
    kb.button(text="Випадковий чат 🎲")
    kb.button(text="Моя пошта 📮")
    kb.button(text="Передбачення Амура ✨")
    kb.button(text="Статистика 📈") # Нова кнопка
    kb.adjust(2, 2, 1) # Групуємо кнопки: 2 в ряд, 2 в ряд і 1 внизу
    return kb.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    # ПЕРЕВІРКА АКТИВНОСТІ
    if not BOT_ACTIVE:
        await message.answer(
            "👋 <b>Дякуємо!</b>\n\nПошта Амура ТНТУ завершила свою роботу цього сезону. "
            "Ми вже готуємо стріли на наступний рік! 🏹\n\n"
            "Бот знову запрацює до наступного <b>Дня святого Валентина</b>. До зустрічі! ❤️",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove() # Прибираємо старі кнопки, щоб не плутати
        )
        return

    # Твоя звичайна логіка (якщо бот активний)
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

@dp.message(Registration.waiting_for_gender)
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

# --- ЧАТ РУЛЕТКА ---

@dp.message(F.text == "Випадковий чат 🎲")
async def roulette_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardBuilder()
    kb.button(text="Шукати хлопця 👨")
    kb.button(text="Шукати дівчину 👩")
    kb.button(text="Будь-хто 🔄")
    kb.button(text="Назад 🔙")
    kb.adjust(2)
    await message.answer("Кого шукаємо?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(ChatRoulette.choosing_target)

@dp.message(ChatRoulette.choosing_target)
async def start_search(message: types.Message, state: FSMContext):
    if "Назад" in message.text or "Скасувати пошук ❌" in message.text:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("DELETE FROM queue WHERE user_id = %s", (message.from_user.id,))
        conn.commit(); cursor.close(); conn.close()
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=get_main_kb())
        return

    target = "male" if "хлопця" in message.text else "female" if "дівчину" in message.text else "any"
    user_id = message.from_user.id
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT gender FROM users WHERE user_id = %s", (user_id,))
    my_gender = cursor.fetchone()[0]

    query = """
        SELECT user_id FROM queue 
        WHERE user_id != %s 
        AND (search_gender = %s OR search_gender = 'any')
        AND (%s = gender OR %s = 'any')
        LIMIT 1
    """
    cursor.execute(query, (user_id, my_gender, target, target))
    partner = cursor.fetchone()

    if partner:
        p_id = partner[0]
        cursor.execute("DELETE FROM queue WHERE user_id = %s", (p_id,))
        cursor.execute("INSERT INTO active_chats (user1, user2) VALUES (%s, %s)", (user_id, p_id))
        conn.commit()
        
        await state.set_state(ChatRoulette.in_chat); await state.update_data(partner_id=p_id)
        p_state = dp.fsm.get_context(bot, user_id=p_id, chat_id=p_id)
        await p_state.set_state(ChatRoulette.in_chat); await p_state.update_data(partner_id=user_id)
        
        msg = "💎 Пару знайдено! Напиши /stop для виходу."
        await message.answer(msg, reply_markup=ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True))
        await bot.send_message(p_id, msg, reply_markup=ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True))
    else:
        cursor.execute("INSERT INTO queue (user_id, gender, search_gender) VALUES (%s, %s, %s) "
                       "ON CONFLICT (user_id) DO UPDATE SET search_gender = EXCLUDED.search_gender", 
                       (user_id, my_gender, target))
        conn.commit()
        await message.answer("Шукаю пару... 🔍", 
                             reply_markup=ReplyKeyboardBuilder().button(text="Скасувати пошук ❌").as_markup(resize_keyboard=True))
    cursor.close(); conn.close()

@dp.message(F.text == "Скасувати пошук ❌")
async def global_cancel_search(message: types.Message, state: FSMContext):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM queue WHERE user_id = %s", (message.from_user.id,))
    conn.commit(); cursor.close(); conn.close()
    await state.clear()
    await message.answer("Пошук припинено.", reply_markup=get_main_kb())

@dp.message(ChatRoulette.in_chat)
async def chat_messages(message: types.Message, state: FSMContext):
    data = await state.get_data(); p_id = data.get("partner_id")
    if message.text == "/stop":
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("DELETE FROM active_chats WHERE user1 = %s OR user2 = %s", (message.from_user.id, message.from_user.id))
        conn.commit(); cursor.close(); conn.close()
        await state.clear(); await message.answer("Чат завершено ❤️", reply_markup=get_main_kb())
        if p_id:
            await bot.send_message(p_id, "Співрозмовник вийшов. ✨", reply_markup=get_main_kb())
            await dp.fsm.get_context(bot, user_id=p_id, chat_id=p_id).clear()
        return

    if p_id:
        try:
            if message.text:
                await bot.send_message(p_id, f"👤: {censor_text(message.text)}")
            elif message.sticker:
                await bot.send_sticker(p_id, message.sticker.file_id)
        except: pass

# --- ВАЛЕНТИНКИ ---

@dp.message(F.text == "Надіслати валентинку 💌")
async def start_val(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardBuilder().button(text="Скасувати ❌")
    await message.answer("📝 Введіть <b>@username</b> отримувача (наприклад, @tntu_student):", 
                         parse_mode="HTML", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_receiver)

@dp.message(F.text == "Скасувати ❌", SendValentine())
async def cancel_valentine(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Надсилання скасовано. 🕊️", reply_markup=get_main_kb())

@dp.message(SendValentine.waiting_for_receiver)
async def process_rec(message: types.Message, state: FSMContext):
    if "Скасувати ❌" in message.text: return
    if not message.text or not message.text.startswith("@"):
        await message.answer("❌ Вкажіть нікнейм через @")
        return
    await state.update_data(receiver=message.text.replace("@", "").lower().strip())
    kb = ReplyKeyboardBuilder().button(text="Скасувати ❌")
    await message.answer("Напишіть текст або надішліть стікер:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_message)

@dp.message(SendValentine.waiting_for_message)
async def process_msg(message: types.Message, state: FSMContext):
    if message.text == "Скасувати ❌": return
    c_type = "sticker" if message.sticker else "text"
    content = message.sticker.file_id if message.sticker else message.text
    if c_type == "text":
        content = censor_text(content)
    await state.update_data(content=content, type=c_type)
    
    kb = ReplyKeyboardBuilder()
    kb.button(text="Анонімно 🔒")
    kb.button(text="Підписатися ✍️")
    kb.button(text="Скасувати ❌")
    kb.adjust(2, 1)
    await message.answer("Як надіслати?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_anon)

@dp.message(SendValentine.waiting_for_anon)
async def process_fin(message: types.Message, state: FSMContext):
    if "Скасувати ❌" in message.text: return
    is_anon = 1 if "Анонімно" in message.text else 0
    data = await state.get_data(); s_id = message.from_user.id
    s_un = message.from_user.username.lower() if message.from_user.username else None
    r_un = data['receiver']

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO valentines (sender_id, receiver_username, content, content_type, is_anonymous) "
                   "VALUES (%s, %s, %s, %s, %s)", (s_id, r_un, data['content'], data['type'], is_anon))
    
    cursor.execute("SELECT sender_id FROM valentines WHERE sender_id = (SELECT user_id FROM users WHERE username = %s LIMIT 1) "
                   "AND receiver_username = %s LIMIT 1", (r_un, s_un))
    match = cursor.fetchone()
    
    cursor.execute("SELECT user_id FROM users WHERE username = %s", (r_un,))
    rec_data = cursor.fetchone()
    conn.commit()

    if match and rec_data and s_un:
        await message.answer("🔥 <b>IT'S A MATCH!</b> ❤️", parse_mode="HTML")
        try: await bot.send_message(rec_data[0], f"🔥 <b>IT'S A MATCH!</b> ❤️\n@{s_un} теж надіслав валентинку!", parse_mode="HTML")
        except: pass
    elif rec_data:
        try: await bot.send_message(rec_data[0], "💘 Нова валентинка! Перевір пошту 📮")
        except: pass

    await message.answer("🚀 Доставлено!", reply_markup=get_main_kb())
    cursor.close(); conn.close(); await state.clear()

# --- ПОШТА ТА ПЕРЕДБАЧЕННЯ ---

@dp.message(F.text == "Моя пошта 📮")
async def check_mail(message: types.Message):
    un = message.from_user.username.lower() if message.from_user.username else None
    if not un:
        await message.answer("❌ Встановіть @username!")
        return
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT v.content, v.content_type, v.is_anonymous, u.full_name, u.username "
                   "FROM valentines v LEFT JOIN users u ON v.sender_id = u.user_id "
                   "WHERE v.receiver_username = %s", (un,))
    mails = cursor.fetchall()
    
    if not mails:
        await message.answer("📬 <b>Твоя скринька поки що порожня...</b>\n\nМожливо, твоя половинка чекає на перший крок? Надішли валентинку комусь особливому прямо зараз! 😉 ✨", parse_mode="HTML")
    else:
        for ct, tp, an, nm, sun in mails:
            lb = "🎭 Таємний шанувальник" if an else f"✍️ Від: {nm}"
            if tp == "sticker":
                await message.answer(lb); await message.answer_sticker(ct)
            else:
                await message.answer(f"<b>{lb}</b>:\n<tg-spoiler>{ct}</tg-spoiler>", parse_mode="HTML")
    cursor.close(); conn.close()

@dp.message(F.text == "Передбачення Амура ✨")
async def get_prediction(message: types.Message):
    res = f"🔮 <b>Твоє передбачення на сьогодні:</b>\n\n<i>{random.choice(PREDICTIONS)}</i>"
    await message.answer(res, parse_mode="HTML")

@dp.message(F.text == "Статистика 📈")
async def show_stats(message: types.Message):
    conn = get_db_connection(); cursor = conn.cursor()
    # Кількість людей у черзі
    cursor.execute("SELECT COUNT(*) FROM queue")
    q = cursor.fetchone()[0]
    # Кількість активних пар
    cursor.execute("SELECT COUNT(*) FROM active_chats")
    a = cursor.fetchone()[0]
    # Загальна кількість користувачів бота
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    # Загальна кількість надісланих валентинок
    cursor.execute("SELECT COUNT(*) FROM valentines")
    v = cursor.fetchone()[0]
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

@dp.message(Command("broadcast_end"))
async def broadcast_finish(message: types.Message):
    if message.from_user.id != TELEGRAM_ME_ID:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    cursor.close(); conn.close()

    count = 0
    blocked_count = 0
    
    await message.answer(f"🚀 Починаю розсилку для {len(users)} людей...")

    for user in users:
        user_id = user[0]
        try:
            await bot.send_message(
                user[0], 
                "❤️ <b>Пошта Амура ТНТУ завершує свою роботу цього року!</b>\n\n"
                "Дякуємо, що були з нами, надсилали валентинки та знаходили нові знайомства. "
                "Бот іде на відпочинок, але рівно за рік, на наступний День святого Валентина, "
                "ми знову відкриємо наші двері для ваших палких сердець! 🏹\n\n"
                "До зустрічі у 2027 році! ✨",
                parse_mode="HTML"
            )
            count += 1
            # Чекаємо 0.05 сек (20 повідомлень на секунду), щоб не отримати бан за спам
            await asyncio.sleep(0.05) 

        except TelegramForbiddenError:
            # Юзер заблокував бота
            blocked_count += 1
            logging.warning(f"Користувач {user_id} заблокував бота.")
            
        except TelegramRetryAfter as e:
            # Якщо Telegram просить зачекати (флуд-контроль)
            logging.error(f"Флуд-ліміт! Чекаємо {e.retry_after} секунд.")
            await asyncio.sleep(e.retry_after)
            # Можна спробувати надіслати ще раз після очікування
            
        except TelegramAPIError as e:
            # Будь-яка інша помилка Telegram (наприклад, юзера не існує)
            logging.error(f"Помилка API для {user_id}: {e}")
            
        except Exception as e:
            # Всі інші помилки (наприклад, проблеми з мережею)
            logging.error(f"Непередбачена помилка для {user_id}: {e}")

    await message.answer(
        f"✅ <b>Розсилка завершена!</b>\n\n"
        f"📥 Отримали: {count}\n"
        f"🚫 Заблокували: {blocked_count}",
        parse_mode="HTML"
    )

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())