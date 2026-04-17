import sqlite3
import datetime
import logging

class DB:
    def __init__(self, db_path="casino_pro.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Пользователи
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                referrals INTEGER DEFAULT 0,
                total_wager REAL DEFAULT 0.0,
                reg_date TEXT
            )
        """)
        # Промокоды
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promo (
                code TEXT PRIMARY KEY,
                amount REAL,
                uses INTEGER
            )
        """)
        # Логи транзакций
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                amount REAL,
                timestamp TEXT
            )
        """)
        self.conn.commit()

    def get_balance(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res else 0.0

    def update_balance(self, user_id, amount):
        current = self.get_balance(user_id)
        new_bal = current + amount
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (id, balance) VALUES (?, ?)", (user_id, new_bal))
        self.conn.commit()
        self._add_log(user_id, "BALANCE_UPDATE", amount)

    def _add_log(self, user_id, action, amount):
        cursor = self.conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO logs (user_id, action, amount, timestamp) VALUES (?, ?, ?, ?)",
                       (user_id, action, amount, now))
        self.conn.commit()

    def get_top_users(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, balance FROM users ORDER BY balance DESC LIMIT 10")
        return cursor.fetchall()