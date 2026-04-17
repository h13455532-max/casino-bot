# bot.py — MEGA CASINO PRO v3.0 (Production)
import telebot, sqlite3, random, threading, time, os, logging, io, math
from telebot import types
from flask import Flask
from PIL import Image, ImageDraw, ImageFont

# ════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════
TOKEN = os.environ.get("TOKEN")
ADMIN_IDS = [8357023784, 8539734813]
MODERATOR_IDS = [8357023784, 8539734813]
LOG_CHANNEL_ID = -1003951162583
CRYPTO_LINK = "http://t.me/send?start=IVpZKHj5lZFO"
CASINO_NAME = "NEZZX x KLITOK CASINO"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ════════════════════════════════════════════
#  DATABASE
# ════════════════════════════════════════════
class CasinoDB:
    def __init__(self):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect("casino.db", check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init()

    def _init(self):
        with self.lock:
            self.cur.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id        INTEGER PRIMARY KEY,
                    username  TEXT    DEFAULT 'Player',
                    balance   REAL    DEFAULT 0,
                    wins      INTEGER DEFAULT 0,
                    losses    INTEGER DEFAULT 0,
                    games     INTEGER DEFAULT 0,
                    total_bet REAL    DEFAULT 0,
                    total_won REAL    DEFAULT 0,
                    mode      TEXT    DEFAULT 'crypto',
                    created_at INTEGER DEFAULT 0
                );
            """)
            self.conn.commit()

    def ensure(self, uid, username="Player"):
        with self.lock:
            self.cur.execute("INSERT OR IGNORE INTO users (id, username, created_at) VALUES (?,?,?)",
                            (uid, username, int(time.time())))
            self.cur.execute("UPDATE users SET username=? WHERE id=?", (username, uid))
            self.conn.commit()

    def get(self, uid):
        self.cur.execute("SELECT * FROM users WHERE id=?", (uid,))
        r = self.cur.fetchone()
        return dict(r) if r else None

    def bal(self, uid):
        self.cur.execute("SELECT balance FROM users WHERE id=?", (uid,))
        r = self.cur.fetchone()
        return r[0] if r else 0.0

    def add(self, uid, amount):
        with self.lock:
            self.cur.execute("UPDATE users SET balance=balance+? WHERE id=?", 
                           (round(amount, 4), uid))
            self.conn.commit()

    def set_bal(self, uid, amount):
        with self.lock:
            self.cur.execute("UPDATE users SET balance=? WHERE id=?", 
                           (round(amount, 4), uid))
            self.conn.commit()

    def record(self, uid, bet, won, profit=0):
        with self.lock:
            if won:
                self.cur.execute("""UPDATE users SET
                    wins=wins+1, games=games+1,
                    total_bet=total_bet+?,
                    total_won=total_won+?,
                    balance=balance+?
                    WHERE id=?""", (bet, profit, profit, uid))
            else:
                self.cur.execute("""UPDATE users SET
                    losses=losses+1, games=games+1,
                    total_bet=total_bet+?,
                    balance=balance-?
                    WHERE id=?""", (bet, bet, uid))
            self.conn.commit()

    def set_mode(self, uid, mode):
        with self.lock:
            self.cur.execute("UPDATE users SET mode=? WHERE id=?", (mode, uid))
            self.conn.commit()

    def get_mode(self, uid):
        self.cur.execute("SELECT mode FROM users WHERE id=?", (uid,))
        r = self.cur.fetchone()
        return r[0] if r else "crypto"

    def top(self, n=10):
        self.cur.execute(
            "SELECT username, total_won, wins, games FROM users "
            "WHERE games > 0 ORDER BY total_won DESC LIMIT ?", (n,)
        )
        return self.cur.fetchall()

db = CasinoDB()

# ════════════════════════════════════════════
#  ЛОГИРОВАНИЕ В КАНАЛ
# ════════════════════════════════════════════
def log_to_channel(text, photo_path=None):
    """Логирование событий в канал"""
    try:
        if photo_path:
            with open(photo_path, 'rb') as f:
                bot.send_photo(LOG_CHANNEL_ID, f, caption=text)
        else:
            bot.send_message(LOG_CHANNEL_ID, text)
    except Exception as e:
        logger.error(f"Ошибка логирования: {e}")

# ════════════════════════════════════════════
#  ГЕНЕРАЦИЯ КАРТИНОК (PIL)
# ════════════════════════════════════════════
def make_win_image(username: str, amount: float, game_name: str) -> io.BytesIO:
    """Красивая картинка ПОБЕДЫ"""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), (10, 15, 35))
    draw = ImageDraw.Draw(img)
    
    # Градиентный фон
    for y in range(H):
        ratio = y / H
        r = int(10 + 30 * ratio)
        g = int(15 + 40 * ratio)
        b = int(35 + 80 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # Рамка
    draw.rounded_rectangle([30, 30, W-30, H-30], radius=40,
                          outline=(0, 255, 100), width=6)
    
    # Закругленные углы для внутреннего контента
    draw.rounded_rectangle([60, 60, W-60, H-60], radius=35,
                          outline=(0, 200, 100), width=3)
    
    # ТОП: заголовок
    draw.rectangle([60, 60, W-60, 250], fill=(15, 30, 60))
    draw.text((W//2-120, 100), "🎉 ПОБЕДА! 🎉", fill=(0, 255, 100))
    
    # СЕРЕДИНА: сумма выигрыша (БОЛЬШОЙ)
    draw.text((W//2-200, 300), f"+ ${amount:.2f}", fill=(0, 255, 100))
    
    # ИГРА
    draw.text((W//2-150, 500), f"{game_name}", fill=(150, 200, 255))
    
    # ИГРОК
    draw.text((W//2-180, 650), f"Игрок: {username[:20]}", fill=(200, 200, 255))
    
    # НИЖНЯЯ ПОЛОСА
    draw.rectangle([60, 850, W-60, 950], fill=(0, 100, 50))
    draw.text((W//2-150, 880), "MEGA CASINO", fill=(0, 255, 100))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def make_lose_image(username: str, amount: float, game_name: str) -> io.BytesIO:
    """Красивая картинка ПРОИГРЫША"""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), (35, 10, 10))
    draw = ImageDraw.Draw(img)
    
    # Градиентный фон (красный)
    for y in range(H):
        ratio = y / H
        r = int(35 + 50 * ratio)
        g = int(10 + 10 * ratio)
        b = int(10 + 20 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # Рамка
    draw.rounded_rectangle([30, 30, W-30, H-30], radius=40,
                          outline=(255, 100, 100), width=6)
    draw.rounded_rectangle([60, 60, W-60, H-60], radius=35,
                          outline=(200, 100, 100), width=3)
    
    # ТОП
    draw.rectangle([60, 60, W-60, 250], fill=(60, 30, 30))
    draw.text((W//2-120, 100), "❌ ПРОИГРЫШ ❌", fill=(255, 100, 100))
    
    # СУММА ПОТЕРИ
    draw.text((W//2-180, 300), f"- ${amount:.2f}", fill=(255, 100, 100))
    
    # ИГРА
    draw.text((W//2-150, 500), f"{game_name}", fill=(255, 150, 150))
    
    # ИГРОК
    draw.text((W//2-180, 650), f"Игрок: {username[:20]}", fill=(255, 200, 200))
    
    # НИЖНЯЯ ПОЛОСА
    draw.rectangle([60, 850, W-60, 950], fill=(100, 30, 30))
    draw.text((W//2-150, 880), "MEGA CASINO", fill=(255, 100, 100))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def make_game_image(game_name: str, bet: float, username: str) -> io.BytesIO:
    """Картинка ИГРА В ПРОЦЕССЕ"""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), (15, 20, 40))
    draw = ImageDraw.Draw(img)
    
    # Градиент (синий)
    for y in range(H):
        ratio = y / H
        r = int(15 + 20 * ratio)
        g = int(20 + 40 * ratio)
        b = int(40 + 80 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # Рамка
    draw.rounded_rectangle([30, 30, W-30, H-30], radius=40,
                          outline=(100, 150, 255), width=6)
    draw.rounded_rectangle([60, 60, W-60, H-60], radius=35,
                          outline=(150, 200, 255), width=3)
    
    # ТОП
    draw.rectangle([60, 60, W-60, 250], fill=(20, 30, 70))
    draw.text((W//2-180, 100), "🎮 ИГРА В ПРОЦЕССЕ 🎮", fill=(100, 200, 255))
    
    # НАЗВАНИЕ ИГРЫ
    draw.text((W//2-200, 350), f"{game_name}", fill=(150, 220, 255))
    
    # СТАВКА
    draw.text((W//2-120, 500), f"СТАВКА: ${bet:.2f}", fill=(100, 255, 200))
    
    # ИГРОК
    draw.text((W//2-180, 650), f"Игрок: {username[:20]}", fill=(180, 220, 255))
    
    # НИЖНЯЯ ПОЛОСА
    draw.rectangle([60, 850, W-60, 950], fill=(20, 40, 80))
    draw.text((W//2-150, 880), "MEGA CASINO", fill=(100, 200, 255))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def make_profile_card(user: dict) -> io.BytesIO:
    """Красивая профиль-карточка"""
    W, H = 1080, 600
    img = Image.new("RGB", (W, H), (10, 10, 25))
    draw = ImageDraw.Draw(img)
    
    # Градиент
    for y in range(H):
        ratio = y / H
        r = int(10 + 40 * ratio)
        g = int(10 + 30 * ratio)
        b = int(25 + 100 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # Рамка
    draw.rounded_rectangle([20, 20, W-20, H-20], radius=30,
                          outline=(100, 80, 200), width=4)
    
    # Левая часть — аватар
    draw.ellipse([40, 80, 280, 320], fill=(40, 30, 80), outline=(150, 100, 200), width=3)
    draw.text((130, 180), "👤", fill=(200, 180, 255))
    
    # Правая часть — инфо
    draw.text((320, 60), f"{user['username']}", fill=(240, 230, 255))
    draw.text((320, 120), f"ID: {user['id']}", fill=(150, 130, 200))
    
    # Баланс
    draw.text((320, 200), f"$ {user['balance']:.2f}", fill=(80, 255, 150))
    draw.text((320, 260), f"Игр: {user['games']} | Побед: {user['wins']}", fill=(150, 200, 255))
    
    wr = round(user['wins'] / user['games'] * 100, 1) if user['games'] else 0
    profit = user['total_won'] - user['total_bet']
    sign = "+" if profit >= 0 else ""
    
    draw.text((320, 320), f"WR: {wr}% | Прибыль: {sign}${profit:.2f}", fill=(150, 200, 255))
    
    draw.text((320, 400), f"NEZZX x KLITOK CASINO", fill=(100, 200, 255))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════
def uname(m_or_c):
    u = m_or_c.from_user if hasattr(m_or_c, 'from_user') else m_or_c
    return f"@{u.username}" if u.username else (u.first_name or "Player")

def fmt(n):
    if n < 0.01:
        return f"{n:.4f}"
    return f"{n:.2f}"

def parse_bet(text, uid):
    text = text.strip().lower()
    if text in ('all', 'всё', 'allin'):
        return db.bal(uid)
    try:
        v = float(text)
        return v if v >= 0.15 else None
    except:
        return None

def enough(uid, bet):
    return db.bal(uid) >= bet

# Состояния
G = {}
BJ = {}
MN = {}
CR = {}
PVP = {}
TOWER = {}

# ════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ════════════════════════════════════════════
def kb_main():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    k.add("🎮 Играть", "💼 Профиль",
          "🏆 Топ", "📊 Статистика",
          "💰 Пополнение", "ℹ️ Помощь")
    return k

def kb_play_mode():
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("🐸 BrainRot", callback_data="mode_brainrot"))
    k.add(types.InlineKeyboardButton("💎 Crypto Casino", callback_data="mode_crypto"))
    return k

def kb_brainrot():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🎲 Кости", callback_data="g_dice"),
        types.InlineKeyboardButton("🪙 Монетка", callback_data="g_coin"),
        types.InlineKeyboardButton("⚽ Футбол", callback_data="g_football"),
        types.InlineKeyboardButton("🏀 Баскет", callback_data="g_basket"),
        types.InlineKeyboardButton("🎯 Дартс", callback_data="g_darts"),
        types.InlineKeyboardButton("🎳 Боулинг", callback_data="g_bowling"),
        types.InlineKeyboardButton("⚔️ PvP Дуэль", callback_data="g_pvp"),
        types.InlineKeyboardButton("🐍 Угадай 1/5", callback_data="g_snake"),
    )
    k.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_mode"))
    return k

def kb_crypto():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🃏 Блэкджек", callback_data="g_blackjack"),
        types.InlineKeyboardButton("🎰 Слоты", callback_data="g_slots"),
        types.InlineKeyboardButton("🎡 Рулетка", callback_data="g_roulette"),
        types.InlineKeyboardButton("💣 Майнс (1 мина)", callback_data="g_mines1"),
        types.InlineKeyboardButton("💣💣 Майнс (2 мины)", callback_data="g_mines2"),
        types.InlineKeyboardButton("🏔️ Башня", callback_data="g_tower"),
        types.InlineKeyboardButton("🚀 Краш", callback_data="g_crash"),
        types.InlineKeyboardButton("📈 Трейдер", callback_data="g_trader"),
    )
    k.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_mode"))
    return k

def kb_bet(game):
    k = types.InlineKeyboardMarkup(row_width=4)
    amounts = [1, 5, 10, 50, 100, 500, 1000, 5000]
    k.add(*[types.InlineKeyboardButton(f"${a}", callback_data=f"bet_{game}_{a}")
            for a in amounts if a >= 1])
    k.add(
        types.InlineKeyboardButton("✏️ Своя сумма", callback_data=f"bet_{game}_custom"),
        types.InlineKeyboardButton("💸 Ва-банк", callback_data=f"bet_{game}_all"),
    )
    k.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_games"))
    return k

def kb_again(game, mode):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔄 Ещё раз", callback_data=f"g_{game}"),
        types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
    )
    return k

# ════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def cmd_start(m):
    uid = m.from_user.id
    username = uname(m)
    db.ensure(uid, username)
    
    log_to_channel(f"🆕 Новый игрок: {username} (ID: {uid})")
    
    text = (
        f"<b>🎰 {CASINO_NAME}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Привет, <b>{m.from_user.first_name}!</b>\n\n"
        f"Стартовый баланс: <b>0.00 $</b>\n"
        f"Пополни счёт через крипто-ссылку чтобы начать играть!\n\n"
        f"<a href='{CRYPTO_LINK}'>💰 Пополнить счёт</a>"
    )
    bot.send_message(m.chat.id, text, reply_markup=kb_main())

# ════════════════════════════════════════════
#  🎮 ИГРАТЬ
# ════════════════════════════════════════════
@bot.message_handler(commands=['play'])
@bot.message_handler(func=lambda m: m.text == "🎮 Играть")
def cmd_play(m):
    uid = m.from_user.id
    db.ensure(uid, uname(m))
    bal = db.bal(uid)
    
    if bal <= 0:
        text = (
            f"<b>❌ Баланс пуст!</b>\n\n"
            f"Текущий баланс: <b>${fmt(bal)}</b>\n\n"
            f"Пополни счёт чтобы начать играть:"
        )
        k = types.InlineKeyboardMarkup()
        k.add(types.InlineKeyboardButton("💰 Пополнить", url=CRYPTO_LINK))
        bot.send_message(m.chat.id, text, reply_markup=k)
        return
    
    text = (
        f"<b>🎮 ВЫБЕРИ РЕЖИМ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Баланс: <b>${fmt(bal)}</b>\n\n"
        "<b>🐸 BrainRot</b> — Дайсы, PvP\n"
        "<b>💎 Crypto</b> — Блэкджек, Майнс, Краш"
    )
    bot.send_message(m.chat.id, text, reply_markup=kb_play_mode())

@bot.callback_query_handler(func=lambda c: c.data.startswith("mode_"))
def cb_mode(c):
    uid = c.from_user.id
    mode = c.data.split("_")[1]
    db.ensure(uid, uname(c))
    db.set_mode(uid, mode)

    if mode == "brainrot":
        text = f"<b>🐸 BRAINROT CASINO</b>\n💰 ${fmt(db.bal(uid))}\n\nВыбери игру:"
        kb = kb_brainrot()
    else:
        text = f"<b>💎 CRYPTO CASINO</b>\n💰 ${fmt(db.bal(uid))}\n\nВыбери игру:"
        kb = kb_crypto()

    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_mode")
def cb_back_mode(c):
    uid = c.from_user.id
    text = f"<b>🎮 ВЫБЕРИ РЕЖИМ</b>\n💰 ${fmt(db.bal(uid))}"
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb_play_mode())
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb_play_mode())
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data in ("back_brainrot", "back_crypto"))
def cb_back_games(c):
    uid = c.from_user.id
    mode = "brainrot" if c.data == "back_brainrot" else "crypto"
    text = f"<b>{'🐸 BRAINROT' if mode=='brainrot' else '💎 CRYPTO'} CASINO</b>\n💰 ${fmt(db.bal(uid))}"
    kb = kb_brainrot() if mode == "brainrot" else kb_crypto()
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_games")
def cb_back_g(c):
    uid = c.from_user.id
    mode = db.get_mode(uid)
    text = f"<b>{'🐸 BRAINROT' if mode=='brainrot' else '💎 CRYPTO'} CASINO</b>\n💰 ${fmt(db.bal(uid))}"
    kb = kb_brainrot() if mode == "brainrot" else kb_crypto()
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  ВЫБОР ИГРЫ → СТАВКА
# ════════════════════════════════════════════
GNAMES = {
    "dice": "🎲 Кости", "coin": "🪙 Монетка", "football": "⚽ Футбол",
    "basket": "🏀 Баскет", "darts": "🎯 Дартс", "bowling": "🎳 Боулинг",
    "pvp": "⚔️ PvP Дуэль", "snake": "🐍 Угадай 1/5",
    "blackjack": "🃏 Блэкджек", "slots": "🎰 Слоты", "roulette": "🎡 Рулетка",
    "mines1": "💣 Майнс (1 мина)", "mines2": "💣💣 Майнс (2 мины)",
    "tower": "🏔️ Башня", "crash": "🚀 Краш", "trader": "📈 Трейдер",
}

@bot.callback_query_handler(func=lambda c: c.data.startswith("g_"))
def cb_game_pick(c):
    uid = c.from_user.id
    game = c.data[2:]
    db.ensure(uid, uname(c))

    # Особые игры
    if game == "pvp":
        _pvp_create(c)
        return
    if game == "crash":
        _crash_info(c)
        return

    bal = db.bal(uid)
    name = GNAMES.get(game, game)
    text = f"<b>{name}</b>\n💰 ${fmt(bal)}\n\nВыбери ставку (мин. 0.15 $):"
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb_bet(game))
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb_bet(game))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bet_"))
def cb_bet(c):
    uid = c.from_user.id
    parts = c.data.split("_")
    game = parts[1]
    amt_s = parts[2]
    db.ensure(uid, uname(c))

    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Это не твоя игра!", show_alert=True)
        return

    if amt_s == "custom":
        G[uid] = {"wait": "bet", "game": game, "creator": uid}
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id,
            f"✏️ Введи сумму ставки (мин. 0.15 $):\n💰 Баланс: <b>${fmt(db.bal(uid))}</b>")
        return

    bet = db.bal(uid) if amt_s == "all" else float(amt_s)

    if bet < 0.15:
        bot.answer_callback_query(c.id, "Мин. ставка — 0.15 $!", show_alert=True)
        return
    if not enough(uid, bet):
        bot.answer_callback_query(c.id, "❌ Недостаточно средств!", show_alert=True)
        return

    bot.answer_callback_query(c.id, f"Ставка ${fmt(bet)} принята!")
    _launch(c.message, uid, game, bet, uname(c))

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "bet")
def handle_custom_bet(m):
    uid = m.from_user.id
    state = G.pop(uid, None)
    if not state:
        bot.reply_to(m, "❌ Состояние потеряно")
        return
    
    if state.get("creator") != uid:
        bot.reply_to(m, "❌ Это не твоя игра!")
        return
    
    game = state["game"]
    bet = parse_bet(m.text, uid)

    if not bet or bet < 0.15:
        bot.reply_to(m, "❌ Минимум 0.15 $. Попробуй снова.")
        return
    if not enough(uid, bet):
        bot.reply_to(m, f"❌ Недостаточно средств. Баланс: ${fmt(db.bal(uid))}")
        return

    _launch(m, uid, game, bet, uname(m))

# ════════════════════════════════════════════
#  ДИСПЕТЧЕР ИГР
# ════════════════════════════════════════════
def _launch(m, uid, game, bet, username):
    fn = {
        "dice": _dice, "coin": _coin, "football": _football,
        "basket": _basket, "darts": _darts, "bowling": _bowling,
        "snake": _snake, "blackjack": _bj_start, "slots": _slots,
        "roulette": _roulette_start, "mines1": lambda m,u,b: _mines_start(m,u,b,1),
        "mines2": lambda m,u,b: _mines_start(m,u,b,2),
        "tower": _tower_start, "trader": _trader,
    }.get(game)
    if fn:
        fn(m, uid, bet)
    else:
        bot.send_message(m.chat.id, "⚠️ Игра в разработке!")

# ════════════════════════════════════════════
#  🎲 КОСТИ
# ════════════════════════════════════════════
def _dice(m, uid, bet):
    mode = db.get_mode(uid)
    username = uname(m)
    
    # Картинка процесса
    img_buf = make_game_image("🎲 Кости", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption=f"Бросаем кости...")
    
    dv = bot.send_dice(m.chat.id, emoji='🎲').dice.value
    time.sleep(4)
    
    if dv >= 4:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎲 Кости")
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Кости (выпало {dv})")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🎲 Кости")
        log_to_channel(f"❌ {username} проиграл ${fmt(bet)} в Кости (выпало {dv})")
    
    bot.send_photo(m.chat.id, img_buf, 
                  caption=f"💰 Баланс: ${fmt(db.bal(uid))}\n\nВыпало: <b>{dv}</b>",
                  reply_markup=kb_again("dice", mode))

# ════════════════════════════════════════════
#  🪙 МОНЕТКА
# ════════════════════════════════════════════
def _coin(m, uid, bet):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("👑 Орёл", callback_data=f"coin_{uid}_{bet}_h"),
        types.InlineKeyboardButton("🔵 Решка", callback_data=f"coin_{uid}_{bet}_t"),
    )
    username = uname(m)
    img_buf = make_game_image("🪙 Монетка", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Выбери сторону:", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("coin_"))
def cb_coin(c):
    _, uid_s, bet_s, side = c.data.split("_")
    uid = int(uid_s)
    bet = float(bet_s)
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Это не твоя игра!", show_alert=True)
        return
    
    mode = db.get_mode(uid)
    username = uname(c)
    result = random.choice(["h", "t"])
    won = result == side
    emoji = "👑" if result == "h" else "🔵"
    
    if won:
        profit = round(bet * 0.95, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🪙 Монетка")
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Монетку ({emoji})")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🪙 Монетка")
        log_to_channel(f"❌ {username} проиграл ${fmt(bet)} в Монетку ({emoji})")
    
    try:
        bot.edit_message_media(
            types.InputMediaPhoto(img_buf, caption=f"Выпало: {emoji}\n💰 ${fmt(db.bal(uid))}"),
            c.message.chat.id, c.message.message_id, reply_markup=kb_again("coin", mode))
    except:
        bot.send_photo(c.message.chat.id, img_buf,
                      caption=f"Выпало: {emoji}\n💰 ${fmt(db.bal(uid))}",
                      reply_markup=kb_again("coin", mode))
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  ⚽ ФУТБОЛ
# ════════════════════════════════════════════
def _football(m, uid, bet):
    mode = db.get_mode(uid)
    username = uname(m)
    img_buf = make_game_image("⚽ Футбол", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Бросаем...")
    dv = bot.send_dice(m.chat.id, emoji='⚽').dice.value
    time.sleep(4)
    if dv >= 4:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "⚽ Футбол")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "⚽ Футбол")
    bot.send_photo(m.chat.id, img_buf,
                  caption=f"Счёт: {dv}/5\n💰 ${fmt(db.bal(uid))}",
                  reply_markup=kb_again("football", mode))

# ════════════════════════════════════════════
#  🏀 БАСКЕТ
# ════════════════════════════════════════════
def _basket(m, uid, bet):
    mode = db.get_mode(uid)
    username = uname(m)
    img_buf = make_game_image("🏀 Баскетбол", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Бросаем...")
    dv = bot.send_dice(m.chat.id, emoji='🏀').dice.value
    time.sleep(4)
    if dv >= 4:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🏀 Баскетбол")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🏀 Баскетбол")
    bot.send_photo(m.chat.id, img_buf,
                  caption=f"Бросок: {dv}/5\n💰 ${fmt(db.bal(uid))}",
                  reply_markup=kb_again("basket", mode))

# ════════════════════════════════════════════
#  🎯 ДАРТС
# ════════════════════════════════════════════
def _darts(m, uid, bet):
    mode = db.get_mode(uid)
    username = uname(m)
    img_buf = make_game_image("🎯 Дартс", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Бросаем...")
    dv = bot.send_dice(m.chat.id, emoji='🎯').dice.value
    time.sleep(4)
    if dv == 6:
        profit = round(bet * 2.0, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎯 Дартс (ЯБЛОЧКО!)")
    elif dv >= 4:
        profit = round(bet * 0.7, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎯 Дартс (Близко)")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🎯 Дартс")
    bot.send_photo(m.chat.id, img_buf,
                  caption=f"Попадание: {dv}/6\n💰 ${fmt(db.bal(uid))}",
                  reply_markup=kb_again("darts", mode))

# ════════════════════════════════════════════
#  🎳 БОУЛИНГ
# ════════════════════════════════════════════
def _bowling(m, uid, bet):
    mode = db.get_mode(uid)
    username = uname(m)
    img_buf = make_game_image("🎳 Боулинг", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Бросаем...")
    dv = bot.send_dice(m.chat.id, emoji='🎳').dice.value
    time.sleep(4)
    if dv == 6:
        profit = round(bet * 1.5, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎳 Боулинг (СТРАЙК!)")
    elif dv >= 3:
        profit = round(bet * 0.5, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎳 Боулинг")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🎳 Боулинг")
    bot.send_photo(m.chat.id, img_buf,
                  caption=f"Кегли: {dv}/6\n💰 ${fmt(db.bal(uid))}",
                  reply_markup=kb_again("bowling", mode))

# ════════════════════════════════════════════
#  🐍 УГАДАЙ 1/5
# ════════════════════════════════════════════
def _snake(m, uid, bet):
    target = random.randint(1, 5)
    G[uid] = {"game": "snake", "target": target, "bet": bet, "creator": uid}
    k = types.InlineKeyboardMarkup(row_width=5)
    k.add(*[types.InlineKeyboardButton(str(i), callback_data=f"snake_{uid}_{i}") for i in range(1, 6)])
    username = uname(m)
    img_buf = make_game_image("🐍 Угадай 1/5", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Выбери число 1-5:", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("snake_"))
def cb_snake(c):
    _, uid_s, g_s = c.data.split("_")
    uid = int(uid_s)
    guess = int(g_s)
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Это не твоя игра!", show_alert=True)
        return
    
    state = G.pop(uid, None)
    if not state:
        bot.answer_callback_query(c.id, "Игра истекла!")
        return
    
    bet = state["bet"]
    target = state["target"]
    mode = db.get_mode(uid)
    username = uname(c)
    
    if guess == target:
        profit = round(bet * 3.0, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🐍 Угадай 1/5")
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Угадай 1/5 (было {target})")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🐍 Угадай 1/5")
        log_to_channel(f"❌ {username} проиграл ${fmt(bet)} в Угадай 1/5 (было {target})")
    
    try:
        bot.edit_message_media(
            types.InputMediaPhoto(img_buf, caption=f"Было: {target}\n💰 ${fmt(db.bal(uid))}"),
            c.message.chat.id, c.message.message_id, reply_markup=kb_again("snake", mode))
    except:
        bot.send_photo(c.message.chat.id, img_buf,
                      caption=f"Было: {target}\n💰 ${fmt(db.bal(uid))}",
                      reply_markup=kb_again("snake", mode))
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  ⚔️ PvP ДУЭЛЬ
# ════════════════════════════════════════════
def _pvp_create(c):
    uid = c.from_user.id
    chat_id = c.message.chat.id
    if chat_id in PVP:
        bot.answer_callback_query(c.id, "Уже есть активная дуэль!", show_alert=True)
        return
    G[uid] = {"wait": "pvp_bet", "chat_id": chat_id, "creator": uid}
    bot.answer_callback_query(c.id)
    bot.send_message(chat_id,
        f"<b>⚔️ PvP ДУЭЛЬ</b>\n{uname(c)} создаёт дуэль!\nВведи ставку (мин. 0.5 $):")

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "pvp_bet")
def handle_pvp_bet(m):
    uid = m.from_user.id
    state = G.pop(uid, None)
    if not state or state.get("creator") != uid:
        bot.reply_to(m, "❌ Это не твоя игра!")
        return
    
    bet = parse_bet(m.text, uid)
    chat_id = state.get("chat_id", m.chat.id)
    if not bet or bet < 0.5:
        bot.reply_to(m, "❌ Минимум 0.5 $")
        return
    if not enough(uid, bet):
        bot.reply_to(m, "❌ Недостаточно средств!")
        return
    
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton(f"⚔️ Принять ({bet})", callback_data=f"pvp_acc_{uid}_{bet}"))
    msg = bot.send_message(chat_id,
        f"<b>⚔️ ДУЭЛЬ!</b>\n{uname(m)} vs ???\n"
        f"Ставка: ${fmt(bet)}\n⏱ 60 сек", reply_markup=k)
    PVP[chat_id] = {"creator": uid, "cname": uname(m), "bet": bet, "mid": msg.message_id}

    def _cancel():
        time.sleep(60)
        if chat_id in PVP and PVP[chat_id].get("mid") == msg.message_id:
            PVP.pop(chat_id, None)
            try:
                bot.edit_message_text("<b>⚔️ Дуэль отменена</b> — никто не принял.",
                                     chat_id, msg.message_id)
            except: pass
    threading.Thread(target=_cancel, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_acc_"))
def cb_pvp(c):
    _, _, uid_s, bet_s = c.data.split("_")
    creator = int(uid_s)
    bet = float(bet_s)
    uid = c.from_user.id
    chat_id = c.message.chat.id
    
    if uid == creator:
        bot.answer_callback_query(c.id, "Нельзя принять свою дуэль!", show_alert=True)
        return
    if not enough(uid, bet):
        bot.answer_callback_query(c.id, "❌ Недостаточно средств!", show_alert=True)
        return
    if chat_id not in PVP:
        bot.answer_callback_query(c.id, "Дуэль уже завершена!")
        return
    
    lobby = PVP.pop(chat_id)
    bot.answer_callback_query(c.id, "🎲 Начало!")
    bot.edit_message_text(
        f"<b>⚔️ ДУЭЛЬ НАЧАЛАСЬ!</b>\n"
        f"🔴 {lobby['cname']} vs 🔵 {uname(c)}\n"
        f"Ставка: ${fmt(bet)}\n\nБросаем...", chat_id, c.message.message_id)
    
    time.sleep(1)
    bot.send_message(chat_id, f"🔴 {lobby['cname']} бросает...")
    d1 = bot.send_dice(chat_id, emoji='🎲').dice.value
    time.sleep(1)
    bot.send_message(chat_id, f"🔵 {uname(c)} бросает...")
    d2 = bot.send_dice(chat_id, emoji='🎲').dice.value
    time.sleep(4)
    
    if d1 == d2:
        bot.send_message(chat_id, f"<b>🤝 НИЧЬЯ!</b>  {d1} vs {d2}")
        return
    
    if d1 > d2:
        wid = creator; wname = lobby['cname']; wd, ld = d1, d2
    else:
        wid = uid; wname = uname(c); wd, ld = d2, d1
    
    prize = round(bet * 1.85, 2)
    db.record(wid, bet, True, prize)
    db.record(uid if wid != uid else creator, bet, False)
    
    bot.send_message(chat_id,
        f"<b>⚔️ РЕЗУЛЬТАТ</b>\n\n"
        f"🔴 {lobby['cname']}: {d1}\n"
        f"🔵 {uname(c)}: {d2}\n\n"
        f"<b>👑 Победитель: {wname}!</b>\n"
        f"${fmt(prize)}")

# ════════════════════════════════════════════
#  🃏 БЛЭКДЖЕК
# ════════════════════════════════════════════
SUITS = ["♠","♥","♦","♣"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

def _deck():
    d = [(r, s) for s in SUITS for r in RANKS]
    random.shuffle(d)
    return d

def _cv(card):
    r = card[0]
    if r in ("J", "Q", "K"): return 10
    if r == "A": return 11
    try: return int(r)
    except: return 10

def _hv(hand):
    t = sum(_cv(c) for c in hand)
    a = sum(1 for c in hand if c[0] == "A")
    while t > 21 and a:
        t -= 10
        a -= 1
    return t

def _hstr(hand):
    return "  ".join(f"{c[0]}{c[1]}" for c in hand)

def _bj_start(m, uid, bet):
    deck = _deck()
    ph = [deck.pop(), deck.pop()]
    dh = [deck.pop(), deck.pop()]
    BJ[uid] = {"deck": deck, "p": ph, "d": dh, "bet": bet, "cid": m.chat.id}
    username = uname(m)
    img_buf = make_game_image("🃏 Блэкджек", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption=f"Раздача...")
    _bj_show(m.chat.id, uid)

def _bj_show(cid, uid, end=False, edit_mid=None):
    s = BJ.get(uid)
    if not s: return
    ph = s["p"]
    dh = s["d"]
    pv = _hv(ph)
    dv = _hv(dh)
    
    text = f"<b>🃏 Блэкджек</b>\n🏦 Дилер: {dh[0][0]}{dh[0][1]} 🂠\n👤 Ты: {_hstr(ph)} [{pv}]"
    
    if not end:
        k = types.InlineKeyboardMarkup(row_width=2)
        k.add(
            types.InlineKeyboardButton("👊 Ещё", callback_data=f"bj_h_{uid}"),
            types.InlineKeyboardButton("✋ Стоп", callback_data=f"bj_s_{uid}"),
        )
        if db.bal(uid) >= s["bet"]:
            k.add(types.InlineKeyboardButton("💰 Удвоить", callback_data=f"bj_d_{uid}"))
        
        if edit_mid:
            try:
                bot.edit_message_text(text, cid, edit_mid, reply_markup=k)
                return
            except: pass
        bot.send_message(cid, text, reply_markup=k)
    else:
        res, won = _bj_resolve(uid, pv, dv, s["bet"])
        mode = db.get_mode(uid)
        username = uname(BJ[uid]['p'] if uid in BJ else '')
        
        if won:
            img_buf = make_win_image(username, res, "🃏 Блэкджек")
        else:
            img_buf = make_lose_image(username, res, "🃏 Блэкджек")
        
        try:
            bot.edit_message_text(text, cid, edit_mid, reply_markup=kb_again("blackjack", mode))
        except:
            pass
        bot.send_photo(cid, img_buf, caption=f"💰 ${fmt(db.bal(uid))}",
                      reply_markup=kb_again("blackjack", mode))

def _bj_resolve(uid, pv, dv, bet):
    if pv > 21:
        db.record(uid, bet, False)
        return bet, False
    if dv > 21 or pv > dv:
        p = round(bet * 0.95, 2)
        db.record(uid, bet, True, p)
        return p, True
    if pv == dv:
        return 0, False
    db.record(uid, bet, False)
    return bet, False

@bot.callback_query_handler(func=lambda c: c.data.startswith("bj_"))
def cb_bj(c):
    parts = c.data.split("_")
    action = parts[1]
    uid = int(parts[2])
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    s = BJ.get(uid)
    if not s:
        bot.answer_callback_query(c.id, "Игра не найдена!")
        return
    
    if action == "h":
        s["p"].append(s["deck"].pop())
        if _hv(s["p"]) >= 21:
            _bj_dealer(uid, c.message.message_id)
        else:
            _bj_show(c.message.chat.id, uid, edit_mid=c.message.message_id)
    elif action == "s":
        _bj_dealer(uid, c.message.message_id)
    elif action == "d":
        if db.bal(uid) >= s["bet"]:
            s["bet"] *= 2
            s["p"].append(s["deck"].pop())
            _bj_dealer(uid, c.message.message_id)
        else:
            bot.answer_callback_query(c.id, "Не хватает!", show_alert=True)
            return
    
    bot.answer_callback_query(c.id)

def _bj_dealer(uid, edit_mid=None):
    s = BJ.pop(uid, None)
    if not s: return
    while _hv(s["d"]) < 17:
        s["d"].append(s["deck"].pop())
    BJ[uid] = s
    _bj_show(s["cid"], uid, end=True, edit_mid=edit_mid)
    BJ.pop(uid, None)

# ════════════════════════════════════════════
#  🎰 СЛОТЫ
# ════════════════════════════════════════════
SYM = ["🍒","🍋","🍊","🍇","🔔","💎","7️⃣","🎰"]
SWGT = [30, 25, 20, 15, 5, 3, 1.5, 0.5]
SPAY = {"🎰🎰🎰": 50, "7️⃣7️⃣7️⃣": 20, "💎💎💎": 15,
        "🔔🔔🔔": 10, "🍇🍇🍇": 8, "🍊🍊🍊": 6,
        "🍋🍋🍋": 5, "🍒🍒🍒": 4}

def _spin():
    tw = sum(SWGT)
    out = []
    for _ in range(3):
        r = random.uniform(0, tw)
        c = 0
        for s, w in zip(SYM, SWGT):
            c += w
            if r <= c:
                out.append(s)
                break
    return out

def _slots(m, uid, bet):
    mode = db.get_mode(uid)
    username = uname(m)
    img_buf = make_game_image("🎰 Слоты", bet, username)
    anim = bot.send_photo(m.chat.id, img_buf, caption="Крутим...")
    time.sleep(0.5)
    
    reels = _spin()
    key = "".join(reels)
    
    for _ in range(3):
        f2 = [random.choice(SYM) for _ in range(3)]
        try:
            bot.edit_message_caption(
                f"| {' | '.join(f2)} |", anim.chat.id, anim.message_id)
        except: pass
        time.sleep(0.5)
    
    mult = SPAY.get(key, 0)
    if mult == 0 and len(set(reels)) == 2:
        mult = 1.5
    
    if mult > 0:
        profit = round(bet * mult, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎰 Слоты")
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Слоты (×{mult})")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🎰 Слоты")
        log_to_channel(f"❌ {username} проиграл ${fmt(bet)} в Слоты")
    
    try:
        bot.edit_message_media(
            types.InputMediaPhoto(img_buf, caption=f"| {' | '.join(reels)} |\n💰 ${fmt(db.bal(uid))}"),
            anim.chat.id, anim.message_id, reply_markup=kb_again("slots", mode))
    except:
        bot.send_photo(m.chat.id, img_buf,
                      caption=f"| {' | '.join(reels)} |\n💰 ${fmt(db.bal(uid))}",
                      reply_markup=kb_again("slots", mode))

# ════════════════════════════════════════════
#  🎡 РУЛЕТКА
# ════════════════════════════════════════════
RCOL = {0: "🟢", **{n:"🔴" for n in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]},
        **{n:"⚫" for n in [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]}}

def _roulette_start(m, uid, bet):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔴 Красное ×2", callback_data=f"rul_{uid}_{bet}_red"),
        types.InlineKeyboardButton("⚫ Чёрное ×2", callback_data=f"rul_{uid}_{bet}_black"),
        types.InlineKeyboardButton("🟢 Зеро ×35", callback_data=f"rul_{uid}_{bet}_zero"),
        types.InlineKeyboardButton("1–18 ×2", callback_data=f"rul_{uid}_{bet}_low"),
        types.InlineKeyboardButton("19–36 ×2", callback_data=f"rul_{uid}_{bet}_high"),
        types.InlineKeyboardButton("Чётное ×2", callback_data=f"rul_{uid}_{bet}_even"),
    )
    username = uname(m)
    img_buf = make_game_image("🎡 Рулетка", bet, username)
    bot.send_photo(m.chat.id, img_buf, caption="Выбери ставку:", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rul_"))
def cb_rul(c):
    parts = c.data.split("_")
    uid = int(parts[1])
    bet = float(parts[2])
    choice = parts[3]
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    bot.answer_callback_query(c.id, "Крутим...")
    _rul_spin(c.message, uid, bet, choice)

def _rul_spin(msg, uid, bet, choice):
    cid = msg.chat.id
    result = random.randint(0, 36)
    col = RCOL.get(result, "⚫")
    won = False
    mult = 0
    
    if choice == "red" and col == "🔴": won, mult = True, 1.0
    elif choice == "black" and col == "⚫": won, mult = True, 1.0
    elif choice == "zero" and result == 0: won, mult = True, 34.0
    elif choice == "low" and 1 <= result <= 18: won, mult = True, 1.0
    elif choice == "high" and 19 <= result <= 36: won, mult = True, 1.0
    elif choice == "even" and result != 0 and result % 2 == 0: won, mult = True, 1.0
    
    mode = db.get_mode(uid)
    username = uname(msg)
    
    if won:
        profit = round(bet * mult, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, "🎡 Рулетка")
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Рулетку ({col} {result})")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, "🎡 Рулетка")
        log_to_channel(f"❌ {username} проиграл ${fmt(bet)} в Рулетку ({col} {result})")
    
    bot.send_photo(cid, img_buf,
                  caption=f"{col} <b>{result}</b>\n💰 ${fmt(db.bal(uid))}",
                  reply_markup=kb_again("roulette", mode))

# ════════════════════════════════════════════
#  💣 МАЙНС (1 или 2 мины)
# ════════════════════════════════════════════
def _mines_start(m, uid, bet, mine_count=1):
    k = types.InlineKeyboardMarkup(row_width=5)
    amounts = [3, 5, 7, 10, 15, 20] if mine_count == 1 else [1, 2, 3, 4, 5, 10]
    for n in amounts:
        k.add(types.InlineKeyboardButton(
            f"💣 {n}", callback_data=f"mn_init_{uid}_{bet}_{n}_{mine_count}"))
    
    username = uname(m)
    img_buf = make_game_image(f"💣{'💣' if mine_count == 2 else ''} Майнс", bet, username)
    bot.send_photo(m.chat.id, img_buf,
                  caption=f"Выбери мин (макс {min(amounts)}):", reply_markup=k)

def _mn_mult(safe, mines):
    total = 25
    if safe == 0: return 1.0
    prob = 1.0
    for i in range(safe):
        prob *= (total - mines - i) / (total - i)
    return round(0.97 / prob, 3)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mn_init_"))
def cb_mn_init(c):
    parts = c.data.split("_")
    uid = int(parts[1])
    bet = float(parts[2])
    mines = int(parts[3])
    mine_count = int(parts[4]) if len(parts) > 4 else 1
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    field = [False] * 25
    for p in random.sample(range(25), mines):
        field[p] = True
    
    MN[uid] = {"field": field, "rev": [False]*25, "bet": bet,
               "mines": mines, "safe": 0, "cid": c.message.chat.id,
               "active": True, "mine_count": mine_count}
    bot.answer_callback_query(c.id)
    _mn_show(c.message.chat.id, uid, c.message.message_id)

def _mn_show(cid, uid, edit_mid=None):
    s = MN.get(uid)
    if not s: return
    
    mult = _mn_mult(s["safe"], s["mines"])
    pot = round(s["bet"] * mult, 2)
    text = (f"<b>💣 Майнс</b>  ${fmt(s['bet'])}\n"
            f"💣 Мин: {s['mines']}  ✅ Открыто: {s['safe']}\n"
            f"×{mult}  Потенциал: ${fmt(pot)}")
    
    k = types.InlineKeyboardMarkup(row_width=5)
    btns = []
    for i in range(25):
        if s["rev"][i]:
            txt = "✅" if not s["field"][i] else "💣"
        else:
            txt = "⬛"
        btns.append(types.InlineKeyboardButton(txt, callback_data=f"mn_c_{uid}_{i}"))
    k.add(*btns)
    if s["safe"] > 0:
        k.add(types.InlineKeyboardButton(f"💸 ${fmt(pot)}", callback_data=f"mn_co_{uid}"))
    
    try:
        if edit_mid:
            bot.edit_message_text(text, cid, edit_mid, reply_markup=k)
            return
    except: pass
    bot.send_message(cid, text, reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mn_c_"))
def cb_mn_cell(c):
    parts = c.data.split("_")
    uid = int(parts[1])
    cell = int(parts[2])
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    s = MN.get(uid)
    if not s or not s["active"]:
        bot.answer_callback_query(c.id, "Игра завершена!")
        return
    if s["rev"][cell]:
        bot.answer_callback_query(c.id, "Уже открыто!")
        return
    
    s["rev"][cell] = True
    
    if s["field"][cell]:
        s["active"] = False
        db.record(uid, s["bet"], False)
        
        k = types.InlineKeyboardMarkup(row_width=5)
        btns = []
        for i in range(25):
            btns.append(types.InlineKeyboardButton(
                "💣" if s["field"][i] else ("✅" if s["rev"][i] else "⬜"),
                callback_data="noop"))
        k.add(*btns)
        
        mode = db.get_mode(uid)
        k.add(
            types.InlineKeyboardButton("🔄 Снова", callback_data=f"g_mines{s['mine_count']}"),
            types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
        )
        
        username = uname(c)
        img_buf = make_lose_image(username, s["bet"], f"💣 Майнс")
        MN.pop(uid, None)
        
        try:
            bot.edit_message_media(
                types.InputMediaPhoto(img_buf, caption=f"Мина! 💀\n💰 ${fmt(db.bal(uid))}"),
                c.message.chat.id, c.message.message_id, reply_markup=k)
        except:
            bot.send_photo(c.message.chat.id, img_buf,
                          caption=f"Мина! 💀\n💰 ${fmt(db.bal(uid))}", reply_markup=k)
    else:
        s["safe"] += 1
        _mn_show(c.message.chat.id, uid, c.message.message_id)
    
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mn_co_"))
def cb_mn_cashout(c):
    uid = int(c.data.split("_")[2])
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    s = MN.pop(uid, None)
    if not s:
        bot.answer_callback_query(c.id, "Игра не найдена!")
        return
    
    mult = _mn_mult(s["safe"], s["mines"])
    profit = round(s["bet"] * mult - s["bet"], 2)
    db.record(uid, s["bet"], True, profit)
    
    mode = db.get_mode(uid)
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔄 Снова", callback_data=f"g_mines{s['mine_count']}"),
        types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
    )
    
    username = uname(c)
    img_buf = make_win_image(username, profit, "💣 Майнс — Кэшаут")
    
    try:
        bot.edit_message_media(
            types.InputMediaPhoto(img_buf, caption=f"✅ {s['safe']} ×{mult}\n💰 ${fmt(db.bal(uid))}"),
            c.message.chat.id, c.message.message_id, reply_markup=k)
    except:
        bot.send_photo(c.message.chat.id, img_buf,
                      caption=f"✅ {s['safe']} ×{mult}\n💰 ${fmt(db.bal(uid))}", reply_markup=k)
    
    log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Майнс (×{mult})")
    bot.answer_callback_query(c.id, f"💸 +${fmt(profit)}!")

# ════════════════════════════════════════════
#  🏔️ БАШНЯ
# ════════════════════════════════════════════
def _tower_start(m, uid, bet):
    username = uname(m)
    TOWER[uid] = {
        "level": 0,
        "bet": bet,
        "cid": m.chat.id,
        "active": True,
        "history": []
    }
    
    img_buf = make_game_image("🏔️ Башня", bet, username)
    msg = bot.send_photo(m.chat.id, img_buf, caption="🏔️ Башня\n\nУровень 0\nНажми ВПЕРЁД!")
    
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(types.InlineKeyboardButton("⬆️ ВПЕРЁД", callback_data=f"twr_{uid}"))
    k.add(types.InlineKeyboardButton("💸 ЗАБРАТЬ", callback_data=f"twr_cash_{uid}"))
    
    TOWER[uid]["msg_id"] = msg.message_id
    bot.edit_message_reply_markup(m.chat.id, msg.message_id, reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("twr_"))
def cb_tower(c):
    if "_cash_" in c.data:
        uid = int(c.data.split("_")[2])
        if c.from_user.id != uid:
            bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
            return
        
        s = TOWER.pop(uid, None)
        if not s:
            bot.answer_callback_query(c.id, "Игра не найдена!")
            return
        
        level = s["level"]
        mult = 1.0 + (level * 0.1)
        profit = round(s["bet"] * mult - s["bet"], 2)
        
        if level == 0:
            bot.answer_callback_query(c.id, "Поднимись хотя бы на 1 уровень!")
            return
        
        db.record(uid, s["bet"], True, profit)
        mode = db.get_mode(uid)
        username = uname(c)
        
        img_buf = make_win_image(username, profit, f"🏔️ Башня (Уровень {level})")
        
        k = types.InlineKeyboardMarkup(row_width=2)
        k.add(
            types.InlineKeyboardButton("🔄 Снова", callback_data="g_tower"),
            types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
        )
        
        try:
            bot.edit_message_media(
                types.InputMediaPhoto(img_buf, caption=f"🏔️ Уровень {level}\n×{mult:.1f}\n💰 ${fmt(db.bal(uid))}"),
                c.message.chat.id, c.message.message_id, reply_markup=k)
        except:
            bot.send_photo(c.message.chat.id, img_buf,
                          caption=f"🏔️ Уровень {level}\n×{mult:.1f}\n💰 ${fmt(db.bal(uid))}", reply_markup=k)
        
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Башню (Уровень {level})")
        bot.answer_callback_query(c.id, f"💸 +${fmt(profit)}!")
        return
    
    uid = int(c.data.split("_")[1])
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    s = TOWER.get(uid)
    if not s or not s["active"]:
        bot.answer_callback_query(c.id, "Игра завершена!")
        return
    
    # 50% шанс упасть
    if random.random() < 0.5:
        s["active"] = False
        level = s["level"]
        if level == 0:
            db.record(uid, s["bet"], False)
            mode = db.get_mode(uid)
            username = uname(c)
            img_buf = make_lose_image(username, s["bet"], "🏔️ Башня (Упал с 0)")
            
            k = types.InlineKeyboardMarkup(row_width=2)
            k.add(
                types.InlineKeyboardButton("🔄 Снова", callback_data="g_tower"),
                types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
            )
            
            try:
                bot.edit_message_media(
                    types.InputMediaPhoto(img_buf, caption=f"💀 Упал!\n💰 ${fmt(db.bal(uid))}"),
                    c.message.chat.id, c.message.message_id, reply_markup=k)
            except:
                bot.send_photo(c.message.chat.id, img_buf,
                              caption=f"💀 Упал!\n💰 ${fmt(db.bal(uid))}", reply_markup=k)
            
            TOWER.pop(uid, None)
            bot.answer_callback_query(c.id, "💀 Упал!")
            return
        else:
            # Выигрыш пополам
            mult = 1.0 + ((level - 1) * 0.1)
            profit = round(s["bet"] * mult - s["bet"], 2) / 2
            db.record(uid, s["bet"], True, profit)
            mode = db.get_mode(uid)
            username = uname(c)
            img_buf = make_lose_image(username, -profit, "🏔️ Башня (Упал)")
            
            k = types.InlineKeyboardMarkup(row_width=2)
            k.add(
                types.InlineKeyboardButton("🔄 Снова", callback_data="g_tower"),
                types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
            )
            
            try:
                bot.edit_message_media(
                    types.InputMediaPhoto(img_buf, caption=f"💀 Упал на уровне {level}!\n"
                                                           f"Половина выигрыша!\n💰 ${fmt(db.bal(uid))}"),
                    c.message.chat.id, c.message.message_id, reply_markup=k)
            except:
                bot.send_photo(c.message.chat.id, img_buf,
                              caption=f"💀 Упал на уровне {level}!\n"
                                     f"Половина выигрыша!\n💰 ${fmt(db.bal(uid))}", reply_markup=k)
            
            TOWER.pop(uid, None)
            bot.answer_callback_query(c.id, f"💀 Упал!")
            return
    
    # Успешно подняться на уровень
    s["level"] += 1
    mult = 1.0 + (s["level"] * 0.1)
    
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(types.InlineKeyboardButton("⬆️ ВПЕРЁД", callback_data=f"twr_{uid}"))
    k.add(types.InlineKeyboardButton("💸 ЗАБРАТЬ", callback_data=f"twr_cash_{uid}"))
    
    try:
        bot.edit_message_caption(
            f"🏔️ Башня\nУровень {s['level']}\n×{mult:.1f}",
            c.message.chat.id, c.message.message_id, reply_markup=k)
    except:
        pass
    
    bot.answer_callback_query(c.id, f"⬆️ Уровень {s['level']}!")

# ════════════════════════════════════════════
#  🚀 КРАШ
# ════════════════════════════════════════════
def _crash_info(c):
    uid = c.from_user.id
    G[uid] = {"wait": "crash_bet", "cid": c.message.chat.id, "creator": uid}
    bot.answer_callback_query(c.id)
    username = uname(c)
    img_buf = make_game_image("🚀 Краш", 0, username)
    bot.send_photo(c.message.chat.id, img_buf,
                  caption=f"Ракета взлетает!\nВведи ставку (мин. 0.15 $):")

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "crash_bet")
def handle_crash_bet(m):
    uid = m.from_user.id
    s = G.pop(uid, None)
    if not s or s.get("creator") != uid:
        bot.reply_to(m, "❌ Это не твоя игра!")
        return
    
    bet = parse_bet(m.text, uid)
    if not bet or bet < 0.15:
        bot.reply_to(m, "❌ Мин. 0.15 $!")
        return
    if not enough(uid, bet):
        bot.reply_to(m, "❌ Недостаточно средств!")
        return
    
    _crash_run(m, uid, bet)

def _crash_point():
    r = random.random()
    if r < 0.02: return 1.01
    return round(min(0.99 / (1 - r), 1000.0), 2)

def _crash_run(m, uid, bet):
    cid = m.chat.id
    crash = _crash_point()
    mult = 1.00
    username = uname(m)
    
    msg = bot.send_message(cid,
        f"<b>🚀 КРАШ</b>  ${fmt(bet)}\n\n"
        f"📈 ×{mult:.2f}\n\nНажми ВЫВЕСТИ!")
    
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("💸 ВЫВЕСТИ", callback_data=f"cr_out_{uid}_{msg.message_id}"))
    
    CR[uid] = {"active": True, "cashed": False, "mult": mult,
               "cid": cid, "mid": msg.message_id, "bet": bet,
               "crash": crash, "username": username}
    
    bot.edit_message_reply_markup(cid, msg.message_id, reply_markup=k)

    def tick():
        nonlocal mult
        while True:
            time.sleep(0.6)
            if uid not in CR or not CR[uid]["active"]: return
            
            step = 0.05 if mult < 2 else (0.1 if mult < 5 else 0.2)
            mult = round(mult + step, 2)
            CR[uid]["mult"] = mult
            
            if mult >= crash:
                state = CR.pop(uid, None)
                if not state or state["cashed"]: return
                
                db.record(uid, bet, False)
                mode = db.get_mode(uid)
                img_buf = make_lose_image(state["username"], bet, f"🚀 Краш (×{crash})")
                
                kb2 = types.InlineKeyboardMarkup(row_width=2)
                kb2.add(
                    types.InlineKeyboardButton("🔄 Снова", callback_data="g_crash"),
                    types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
                )
                
                try:
                    bot.edit_message_media(
                        types.InputMediaPhoto(img_buf, caption=f"💥 Краш на ×{crash}!\n"
                                                              f"💰 ${fmt(db.bal(uid))}"),
                        cid, msg.message_id, reply_markup=kb2)
                except:
                    pass
                
                log_to_channel(f"❌ {state['username']} проиграл ${fmt(bet)} в Краш (×{crash})")
                return
            
            try:
                bot.edit_message_text(
                    f"<b>🚀 КРАШ</b>  ${fmt(bet)}\n\n"
                    f"📈 <b>×{mult:.2f}</b>\n\nНажми ВЫВЕСТИ!",
                    cid, msg.message_id, reply_markup=k)
            except: pass

    threading.Thread(target=tick, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("cr_out_"))
def cb_crash_out(c):
    parts = c.data.split("_")
    uid = int(parts[2])
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    s = CR.pop(uid, None)
    if not s or not s["active"]:
        bot.answer_callback_query(c.id, "Игра уже завершена!")
        return
    
    s["cashed"] = True
    s["active"] = False
    mult = s["mult"]
    bet = s["bet"]
    profit = round(bet * mult - bet, 2)
    
    db.record(uid, bet, True, profit)
    mode = db.get_mode(uid)
    
    img_buf = make_win_image(s["username"], profit, f"🚀 Краш (×{mult:.2f})")
    
    kb2 = types.InlineKeyboardMarkup(row_width=2)
    kb2.add(
        types.InlineKeyboardButton("🔄 Снова", callback_data="g_crash"),
        types.InlineKeyboardButton("🏠 Меню", callback_data=f"back_{mode}"),
    )
    
    try:
        bot.edit_message_media(
            types.InputMediaPhoto(img_buf, caption=f"🚀 Вывод ×{mult:.2f}\n"
                                                   f"💰 ${fmt(db.bal(uid))}"),
            s["cid"], s["mid"], reply_markup=kb2)
    except:
        bot.send_photo(s["cid"], img_buf,
                      caption=f"🚀 Вывод ×{mult:.2f}\n💰 ${fmt(db.bal(uid))}", reply_markup=kb2)
    
    log_to_channel(f"✅ {s['username']} выиграл ${fmt(profit)} в Краш (×{mult:.2f})")
    bot.answer_callback_query(c.id, f"💸 ×{mult:.2f}!")

# ════════════════════════════════════════════
#  📈 ТРЕЙДЕР
# ════════════════════════════════════════════
COINS = ["BTC","ETH","SOL","DOGE","PEPE","BNB","XRP"]

def _trader(m, uid, bet):
    coin = random.choice(COINS)
    price = round(random.uniform(0.01, 50000), 2)
    G[uid] = {"game": "trader", "coin": coin, "price": price, "bet": bet, "creator": uid}
    
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("📈 LONG", callback_data=f"tr_{uid}_up"),
        types.InlineKeyboardButton("📉 SHORT", callback_data=f"tr_{uid}_down"),
    )
    
    username = uname(m)
    img_buf = make_game_image(f"📈 {coin}", bet, username)
    bot.send_photo(m.chat.id, img_buf,
                  caption=f"🪙 {coin} = ${fmt(price)}\n\nКуда пойдёт цена?", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("tr_"))
def cb_trader(c):
    parts = c.data.split("_")
    uid = int(parts[1])
    dir_ = parts[2]
    
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "❌ Не твоя игра!", show_alert=True)
        return
    
    s = G.pop(uid, None)
    if not s:
        bot.answer_callback_query(c.id, "Игра не найдена!")
        return
    
    bet = s["bet"]
    coin = s["coin"]
    old_p = s["price"]
    
    bot.answer_callback_query(c.id, "⏳ Ждём...")
    bot.edit_message_caption(f"📈 {coin}\n\n⏳ Считаем...",
                            c.message.chat.id, c.message.message_id)
    time.sleep(3)
    
    change = random.uniform(-0.15, 0.15)
    new_p = round(old_p * (1 + change), 2)
    went_up = new_p > old_p
    correct = (dir_ == "up" and went_up) or (dir_ == "down" and not went_up)
    pct = round(abs(change) * 100, 1)
    mode = db.get_mode(uid)
    username = uname(c)
    
    if correct:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        img_buf = make_win_image(username, profit, f"📈 {coin}")
        log_to_channel(f"✅ {username} выиграл ${fmt(profit)} в Трейдер ({coin})")
    else:
        db.record(uid, bet, False)
        img_buf = make_lose_image(username, bet, f"📈 {coin}")
        log_to_channel(f"❌ {username} проиграл ${fmt(bet)} в Трейдер ({coin})")
    
    arrow = "📈" if went_up else "📉"
    try:
        bot.edit_message_media(
            types.InputMediaPhoto(img_buf, caption=f"{arrow} ${fmt(old_p)} → ${fmt(new_p)}\n"
                                                   f"({'+' if went_up else '-'}{pct}%)\n"
                                                   f"💰 ${fmt(db.bal(uid))}"),
            c.message.chat.id, c.message.message_id, reply_markup=kb_again("trader", mode))
    except:
        bot.send_photo(c.message.chat.id, img_buf,
                      caption=f"{arrow} ${fmt(old_p)} → ${fmt(new_p)}\n"
                             f"({'+' if went_up else '-'}{pct}%)\n"
                             f"💰 ${fmt(db.bal(uid))}", reply_markup=kb_again("trader", mode))

# ════════════════════════════════════════════
#  💼 ПРОФИЛЬ
# ════════════════════════════════════════════
@bot.message_handler(commands=['profile'])
@bot.message_handler(func=lambda m: m.text == "💼 Профиль")
def cmd_profile(m):
    uid = m.from_user.id
    db.ensure(uid, uname(m))
    user = db.get(uid)
    if not user:
        bot.send_message(m.chat.id, "Профиль не найден.")
        return
    
    buf = make_profile_card(user)
    bot.send_photo(m.chat.id, buf)

# ════════════════════════════════════════════
#  🏆 ТОП
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🏆 Топ")
def cmd_top(m):
    rows = db.top(10)
    if not rows:
        bot.send_message(m.chat.id, "Таблица пуста.");  return
    
    medals = ["🥇","🥈","🥉"] + ["🔹"]*7
    text = "<b>🏆 ТОП-10</b>\n"
    for i, r in enumerate(rows):
        wr = round(r[2] / r[3] * 100, 1) if r[3] else 0
        text += f"{medals[i]} <b>{r[0]}</b> — ${fmt(r[1])}\n"
    bot.send_message(m.chat.id, text)

# ════════════════════════════════════════════
#  📊 СТАТИСТИКА
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def cmd_stats(m):
    uid = m.from_user.id
    db.ensure(uid, uname(m))
    user = db.get(uid)
    if not user:
        bot.send_message(m.chat.id, "Нет данных.");  return
    
    wr = round(user['wins'] / user['games'] * 100, 1) if user['games'] else 0
    profit = user['total_won'] - user['total_bet']
    sign = "+" if profit >= 0 else ""
    
    bot.send_message(m.chat.id,
        f"<b>📊 СТАТИСТИКА</b>\n"
        f"🎮 Игр: <b>{user['games']}</b>\n"
        f"✅ Побед: <b>{user['wins']}</b>\n"
        f"❌ Поражений: <b>{user['losses']}</b>\n"
        f"📈 WR: <b>{wr}%</b>\n\n"
        f"💸 Оборот: <b>${fmt(user['total_bet'])}</b>\n"
        f"💰 Выигрыш: <b>${fmt(user['total_won'])}</b>\n"
        f"📊 Прибыль: <b>{sign}${fmt(profit)}</b>")

# ════════════════════════════════════════════
#  💰 ПОПОЛНЕНИЕ
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "💰 Пополнение")
def cmd_deposit(m):
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("💳 Пополнить", url=CRYPTO_LINK))
    bot.send_message(m.chat.id,
        f"<b>💰 Пополни счёт</b>\n\n"
        f"Нажми кнопку ниже и выбери сумму.\n"
        f"Криптовалюта поступит мгновенно!", reply_markup=k)

# ════════════════════════════════════════════
#  ℹ️ ПОМОЩЬ
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def cmd_help(m):
    bot.send_message(m.chat.id,
        f"<b>ℹ️ {CASINO_NAME}</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"🎲 Кости · 🪙 Монетка\n"
        f"⚽ Футбол · 🏀 Баскет · 🎯 Дартс · 🎳 Боулинг\n"
        f"🐍 Угадай 1/5 · ⚔️ PvP Дуэль\n"
        f"🃏 Блэкджек · 🎰 Слоты · 🎡 Рулетка\n"
        f"💣 Майнс (1 и 2 мины) · 🏔️ Башня\n"
        f"🚀 Краш · 📈 Трейдер\n\n"
        f"<b>💡 Советы:</b>\n"
        f"• Минимальная ставка: 0.15 $\n"
        f"• Максимум в ва-банк\n"
        f"• PvP только в группах\n\n"
        f"<b>💰 Пополнение:</b>\n"
        f"Нажми «Пополнение» в меню")

# ════════════════════════════════════════════
#  👑 МОДЕРАТОР
# ════════════════════════════════════════════
@bot.message_handler(commands=['modgive'])
def mod_give(m):
    if m.from_user.id not in MODERATOR_IDS:
        return
    try:
        _, uid, amt = m.text.split()
        db.ensure(int(uid))
        db.add(int(uid), float(amt))
        log_to_channel(f"💰 Модератор @{m.from_user.username} выдал "
                      f"${fmt(float(amt))} игроку {uid}")
        bot.reply_to(m, f"✅ Выдано ${fmt(float(amt))}")
    except:
        bot.reply_to(m, "Формат: /modgive ID СУММА")

@bot.message_handler(commands=['modset'])
def mod_set(m):
    if m.from_user.id not in MODERATOR_IDS:
        return
    try:
        _, uid, amt = m.text.split()
        db.ensure(int(uid))
        db.set_bal(int(uid), float(amt))
        log_to_channel(f"💰 Модератор @{m.from_user.username} установил баланс "
                      f"${fmt(float(amt))} игроку {uid}")
        bot.reply_to(m, f"✅ Баланс = ${fmt(float(amt))}")
    except:
        bot.reply_to(m, "Формат: /modset ID СУММА")

@bot.message_handler(commands=['modstats'])
def mod_stats(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    db.cur.execute("SELECT COUNT(*), SUM(balance), SUM(games), SUM(total_bet) FROM users")
    r = db.cur.fetchone()
    bot.reply_to(m,
        f"<b>📊 КАЗИНО СТАТИСТИКА</b>\n\n"
        f"👥 Игроков: <b>{r[0]}</b>\n"
        f"💰 Всего баланса: <b>${fmt(r[1] or 0)}</b>\n"
        f"🎮 Всего игр: <b>{r[2]}</b>\n"
        f"💸 Оборот: <b>${fmt(r[3] or 0)}</b>")

# ════════════════════════════════════════════
#  NOOP
# ════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "noop")
def cb_noop(c):
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  FLASK (Render)
# ════════════════════════════════════════════
def run_flask():
    app = Flask(__name__)

    @app.route('/')
    def index():
        return "<h2>🎰 NEZZX x KLITOK CASINO — Online</h2>"

    @app.route('/health')
    def health():
        return {"status": "ok", "casino": "running"}

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ════════════════════════════════════════════
#  ЗАПУСК
# ════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("🎰 NEZZX x KLITOK CASINO — ЗАПУСК")
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("🌐 Flask запущен")
    
    while True:
        try:
            logger.info("🤖 Polling...")
            bot.remove_webhook()
            time.sleep(0.5)
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=["message", "callback_query"]
            )
        except Exception as e:
            logger.error(f"Ошибка polling: {e}")
            time.sleep(10)
