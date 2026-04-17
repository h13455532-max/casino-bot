import os

# Основные токены и ID
TOKEN = os.environ.get("TOKEN")
ADMIN_IDS = [8357023784, 8539734813] # Твои ID
LOG_CHANNEL_ID = -1003951162583      # Канал для логов

# Ссылки и кастомизация
CRYPTO_LINK = "http://t.me/send?start=IVpZKHj5lZFO"
CASINO_NAME = "NEZZX x KLITOK CASINO"
WIN_IMAGE = "win.png"

# Настройки игр (Математика казино)
DICE_COEFF = 1.8
SLOTS_JACKPOT_COEFF = 10.0
COIN_COEFF = 1.9
MIN_BET = 0.1
MIN_WITHDRAW = 5.0

# Тексты справки
RULES_TEXT = (
    "📜 **ПРАВИЛА КАЗИНО**\n\n"
    "1. Играя у нас, вы подтверждаете свое согласие с риском.\n"
    "2. Мультиаккаунты запрещены (бан без возврата).\n"
    "3. Пополнение происходит через администратора или CryptoBot.\n"
    "4. Вывод средств занимает от 5 минут до 24 часов."
)