import sqlite3
from data_pull.schema import ensure_schema

def test_ensure_schema_creates_tables():
    c = sqlite3.connect(":memory:")
    ensure_schema(c)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'users', 'app_config', 'sync_status', 'sync_runs'} <= names
    # idempotent: calling again must not raise
    ensure_schema(c)

if __name__ == "__main__":
    import sys
    try:
        test_ensure_schema_creates_tables()
        print("PASS test_ensure_schema_creates_tables")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
