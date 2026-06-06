def ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE, pwd_hash TEXT,
            role TEXT DEFAULT 'super', created_at TEXT);
        CREATE TABLE IF NOT EXISTS app_config(
            key TEXT PRIMARY KEY, value_enc TEXT, status TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS sync_status(
            id INTEGER PRIMARY KEY CHECK(id=1), in_progress INTEGER DEFAULT 0,
            last_run TEXT, cookie_valid INTEGER DEFAULT 0, summary TEXT);
        CREATE TABLE IF NOT EXISTS sync_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT,
            ok INTEGER, report TEXT);
        INSERT OR IGNORE INTO sync_status(id, in_progress, cookie_valid) VALUES (1,0,0);
    """)
    conn.commit()
