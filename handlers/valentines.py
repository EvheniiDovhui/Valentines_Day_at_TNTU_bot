from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from database import get_db_connection
from keyboards import get_main_kb
from states import SendValentine
from utils import censor_text
import os

router = Router()

@router.message(F.text == "Надіслати валентинку 💌")
async def start_val(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardBuilder().button(text="Скасувати ❌")
    await message.answer("📝 Введіть <b>@username</b> отримувача (наприклад, @student_tntu):", 
                         parse_mode="HTML", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_receiver)

@router.message(F.text == "Скасувати ❌", SendValentine())
async def cancel_valentine(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Надсилання скасовано. 🕊️", reply_markup=get_main_kb())

@router.message(SendValentine.waiting_for_receiver)
async def process_rec(message: types.Message, state: FSMContext):
    if not message.text or not message.text.startswith("@"):
        await message.answer("❌ Вкажіть нікнейм через @")
        return
    await state.update_data(receiver=message.text.replace("@", "").lower().strip())
    await message.answer("Напишіть текст або надішліть стікер:")
    await state.set_state(SendValentine.waiting_for_message)

@router.message(SendValentine.waiting_for_message)
async def process_msg(message: types.Message, state: FSMContext):
    c_type = "sticker" if message.sticker else "text"
    content = message.sticker.file_id if message.sticker else message.text
    if c_type == "text":
        content = censor_text(content)
    await state.update_data(content=content, type=c_type)
    
    kb = ReplyKeyboardBuilder().button(text="Анонімно 🔒").button(text="Підписатися ✍️").button(text="Скасувати ❌")
    kb.adjust(2, 1)
    await message.answer("Як надіслати?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(SendValentine.waiting_for_anon)

@router.message(SendValentine.waiting_for_anon)
async def process_fin(message: types.Message, state: FSMContext, bot: Bot):
    is_anon = 1 if "Анонімно" in message.text else 0
    data = await state.get_data()
    s_id, s_un = message.from_user.id, (message.from_user.username.lower() if message.from_user.username else None)
    r_un = data['receiver']

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO valentines (sender_id, receiver_username, content, content_type, is_anonymous) VALUES (%s, %s, %s, %s, %s)",
                   (s_id, r_un, data['content'], data['type'], is_anon))
    
    # Перевірка на MATCH
    cursor.execute("SELECT sender_id FROM valentines WHERE sender_id = (SELECT user_id FROM users WHERE username = %s LIMIT 1) AND receiver_username = %s LIMIT 1", (r_un, s_un))
    match = cursor.fetchone()
    cursor.execute("SELECT user_id FROM users WHERE username = %s", (r_un,))
    rec_data = cursor.fetchone(); conn.commit()

    if match and rec_data and s_un:
        await message.answer("🔥 <b>IT'S A MATCH!</b> ❤️\nВи обмінялися валентинками!", parse_mode="HTML")
        try: await bot.send_message(rec_data[0], f"🔥 <b>IT'S A MATCH!</b> ❤️\n@{s_un} теж надіслав тобі валентинку!", parse_mode="HTML")
        except: pass
    elif rec_data:
        try: await bot.send_message(rec_data[0], "💘 Нова валентинка! Перевір пошту 📮")
        except: pass

    await message.answer("🚀 Доставлено!", reply_markup=get_main_kb())
    cursor.close(); conn.close(); await state.clear()

@router.message(F.text == "Моя пошта 📮")
async def check_mail(message: types.Message):
    un = message.from_user.username.lower() if message.from_user.username else None
    if not un:
        await message.answer("❌ Встановіть @username!")
        return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT v.content, v.content_type, v.is_anonymous, u.full_name, u.username FROM valentines v LEFT JOIN users u ON v.sender_id = u.user_id WHERE v.receiver_username = %s", (un,))
    mails = cursor.fetchall()
    if not mails:
        await message.answer("📬 Скринька порожня... Зроби перший крок! ✨")
    else:
        for ct, tp, an, nm, sun in mails:
            lb = "🎭 Таємний шанувальник" if an else f"✍️ Від: {nm}"
            if tp == "sticker": await message.answer(lb); await message.answer_sticker(ct)
            else: await message.answer(f"<b>{lb}</b>:\n<tg-spoiler>{ct}</tg-spoiler>", parse_mode="HTML")
    cursor.close(); conn.close()