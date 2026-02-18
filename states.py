from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    waiting_for_gender = State()

class SendValentine(StatesGroup):
    waiting_for_receiver = State()
    waiting_for_message = State()
    waiting_for_anon = State()

class ChatRoulette(StatesGroup):
    choosing_target = State()
    in_chat = State()

class LoveTest(StatesGroup):
    waiting_for_name = State()