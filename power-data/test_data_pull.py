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

from data_pull.sync_engine import sync_incremental
from data_pull.incremental import AuthExpired
import sqlite3 as _sq3

def _seed_da_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS day_ahead_node_price_96(trade_date TEXT, region TEXT, node_name TEXT, period TEXT, price REAL)")
    c.commit()

def test_sync_incremental_inserts():
    c = _sq3.connect(":memory:"); _seed_da_table(c)
    sources = [{"label":"DA","table":"day_ahead_node_price_96","date_col":"trade_date",
                "fetch": lambda cookie,d: {"data":{"data":[{"ok":1}]}},
                "insert": lambda conn,d,resp: conn.execute(
                    "INSERT INTO day_ahead_node_price_96 VALUES(?,?,?,?,?)",(d,'云南','__avg__','00:00',100.0))}]
    rep = sync_incremental("CAMSID=x", c, today="20260102", sources=sources, lookback_days=1, default_start="20260101")
    assert rep["DA"]["rows_added"] >= 1

def test_sync_incremental_auth_expired():
    c = _sq3.connect(":memory:"); _seed_da_table(c)
    sources = [{"label":"DA","table":"day_ahead_node_price_96","date_col":"trade_date",
                "fetch": lambda cookie,d: {"code":"401"},
                "insert": lambda conn,d,resp: None}]
    raised = False
    try:
        sync_incremental("bad", c, today="20260101", sources=sources, lookback_days=1, default_start="20260101")
    except AuthExpired:
        raised = True
    assert raised, "should have raised AuthExpired"

from data_pull import weather_sync as _ws
import inspect as _ins

def test_weather_sync_signature():
    assert hasattr(_ws, 'sync_weather_incremental')
    assert 'conn' in _ins.signature(_ws.sync_weather_incremental).parameters

from data_pull import orchestrator as _orch
from data_pull.schema import ensure_schema as _es
import sqlite3 as _sq3b, os as _os2

def test_orchestrator_lock_prevents_concurrent():
    _os2.environ['DATA_PULL_KEY'] = 'k'
    _orch._reset_lock_for_test()
    assert _orch._try_acquire() is True
    assert _orch._try_acquire() is False
    _orch._release()
    assert _orch._try_acquire() is True
    _orch._release()

def test_get_status_shape():
    c = _sq3b.connect(":memory:"); _es(c)
    st = _orch.get_status(c)
    assert {'in_progress','cookie_valid','last_run'} <= set(st.keys())

from data_pull import auth as _auth
from data_pull.schema import ensure_schema as _es2
import sqlite3 as _sq3c

def test_create_and_verify_user():
    c = _sq3c.connect(":memory:"); _es2(c)
    _auth.create_super(c, "admin", "secret")
    assert _auth.verify(c, "admin", "secret") is True
    assert _auth.verify(c, "admin", "wrong") is False
    assert _auth.verify(c, "nouser", "secret") is False

def test_flask_routes():
    import sys, os
    os.environ['DATA_PULL_KEY'] = 'k'
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'electrate'))
    import importlib
    import api_server
    importlib.reload(api_server)
    api_server.app.config['TESTING'] = True
    cli = api_server.app.test_client()
    # admin route requires auth — must return 401 without login
    r = cli.post('/api/admin/cookie', json={"cookie":"x"})
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
    # sync status is public
    r2 = cli.get('/api/sync/status')
    assert r2.status_code == 200, f"expected 200, got {r2.status_code}"

def test_init_super_cli_importable():
    from data_pull import init_super
    assert hasattr(init_super, 'main')

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
    try:
        test_sync_incremental_inserts()
        print("PASS test_sync_incremental_inserts")
    except Exception as e:
        print(f"FAIL test_sync_incremental_inserts: {e}")
        sys.exit(1)
    try:
        test_sync_incremental_auth_expired()
        print("PASS test_sync_incremental_auth_expired")
    except Exception as e:
        print(f"FAIL test_sync_incremental_auth_expired: {e}")
        sys.exit(1)
    try:
        test_weather_sync_signature()
        print("PASS test_weather_sync_signature")
    except Exception as e:
        print(f"FAIL test_weather_sync_signature: {e}")
        sys.exit(1)
    try:
        test_orchestrator_lock_prevents_concurrent()
        print("PASS test_orchestrator_lock_prevents_concurrent")
    except Exception as e:
        print(f"FAIL test_orchestrator_lock_prevents_concurrent: {e}")
        sys.exit(1)
    try:
        test_get_status_shape()
        print("PASS test_get_status_shape")
    except Exception as e:
        print(f"FAIL test_get_status_shape: {e}")
        sys.exit(1)
    try:
        test_create_and_verify_user()
        print("PASS test_create_and_verify_user")
    except Exception as e:
        print(f"FAIL test_create_and_verify_user: {e}")
        sys.exit(1)
    try:
        test_flask_routes()
        print("PASS test_flask_routes")
    except Exception as e:
        print(f"FAIL test_flask_routes: {e}")
        sys.exit(1)
    try:
        test_init_super_cli_importable()
        print("PASS test_init_super_cli_importable")
    except Exception as e:
        print(f"FAIL test_init_super_cli_importable: {e}")
        sys.exit(1)
