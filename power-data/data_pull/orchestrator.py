import threading, json, sqlite3
from datetime import datetime
from .cookie_store import get_cookie, mark_invalid
from .sync_engine import sync_incremental
from .weather_sync import sync_weather_incremental
from .incremental import AuthExpired

_lock = threading.Lock()

def _try_acquire(): return _lock.acquire(blocking=False)
def _release():
    try:
        _lock.release()
    except RuntimeError:
        pass
def _reset_lock_for_test():
    global _lock; _lock = threading.Lock()

def _set_status(conn, **kw):
    cols = ",".join(f"{k}=?" for k in kw)
    conn.execute(f"UPDATE sync_status SET {cols} WHERE id=1", tuple(kw.values())); conn.commit()

def get_status(conn):
    r = conn.execute("SELECT in_progress,last_run,cookie_valid,summary FROM sync_status WHERE id=1").fetchone()
    return {"in_progress":bool(r[0]),"last_run":r[1],"cookie_valid":bool(r[2]),"summary":r[3]}

def _run(db_path):
    conn = sqlite3.connect(db_path)
    try:
        _set_status(conn, in_progress=1)
        report = {}
        try:
            report["weather"] = {"rows": sync_weather_incremental(conn)}
        except Exception as e:
            report["weather"] = {"error": str(e)}
        cookie = get_cookie(conn)
        if not cookie:
            _set_status(conn, cookie_valid=0, summary=json.dumps({"need_cookie":True, **report}, ensure_ascii=False))
        else:
            try:
                report.update(sync_incremental(cookie, conn))
                _set_status(conn, cookie_valid=1, summary=json.dumps(report, ensure_ascii=False))
            except AuthExpired:
                mark_invalid(conn)
                _set_status(conn, cookie_valid=0, summary=json.dumps({"cookie_invalid":True, **report}, ensure_ascii=False))
        conn.execute("INSERT INTO sync_runs(started_at,finished_at,ok,report) VALUES(?,?,?,?)",
                     (None, datetime.now().isoformat(timespec='seconds'), 1, json.dumps(report, ensure_ascii=False)))
        conn.commit()
    finally:
        _set_status(conn, in_progress=0, last_run=datetime.now().isoformat(timespec='seconds'))
        conn.close(); _release()

def trigger_sync(db_path):
    if not _try_acquire():
        return {"started": False, "reason": "already_running"}
    threading.Thread(target=_run, args=(db_path,), daemon=True).start()
    return {"started": True}
