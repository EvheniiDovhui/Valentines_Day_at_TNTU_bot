import random
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

async def play_arrow(message: types.Message, get_db_connection):
    user_id = message.from_user.id
    conn = get_db_connection(); cursor = conn.cursor()
    
    # Визначаємо стать користувача
    cursor.execute("SELECT gender FROM users WHERE user_id = %s", (user_id,))
    res = cursor.fetchone()
    my_gender = res[0] if res else 'male'
    target_gender = 'female' if my_gender == 'male' else 'male'

    # Шукаємо випадкову людину протилежної статі
    cursor.execute(
        "SELECT username, full_name FROM users WHERE gender = %s AND user_id != %s ORDER BY RANDOM() LIMIT 1",
        (target_gender, user_id)
    )
    target = cursor.fetchone()
    cursor.close(); conn.close()

    if target:
        un, name = target
        text = f"🏹 <b>Стріла Амура влучила!</b>\n\nАмур вважає, що тобі варто познайомитися з: <b>{name}</b>"
        kb = InlineKeyboardBuilder()
        if un:
            kb.button(text="Написати 💌", url=f"https://t.me/{un}")
        
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer("Стріла пролетіла повз... Можливо, ще мало людей у базі. ✨")