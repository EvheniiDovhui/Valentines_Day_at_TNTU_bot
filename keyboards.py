from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_main_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Надіслати валентинку 💌")
    kb.button(text="Випадковий чат 🎲")
    kb.button(text="Ігри Амура 🎮")
    kb.button(text="Моя пошта 📮")
    kb.button(text="Передбачення Амура ✨")
    kb.button(text="Статистика 📈")
    kb.adjust(2, 1, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def get_games_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Правда або Дія 🎭")
    kb.button(text="Стріла Амура 🏹")
    kb.button(text="Сумісність ❤️")
    kb.button(text="Рулетка 🎰")
    kb.button(text="Назад 🔙")
    kb.adjust(1, 2, 1, 1)
    return kb.as_markup(resize_keyboard=True)