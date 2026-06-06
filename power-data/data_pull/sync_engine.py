from datetime import datetime, timedelta
from .incremental import missing_range, is_auth_expired, AuthExpired


def _dates(start, end):
    a = datetime.strptime(start, "%Y%m%d")
    b = datetime.strptime(end, "%Y%m%d")
    while a <= b:
        yield a.strftime("%Y%m%d")
        a += timedelta(days=1)


def _latest(conn, table, date_col):
    try:
        row = conn.execute(f"SELECT MAX(REPLACE({date_col},'-','')) FROM \"{table}\"").fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def sync_incremental(cookie, conn, today=None, sources=None, lookback_days=3, default_start="20251201"):
    if sources is None:
        import sync_all
        sources = sync_all.SOURCES
    if today is None:
        today = datetime.now().strftime("%Y%m%d")
    report = {}
    consecutive_empty = 0
    total_checks = 0
    for s in sources:
        start, end = missing_range(_latest(conn, s["table"], s["date_col"]), today, lookback_days, default_start)
        added = 0
        for d in _dates(start, end):
            ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            resp = s["fetch"](cookie, ds)
            total_checks += 1
            if is_auth_expired(resp):
                consecutive_empty += 1
                continue
            consecutive_empty = 0
            before = conn.execute(f"SELECT COUNT(*) FROM \"{s['table']}\"").fetchone()[0]
            s["insert"](conn, ds, resp)
            conn.commit()
            added += conn.execute(f"SELECT COUNT(*) FROM \"{s['table']}\"").fetchone()[0] - before
        report[s["label"]] = {"rows_added": added, "range": (start, end)}
    if total_checks > 0 and consecutive_empty == total_checks:
        raise AuthExpired("所有请求均无有效数据, cookie 可能失效")
    return report
