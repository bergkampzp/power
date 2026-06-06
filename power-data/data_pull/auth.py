from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


def create_super(conn, username, password):
    conn.execute(
        "INSERT OR REPLACE INTO users(username,pwd_hash,role,created_at) VALUES(?,?,?,?)",
        (username, generate_password_hash(password), 'super', datetime.now().isoformat(timespec='seconds'))
    )
    conn.commit()


def verify(conn, username, password) -> bool:
    row = conn.execute("SELECT pwd_hash FROM users WHERE username=?", (username,)).fetchone()
    return bool(row) and check_password_hash(row[0], password)
