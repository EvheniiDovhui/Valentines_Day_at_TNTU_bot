from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from database import get_db_connection
from keyboards import get_main_kb
from states import ChatRoulette
from utils import censor_text

router = Router()

@router.message(F.text == "Випадковий чат 🎲")
async def roulette_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardBuilder()
    kb.button(text="Шукати хлопця 👨")
    kb.button(text="Шукати дівчину 👩")
    kb.button(text="Будь-хто 🔄")
    kb.button(text="Назад 🔙")
    kb.adjust(2)
    await message.answer("Кого шукаємо?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(ChatRoulette.choosing_target)

@router.message(ChatRoulette.choosing_target)
async def start_search(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    
    # ОБРОБКА СКАСУВАННЯ ТА ПОВЕРНЕННЯ
    if "Назад" in message.text or "Скасувати пошук ❌" in message.text:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("DELETE FROM queue WHERE user_id = %s", (user_id,))
        conn.commit(); cursor.close(); conn.close()
        
        await state.clear()
        await message.answer("Пошук скасовано.", reply_markup=get_main_kb())
        return

    # Логіка визначення цілі пошуку
    target = "male" if "хлопця" in message.text else "female" if "дівчину" in message.text else "any"
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT gender FROM users WHERE user_id = %s", (user_id,))
    res = cursor.fetchone()
    my_gender = res[0] if res else "any"

    # Пошук партнера
    cursor.execute("""
        SELECT user_id FROM queue 
        WHERE user_id != %s 
        AND (search_gender = %s OR search_gender = 'any') 
        AND (%s = gender OR %s = 'any') 
        LIMIT 1
    """, (user_id, my_gender, target, target))
    partner = cursor.fetchone()

    if partner:
        p_id = partner[0]
        cursor.execute("DELETE FROM queue WHERE user_id = %s", (p_id,))
        cursor.execute("INSERT INTO active_chats (user1, user2) VALUES (%s, %s)", (user_id, p_id))
        conn.commit()
        
        # Встановлюємо стан собі
        await state.set_state(ChatRoulette.in_chat)
        await state.update_data(partner_id=p_id)
        
        # Встановлюємо стан партнеру (через bot.get_context не вийде, тому використовуємо такий хак)
        from bot import dp # Імпортуємо dp для доступу до FSM партнера
        p_state = dp.fsm.get_context(bot, user_id=p_id, chat_id=p_id)
        await p_state.set_state(ChatRoulette.in_chat)
        await p_state.update_data(partner_id=user_id)
        
        msg = "💎 Пару знайдено! Напиши /stop для виходу."
        kb = ReplyKeyboardBuilder().button(text="/stop").as_markup(resize_keyboard=True)
        await message.answer(msg, reply_markup=kb)
        await bot.send_message(p_id, msg, reply_markup=kb)
    else:
        # Додаємо в чергу
        cursor.execute("""
            INSERT INTO queue (user_id, gender, search_gender) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id) 
            DO UPDATE SET search_gender = EXCLUDED.search_gender
        """, (user_id, my_gender, target))
        conn.commit()
        
        kb = ReplyKeyboardBuilder().button(text="Скасувати пошук ❌").as_markup(resize_keyboard=True)
        await message.answer("Шукаю пару... 🔍", reply_markup=kb)
    
    cursor.close(); conn.close()

@router.message(ChatRoulette.in_chat)
async def chat_messages(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    p_id = data.get("partner_id")
    
    if message.text == "/stop":
        user_id = message.from_user.id
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("DELETE FROM active_chats WHERE user1 = %s OR user2 = %s", (user_id, user_id))
        conn.commit(); cursor.close(); conn.close()
        
        await state.clear()
        await message.answer("Чат завершено ❤️", reply_markup=get_main_kb())
        
        if p_id:
            try:
                await bot.send_message(p_id, "Співрозмовник вийшов з чату. ✨", reply_markup=get_main_kb())
                from bot import dp
                p_state = dp.fsm.get_context(bot, user_id=p_id, chat_id=p_id)
                await p_state.clear()
            except:
                pass
        return

    if p_id:
        try:
            if message.text:
                await bot.send_message(p_id, f"👤: {censor_text(message.text)}")
            elif message.sticker:
                await bot.send_sticker(p_id, message.sticker.file_id)
        except:
            await message.answer("⚠️ Не вдалося надіслати повідомлення партнеру.")