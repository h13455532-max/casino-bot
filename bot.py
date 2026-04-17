import telebot
import random
import os
import time  # Важно для задержки в слотах
from telebot import types
from flask import Flask
from threading import Thread

# Настройки
TOKEN = os.environ.get("TOKEN")
bot = telebot.TeleBot(TOKEN)
ADMIN_IDS = [8357023784, 8539734813]
LOG_CHANNEL_ID = -1003951162583  # Твой ID канала вывода

# Путь к картинке выигрыша (файл 'win.png' должен лежать на GitHub рядом с bot.py)
WIN_IMAGE_PATH = "win.png" 

# Название казино
CASINO_NAME = "NEZZX x KLITOK CASINO"

# База данных (в оперативной памяти - при перезагрузке сбросится)
user_balances = {} 
games = {}

app = Flask(__name__)

@app.route('/')
def home():
    return f"{CASINO_NAME} is Online!"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# Проверка и создание баланса
def get_balance(user_id):
    if user_id not in user_balances:
        user_balances[user_id] = 0.0
    return user_balances[user_id]

# Функция отправки картинки выигрыша
def send_win_image(chat_id, text):
    try:
        if os.path.exists(WIN_IMAGE_PATH):
            with open(WIN_IMAGE_PATH, 'rb') as photo:
                # Добавляем название казино в подпись
                full_text = f"🎰 **{CASINO_NAME}**\n\n{text}"
                bot.send_photo(chat_id, photo, caption=full_text, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, text, parse_mode='Markdown') # Если файла нет, просто текст
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")
        bot.send_message(chat_id, text, parse_mode='Markdown')

# --- КОМАНДЫ АДМИНА ---

@bot.message_handler(commands=['givebal'])
def give_balance(message):
    if message.from_user.id in ADMIN_IDS:
        try:
            parts = message.text.split()
            target_user_id = int(parts[1])
            amount = float(parts[2])
            user_balances[target_user_id] = get_balance(target_user_id) + amount
            bot.reply_to(message, f"✅ Баланс пользователя `{target_user_id}` пополнен на {amount:.2f} монет.")
        except:
            bot.reply_to(message, "⚠️ Формат: `/givebal ID_ПОЛЬЗОВАТЕЛЯ СУММА` (через точку)")

# --- КОМАНДЫ ИГРОКА ---

@bot.message_handler(commands=['balance'])
def check_balance(message):
    bal = get_balance(message.from_user.id)
    bot.reply_to(message, f"💰 **Твой кошелек**\n\nБаланс: `{bal:.2f}` монет.\n💵 Курс: 1 монета = 1 USD")

@bot.message_handler(commands=['payback'])
def request_withdraw(message):
    try:
        parts = message.text.split()
        amount = float(parts[1])
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

        if amount < 3:
            bot.reply_to(message, "❌ Минимальный вывод — 3 монеты.")
            return
        
        if get_balance(user_id) < amount:
            bot.reply_to(message, "❌ Недостаточно монет на балансе.")
            return

        # Снимаем баланс
        user_balances[user_id] -= amount
        
        # Отправка лога в канал
        log_text = (f"🚀 **ЗАЯВКА НА ВЫВОД**\n\n"
                    f"🏢 Казино: {CASINO_NAME}\n"
                    f"👤 Игрок: {username} (ID: `{user_id}`)\n"
                    f"💳 Сумма: `{amount:.2f}` монет\n"
                    f"💰 Остаток: `{user_balances[user_id]:.2f}`\n\n"
                    f"Свяжитесь для выплаты криптой.")
        
        bot.send_message(LOG_CHANNEL_ID, log_text)
        bot.reply_to(message, "✅ Заявка на вывод отправлена админам! Ожидайте выплаты.")
    except:
        bot.reply_to(message, "⚠️ Используйте: `/payback СУММА` (например: `/payback 5.5`) ")

@bot.message_handler(commands=['crypto'])
def crypto_info(message):
    bot.reply_to(message, f"💎 **ОПЛАТА КРИПТОЙ в {CASINO_NAME}**\n\nДля пополнения баланса напишите админу. \nКурс: $0.01 = 0.01 монета.\nПринимаем USDT (TRC20), BTC, TON.")

# --- ОСТАЛЬНАЯ ЛОГИКА (START / PLAY) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, f"🎰 **{CASINO_NAME}**\n\nДобро пожаловать!\n/balance - Мой кошелек\n/play - Играть\n/crypto - Пополнение\n/payback - Вывод")

