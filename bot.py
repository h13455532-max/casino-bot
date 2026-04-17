import telebot, sqlite3, random, threading, time, os, logging
from telebot import types
from flask import Flask
from PIL import Image, ImageDraw

# Настройка логов для отладки в Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
bot = telebot.TeleBot(TOKEN)
ADMIN_IDS = [8357023784, 8539734813]

# --- КЛАСС ДЛЯ РАБОТЫ С БД (Расширенный) ---
class CasinoDB:
    def __init__(self):
        self.conn = sqlite3.connect("casino_pro.db", check_same_thread=False)
        self.cur = self.conn.cursor()
        self.cur.execute("""CREATE TABLE IF NOT EXISTS users 
            (id INTEGER PRIMARY KEY, balance REAL DEFAULT 500, wins INTEGER DEFAULT 0, games INTEGER DEFAULT 0)""")
        self.conn.commit()

    def get_stats(self, uid):
        self.cur.execute("SELECT * FROM users WHERE id=?", (uid,))
        return self.cur.fetchone()

    def update_stats(self, uid, amt, win=False):
        self.cur.execute("INSERT OR REPLACE INTO users (id, balance, wins, games) VALUES (?, ?, ?, ?)", 
                         (uid, self.get_bal(uid) + amt, self.get_stats(uid)[2] + (1 if win else 0), self.get_stats(uid)[3] + 1))
        self.conn.commit()

    def get_bal(self, uid):
        self.cur.execute("SELECT balance FROM users WHERE id=?", (uid,))
        res = self.cur.fetchone()
        return res[0] if res else 500

db = CasinoDB()

# --- ЛОГИКА ГЕНЕРАЦИИ КАРТИНКИ (Красивый интерфейс) ---
def render_profile_card(uid, bal):
    img = Image.new('RGB', (500, 300), color=(15, 15, 20))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), f"USER ID: {uid}", fill=(200, 200, 200))
    draw.text((50, 100), f"CURRENT BALANCE: {bal} USD", fill=(0, 255, 100))
    draw.text((50, 200), "STATUS: ELITE PLAYER", fill=(255, 215, 0))
    img.save("profile.png")
    return "profile.png"

# --- ИГРОВАЯ ЛОГИКА (Раздутая) ---
def play_dice_game(m, bet):
    """Классические кости с шансом 50/50"""
    dice_val = bot.send_dice(m.chat.id, emoji='🎲').dice.value
    if dice_val >= 4:
        db.update_stats(m.from_user.id, bet * 0.9, True)
        bot.reply_to(m, f"✅ ВЫИГРЫШ! Выпало {dice_val}")
    else:
        db.update_stats(m.from_user.id, -bet, False)
        bot.reply_to(m, f"❌ ПРОИГРЫШ! Выпало {dice_val}")

def play_roulette_game(m, bet, guess):
    """Рулетка: шанс 1 к 37"""
    win_num = random.randint(0, 36)
    if guess == win_num:
        db.update_stats(m.from_user.id, bet * 35, True)
        bot.reply_to(m, f"🎯 ДЖЕКПОТ! Выпало {win_num}. Выигрыш X35!")
    else:
        db.update_stats(m.from_user.id, -bet, False)
        bot.reply_to(m, f"📉 Мимо! Выпало {win_num}.")

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---
@bot.message_handler(commands=['start'])
def start(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎲 ИГРАТЬ", "💰 ПРОФИЛЬ", "🛠 АДМИНКА")
    bot.send_message(m.chat.id, "🎰 Добро пожаловать в хардкорное казино!", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "💰 ПРОФИЛЬ")
def profile(m):
    stats = db.get_stats(m.from_user.id)
    if not stats: stats = (m.from_user.id, 500, 0, 0)
    img = render_profile_card(stats[0], stats[1])
    with open(img, 'rb') as f:
        bot.send_photo(m.chat.id, f, caption=f"📊 Твоя статистика:\nИгр: {stats[3]}\nПобед: {stats[2]}")

@bot.message_handler(commands=['givebal'])
def give(m):
    if m.from_user.id in ADMIN_IDS:
        try:
            _, uid, amt = m.text.split()
            db.update_stats(int(uid), float(amt))
            bot.reply_to(m, "✅ Баланс выдан")
        except: bot.reply_to(m, "Формат: /givebal ID СУММА")

# --- СЕРВЕР RENDER ---
def run_flask():
    app = Flask(__name__)
    @app.route('/')
    def index(): return "Casino API Online"
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # Запуск Flask
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Рекурсивный запуск бота с автоперезагрузкой
    while True:
        try:
            logger.info("Бот запущен...")
            bot.remove_webhook()
            bot.infinity_polling()
        except Exception as e:
            logger.error(f"Сбой: {e}")
            time.sleep(5)
