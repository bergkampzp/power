import os, base64, hashlib
from cryptography.fernet import Fernet

def _fernet():
    key = os.environ.get('DATA_PULL_KEY')
    if not key:
        raise RuntimeError("环境变量 DATA_PULL_KEY 未设置")
    digest = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()

def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
