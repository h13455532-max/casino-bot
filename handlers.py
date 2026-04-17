import telebot
import random
import time
import os
from telebot import types
from config import ADMIN_IDS, LOG_CHANNEL_ID, CRYPTO_LINK, CASINO_NAME, WIN_IMAGE
from db_manager import DB

db = DB()

# --- КЛАВИАТУРЫ ---
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎲 ИГРАТЬ", "💰 ПРОФИЛЬ")
    markup.add("💎 ПОПОЛНИТЬ", "💸 ВЫВОД")
    markup.add("🎁 ПРОМОКОД", "📊 ТОП")
    if user_id in ADMIN_IDS:
        markup.add("🛠 АДМИНКА")
    return markup

def games_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎲 Кубики (x1.8)", callback_data="g_dice"),
        types.InlineKeyboardButton("🎰 Слоты (x2-x10)", callback_data="g_slots"),
        types.InlineKeyboardButton("🪙 Монетка (x1.9)", callback_data="g_coin"),
        types.InlineKeyboardButton("🎯 Рулетка (x3)", callback_data="g_roulette")
    )
    return markup

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def send_log(bot, text):
    try:
        bot.send_message(LOG_CHANNEL_ID, f"📑 **LOG:**\n{text}", parse_mode='Markdown')
    except: pass

def check_win_photo(bot, chat_id, text):
    if os.path.exists(WIN_IMAGE):
        with open(WIN_IMAGE, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=f"🎰 **{CASINO_NAME}**\n\n{text}", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, f"🏆 **ПОБЕДА!**\n\n{text}", parse_mode='Markdown')

# --- ГЛАВНАЯ ЛОГИКА ---
def register_handlers(bot):
    
    @bot.message_handler(func=lambda m: m.text == "💰 ПРОФИЛЬ")
    def profile(m):
        bal = db.get_balance(m.from_user.id)
        text = (f"👤 **ВАШ ПРОФИЛЬ**\n\n"
                f"🆔 ID: `{m.from_user.id}`\n"
                f"💰 Баланс: `{bal:.2f}` USD\n"
                f"🔗 Реф. ссылка: `t.me/{(bot.get_me().username)}?start={m.from_user.id}`")
        bot.reply_to(m, text, parse_mode='Markdown', reply_markup=main_menu(m.from_user.id))

    @bot.message_handler(func=lambda m: m.text == "🎲 ИГРАТЬ")
    def play_select(m):
        bot.send_message(m.chat.id, "🎯 **Выберите режим игры:**", reply_markup=games_menu(), parse_mode='Markdown')

    @bot.message_handler(func=lambda m: m.text == "💎 ПОПОЛНИТЬ")
    def deposit(m):
        text = (f"💎 **ПОПОЛНЕНИЕ**\n\n"
                f"Минимальная сумма: 1 USD\n"
                f"Курс: 1 USD = 1 монета\n\n"
                f"🔗 [ОПЛАТИТЬ ЧЕРЕЗ CRYPTO]({CRYPTO_LINK})")
        bot.send_message(m.chat.id, text, parse_mode='Markdown', disable_web_page_preview=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("g_"))
    def start_game(call):
        game_type = call.data.split("_")[1]
        msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму ставки:**")
        bot.register_next_step_handler(msg, lambda m: process_bet(m, bot, game_type))

    # --- МАТЕМАТИКА ИГР ---
    def process_bet(message, bot, game_type):
        try:
            bet = float(message.text.replace(',', '.'))
            user_id = message.from_user.id
            balance = db.get_balance(user_id)

            if bet < 0.1: return bot.reply_to(message, "❌ Минимум 0.1")
            if bet > balance: return bot.reply_to(message, "❌ Недостаточно средств!")

            db.update_balance(user_id, -bet) # Списание
            
            if game_type == "dice":
                dice = bot.send_dice(message.chat.id, emoji='🎲')
                time.sleep(3)
                if dice.dice.value >= 4:
                    win = bet * 1.8
                    db.update_balance(user_id, win)
                    check_win_photo(bot, message.chat.id, f"Выпало {dice.dice.value}! Выигрыш: `{win:.2f}`")
                else:
                    bot.send_message(message.chat.id, f"💀 Проигрыш! Выпало {dice.dice.value}")

            elif game_type == "slots":
                slot = bot.send_dice(message.chat.id, emoji='🎰')
                time.sleep(4)
                # Логика Telegram Slots: 1, 22, 43, 64 - джекпоты
                if slot.dice.value in [1, 22, 43, 64]:
                    win = bet * 10
                    db.update_balance(user_id, win)
                    check_win_photo(bot, message.chat.id, f"🔥 ДЖЕКПОТ! Выигрыш: `{win:.2f}`")
                else:
                    bot.send_message(message.chat.id, "❌ Не повезло!")

            elif game_type == "coin":
                res = random.choice(["Орел", "Решка"])
                bot.send_message(message.chat.id, f"🪙 Выпало: **{res}**")
                if random.random() > 0.55: # 45% на победу
                    win = bet * 1.9
                    db.update_balance(user_id, win)
                    bot.send_message(message.chat.id, f"🏆 Победа! +`{win:.2f}`")
                else:
                    bot.send_message(message.chat.id, "💀 Проигрыш")

            send_log(bot, f"Игрок `{user_id}` поставил `{bet}` в `{game_type}`")

        except: bot.reply_to(message, "⚠️ Введите число!")

    # --- АДМИН-ПАНЕЛЬ ---
    @bot.message_handler(func=lambda m: m.text == "🛠 АДМИНКА")
    def admin_p(m):
        if m.from_user.id not in ADMIN_IDS: return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💰 Выдать баланс", callback_data="adm_give"))
        markup.add(types.InlineKeyboardButton("📢 Рассылка", callback_data="adm_mail"))
        bot.send_message(m.chat.id, "👨‍💻 Меню разработчика:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "adm_give")
    def adm_give(call):
        msg = bot.send_message(call.message.chat.id, "Введите: `ID СУММА` (через пробел)")
        bot.register_next_step_handler(msg, lambda m: process_adm_give(m, bot))

    def process_adm_give(m, bot):
        try:
            uid, amt = int(m.text.split()[0]), float(m.text.split()[1])
            db.update_balance(uid, amt)
            bot.reply_to(m, f"✅ Баланс {uid} изменен на {amt}")
            bot.send_message(uid, f"💰 Ваш баланс пополнен на `{amt}` USD администратором!")
        except: bot.reply_to(m, "Ошибка формата.")