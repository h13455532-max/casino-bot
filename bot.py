import telebot
import os
import logging
import threading
from flask import Flask
from config import TOKEN, CASINO_NAME
from db_manager import DB
import handlers # Импортируем твой огромный файл с логикой

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация
bot = telebot.TeleBot(TOKEN)
db = DB()

# Регистрация всех команд из handlers.py
try:
    handlers.register_handlers(bot)
    logging.info("Все хендлеры успешно зарегистрированы!")
except Exception as e:
    logging.error(f"Критическая ошибка при регистрации хендлеров: {e}")

# --- KEEP ALIVE СЕРВЕР ДЛЯ RENDER ---
app = Flask(__name__)

@app.route('/')
def main():
    return "Casino Bot is Alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# --- ЗАПУСК ---
if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    
    logging.info(f"Бот {CASINO_NAME} запускается...")
    
    # Бесконечный цикл с защитой от вылетов
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logging.error(f"Ошибка Polling: {e}")
            import time
            time.sleep(5) # Пауза перед перезапуском при сбое сети
