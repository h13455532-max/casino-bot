import telebot
import random
from telebot import types

TOKEN = "8496621429:AAEzr2R8qbgWW12Ng8K5aHmAyhOnL9HWqTM"
bot = telebot.TeleBot(TOKEN)

# Список ID админов
ADMIN_IDS = [8357023784, 8539734813]

# Хранилище игр: {chat_id: {данные}}
games = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🎰 **NEZZZ x KLITOK CASINO** 🎰\n\nИспользуйте /play для начала.")

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
    if chat_id not in games:
        return

    state = games[chat_id]
    user_id = message.from_user.id

    # 1. КОМАНДА ЗАПУСКА АДМИНОМ (вне очереди проверок)
    if message.text == "/starthisplay":
        if user_id in ADMIN_IDS:
            if not message.reply_to_message:
                bot.reply_to(message, "❌ Ответьте этой командой на сообщение с матчем!")
                return
            
            # Логика запуска игры
            if state["game"] == "🎲 Кубики":
                n1, n2 = random.randint(1, 10), random.randint(1, 10)
                res = f"🎲 **РЕЗУЛЬТАТЫ КУБИКОВ**\n\n{state['challenger']}: `{n1}`\n{state['target']}: `{n2}`\n\n"
                if n1 > n2: res += f"🏆 Победил {state['challenger']}!"
                elif n2 > n1: res += f"🏆 Победил {state['target']}!"
                else: res += "🤝 Ничья!"
                bot.send_message(chat_id, res + "\n\nОжидайте выдачи от гаранта.")
            
            elif state["game"] == "🪙 Орёл и Решка":
                win_side = random.choice(["Орёл", "Решка"])
                winner = state["challenger"] if state["challenger_side"] == win_side else state["target"]
                bot.send_message(chat_id, f"🪙 **ВЫПАЛО: {win_side}**\n\n🏆 Победитель: {winner}\n\nОжидайте выдачи от гаранта.")
            
            elif state["game"] == "🎰 Слот-Машина":
                msg1 = bot.send_dice(chat_id, emoji='🎰')
                bot.send_message(chat_id, f"⬆️ Крутит {state['challenger']}")
                msg2 = bot.send_dice(chat_id, emoji='🎰')
                bot.send_message(chat_id, f"⬆️ Крутит {state['target']}")
                winner = state["challenger"] if msg1.dice.value > msg2.dice.value else (state['target'] if msg2.dice.value > msg1.dice.value else "Ничья")
                bot.send_message(chat_id, f"🏆 Итог слотов: **{winner}**\n\nОжидайте выдачи от гаранта.")
            
            del games[chat_id]
        else:
            bot.reply_to(message, "⛔ Только админы могут запускать игру.")
        return

    # 2. ПРОВЕРКА: Только владелец игры может отвечать
    if user_id != state["owner_id"] or not message.reply_to_message:
        return

    # 3. Логика шагов
    if state["step"] == "choose_game":
        if message.text in ["🎲 Кубики", "🪙 Орёл и Решка", "🎰 Слот-Машина"]:
            state["game"] = message.text
            state["step"] = "wait_username"
            bot.send_message(chat_id, "✅ Выбрано. Теперь введите @юзернейм оппонента (ответом):", reply_markup=types.ReplyKeyboardRemove())

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
                bot.send_message(chat_id, f"⚔️ **МАТЧ ГОТОВ**\n{state['challenger']} vs {state['target']}\n📢 Админ, введите /starthisplay")
        else:
            bot.reply_to(message, "❌ Юзернейм должен начинаться с @")

    elif state["step"] == "wait_side_choice":
        if message.text in ["Орёл", "Решка"]:
            state["challenger_side"] = message.text
            state["target_side"] = "Решка" if message.text == "Орёл" else "Орёл"
            state["step"] = "wait_admin"
            bot.send_message(chat_id, f"⚔️ **МАТЧ ГОТОВ**\n{state['challenger']} ({state['challenger_side']}) vs {state['target']} ({state['target_side']})\n📢 Админ, введите /starthisplay", reply_markup=types.ReplyKeyboardRemove())

print("Бот nezzz x klitok casino запущен!")
bot.polling(none_stop=True)