@bot.message_handler(commands=['play'])
def cmd_play(message):
    chat_id = message.chat.id
    games[chat_id] = {
        "step": "choose_game", 
        "owner_id": message.from_user.id,
        "challenger": f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    }
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("🎲 Кубики", "🪙 Орёл и Решка", "🎰 Слот-Машина")
    bot.send_message(chat_id, "✨ **ВЫБЕРИТЕ ИГРУ:**", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    chat_id = message.chat.id
    if chat_id not in games: return

    state = games[chat_id]
    user_id = message.from_user.id

    # 1. Запуск админом
    if message.text == "/starthisplay":
        if user_id in ADMIN_IDS:
            if not message.reply_to_message:
                bot.reply_to(message, "❌ Ответьте на сообщение с данными матча!")
                return
            
            if state["game"] == "🎲 Кубики":
                n1, n2 = random.randint(1, 10), random.randint(1, 10)
                res = f"🎲 **РЕЗУЛЬТАТЫ**\n\n{state['challenger']}: `{n1}`\n{state['target']}: `{n2}`\n\n"
                if n1 > n2: res += f"🏆 Победил {state['challenger']}!"
                elif n2 > n1: res += f"🏆 Победил {state['target']}!"
                else: res += "🤝 Ничья!"
                
                # Отправляем картинку выигрыша
                if n1 != n2:
                    send_win_image(chat_id, res + "\n\nОжидайте выдачи от гаранта.")
                else:
                    bot.send_message(chat_id, res + "\n\nОжидайте выдачи от гаранта.")
            
            elif state["game"] == "🪙 Орёл и Решка":
                win_side = random.choice(["Орёл", "Решка"])
                winner = state["challenger"] if state["challenger_side"] == win_side else state["target"]
                text = f"🪙 **ВЫПАЛО: {win_side}**\n\n🏆 Победитель: {winner}\n\nОжидайте выдачи от гаранта."
                send_win_image(chat_id, text)
            
            elif state["game"] == "🎰 Слот-Машина":
                msg1 = bot.send_dice(chat_id, emoji='🎰')
                msg2 = bot.send_dice(chat_id, emoji='🎰')
                
                # Задержка 4 секунды, чтобы анимация прокрутки успела пройти
                bot.send_message(chat_id, "🎰 *Крутим слоты...*", parse_mode='Markdown')
                time.sleep(4) 
                
                if msg1.dice.value > msg2.dice.value:
                    winner = state["challenger"]
                elif msg2.dice.value > msg1.dice.value:
                    winner = state["target"]
                else:
                    winner = "Ничья"
                
                text = f"🏆 Итог слотов: **{winner}**\n\nОжидайте выдачи от гаранта."
                if winner != "Ничья":
                    send_win_image(chat_id, text)
                else:
                    bot.send_message(chat_id, text)
            
            del games[chat_id]
        return

    # 2. Логика инициатора
    if user_id != state["owner_id"] or not message.reply_to_message:
        return

    if state["step"] == "choose_game":
        if message.text in ["🎲 Кубики", "🪙 Орёл и Решка", "🎰 Слот-Машина"]:
            state["game"] = message.text
            state["step"] = "wait_username"
            bot.send_message(chat_id, "✅ Выбрано. Введите @юзернейм оппонента (ответом):", reply_markup=types.ReplyKeyboardRemove())

    elif state["step"] == "wait_username":
        if message.text.startswith("@"):
            state["target"] = message.text
            if state["game"] == "🪙 Орёл и Решка":
                state["step"] = "wait_side_choice"
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.add("Орёл", "Решка")
                bot.send_message(chat_id, "🪙 Выберите сторону:", reply_markup=markup)
            else:
                state["step"] = "wait_admin"
                bot.send_message(chat_id, f"⚔️ **МАТЧ ГОТОВ**\n{state['challenger']} vs {state['target']}\n📢 Админ: /starthisplay")
        else:
            bot.reply_to(message, "❌ Юзернейм с @")

    elif state["step"] == "wait_side_choice":
        if message.text in ["Орёл", "Решка"]:
            state["challenger_side"] = message.text
            state["target_side"] = "Решка" if message.text == "Орёл" else "Орёл"
            state["step"] = "wait_admin"
            bot.send_message(chat_id, f"⚔️ **МАТЧ ГОТОВ**\n{state['challenger']} ({state['challenger_side']}) vs {state['target']} ({state['target_side']})\n📢 Админ: /starthisplay", reply_markup=types.ReplyKeyboardRemove())

if __name__ == "__main__":
    t = Thread(target=run_server)
    t.daemon = True
    t.start()
    print(f"{CASINO_NAME} запускается...")
    bot.infinity_polling()
