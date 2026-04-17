import telebot
import sqlite3
import random
import os
import time
import logging
import threading
import datetime
from telebot import types
from flask import Flask

# ==========================================
# 1. КОНФИГУРАЦИЯ (Берем данные из Config)
# ==========================================
TOKEN = os.environ.get("TOKEN")
bot = telebot.TeleBot(TOKEN)

ADMIN_IDS = [8357023784, 8539734813]
LOG_CHANNEL_ID = -1003951162583 
CRYPTO_LINK = "http://t.me/send?start=IVpZKHj5lZFO"
CASINO_NAME = "NEZZX x KLITOK CASINO"
WIN_IMAGE = "win.png"

# Настройка логирования для Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 2. БАЗА ДАННЫХ (SQLite внутри файла)
# ==========================================
class Database:
    def __init__(self, db_name="casino_pro.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                reg_date TEXT
            )
        """)
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()

    def register_user(self, user_id, username):
        if not self.get_user(user_id):
            cursor = self.conn.cursor()
            date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO users (id, username, balance, reg_date) VALUES (?, ?, ?, ?)",
                           (user_id, username, 0.0, date))
            self.conn.commit()

    def update_balance(self, user_id, amount):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        self.conn.commit()

db = Database()

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def send_log(text):
    try:
        bot.send_message(LOG_CHANNEL_ID, f"📑 **LOG:**\n{text}", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка логов: {e}")

def get_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎲 ИГРАТЬ", "💰 БАЛАНС")
    markup.add("💎 ПОПОЛНИТЬ", "💸 ВЫВОД")
    if user_id in ADMIN_IDS:
        markup.add("🛠 АДМИНКА")
    return markup

def check_win_photo(chat_id, text):
    if os.path.exists(WIN_IMAGE):
        with open(WIN_IMAGE, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=f"🎰 **{CASINO_NAME}**\n\n{text}", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, f"🏆 **ПОБЕДА!**\n\n{text}", parse_mode='Markdown')

# ==========================================
# 4. ОБРАБОТКА КОМАНД
# ==========================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Игрок"
    db.register_user(user_id, username)
    
    welcome_text = (
        f"🎰 **ДОБРО ПОЖАЛОВАТЬ В {CASINO_NAME}**\n\n"
        f"Здесь ты можешь умножить свою крипту!\n"
        f"Используй меню ниже для навигации."
    )
    bot.send_message(user_id, welcome_text, reply_markup=get_main_menu(user_id), parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "💰 БАЛАНС")
def balance_view(message):
    user = db.get_user(message.from_user.id)
    bot.reply_to(message, f"💰 Ваш баланс: `{user[2]:.2f}` USD", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "💎 ПОПОЛНИТЬ")
def deposit_view(message):
    text = (f"💎 **ПОПОЛНЕНИЕ**\n\n"
            f"Для оплаты перейдите по ссылке:\n{CRYPTO_LINK}\n\n"
            f"После оплаты отправьте скриншот чека админу!")
    bot.send_message(message.chat.id, text, parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(func=lambda m: m.text == "🎲 ИГРАТЬ")
def games_view(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎲 Кубики", callback_data="game_dice"),
        types.InlineKeyboardButton("🎰 Слоты", callback_data="game_slots"),
        types.InlineKeyboardButton("🪙 Монетка", callback_data="game_coin")
    )
    bot.send_message(message.chat.id, "🎯 **Выбери игру:**", reply_markup=markup, parse_mode='Markdown')

# ==========================================
# 5. ИГРОВАЯ МАТЕМАТИКА
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def handle_game(call):
    game_type = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму ставки:**")
    bot.register_next_step_handler(msg, process_game_bet, game_type)

def process_game_bet(message, game_type):
    try:
        bet = float(message.text.replace(',', '.'))
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        if bet < 0.1:
            return bot.reply_to(message, "❌ Ставка слишком мала!")
        if bet > user[2]:
            return bot.reply_to(message, "❌ Недостаточно средств!")

        db.update_balance(user_id, -bet)
        
        if game_type == "dice":
            d = bot.send_dice(message.chat.id, emoji='🎲')
            time.sleep(3)
            if d.dice.value >= 4:
                win = bet * 1.8
                db.update_balance(user_id, win)
                check_win_photo(message.chat.id, f"Выпало {d.dice.value}! Выигрыш: `{win:.2f}`")
            else:
                bot.send_message(message.chat.id, f"💀 Проигрыш! Выпало {d.dice.value}")

        elif game_type == "slots":
            s = bot.send_dice(message.chat.id, emoji='🎰')
            time.sleep(4)
            if s.dice.value in [1, 22, 43, 64]:
                win = bet * 10
                db.update_balance(user_id, win)
                check_win_photo(message.chat.id, f"🔥 ДЖЕКПОТ! Выигрыш: `{win:.2f}`")
            else:
                bot.send_message(message.chat.id, "❌ Попробуй еще раз!")

        send_log(f"Игрок `{user_id}` сыграл в {game_type} на `{bet}`")
        
    except:
        bot.reply_to(message, "⚠️ Введите число!")

# ==========================================
# 6. АДМИН-ПАНЕЛЬ И ВЫВОД
# ==========================================
@bot.message_handler(func=lambda m: m.text == "🛠 АДМИНКА")
def admin_menu(message):
    if message.from_user.id not in ADMIN_IDS: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💰 Выдать баланс", callback_data="adm_give"))
    bot.send_message(message.chat.id, "👨‍💻 Админ-панель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_give")
def adm_give_call(call):
    msg = bot.send_message(call.message.chat.id, "Введите: `ID СУММА` (через пробел)")
    bot.register_next_step_handler(msg, process_adm_give)

def process_adm_give(message):
    try:
        parts = message.text.split()
        uid, amt = int(parts[0]), float(parts[1])
        db.update_balance(uid, amt)
        bot.reply_to(message, f"✅ Пользователю {uid} начислено {amt}")
        send_log(f"Админ {message.from_user.id} выдал {amt} игроку {uid}")
    except:
        bot.reply_to(message, "Ошибка формата. Пример: `1234567 100` ")

@bot.message_handler(func=lambda m: m.text == "💸 ВЫВОД")
def withdraw_req(message):
    user = db.get_user(message.from_user.id)
    if user[2] < 5:
        return bot.reply_to(message, "❌ Минимальный вывод от 5 USD")
    
    msg = bot.reply_to(message, "Введите сумму для вывода и ваши реквизиты:")
    bot.register_next_step_handler(msg, process_withdraw_final)

def process_withdraw_final(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    send_log(f"🚀 **ЗАЯВКА НА ВЫВОД**\nОт: @{username}\nТекст: {message.text}")
    bot.reply_to(message, "✅ Заявка отправлена админам!")

# ==========================================
# 7. СЕРВЕР И ЗАПУСК
# ==========================================
app = Flask(__name__)
@app.route('/')
def home(): return "Бот работает!"

def run_f():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # Сброс вебхука для чистого старта
    bot.remove_webhook()
    threading.Thread(target=run_f, daemon=True).start()
    logger.info("Запуск бота...")
    bot.infinity_polling()
