# bot.py
import telebot, sqlite3, random, threading, time, os, logging, io
from telebot import types
from flask import Flask
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
ADMIN_IDS = [8357023784, 8539734813]

# ════════════════════════════════════════════
#  БАЗА ДАННЫХ
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
                    balance   REAL    DEFAULT 1000,
                    wins      INTEGER DEFAULT 0,
                    losses    INTEGER DEFAULT 0,
                    games     INTEGER DEFAULT 0,
                    total_bet REAL    DEFAULT 0,
                    total_won REAL    DEFAULT 0,
                    mode      TEXT    DEFAULT 'crypto',
                    last_daily INTEGER DEFAULT 0,
                    streak    INTEGER DEFAULT 0
                );
            """)
            self.conn.commit()

    def ensure(self, uid, username="Player"):
        with self.lock:
            self.cur.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?,?)", (uid, username))
            self.cur.execute("UPDATE users SET username=? WHERE id=?", (username, uid))
            self.conn.commit()

    def get(self, uid):
        self.cur.execute("SELECT * FROM users WHERE id=?", (uid,))
        r = self.cur.fetchone()
        return dict(r) if r else None

    def bal(self, uid):
        self.cur.execute("SELECT balance FROM users WHERE id=?", (uid,))
        r = self.cur.fetchone()
        return r[0] if r else 1000.0

    def add(self, uid, amount):
        with self.lock:
            self.cur.execute("UPDATE users SET balance=balance+? WHERE id=?", (round(amount,2), uid))
            self.conn.commit()

    def set_bal(self, uid, amount):
        with self.lock:
            self.cur.execute("UPDATE users SET balance=? WHERE id=?", (round(amount,2), uid))
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

    def daily(self, uid):
        u = self.get(uid)
        now = int(time.time())
        if now - u['last_daily'] < 86400:
            return False, int(86400 - (now - u['last_daily']))
        streak = (u['streak'] + 1) if (now - u['last_daily'] < 172800) else 1
        bonus = 100 + streak * 20
        with self.lock:
            self.cur.execute(
                "UPDATE users SET last_daily=?, streak=?, balance=balance+? WHERE id=?",
                (now, streak, bonus, uid)
            )
            self.conn.commit()
        return True, bonus

    def top(self, n=10):
        self.cur.execute(
            "SELECT username, total_won, wins, games FROM users ORDER BY total_won DESC LIMIT ?", (n,)
        )
        return self.cur.fetchall()

db = CasinoDB()

# ════════════════════════════════════════════
#  ГЕНЕРАЦИЯ ПРОФИЛЬ-КАРТОЧКИ (PIL)
# ════════════════════════════════════════════
def make_profile_card(user: dict) -> io.BytesIO:
    W, H = 600, 340
    # Фон — тёмный градиент вручную
    img  = Image.new("RGB", (W, H), (10, 10, 18))
    draw = ImageDraw.Draw(img)

    # Градиентная полоска сверху
    for x in range(W):
        r = int(120 * x / W)
        g = int(60  * x / W)
        b = int(200 + 55 * x / W)
        draw.line([(x, 0), (x, 6)], fill=(r, g, b))

    # Рамка карточки
    draw.rounded_rectangle([10, 10, W-10, H-10], radius=18,
                            outline=(80, 60, 180), width=2)

    # Заголовок
    draw.rectangle([10, 10, W-10, 60], fill=(25, 18, 50))
    draw.text((24, 18), "🎰  MEGA CASINO", fill=(180, 140, 255))
    draw.text((W-140, 18), "PLAYER CARD", fill=(100, 100, 140))

    # Аватар-заглушка (круг)
    cx, cy, cr = 70, 130, 42
    draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=(40, 30, 80), outline=(120, 80, 220), width=2)
    draw.text((cx-10, cy-14), "👤", fill=(200, 180, 255))

    # Имя и ID
    name = user.get('username', 'Player')[:20]
    draw.text((130, 75),  name,              fill=(240, 230, 255))
    draw.text((130, 105), f"ID: {user['id']}", fill=(120, 110, 160))

    # Баланс — крупно
    bal_str = f"$ {user['balance']:,.2f}"
    draw.text((130, 130), bal_str, fill=(80, 220, 130))
    draw.text((130, 162), "БАЛАНС", fill=(80, 120, 90))

    # Разделитель
    draw.line([(20, 195), (W-20, 195)], fill=(50, 40, 90), width=1)

    # Статистика — сетка 3 колонки
    stats = [
        ("ИГРЫ",      str(user.get('games', 0))),
        ("ПОБЕДЫ",    str(user.get('wins', 0))),
        ("ПРОИГРЫШИ", str(user.get('losses', 0))),
    ]
    for i, (label, val) in enumerate(stats):
        x = 30 + i * 190
        draw.text((x, 210), val,   fill=(220, 200, 255))
        draw.text((x, 238), label, fill=(100, 90,  140))

    # Оборот и выигрыш
    draw.line([(20, 270), (W-20, 270)], fill=(50, 40, 90), width=1)
    draw.text((30,  280), f"Поставлено: $ {user.get('total_bet',0):,.0f}", fill=(140, 130, 170))
    draw.text((330, 280), f"Выиграно:   $ {user.get('total_won',0):,.0f}", fill=(100, 200, 130))

    # Режим
    mode_txt = "💎 Crypto Casino" if user.get('mode') == 'crypto' else "🐸 BrainRot"
    draw.text((30, 308), mode_txt, fill=(160, 120, 220))

    # Серия дейли
    draw.text((W-180, 308), f"🔥 Серия: {user.get('streak',0)} д.", fill=(220, 160, 60))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════
def uname(m_or_c):
    u = m_or_c.from_user if hasattr(m_or_c, 'from_user') else m_or_c
    return f"@{u.username}" if u.username else (u.first_name or "Игрок")

def fmt(n): return f"{n:,.2f}"

def parse_bet(text, uid):
    text = text.strip().lower()
    if text in ('all', 'всё', 'allin'):
        return db.bal(uid)
    try:
        v = float(text)
        return v if v > 0 else None
    except:
        return None

def enough(uid, bet):
    return db.bal(uid) >= bet

# Хранилища состояний
G = {}   # game_states  uid -> dict
BJ = {}  # blackjack    uid -> dict
MN = {}  # mines        uid -> dict
CR = {}  # crash        uid -> dict
PVP = {} # pvp lobbies  chat_id -> dict

# ════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ════════════════════════════════════════════
def kb_main():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    k.add("🎮 Играть", "💼 Профиль",
          "🏆 Топ",    "📊 Статистика",
          "🎁 Бонус",  "ℹ️ Помощь")
    return k

def kb_play_mode():
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton(
        "🐸  BrainRot — Дайсы, PvP, Мемы",
        callback_data="mode_brainrot"))
    k.add(types.InlineKeyboardButton(
        "💎  Crypto Casino — Блэкджек, Майнс, Краш",
        callback_data="mode_crypto"))
    return k

def kb_brainrot():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🎲 Кости",      callback_data="g_dice"),
        types.InlineKeyboardButton("🪙 Монетка",    callback_data="g_coin"),
        types.InlineKeyboardButton("⚽ Футбол",     callback_data="g_football"),
        types.InlineKeyboardButton("🏀 Баскет",     callback_data="g_basket"),
        types.InlineKeyboardButton("🎯 Дартс",      callback_data="g_darts"),
        types.InlineKeyboardButton("🎳 Боулинг",    callback_data="g_bowling"),
        types.InlineKeyboardButton("⚔️ PvP Дуэль", callback_data="g_pvp"),
        types.InlineKeyboardButton("🐍 Угадай 1/5", callback_data="g_snake"),
    )
    k.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_mode"))
    return k

def kb_crypto():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🃏 Блэкджек",    callback_data="g_blackjack"),
        types.InlineKeyboardButton("🎰 Слоты",       callback_data="g_slots"),
        types.InlineKeyboardButton("🎡 Рулетка",     callback_data="g_roulette"),
        types.InlineKeyboardButton("💣 Майнс",       callback_data="g_mines"),
        types.InlineKeyboardButton("🚀 Краш",        callback_data="g_crash"),
        types.InlineKeyboardButton("🃏 Видео-покер", callback_data="g_poker"),
        types.InlineKeyboardButton("📈 Трейдер",     callback_data="g_trader"),
        types.InlineKeyboardButton("🔢 Угадай число",callback_data="g_guess"),
    )
    k.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_mode"))
    return k

def kb_bet(game):
    k = types.InlineKeyboardMarkup(row_width=4)
    amounts = [50, 100, 250, 500, 1000, 2000, 5000]
    k.add(*[types.InlineKeyboardButton(f"{a}$", callback_data=f"bet_{game}_{a}")
            for a in amounts])
    k.add(
        types.InlineKeyboardButton("✏️ Своя сумма", callback_data=f"bet_{game}_custom"),
        types.InlineKeyboardButton("💸 Ва-банк",    callback_data=f"bet_{game}_all"),
    )
    k.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_games"))
    return k

def kb_again(game, mode):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔄 Ещё раз", callback_data=f"g_{game}"),
        types.InlineKeyboardButton("🏠 Меню",    callback_data=f"back_{'brainrot' if mode=='brainrot' else 'crypto'}"),
    )
    return k

# ════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def cmd_start(m):
    db.ensure(m.from_user.id, uname(m))
    text = (
        "<b>🎰 MEGA CASINO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Привет, <b>{m.from_user.first_name}</b>!\n"
        "Стартовый баланс: <b>1 000 $</b>\n\n"
        "Нажми <b>🎮 Играть</b> и выбери режим."
    )
    bot.send_message(m.chat.id, text, reply_markup=kb_main())

# ════════════════════════════════════════════
#  🎮 ИГРАТЬ — выбор режима
# ════════════════════════════════════════════
@bot.message_handler(commands=['play'])
@bot.message_handler(func=lambda m: m.text == "🎮 Играть")
def cmd_play(m):
    uid = m.from_user.id
    db.ensure(uid, uname(m))
    text = (
        "<b>🎮 ВЫБЕРИ РЕЖИМ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🐸 BrainRot</b>\n"
        "  Кости, монетка, дуэли с друзьями\n\n"
        "<b>💎 Crypto Casino</b>\n"
        "  Блэкджек, майнс, краш, покер\n\n"
        f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>"
    )
    bot.send_message(m.chat.id, text, reply_markup=kb_play_mode())

# ════════════════════════════════════════════
#  CALLBACK — выбор режима
# ════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data.startswith("mode_"))
def cb_mode(c):
    uid  = c.from_user.id
    mode = c.data.split("_")[1]
    db.ensure(uid, uname(c))
    db.set_mode(uid, mode)

    if mode == "brainrot":
        text = (
            "<b>🐸 BRAINROT CASINO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>\n\n"
            "Выбери игру:"
        )
        kb = kb_brainrot()
    else:
        text = (
            "<b>💎 CRYPTO CASINO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>\n\n"
            "Выбери игру:"
        )
        kb = kb_crypto()

    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb)
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_mode")
def cb_back_mode(c):
    uid = c.from_user.id
    text = (
        "<b>🎮 ВЫБЕРИ РЕЖИМ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>"
    )
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb_play_mode())
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb_play_mode())
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data in ("back_brainrot", "back_crypto"))
def cb_back_games(c):
    uid  = c.from_user.id
    mode = "brainrot" if c.data == "back_brainrot" else "crypto"
    text = (
        f"<b>{'🐸 BRAINROT' if mode=='brainrot' else '💎 CRYPTO'} CASINO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>"
    )
    kb = kb_brainrot() if mode == "brainrot" else kb_crypto()
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_games")
def cb_back_g(c):
    uid  = c.from_user.id
    mode = db.get_mode(uid)
    text = (
        f"<b>{'🐸 BRAINROT' if mode=='brainrot' else '💎 CRYPTO'} CASINO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>"
    )
    kb = kb_brainrot() if mode == "brainrot" else kb_crypto()
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb)
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  CALLBACK — выбор игры → ставка
# ════════════════════════════════════════════
GNAMES = {
    "dice": "🎲 Кости", "coin": "🪙 Монетка", "football": "⚽ Футбол",
    "basket": "🏀 Баскет", "darts": "🎯 Дартс", "bowling": "🎳 Боулинг",
    "pvp": "⚔️ PvP Дуэль", "snake": "🐍 Угадай 1/5",
    "blackjack": "🃏 Блэкджек", "slots": "🎰 Слоты", "roulette": "🎡 Рулетка",
    "mines": "💣 Майнс", "crash": "🚀 Краш", "poker": "🃏 Видео-покер",
    "trader": "📈 Трейдер", "guess": "🔢 Угадай число",
}

@bot.callback_query_handler(func=lambda c: c.data.startswith("g_"))
def cb_game_pick(c):
    uid  = c.from_user.id
    game = c.data[2:]
    db.ensure(uid, uname(c))

    # PvP и Краш — особый старт
    if game == "pvp":
        _pvp_create(c)
        return
    if game == "crash":
        _crash_info(c)
        return

    bal  = db.bal(uid)
    name = GNAMES.get(game, game)
    text = (
        f"<b>{name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс: <b>{fmt(bal)} $</b>\n\n"
        "Выбери ставку:"
    )
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb_bet(game))
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb_bet(game))
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  CALLBACK — ставка выбрана
# ════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data.startswith("bet_"))
def cb_bet(c):
    uid   = c.from_user.id
    parts = c.data.split("_")
    game  = parts[1]
    amt_s = parts[2]
    db.ensure(uid, uname(c))

    if amt_s == "custom":
        G[uid] = {"wait": "bet", "game": game}
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id,
            f"✏️ Введи сумму ставки (мин. 10 $):\n💰 Баланс: <b>{fmt(db.bal(uid))} $</b>")
        return

    bet = db.bal(uid) if amt_s == "all" else float(amt_s)

    if bet < 10:
        bot.answer_callback_query(c.id, "Мин. ставка — 10 $!", show_alert=True); return
    if not enough(uid, bet):
        bot.answer_callback_query(c.id, "❌ Недостаточно средств!", show_alert=True); return

    bot.answer_callback_query(c.id, f"Ставка {fmt(bet)} $ принята!")
    _launch(c.message, uid, game, bet)

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "bet")
def handle_custom_bet(m):
    uid   = m.from_user.id
    state = G.pop(uid)
    game  = state["game"]
    bet   = parse_bet(m.text, uid)

    if not bet or bet < 10:
        bot.reply_to(m, "❌ Минимум 10 $. Попробуй снова."); return
    if not enough(uid, bet):
        bot.reply_to(m, f"❌ Недостаточно средств. Баланс: <b>{fmt(db.bal(uid))} $</b>"); return

    _launch(m, uid, game, bet)

# ════════════════════════════════════════════
#  ДИСПЕТЧЕР ИГР
# ════════════════════════════════════════════
def _launch(m, uid, game, bet):
    fn = {
        "dice":      _dice,
        "coin":      _coin,
        "football":  _football,
        "basket":    _basket,
        "darts":     _darts,
        "bowling":   _bowling,
        "snake":     _snake,
        "blackjack": _bj_start,
        "slots":     _slots,
        "roulette":  _roulette_start,
        "mines":     _mines_start,
        "poker":     _poker_start,
        "trader":    _trader,
        "guess":     _guess_start,
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
    bot.send_message(m.chat.id,
        f"<b>🎲 КОСТИ</b>  |  Ставка: <b>{fmt(bet)} $</b>\n"
        "Выброси 4, 5 или 6 — победа!")
    dv = bot.send_dice(m.chat.id, emoji='🎲').dice.value
    time.sleep(4)
    if dv >= 4:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>✅ ПОБЕДА!</b>  Выпало: <b>{dv}</b>\n"
                f"+ <b>{fmt(profit)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>❌ ПРОИГРЫШ</b>  Выпало: <b>{dv}</b>\n"
                f"− <b>{fmt(bet)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    bot.send_message(m.chat.id, text, reply_markup=kb_again("dice", mode))

# ════════════════════════════════════════════
#  🪙 МОНЕТКА
# ════════════════════════════════════════════
def _coin(m, uid, bet):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("👑 Орёл",  callback_data=f"coin_{uid}_{bet}_h"),
        types.InlineKeyboardButton("🔵 Решка", callback_data=f"coin_{uid}_{bet}_t"),
    )
    bot.send_message(m.chat.id,
        f"<b>🪙 МОНЕТКА</b>  |  Ставка: <b>{fmt(bet)} $</b>\n"
        "Выбери сторону:", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("coin_"))
def cb_coin(c):
    _, uid_s, bet_s, side = c.data.split("_")
    uid = int(uid_s); bet = float(bet_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    mode   = db.get_mode(uid)
    result = random.choice(["h", "t"])
    won    = result == side
    emoji  = "👑" if result == "h" else "🔵"
    if won:
        profit = round(bet * 0.95, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🪙 МОНЕТКА</b>  {emoji}\n"
                f"<b>✅ ПОБЕДА!  +{fmt(profit)} $</b>\n"
                f"💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>🪙 МОНЕТКА</b>  {emoji}\n"
                f"<b>❌ ПРОИГРЫШ  −{fmt(bet)} $</b>\n"
                f"💰 <b>{fmt(db.bal(uid))} $</b>")
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb_again("coin", mode))
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb_again("coin", mode))
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  ⚽ ФУТБОЛ
# ════════════════════════════════════════════
def _football(m, uid, bet):
    mode = db.get_mode(uid)
    bot.send_message(m.chat.id,
        f"<b>⚽ ФУТБОЛ</b>  |  Ставка: <b>{fmt(bet)} $</b>")
    dv = bot.send_dice(m.chat.id, emoji='⚽').dice.value
    time.sleep(4)
    if dv >= 4:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>⚽ ГОЛ!</b>  ({dv}/5)\n"
                f"<b>✅ +{fmt(profit)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>⚽ МИМО!</b>  ({dv}/5)\n"
                f"<b>❌ −{fmt(bet)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    bot.send_message(m.chat.id, text, reply_markup=kb_again("football", mode))

# ════════════════════════════════════════════
#  🏀 БАСКЕТ
# ════════════════════════════════════════════
def _basket(m, uid, bet):
    mode = db.get_mode(uid)
    bot.send_message(m.chat.id,
        f"<b>🏀 БАСКЕТБОЛ</b>  |  Ставка: <b>{fmt(bet)} $</b>")
    dv = bot.send_dice(m.chat.id, emoji='🏀').dice.value
    time.sleep(4)
    if dv >= 4:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🏀 ПОПАЛ!</b>  ({dv}/5)\n"
                f"<b>✅ +{fmt(profit)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>🏀 ПРОМАХ!</b>  ({dv}/5)\n"
                f"<b>❌ −{fmt(bet)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    bot.send_message(m.chat.id, text, reply_markup=kb_again("basket", mode))

# ════════════════════════════════════════════
#  🎯 ДАРТС
# ════════════════════════════════════════════
def _darts(m, uid, bet):
    mode = db.get_mode(uid)
    bot.send_message(m.chat.id,
        f"<b>🎯 ДАРТС</b>  |  Ставка: <b>{fmt(bet)} $</b>")
    dv = bot.send_dice(m.chat.id, emoji='🎯').dice.value
    time.sleep(4)
    if dv == 6:
        profit = round(bet * 2.0, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🎯 ЯБЛОЧКО!</b>  (6/6)\n"
                f"<b>✅ +{fmt(profit)} $</b>  ×3  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    elif dv >= 4:
        profit = round(bet * 0.7, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🎯 Близко!</b>  ({dv}/6)\n"
                f"<b>✅ +{fmt(profit)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>🎯 Промах!</b>  ({dv}/6)\n"
                f"<b>❌ −{fmt(bet)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    bot.send_message(m.chat.id, text, reply_markup=kb_again("darts", mode))

# ════════════════════════════════════════════
#  🎳 БОУЛИНГ
# ════════════════════════════════════════════
def _bowling(m, uid, bet):
    mode = db.get_mode(uid)
    bot.send_message(m.chat.id,
        f"<b>🎳 БОУЛИНГ</b>  |  Ставка: <b>{fmt(bet)} $</b>")
    dv = bot.send_dice(m.chat.id, emoji='🎳').dice.value
    time.sleep(4)
    if dv == 6:
        profit = round(bet * 1.5, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🎳 СТРАЙК!</b>\n"
                f"<b>✅ +{fmt(profit)} $</b>  ×2.5  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    elif dv >= 3:
        profit = round(bet * 0.5, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🎳 Неплохо!</b>  {dv} кеглей\n"
                f"<b>✅ +{fmt(profit)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>🎳 Гатер!</b>  {dv} кегли\n"
                f"<b>❌ −{fmt(bet)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    bot.send_message(m.chat.id, text, reply_markup=kb_again("bowling", mode))

# ════════════════════════════════════════════
#  🐍 УГАДАЙ 1/5
# ════════════════════════════════════════════
def _snake(m, uid, bet):
    target = random.randint(1, 5)
    G[uid] = {"game": "snake", "target": target, "bet": bet}
    k = types.InlineKeyboardMarkup(row_width=5)
    k.add(*[types.InlineKeyboardButton(str(i), callback_data=f"snake_{uid}_{i}") for i in range(1, 6)])
    bot.send_message(m.chat.id,
        f"<b>🐍 УГАДАЙ ЧИСЛО</b>  |  Ставка: <b>{fmt(bet)} $</b>\n"
        "Выбери число от 1 до 5  →  победа ×4", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("snake_"))
def cb_snake(c):
    _, uid_s, g_s = c.data.split("_")
    uid = int(uid_s); guess = int(g_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    state = G.pop(uid, None)
    if not state:
        bot.answer_callback_query(c.id, "Игра истекла!"); return
    bet    = state["bet"]
    target = state["target"]
    mode   = db.get_mode(uid)
    if guess == target:
        profit = round(bet * 3.0, 2)
        db.record(uid, bet, True, profit)
        text = (f"<b>🐍 УГАДАЛ!</b>  Число было <b>{target}</b>\n"
                f"<b>✅ +{fmt(profit)} $</b>  ×4  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        text = (f"<b>🐍 НЕ УГАДАЛ!</b>  Было <b>{target}</b>, выбрал <b>{guess}</b>\n"
                f"<b>❌ −{fmt(bet)} $</b>  |  💰 <b>{fmt(db.bal(uid))} $</b>")
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb_again("snake", mode))
    except:
        bot.send_message(c.message.chat.id, text, reply_markup=kb_again("snake", mode))
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  ⚔️ PvP ДУЭЛЬ
# ════════════════════════════════════════════
def _pvp_create(c):
    uid     = c.from_user.id
    chat_id = c.message.chat.id
    if chat_id in PVP:
        bot.answer_callback_query(c.id, "Уже есть активная дуэль!", show_alert=True); return
    G[uid] = {"wait": "pvp_bet", "chat_id": chat_id}
    bot.answer_callback_query(c.id)
    bot.send_message(chat_id,
        f"<b>⚔️ PvP ДУЭЛЬ</b>\n"
        f"{uname(c)} создаёт дуэль!\n"
        "Введи сумму ставки:")

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "pvp_bet")
def handle_pvp_bet(m):
    uid   = m.from_user.id
    state = G.pop(uid)
    bet   = parse_bet(m.text, uid)
    chat_id = state.get("chat_id", m.chat.id)
    if not bet or bet < 50:
        bot.reply_to(m, "❌ Минимум 50 $ для дуэли."); return
    if not enough(uid, bet):
        bot.reply_to(m, "❌ Недостаточно средств!"); return
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton(
        f"⚔️ Принять дуэль ({fmt(bet)} $)",
        callback_data=f"pvp_acc_{uid}_{bet}"))
    msg = bot.send_message(chat_id,
        f"<b>⚔️ ДУЭЛЬ!</b>\n"
        f"Игрок: <b>{uname(m)}</b>\n"
        f"Ставка: <b>{fmt(bet)} $</b>\n\n"
        "Кто примет вызов? ⏱ 60 сек", reply_markup=k)
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
    creator = int(uid_s); bet = float(bet_s)
    uid     = c.from_user.id
    chat_id = c.message.chat.id
    if uid == creator:
        bot.answer_callback_query(c.id, "Нельзя принять свою дуэль!"); return
    if not enough(uid, bet):
        bot.answer_callback_query(c.id, "❌ Недостаточно средств!", show_alert=True); return
    if chat_id not in PVP:
        bot.answer_callback_query(c.id, "Дуэль уже завершена!"); return
    lobby = PVP.pop(chat_id)
    bot.answer_callback_query(c.id, "🎲 Бросаем кости!")
    bot.edit_message_text(
        f"<b>⚔️ ДУЭЛЬ НАЧАЛАСЬ!</b>\n"
        f"🔴 {lobby['cname']} vs 🔵 {uname(c)}\n"
        f"Ставка: <b>{fmt(bet)} $</b> каждый\n\n<i>Бросаем кости...</i>",
        chat_id, c.message.message_id)
    time.sleep(1)
    bot.send_message(chat_id, f"🔴 {lobby['cname']} бросает...")
    d1 = bot.send_dice(chat_id, emoji='🎲').dice.value
    time.sleep(1)
    bot.send_message(chat_id, f"🔵 {uname(c)} бросает...")
    d2 = bot.send_dice(chat_id, emoji='🎲').dice.value
    time.sleep(4)
    if d1 == d2:
        bot.send_message(chat_id,
            f"<b>🤝 НИЧЬЯ!</b>  {d1} vs {d2}\nСтавки возвращены.")
        return
    if d1 > d2:
        wid, wname, wd, ld = creator, lobby['cname'], d1, d2
        lid = uid; lname = uname(c)
    else:
        wid, wname, wd, ld = uid, uname(c), d2, d1
        lid = creator; lname = lobby['cname']
    prize = round(bet * 1.85, 2)
    db.record(wid, bet, True, prize)
    db.record(lid, bet, False)
    bot.send_message(chat_id,
        f"<b>⚔️ РЕЗУЛЬТАТ ДУЭЛИ</b>\n\n"
        f"🔴 {lobby['cname']}: <b>{d1}</b>\n"
        f"🔵 {uname(c)}: <b>{d2}</b>\n\n"
        f"<b>👑 Победитель: {wname}!</b>\n"
        f"Приз: <b>+{fmt(prize)} $</b>\n"
        f"💰 Баланс победителя: <b>{fmt(db.bal(wid))} $</b>")

# ════════════════════════════════════════════
#  🃏 БЛЭКДЖЕК
# ════════════════════════════════════════════
SUITS = ["♠","♥","♦","♣"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

def _deck():
    d = [(r,s) for s in SUITS for r in RANKS]
    random.shuffle(d)
    return d

def _cv(card):
    r = card[0]
    if r in ("J","Q","K"): return 10
    if r == "A":           return 11
    try: return int(r)
    except: return 10

def _hv(hand):
    t = sum(_cv(c) for c in hand)
    a = sum(1 for c in hand if c[0] == "A")
    while t > 21 and a:
        t -= 10; a -= 1
    return t

def _hstr(hand):
    return "  ".join(f"{c[0]}{c[1]}" for c in hand)

def _bj_start(m, uid, bet):
    deck = _deck()
    ph   = [deck.pop(), deck.pop()]
    dh   = [deck.pop(), deck.pop()]
    BJ[uid] = {"deck": deck, "p": ph, "d": dh, "bet": bet, "cid": m.chat.id}
    _bj_show(m.chat.id, uid)

def _bj_show(cid, uid, end=False, edit_mid=None):
    s  = BJ.get(uid)
    if not s: return
    ph = s["p"]; dh = s["d"]; bet = s["bet"]
    pv = _hv(ph); dv = _hv(dh)
    d_line = _hstr(dh) + f"  [{dv}]" if end else f"{dh[0][0]}{dh[0][1]}  🂠  [?]"
    text = (
        f"<b>🃏 БЛЭКДЖЕК</b>  |  Ставка: <b>{fmt(bet)} $</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 Дилер:  <code>{d_line}</code>\n"
        f"👤 Ты:     <code>{_hstr(ph)}</code>  [<b>{pv}</b>]\n"
    )
    if not end:
        k = types.InlineKeyboardMarkup(row_width=2)
        k.add(
            types.InlineKeyboardButton("👊 Ещё",   callback_data=f"bj_h_{uid}"),
            types.InlineKeyboardButton("✋ Стоп",  callback_data=f"bj_s_{uid}"),
        )
        if db.bal(uid) >= bet:
            k.add(types.InlineKeyboardButton("💰 Удвоить", callback_data=f"bj_d_{uid}"))
        if edit_mid:
            try:
                bot.edit_message_text(text, cid, edit_mid, reply_markup=k)
                return
            except: pass
        bot.send_message(cid, text, reply_markup=k)
    else:
        res, won, profit = _bj_resolve(uid, pv, dv, bet)
        mode = db.get_mode(uid)
        text += f"\n{res}"
        if edit_mid:
            try:
                bot.edit_message_text(text, cid, edit_mid, reply_markup=kb_again("blackjack", mode))
                return
            except: pass
        bot.send_message(cid, text, reply_markup=kb_again("blackjack", mode))

def _bj_resolve(uid, pv, dv, bet):
    mode = db.get_mode(uid)
    if pv > 21:
        db.record(uid, bet, False)
        return f"<b>❌ Перебор!  −{fmt(bet)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>", False, 0
    if dv > 21 or pv > dv:
        p = round(bet * 0.95, 2)
        db.record(uid, bet, True, p)
        return f"<b>✅ Победа!  +{fmt(p)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>", True, p
    if pv == dv:
        return f"<b>🤝 Ничья.  Ставка возвращена</b>\n💰 <b>{fmt(db.bal(uid))} $</b>", False, 0
    db.record(uid, bet, False)
    return f"<b>❌ Дилер выигрывает.  −{fmt(bet)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>", False, 0

@bot.callback_query_handler(func=lambda c: c.data.startswith("bj_"))
def cb_bj(c):
    parts  = c.data.split("_")
    action = parts[1]
    uid    = int(parts[2])
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = BJ.get(uid)
    if not s:
        bot.answer_callback_query(c.id, "Игра не найдена!"); return
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
            bot.answer_callback_query(c.id, "Не хватает средств!", show_alert=True); return
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
SYM  = ["🍒","🍋","🍊","🍇","🔔","💎","7️⃣","🎰"]
SWGT = [30,  25,  20,  15,   5,   3,   1.5,  0.5]
SPAY = {
    "🎰🎰🎰": 50, "7️⃣7️⃣7️⃣": 20, "💎💎💎": 15,
    "🔔🔔🔔": 10, "🍇🍇🍇": 8,  "🍊🍊🍊": 6,
    "🍋🍋🍋": 5,  "🍒🍒🍒": 4,
}

def _spin():
    tw = sum(SWGT); out = []
    for _ in range(3):
        r = random.uniform(0, tw); c = 0
        for s, w in zip(SYM, SWGT):
            c += w
            if r <= c: out.append(s); break
    return out

def _slots(m, uid, bet):
    mode = db.get_mode(uid)
    anim = bot.send_message(m.chat.id,
        f"<b>🎰 СЛОТЫ</b>  |  Ставка: <b>{fmt(bet)} $</b>\n\n"
        "🎰 Крутим барабаны...")
    time.sleep(0.5)
    reels = _spin()
    key   = "".join(reels)
    for _ in range(3):
        f2 = [random.choice(SYM) for _ in range(3)]
        try:
            bot.edit_message_text(
                f"<b>🎰 СЛОТЫ</b>\n\n"
                f"| {' | '.join(f2)} |\n\n<i>Крутится...</i>",
                m.chat.id, anim.message_id)
        except: pass
        time.sleep(0.5)
    mult = SPAY.get(key, 0)
    if mult == 0 and len(set(reels)) == 2:
        mult = 1.5
    if mult > 0:
        profit = round(bet * mult, 2)
        db.record(uid, bet, True, profit)
        jackpot = "  🎊 ДЖЕКПОТ!" if mult >= 20 else ""
        res = (f"<b>🎰 СЛОТЫ</b>{jackpot}\n\n"
               f"| {' | '.join(reels)} |\n\n"
               f"×{mult}  →  <b>✅ +{fmt(profit)} $</b>\n"
               f"💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        res = (f"<b>🎰 СЛОТЫ</b>\n\n"
               f"| {' | '.join(reels)} |\n\n"
               f"<b>❌ −{fmt(bet)} $</b>\n"
               f"💰 <b>{fmt(db.bal(uid))} $</b>")
    try:
        bot.edit_message_text(res, m.chat.id, anim.message_id,
                              reply_markup=kb_again("slots", mode))
    except:
        bot.send_message(m.chat.id, res, reply_markup=kb_again("slots", mode))

# ════════════════════════════════════════════
#  🎡 РУЛЕТКА
# ════════════════════════════════════════════
RCOL = {0: "🟢",
        **{n:"🔴" for n in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]},
        **{n:"⚫" for n in [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]}}

def _roulette_start(m, uid, bet):
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔴 Красное ×2",  callback_data=f"rul_{uid}_{bet}_red"),
        types.InlineKeyboardButton("⚫ Чёрное ×2",   callback_data=f"rul_{uid}_{bet}_black"),
        types.InlineKeyboardButton("🟢 Зеро ×35",    callback_data=f"rul_{uid}_{bet}_zero"),
        types.InlineKeyboardButton("1–18 ×2",         callback_data=f"rul_{uid}_{bet}_low"),
        types.InlineKeyboardButton("19–36 ×2",        callback_data=f"rul_{uid}_{bet}_high"),
        types.InlineKeyboardButton("Чётное ×2",       callback_data=f"rul_{uid}_{bet}_even"),
        types.InlineKeyboardButton("Нечётное ×2",     callback_data=f"rul_{uid}_{bet}_odd"),
        types.InlineKeyboardButton("🎯 Число ×35",    callback_data=f"rul_{uid}_{bet}_num"),
    )
    bot.send_message(m.chat.id,
        f"<b>🎡 РУЛЕТКА</b>  |  Ставка: <b>{fmt(bet)} $</b>\n"
        "Выбери тип ставки:", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rul_"))
def cb_rul(c):
    parts  = c.data.split("_")
    uid    = int(parts[1]); bet = float(parts[2]); choice = parts[3]
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    if choice == "num":
        G[uid] = {"wait": "rul_num", "bet": bet, "cid": c.message.chat.id}
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "🔢 Введи число от 0 до 36:")
        return
    bot.answer_callback_query(c.id, "🎡 Крутим...")
    _rul_spin(c.message, uid, bet, choice, None)

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "rul_num")
def handle_rul_num(m):
    uid = m.from_user.id; s = G.pop(uid)
    try:
        num = int(m.text.strip())
        assert 0 <= num <= 36
    except:
        bot.reply_to(m, "❌ Введи число 0–36!"); return
    _rul_spin(m, uid, s["bet"], "num", num)

def _rul_spin(msg, uid, bet, choice, number):
    cid    = msg.chat.id
    result = random.randint(0, 36)
    col    = RCOL.get(result, "⚫")
    won    = False; mult = 0
    if choice == "red"   and col == "🔴": won, mult = True, 1.0
    elif choice == "black" and col == "⚫": won, mult = True, 1.0
    elif choice == "zero"  and result == 0: won, mult = True, 34.0
    elif choice == "low"   and 1 <= result <= 18: won, mult = True, 1.0
    elif choice == "high"  and 19 <= result <= 36: won, mult = True, 1.0
    elif choice == "even"  and result != 0 and result % 2 == 0: won, mult = True, 1.0
    elif choice == "odd"   and result % 2 == 1: won, mult = True, 1.0
    elif choice == "num"   and result == number: won, mult = True, 34.0
    mode = db.get_mode(uid)
    if won:
        profit = round(bet * mult, 2)
        db.record(uid, bet, True, profit)
        res = (f"<b>🎡 РУЛЕТКА</b>  {col} <b>{result}</b>\n\n"
               f"<b>✅ +{fmt(profit)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        res = (f"<b>🎡 РУЛЕТКА</b>  {col} <b>{result}</b>\n\n"
               f"<b>❌ −{fmt(bet)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>")
    bot.send_message(cid, res, reply_markup=kb_again("roulette", mode))

# ════════════════════════════════════════════
#  💣 МАЙНС
# ════════════════════════════════════════════
def _mines_start(m, uid, bet):
    k = types.InlineKeyboardMarkup(row_width=5)
    for n in [3, 5, 7, 10, 15, 20]:
        k.add(types.InlineKeyboardButton(
            f"💣 {n} мин", callback_data=f"mn_init_{uid}_{bet}_{n}"))
    bot.send_message(m.chat.id,
        f"<b>💣 МАЙНС</b>  |  Ставка: <b>{fmt(bet)} $</b>\n\n"
        "Выбери количество мин:\n"
        "<i>Больше мин → выше множитель</i>", reply_markup=k)

def _mn_mult(safe, mines):
    total = 25
    if safe == 0: return 1.0
    prob = 1.0
    for i in range(safe):
        prob *= (total - mines - i) / (total - i)
    return round(0.97 / prob, 3)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mn_init_"))
def cb_mn_init(c):
    _, _, uid_s, bet_s, m_s = c.data.split("_")
    uid = int(uid_s); bet = float(bet_s); mines = int(m_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    field = [False] * 25
    for p in random.sample(range(25), mines):
        field[p] = True
    MN[uid] = {"field": field, "rev": [False]*25,
                "bet": bet, "mines": mines, "safe": 0,
                "cid": c.message.chat.id, "active": True}
    bot.answer_callback_query(c.id)
    _mn_show(c.message.chat.id, uid, c.message.message_id)

def _mn_show(cid, uid, edit_mid=None):
    s = MN.get(uid)
    if not s: return
    mult = _mn_mult(s["safe"], s["mines"])
    pot  = round(s["bet"] * mult, 2)
    text = (
        f"<b>💣 МАЙНС</b>  |  Ставка: <b>{fmt(s['bet'])} $</b>\n"
        f"💣 Мин: <b>{s['mines']}</b>  |  ✅ Открыто: <b>{s['safe']}</b>\n"
        f"Множитель: <b>×{mult}</b>  |  Потенциал: <b>{fmt(pot)} $</b>"
    )
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
        k.add(types.InlineKeyboardButton(
            f"💸 Забрать {fmt(pot)} $", callback_data=f"mn_co_{uid}"))
    try:
        if edit_mid:
            bot.edit_message_text(text, cid, edit_mid, reply_markup=k)
            return
    except: pass
    bot.send_message(cid, text, reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mn_c_"))
def cb_mn_cell(c):
    _, _, uid_s, cell_s = c.data.split("_")
    uid = int(uid_s); cell = int(cell_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = MN.get(uid)
    if not s or not s["active"]:
        bot.answer_callback_query(c.id, "Игра завершена!"); return
    if s["rev"][cell]:
        bot.answer_callback_query(c.id, "Уже открыто!"); return
    s["rev"][cell] = True
    if s["field"][cell]:
        s["active"] = False
        db.record(uid, s["bet"], False)
        # Показываем все мины
        k = types.InlineKeyboardMarkup(row_width=5)
        btns = []
        for i in range(25):
            btns.append(types.InlineKeyboardButton(
                "💣" if s["field"][i] else ("✅" if s["rev"][i] else "⬜"),
                callback_data="noop"))
        k.add(*btns)
        mode = db.get_mode(uid)
        k.add(
            types.InlineKeyboardButton("🔄 Снова", callback_data="g_mines"),
            types.InlineKeyboardButton("🏠 Меню",  callback_data=f"back_{mode}"),
        )
        MN.pop(uid, None)
        try:
            bot.edit_message_text(
                f"<b>💣 ВЗРЫВ!</b>\n\n"
                f"Ты попал на мину! 💀\n"
                f"<b>❌ −{fmt(s['bet'])} $</b>\n"
                f"💰 <b>{fmt(db.bal(uid))} $</b>",
                c.message.chat.id, c.message.message_id, reply_markup=k)
        except: pass
    else:
        s["safe"] += 1
        _mn_show(c.message.chat.id, uid, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mn_co_"))
def cb_mn_cashout(c):
    uid = int(c.data.split("_")[2])
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = MN.pop(uid, None)
    if not s:
        bot.answer_callback_query(c.id, "Игра не найдена!"); return
    mult   = _mn_mult(s["safe"], s["mines"])
    profit = round(s["bet"] * mult - s["bet"], 2)
    db.record(uid, s["bet"], True, profit)
    mode = db.get_mode(uid)
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔄 Снова", callback_data="g_mines"),
        types.InlineKeyboardButton("🏠 Меню",  callback_data=f"back_{mode}"),
    )
    try:
        bot.edit_message_text(
            f"<b>💣 МАЙНС — КЭШАУТ</b>\n\n"
            f"✅ Открыто: <b>{s['safe']}</b>  |  ×{mult}\n"
            f"<b>✅ +{fmt(profit)} $</b>\n"
            f"💰 <b>{fmt(db.bal(uid))} $</b>",
            c.message.chat.id, c.message.message_id, reply_markup=k)
    except:
        bot.send_message(c.message.chat.id,
            f"✅ Кэшаут! +{fmt(profit)} $", reply_markup=k)
    bot.answer_callback_query(c.id, f"💸 +{fmt(profit)} $!")

# ════════════════════════════════════════════
#  🚀 КРАШ
# ════════════════════════════════════════════
def _crash_info(c):
    uid = c.from_user.id
    G[uid] = {"wait": "crash_bet", "cid": c.message.chat.id}
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id,
        f"<b>🚀 КРАШ</b>\n\n"
        "Ракета взлетает, множитель растёт.\n"
        "Нажми ВЫВЕСТИ до краша!\n\n"
        f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>\n"
        "Введи ставку:")

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "crash_bet")
def handle_crash_bet(m):
    uid = m.from_user.id; s = G.pop(uid)
    bet = parse_bet(m.text, uid)
    if not bet or bet < 10:
        bot.reply_to(m, "❌ Мин. 10 $!"); return
    if not enough(uid, bet):
        bot.reply_to(m, "❌ Недостаточно средств!"); return
    _crash_run(m, uid, bet)

def _crash_point():
    r = random.random()
    if r < 0.01: return 1.0
    return round(min(0.99 / (1 - r), 200.0), 2)

def _crash_run(m, uid, bet):
    cid   = m.chat.id
    crash = _crash_point()
    mult  = 1.00
    msg   = bot.send_message(cid,
        f"<b>🚀 КРАШ</b>  |  Ставка: <b>{fmt(bet)} $</b>\n\n"
        f"📈 ×{mult:.2f}\n\nНажми ВЫВЕСТИ!")
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton(
        "💸 ВЫВЕСТИ", callback_data=f"cr_out_{uid}_{msg.message_id}"))
    bot.edit_message_reply_markup(cid, msg.message_id, reply_markup=k)
    CR[uid] = {"active": True, "cashed": False, "mult": mult,
               "cid": cid, "mid": msg.message_id, "bet": bet, "crash": crash}

    def tick():
        nonlocal mult
        while True:
            time.sleep(0.7)
            if uid not in CR or not CR[uid]["active"]: return
            step = 0.08 if mult < 2 else (0.15 if mult < 5 else 0.30)
            mult = round(mult + step, 2)
            CR[uid]["mult"] = mult
            if mult >= crash:
                state = CR.pop(uid, None)
                if not state or state["cashed"]: return
                db.record(uid, bet, False)
                mode = db.get_mode(uid)
                kb2  = types.InlineKeyboardMarkup(row_width=2)
                kb2.add(
                    types.InlineKeyboardButton("🔄 Снова", callback_data="g_crash"),
                    types.InlineKeyboardButton("🏠 Меню",  callback_data=f"back_{mode}"),
                )
                try:
                    bot.edit_message_text(
                        f"<b>💥 КРАШ на ×{crash:.2f}!</b>\n\n"
                        f"<b>❌ −{fmt(bet)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>",
                        cid, msg.message_id, reply_markup=kb2)
                except: pass
                return
            try:
                bot.edit_message_text(
                    f"<b>🚀 КРАШ</b>  |  Ставка: <b>{fmt(bet)} $</b>\n\n"
                    f"📈 <b>×{mult:.2f}</b>\n\nНажми ВЫВЕСТИ!",
                    cid, msg.message_id, reply_markup=k)
            except: pass

    threading.Thread(target=tick, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("cr_out_"))
def cb_crash_out(c):
    parts = c.data.split("_")
    uid   = int(parts[2])
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = CR.pop(uid, None)
    if not s or not s["active"]:
        bot.answer_callback_query(c.id, "Игра уже завершена!"); return
    s["cashed"] = True; s["active"] = False
    mult   = s["mult"]; bet = s["bet"]
    profit = round(bet * mult - bet, 2)
    db.record(uid, bet, True, profit)
    mode = db.get_mode(uid)
    kb2  = types.InlineKeyboardMarkup(row_width=2)
    kb2.add(
        types.InlineKeyboardButton("🔄 Снова", callback_data="g_crash"),
        types.InlineKeyboardButton("🏠 Меню",  callback_data=f"back_{mode}"),
    )
    bot.answer_callback_query(c.id, f"💸 Вышел на ×{mult:.2f}!")
    try:
        bot.edit_message_text(
            f"<b>🚀 КРАШ — ВЫВОД</b>\n\n"
            f"Вышел на: <b>×{mult:.2f}</b>\n"
            f"<b>✅ +{fmt(profit)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>",
            s["cid"], s["mid"], reply_markup=kb2)
    except:
        bot.send_message(s["cid"],
            f"✅ Вывод ×{mult:.2f}! +{fmt(profit)} $", reply_markup=kb2)

# ════════════════════════════════════════════
#  🃏 ВИДЕО-ПОКЕР (Jacks or Better)
# ════════════════════════════════════════════
PRANKS = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']

def _full_deck():
    d = [(r,s) for s in ['♠','♥','♦','♣'] for r in PRANKS]
    random.shuffle(d); return d

def _ri(c): return PRANKS.index(c[0])

def _eval(hand):
    ranks  = sorted([_ri(c) for c in hand], reverse=True)
    suits  = [c[1] for c in hand]
    cnt    = {}
    for r in ranks: cnt[r] = cnt.get(r, 0) + 1
    flush  = len(set(suits)) == 1
    vals   = sorted(set(ranks))
    straight = (len(vals) == 5 and vals[-1] - vals[0] == 4)
    if not straight and set(ranks) == {12, 0, 1, 2, 3}: straight = True
    v = sorted(cnt.values(), reverse=True)
    if flush and straight and max(ranks) == 12: return "🏆 Роял-флэш",  800
    if flush and straight:                       return "👑 Стрит-флэш",  50
    if v[0] == 4:                                return "💎 Каре",        25
    if v[:2] == [3, 2]:                          return "🏠 Фулл-хаус",   9
    if flush:                                    return "🌸 Флэш",         6
    if straight:                                 return "📏 Стрит",        4
    if v[0] == 3:                                return "🎯 Тройка",       3
    if v[:2] == [2, 2]:                          return "✌️ Две пары",    2
    pairs = [r for r, c in cnt.items() if c == 2]
    if pairs and max(pairs) >= PRANKS.index('J'): return "✅ Пара J+",    1
    return "❌ Ничего",                                                     0

def _cd(c): return f"{c[0]}{c[1]}"

def _poker_start(m, uid, bet):
    deck = _full_deck()
    hand = [deck.pop() for _ in range(5)]
    G[uid] = {"game": "poker", "deck": deck, "hand": hand,
               "held": [False]*5, "bet": bet, "cid": m.chat.id}
    _poker_show(m.chat.id, uid)

def _poker_show(cid, uid, edit_mid=None):
    s    = G.get(uid)
    if not s: return
    hand = s["hand"]; held = s["held"]
    name, _ = _eval(hand)
    cards_line = "  ".join(
        f"[{_cd(c)}{'🔒' if held[i] else ''}]" for i, c in enumerate(hand))
    text = (
        f"<b>🃏 ВИДЕО-ПОКЕР</b>  |  Ставка: <b>{fmt(s['bet'])} $</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>{cards_line}</code>\n\n"
        f"Комбинация: <b>{name}</b>\n\n"
        "<i>Выбери карты для удержания, затем «Обменять»</i>"
    )
    k = types.InlineKeyboardMarkup(row_width=5)
    k.add(*[types.InlineKeyboardButton(
        f"{'🔒' if held[i] else '🃏'}", callback_data=f"pk_h_{uid}_{i}")
        for i in range(5)])
    k.add(types.InlineKeyboardButton("🔄 Обменять", callback_data=f"pk_d_{uid}"))
    if edit_mid:
        try:
            bot.edit_message_text(text, cid, edit_mid, reply_markup=k); return
        except: pass
    bot.send_message(cid, text, reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("pk_h_"))
def cb_pk_hold(c):
    _, _, uid_s, i_s = c.data.split("_")
    uid = int(uid_s); i = int(i_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = G.get(uid)
    if not s: bot.answer_callback_query(c.id); return
    s["held"][i] = not s["held"][i]
    _poker_show(c.message.chat.id, uid, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("pk_d_"))
def cb_pk_draw(c):
    uid = int(c.data.split("_")[2])
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = G.pop(uid, None)
    if not s: bot.answer_callback_query(c.id); return
    for i in range(5):
        if not s["held"][i]:
            s["hand"][i] = s["deck"].pop()
    name, mult = _eval(s["hand"])
    bet  = s["bet"]
    mode = db.get_mode(uid)
    cards_line = "  ".join(_cd(c2) for c2 in s["hand"])
    if mult > 0:
        profit = round(bet * mult, 2)
        db.record(uid, bet, True, profit)
        res = (f"<b>🃏 ПОКЕР — РЕЗУЛЬТАТ</b>\n\n"
               f"<code>{cards_line}</code>\n\n"
               f"<b>{name}</b>  ×{mult}\n"
               f"<b>✅ +{fmt(profit)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        res = (f"<b>🃏 ПОКЕР — РЕЗУЛЬТАТ</b>\n\n"
               f"<code>{cards_line}</code>\n\n"
               f"<b>{name}</b>\n"
               f"<b>❌ −{fmt(bet)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>")
    try:
        bot.edit_message_text(res, c.message.chat.id, c.message.message_id,
                              reply_markup=kb_again("poker", mode))
    except:
        bot.send_message(c.message.chat.id, res, reply_markup=kb_again("poker", mode))
    bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  📈 ТРЕЙДЕР
# ════════════════════════════════════════════
COINS = ["BTC","ETH","SOL","DOGE","PEPE","BNB","XRP","TON"]

def _trader(m, uid, bet):
    coin  = random.choice(COINS)
    price = round(random.uniform(0.01, 60000), 2)
    G[uid] = {"game": "trader", "coin": coin, "price": price, "bet": bet}
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("📈 LONG",  callback_data=f"tr_{uid}_up"),
        types.InlineKeyboardButton("📉 SHORT", callback_data=f"tr_{uid}_down"),
    )
    bot.send_message(m.chat.id,
        f"<b>📈 ТРЕЙДЕР</b>  |  Ставка: <b>{fmt(bet)} $</b>\n\n"
        f"🪙 <b>{coin}</b>  =  <b>${fmt(price)}</b>\n\n"
        "Куда пойдёт цена?\n<i>Угадай → ×1.9</i>", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("tr_"))
def cb_trader(c):
    _, uid_s, dir_ = c.data.split("_")
    uid = int(uid_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    s = G.pop(uid, None)
    if not s: bot.answer_callback_query(c.id); return
    bet = s["bet"]; coin = s["coin"]; old = s["price"]
    bot.answer_callback_query(c.id, "⏳ Ждём...")
    try:
        bot.edit_message_text(
            f"<b>📈 ТРЕЙДЕР</b>  {coin}\n\n⏳ Считаем изменение цены...",
            c.message.chat.id, c.message.message_id)
    except: pass
    time.sleep(3)
    change   = random.uniform(-0.12, 0.12)
    new_p    = round(old * (1 + change), 2)
    went_up  = new_p > old
    correct  = (dir_ == "up" and went_up) or (dir_ == "down" and not went_up)
    arrow    = "📈" if went_up else "📉"
    pct      = round(abs(change) * 100, 1)
    mode     = db.get_mode(uid)
    if correct:
        profit = round(bet * 0.9, 2)
        db.record(uid, bet, True, profit)
        res = (f"<b>📈 ТРЕЙДЕР</b>  {coin}\n\n"
               f"{arrow} ${fmt(old)} → ${fmt(new_p)}  ({'+' if went_up else '-'}{pct}%)\n\n"
               f"<b>✅ Угадал!  +{fmt(profit)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>")
    else:
        db.record(uid, bet, False)
        res = (f"<b>📈 ТРЕЙДЕР</b>  {coin}\n\n"
               f"{arrow} ${fmt(old)} → ${fmt(new_p)}  ({'+' if went_up else '-'}{pct}%)\n\n"
               f"<b>❌ Не угадал.  −{fmt(bet)} $</b>\n💰 <b>{fmt(db.bal(uid))} $</b>")
    try:
        bot.edit_message_text(res, c.message.chat.id, c.message.message_id,
                              reply_markup=kb_again("trader", mode))
    except:
        bot.send_message(c.message.chat.id, res, reply_markup=kb_again("trader", mode))

# ════════════════════════════════════════════
#  🔢 УГАДАЙ ЧИСЛО
# ════════════════════════════════════════════
def _guess_start(m, uid, bet):
    k = types.InlineKeyboardMarkup(row_width=2)
    opts = [("1–10  ×8",   10), ("1–25  ×20",  25),
            ("1–50  ×44",  50), ("1–100 ×88", 100)]
    for label, rng in opts:
        k.add(types.InlineKeyboardButton(
            label, callback_data=f"gs_{uid}_{bet}_{rng}"))
    bot.send_message(m.chat.id,
        f"<b>🔢 УГАДАЙ ЧИСЛО</b>  |  Ставка: <b>{fmt(bet)} $</b>\n\n"
        "Выбери диапазон:", reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("gs_"))
def cb_gs_range(c):
    _, uid_s, bet_s, rng_s = c.data.split("_")
    uid = int(uid_s); bet = float(bet_s); rng = int(rng_s)
    if c.from_user.id != uid:
        bot.answer_callback_query(c.id, "Не твоя игра!"); return
    target = random.randint(1, rng)
    G[uid]  = {"wait": "guess", "target": target, "bet": bet, "rng": rng, "cid": c.message.chat.id}
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id,
        f"<b>🔢 УГАДАЙ ЧИСЛО</b>  |  1–{rng}\n"
        "Введи своё число:")

@bot.message_handler(func=lambda m: m.from_user.id in G and G[m.from_user.id].get("wait") == "guess")
def handle_guess(m):
    uid = m.from_user.id; s = G.pop(uid)
    try: guess = int(m.text.strip())
    except:
        bot.reply_to(m, "❌ Введи корректное число!"); return
    bet  = s["bet"]; target = s["target"]; rng = s["rng"]
    mode = db.get_mode(uid)
    mult_map = {10: 7, 25: 19, 50: 43, 100: 87}
    mult = mult_map.get(rng, 7)
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(
        types.InlineKeyboardButton("🔄 Снова", callback_data="g_guess"),
        types.InlineKeyboardButton("🏠 Меню",  callback_data=f"back_{mode}"),
    )
    if guess == target:
        profit = round(bet * mult, 2)
        db.record(uid, bet, True, profit)
        bot.reply_to(m,
            f"<b>🔢 УГАДАЛ!</b>  Число: <b>{target}</b>\n"
            f"×{mult+1}  →  <b>✅ +{fmt(profit)} $</b>\n"
            f"💰 <b>{fmt(db.bal(uid))} $</b>", reply_markup=k)
    else:
        hint = "выше" if target > guess else "ниже"
        db.record(uid, bet, False)
        bot.reply_to(m,
            f"<b>🔢 НЕ УГАДАЛ!</b>  Было <b>{target}</b>  (нужно было {hint})\n"
            f"<b>❌ −{fmt(bet)} $</b>\n"
            f"💰 <b>{fmt(db.bal(uid))} $</b>", reply_markup=k)

# ════════════════════════════════════════════
#  💼 ПРОФИЛЬ — с картинкой
# ════════════════════════════════════════════
@bot.message_handler(commands=['profile'])
@bot.message_handler(func=lambda m: m.text == "💼 Профиль")
def cmd_profile(m):
    uid  = m.from_user.id
    db.ensure(uid, uname(m))
    user = db.get(uid)
    if not user:
        bot.send_message(m.chat.id, "Профиль не найден."); return

    buf     = make_profile_card(user)
    wr      = round(user['wins'] / user['games'] * 100, 1) if user['games'] else 0
    profit  = user['total_won'] - user['total_bet']
    sign    = "+" if profit >= 0 else ""
    caption = (
        f"<b>💼 ПРОФИЛЬ</b>  {user['username']}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс:  <b>{fmt(user['balance'])} $</b>\n\n"
        f"🎮 Игры:    <b>{user['games']}</b>\n"
        f"✅ Победы:  <b>{user['wins']}</b>\n"
        f"❌ Пораж.:  <b>{user['losses']}</b>\n"
        f"📊 Винрейт: <b>{wr}%</b>\n\n"
        f"💸 Оборот:  <b>{fmt(user['total_bet'])} $</b>\n"
        f"📈 Прибыль: <b>{sign}{fmt(profit)} $</b>\n\n"
        f"🔥 Серия:   <b>{user['streak']} д.</b>"
    )
    k = types.InlineKeyboardMarkup()
    k.add(types.InlineKeyboardButton("🎮 Играть", callback_data="open_play"))
    bot.send_photo(m.chat.id, buf, caption=caption, reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data == "open_play")
def cb_open_play(c):
    bot.answer_callback_query(c.id)
    cmd_play(c.message)

# ════════════════════════════════════════════
#  🎁 БОНУС
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🎁 Бонус")
def cmd_daily(m):
    uid = m.from_user.id
    db.ensure(uid, uname(m))
    ok, val = db.daily(uid)
    if ok:
        u = db.get(uid)
        bot.send_message(m.chat.id,
            f"<b>🎁 ЕЖЕДНЕВНЫЙ БОНУС</b>\n\n"
            f"<b>+{val} $</b> получено!\n"
            f"🔥 Серия: <b>{u['streak']} дней</b>\n"
            f"💰 Баланс: <b>{fmt(db.bal(uid))} $</b>\n\n"
            f"<i>Следующий через 24 ч.</i>")
    else:
        h = val // 3600; mn = (val % 3600) // 60
        bot.send_message(m.chat.id,
            f"<b>⏰ Бонус уже получен!</b>\n\n"
            f"Следующий через: <b>{h}ч {mn}мин</b>")

# ════════════════════════════════════════════
#  🏆 ТОП
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🏆 Топ")
def cmd_top(m):
    rows = db.top(10)
    if not rows:
        bot.send_message(m.chat.id, "Таблица пуста."); return
    medals = ["🥇","🥈","🥉"] + ["🔹"]*7
    text   = "<b>🏆 ТОП-10 ИГРОКОВ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, r in enumerate(rows):
        wr = round(r[2] / r[3] * 100, 1) if r[3] else 0
        text += (f"{medals[i]} <b>{i+1}. {r[0]}</b>\n"
                 f"   💰 {fmt(r[1])} $  |  ✅ {r[2]} побед  |  {wr}% WR\n\n")
    bot.send_message(m.chat.id, text)

# ════════════════════════════════════════════
#  📊 СТАТИСТИКА
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def cmd_stats(m):
    uid  = m.from_user.id
    db.ensure(uid, uname(m))
    user = db.get(uid)
    profit = user['total_won'] - user['total_bet']
    sign   = "+" if profit >= 0 else ""
    wr     = round(user['wins'] / user['games'] * 100, 1) if user['games'] else 0
    bot.send_message(m.chat.id,
        f"<b>📊 СТАТИСТИКА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎮 Игр:       <b>{user['games']}</b>\n"
        f"✅ Побед:     <b>{user['wins']}</b>\n"
        f"❌ Поражений: <b>{user['losses']}</b>\n"
        f"📊 Винрейт:   <b>{wr}%</b>\n\n"
        f"💸 Поставлено: <b>{fmt(user['total_bet'])} $</b>\n"
        f"💰 Выиграно:   <b>{fmt(user['total_won'])} $</b>\n"
        f"📈 Прибыль:    <b>{sign}{fmt(profit)} $</b>")

# ════════════════════════════════════════════
#  ℹ️ ПОМОЩЬ
# ════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def cmd_help(m):
    bot.send_message(m.chat.id,
        "<b>ℹ️ ПОМОЩЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Команды:</b>\n"
        "/start   — главное меню\n"
        "/play    — выбор игры\n"
        "/profile — профиль\n\n"
        "<b>🐸 BrainRot:</b>\n"
        "🎲 Кости · 🪙 Монетка · ⚽⚽🏀 Спорт\n"
        "🎯 Дартс · 🎳 Боулинг · 🐍 1/5\n"
        "⚔️ PvP Дуэль (только в группах)\n\n"
        "<b>💎 Crypto:</b>\n"
        "🃏 Блэкджек · 🎰 Слоты · 🎡 Рулетка\n"
        "💣 Майнс · 🚀 Краш · 🃏 Покер\n"
        "📈 Трейдер · 🔢 Угадай число\n\n"
        "<b>💡 Советы:</b>\n"
        "• Бонус каждые 24 ч\n"
        "• Майнс — кэшаут вовремя!\n"
        "• PvP работает в группах")

# ════════════════════════════════════════════
#  👑 ADMIN
# ════════════════════════════════════════════
@bot.message_handler(commands=['givebal'])
def admin_give(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        _, uid, amt = m.text.split()
        db.ensure(int(uid))
        db.add(int(uid), float(amt))
        bot.reply_to(m, f"✅ Выдано <b>{fmt(float(amt))} $</b> → {uid}")
    except:
        bot.reply_to(m, "Формат: /givebal ID СУММА")

@bot.message_handler(commands=['setbal'])
def admin_set(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        _, uid, amt = m.text.split()
        db.ensure(int(uid))
        db.set_bal(int(uid), float(amt))
        bot.reply_to(m, f"✅ Баланс {uid} = <b>{fmt(float(amt))} $</b>")
    except:
        bot.reply_to(m, "Формат: /setbal ID СУММА")

@bot.message_handler(commands=['adminstats'])
def admin_stats(m):
    if m.from_user.id not in ADMIN_IDS: return
    db.cur.execute("SELECT COUNT(*), SUM(balance), SUM(games), SUM(total_bet) FROM users")
    r = db.cur.fetchone()
    bot.reply_to(m,
        f"<b>📊 КАЗИНО СТАТИСТИКА</b>\n\n"
        f"👥 Игроков:  <b>{r[0]}</b>\n"
        f"💰 Балансы:  <b>{fmt(r[1] or 0)} $</b>\n"
        f"🎮 Игр:      <b>{r[2]}</b>\n"
        f"💸 Оборот:   <b>{fmt(r[3] or 0)} $</b>")

@bot.message_handler(commands=['broadcast'])
def admin_bc(m):
    if m.from_user.id not in ADMIN_IDS: return
    txt = m.text.replace("/broadcast", "", 1).strip()
    if not txt:
        bot.reply_to(m, "Укажи текст!"); return
    db.cur.execute("SELECT id FROM users")
    users = db.cur.fetchall()
    ok = fail = 0
    for (uid,) in users:
        try:
            bot.send_message(uid, f"📢 <b>Объявление</b>\n\n{txt}")
            ok += 1; time.sleep(0.05)
        except: fail += 1
    bot.reply_to(m, f"✅ Отправлено: {ok}  |  ❌ Ошибок: {fail}")

# ════════════════════════════════════════════
#  NOOP
# ════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "noop")
def cb_noop(c): bot.answer_callback_query(c.id)

# ════════════════════════════════════════════
#  FLASK (Render keep-alive)
# ════════════════════════════════════════════
def run_flask():
    app = Flask(__name__)

    @app.route('/')
    def index(): return "<h2>🎰 Casino Bot — Online</h2>"

    @app.route('/health')
    def health(): return {"status": "ok"}

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ════════════════════════════════════════════
#  ЗАПУСК
# ════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("🎰 MEGA CASINO — старт")
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
            logger.error(f"Ошибок polling: {e}")
            time.sleep(10)
