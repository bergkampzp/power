from datetime import datetime
from .crypto_util import encrypt, decrypt

KEY = 'platform_cookie'


def set_cookie(conn, cookie: str):
    conn.execute(
        """INSERT INTO app_config(key,value_enc,status,updated_at)
           VALUES(?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET value_enc=excluded.value_enc,
             status='valid', updated_at=excluded.updated_at""",
        (KEY, encrypt(cookie), 'valid', datetime.now().isoformat(timespec='seconds'))
    )
    conn.commit()


def get_cookie(conn):
    row = conn.execute("SELECT value_enc FROM app_config WHERE key=?", (KEY,)).fetchone()
    return decrypt(row[0]) if row else None


def mark_invalid(conn):
    conn.execute("UPDATE app_config SET status='invalid' WHERE key=?", (KEY,))
    conn.commit()
