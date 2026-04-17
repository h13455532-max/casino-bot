import sqlite3

class DB:
    def __init__(self):
        self.conn = sqlite3.connect("casino.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance REAL)")
        self.conn.commit()

    def get_balance(self, user_id):
        self.cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        res = self.cursor.fetchone()
        return res[0] if res else 0.0

    def update_balance(self, user_id, amount):
        current = self.get_balance(user_id)
        self.cursor.execute("INSERT OR REPLACE INTO users (id, balance) VALUES (?, ?)", (user_id, current + amount))
        self.conn.commit()
