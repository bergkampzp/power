import sqlite3
from data_pull.schema import ensure_schema

def test_ensure_schema_creates_tables():
    c = sqlite3.connect(":memory:")
    ensure_schema(c)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'users', 'app_config', 'sync_status', 'sync_runs'} <= names
    # idempotent: calling again must not raise
    ensure_schema(c)

from data_pull.crypto_util import encrypt, decrypt

def test_crypto_round_trip():
    import os
    os.environ['DATA_PULL_KEY'] = 'test-key-please-change'
    token = encrypt("CAMSID=abc123")
    assert token != "CAMSID=abc123"          # must be encrypted
    assert decrypt(token) == "CAMSID=abc123"  # must round-trip

from data_pull.cookie_store import set_cookie, get_cookie, mark_invalid
import os

def test_cookie_store():
    os.environ['DATA_PULL_KEY'] = 'k'
    c = sqlite3.connect(":memory:"); ensure_schema(c)
    assert get_cookie(c) is None
    set_cookie(c, "CAMSID=xyz")
    assert get_cookie(c) == "CAMSID=xyz"            # decrypted plaintext
    row = c.execute("SELECT value_enc FROM app_config WHERE key='platform_cookie'").fetchone()
    assert row[0] != "CAMSID=xyz"                   # stored as ciphertext
    mark_invalid(c)
    assert c.execute("SELECT status FROM app_config WHERE key='platform_cookie'").fetchone()[0] == 'invalid'

from data_pull.incremental import missing_range, AuthExpired, is_auth_expired

def test_missing_range_basic():
    assert missing_range("20260601", "20260605", lookback_days=2) == ("20260531", "20260605")

def test_missing_range_empty_table():
    assert missing_range(None, "20260605", lookback_days=2, default_start="20251201") == ("20251201", "20260605")

def test_is_auth_expired_detects():
    assert is_auth_expired({"code": "401"}) is True
    assert is_auth_expired({"data": {"data": []}}) is True
    assert is_auth_expired({"data": {"data": [{"x": 1}]}}) is False

import sync_all, inspect

def test_sync_all_exports():
    assert 'cookie' in inspect.signature(sync_all.api_post).parameters
    assert hasattr(sync_all, 'SOURCES') and len(sync_all.SOURCES) >= 5
    for s in sync_all.SOURCES:
        assert 'label' in s and 'table' in s and 'fetch' in s and 'insert' in s

if __name__ == "__main__":
    import sys
    try:
        test_ensure_schema_creates_tables()
        print("PASS test_ensure_schema_creates_tables")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    try:
        test_crypto_round_trip()
        print("PASS test_crypto_round_trip")
    except Exception as e:
        print(f"FAIL test_crypto_round_trip: {e}")
        sys.exit(1)
    try:
        test_cookie_store()
        print("PASS test_cookie_store")
    except Exception as e:
        print(f"FAIL test_cookie_store: {e}")
        sys.exit(1)
    try:
        test_missing_range_basic()
        print("PASS test_missing_range_basic")
    except Exception as e:
        print(f"FAIL test_missing_range_basic: {e}")
        sys.exit(1)
    try:
        test_missing_range_empty_table()
        print("PASS test_missing_range_empty_table")
    except Exception as e:
        print(f"FAIL test_missing_range_empty_table: {e}")
        sys.exit(1)
    try:
        test_is_auth_expired_detects()
        print("PASS test_is_auth_expired_detects")
    except Exception as e:
        print(f"FAIL test_is_auth_expired_detects: {e}")
        sys.exit(1)
    try:
        test_sync_all_exports()
        print("PASS test_sync_all_exports")
    except Exception as e:
        print(f"FAIL test_sync_all_exports: {e}")
        sys.exit(1)
