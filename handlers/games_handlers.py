from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from database import get_db_connection
from keyboards import get_main_kb, get_games_kb
from states import LoveTest
from games.arrow import play_arrow
from games.roulette import play_roulette
from games.compatibility import start_love_test, calculate_love
from games.truth_or_dare import play_truth_or_dare, get_truth, get_dare

router = Router()

# --- Головне меню ігор ---
@router.message(F.text == "Ігри Амура 🎮")
async def games_menu(message: types.Message):
    await message.answer("Оберіть розвагу:", reply_markup=get_games_kb())

# --- Правда або Дія ---
@router.message(F.text == "Правда або Дія 🎭")
async def handle_tod(message: types.Message): 
    await play_truth_or_dare(message)

@router.message(F.text == "Правда 🧐")
async def handle_truth(message: types.Message): 
    await get_truth(message)

@router.message(F.text == "Дія 🔥")
async def handle_dare(message: types.Message): 
    await get_dare(message)

@router.message(F.text == "Назад до ігор 🔙")
async def back_to_games_from_tod(message: types.Message):
    await message.answer("Повертаємось до списку ігор:", reply_markup=get_games_kb())

# --- Стріла Амура ---
@router.message(F.text == "Стріла Амура 🏹")
async def handle_arrow(message: types.Message): 
    await play_arrow(message, get_db_connection)

# --- Рулетка ---
@router.message(F.text == "Рулетка 🎰")
async def handle_roulette(message: types.Message): 
    await play_roulette(message)

# --- Тест на сумісність (FSM) ---
@router.message(F.text == "Сумісність ❤️")
async def handle_love_test(message: types.Message, state: FSMContext):
    await state.set_state(LoveTest.waiting_for_name)
    await start_love_test(message)

@router.message(LoveTest.waiting_for_name)
async def handle_love_calculation(message: types.Message, state: FSMContext):
    await calculate_love(message)
    await state.clear()
    # Після гри краще показувати меню ігор, а не головне
    await message.answer("Бажаєте спробувати ще щось?", reply_markup=get_games_kb())

# --- Навігація назад ---
@router.message(F.text == "Назад 🔙")
async def back_to_main(message: types.Message):
    await message.answer("Головне меню:", reply_markup=get_main_kb())