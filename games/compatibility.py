import random
from aiogram import types
from aiogram.fsm.state import State, StatesGroup

class LoveTest(StatesGroup):
    waiting_for_name = State()

async def start_love_test(message: types.Message):
    await message.answer("❤️ Введи ім'я людини, з якою хочеш перевірити сумісність:")

async def calculate_love(message: types.Message):
    name = message.text
    percent = random.randint(50, 100) # Нижче 50 не ставимо, щоб не розбудовувати :)
    
    progress_bar = "❤️" * (percent // 10) + "🤍" * (10 - (percent // 10))
    
    res = (
        f"📊 <b>Результат тесту:</b>\n\n"
        f"Ти + {name}\n"
        f"Сумісність: <b>{percent}%</b>\n"
        f"[{progress_bar}]\n\n"
        f"<i>Амур каже: {'Чудова пара!' if percent > 80 else 'Варто спробувати!'}</i>"
    )
    await message.answer(res, parse_mode="HTML")