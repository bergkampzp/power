import secrets
from datetime import datetime
from .crypto_util import encrypt, decrypt
KEY = 'pairing_token'

def generate_token(conn) -> str:
    tok = secrets.token_urlsafe(24)
    conn.execute("""INSERT INTO app_config(key,value_enc,status,updated_at) VALUES(?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value_enc=excluded.value_enc,
                      status='valid', updated_at=excluded.updated_at""",
                 (KEY, encrypt(tok), 'valid', datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    return tok

def verify_token(conn, token: str) -> bool:
    row = conn.execute("SELECT value_enc FROM app_config WHERE key=?", (KEY,)).fetchone()
    if not row or not token:
        return False
    try:
        return secrets.compare_digest(decrypt(row[0]), token)
    except Exception:
        return False
