import psycopg2
import os
from dotenv import load_dotenv

# Завантажуємо змінні, щоб database.py їх бачив
load_dotenv(dotenv_path="api.env")

def get_db_connection():
    # Отримуємо URL з api.env
    url = os.getenv("DATABASE_URL")
    
    if not url:
        raise ValueError("DATABASE_URL не знайдено в api.env!")

    # Neon DB іноді потребує заміни postgres:// на postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    # Підключаємося
    return psycopg2.connect(url)

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Створення таблиць (якщо їх немає)
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT, gender TEXT)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS valentines (
            id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_username TEXT, 
            content TEXT, content_type TEXT, is_anonymous INTEGER)""")
        
        cursor.execute("CREATE TABLE IF NOT EXISTS active_chats (user1 BIGINT PRIMARY KEY, user2 BIGINT)")
        
        cursor.execute("CREATE TABLE IF NOT EXISTS queue (user_id BIGINT PRIMARY KEY, gender TEXT, search_gender TEXT)")
        
        # Очищення тимчасових даних при перезапуску
        cursor.execute("DELETE FROM queue")
        cursor.execute("DELETE FROM active_chats")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ База даних Neon підключена успішно!")
    except Exception as e:
        print(f"❌ Помилка БД: {e}")