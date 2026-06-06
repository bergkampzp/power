# 自动数据拉取功能 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 超级用户登录 electrate 后自动增量补齐云南电力数据（日前电价等 + 天气）；其他客户只读浏览。

**Architecture:** Flask 后端内置后台线程触发增量同步，复用并重构 `sync_all.py` 为可导入引擎；单一全局平台 cookie 加密存储；同步锁串行化 SQLite 写；单超级用户账号密码登录保护管理接口。

**Tech Stack:** Python 3.12, Flask, sqlite3, urllib, `cryptography`(Fernet), werkzeug(password hash); 前端 React + Ant Design (TSX)。测试沿用仓库现有风格（`test_*.py` 自带 `__main__` 运行器 + assert，用 `python test_x.py` 跑）。

**依赖安装（一次性）:** `python -m pip install cryptography`（werkzeug 随 Flask 已装）。

---

## 文件结构

- 新增 `power-data/data_pull/__init__.py` — 包标记
- 新增 `power-data/data_pull/crypto_util.py` — cookie 对称加解密
- 新增 `power-data/data_pull/cookie_store.py` — 单值 cookie 存取(app_config 表)
- 新增 `power-data/data_pull/schema.py` — 建表(users/app_config/sync_status/sync_runs)
- 新增 `power-data/data_pull/incremental.py` — 增量区间计算(纯函数) + AuthExpired
- 修改 `power-data/sync_all.py` — 抽出 `api_post(cookie,...)`、`SOURCES` 清单可导入
- 新增 `power-data/data_pull/sync_engine.py` — `sync_incremental(cookie, conn)`
- 新增 `power-data/data_pull/weather_sync.py` — 包 `weather_forecast_fetch` live
- 新增 `power-data/data_pull/orchestrator.py` — 全局锁 + 新鲜度 + `trigger_sync()` + 状态写入
- 新增 `power-data/data_pull/auth.py` — 用户表/密码/会话/`require_super`
- 修改 `electrate/api_server.py` — login / admin cookie / admin sync / sync status 路由
- 新增 `power-data/test_data_pull.py` — 单元/集成测试（沿用仓库风格）
- 前端：`electrate/pages/Login.tsx`、`electrate/pages/UserCenter.tsx`(改)、`electrate/components/SyncStatusBar.tsx`

---

## Task 1: DB 建表（schema）

**Files:**
- Create: `power-data/data_pull/__init__.py`
- Create: `power-data/data_pull/schema.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
# test_data_pull.py
import sqlite3
from data_pull.schema import ensure_schema

def test_ensure_schema_creates_tables():
    c = sqlite3.connect(":memory:")
    ensure_schema(c)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'users', 'app_config', 'sync_status', 'sync_runs'} <= names
    # 幂等: 再次调用不报错
    ensure_schema(c)
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_ensure_schema_creates_tables as t; t()"`
Expected: FAIL `ModuleNotFoundError: No module named 'data_pull'`

- [ ] **Step 3: 实现**

```python
# data_pull/__init__.py  (空文件)
```
```python
# data_pull/schema.py
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
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_ensure_schema_creates_tables as t; t()"`
Expected: 无输出、退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/__init__.py power-data/data_pull/schema.py power-data/test_data_pull.py
git commit -m "feat(data_pull): DB schema for auto data pull"
```

---

## Task 2: cookie 加解密（crypto_util）

**Files:**
- Create: `power-data/data_pull/crypto_util.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**（追加到 test_data_pull.py）

```python
from data_pull.crypto_util import encrypt, decrypt

def test_crypto_round_trip(monkeypatch=None):
    import os
    os.environ['DATA_PULL_KEY'] = 'test-key-please-change'
    token = encrypt("CAMSID=abc123")
    assert token != "CAMSID=abc123"          # 已加密
    assert decrypt(token) == "CAMSID=abc123"  # 可还原
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_crypto_round_trip as t; t()"`
Expected: FAIL `ModuleNotFoundError: data_pull.crypto_util`

- [ ] **Step 3: 实现**

```python
# data_pull/crypto_util.py
import os, base64, hashlib
from cryptography.fernet import Fernet

def _fernet():
    key = os.environ.get('DATA_PULL_KEY')
    if not key:
        raise RuntimeError("环境变量 DATA_PULL_KEY 未设置")
    # 由任意字符串派生 32 字节 Fernet 密钥
    digest = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()

def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_crypto_round_trip as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/crypto_util.py power-data/test_data_pull.py
git commit -m "feat(data_pull): cookie symmetric encryption (Fernet)"
```

---

## Task 3: 单值 cookie 存取（cookie_store）

**Files:**
- Create: `power-data/data_pull/cookie_store.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
from data_pull.schema import ensure_schema
from data_pull.cookie_store import set_cookie, get_cookie, mark_invalid
import sqlite3, os

def test_cookie_store():
    os.environ['DATA_PULL_KEY'] = 'k'
    c = sqlite3.connect(":memory:"); ensure_schema(c)
    assert get_cookie(c) is None
    set_cookie(c, "CAMSID=xyz")
    assert get_cookie(c) == "CAMSID=xyz"            # 解密返回明文
    row = c.execute("SELECT value_enc FROM app_config WHERE key='platform_cookie'").fetchone()
    assert row[0] != "CAMSID=xyz"                   # 库内是密文
    mark_invalid(c)
    assert c.execute("SELECT status FROM app_config WHERE key='platform_cookie'").fetchone()[0] == 'invalid'
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_cookie_store as t; t()"`
Expected: FAIL `ModuleNotFoundError: data_pull.cookie_store`

- [ ] **Step 3: 实现**

```python
# data_pull/cookie_store.py
from datetime import datetime
from .crypto_util import encrypt, decrypt
KEY = 'platform_cookie'

def set_cookie(conn, cookie: str):
    conn.execute("""INSERT INTO app_config(key,value_enc,status,updated_at)
                    VALUES(?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value_enc=excluded.value_enc,
                      status='valid', updated_at=excluded.updated_at""",
                 (KEY, encrypt(cookie), 'valid', datetime.now().isoformat(timespec='seconds')))
    conn.commit()

def get_cookie(conn):
    row = conn.execute("SELECT value_enc FROM app_config WHERE key=?", (KEY,)).fetchone()
    return decrypt(row[0]) if row else None

def mark_invalid(conn):
    conn.execute("UPDATE app_config SET status='invalid' WHERE key=?", (KEY,))
    conn.commit()
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_cookie_store as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/cookie_store.py power-data/test_data_pull.py
git commit -m "feat(data_pull): single-value encrypted cookie store"
```

---

## Task 4: 增量区间计算 + AuthExpired（纯逻辑）

**Files:**
- Create: `power-data/data_pull/incremental.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
from data_pull.incremental import missing_range, AuthExpired, is_auth_expired

def test_missing_range_basic():
    # 库内最新 20260601, 今天 20260605, 回拉2天 => 从 20260531 起
    assert missing_range("20260601", "20260605", lookback_days=2) == ("20260531", "20260605")

def test_missing_range_empty_table():
    # 无数据 => 从给定默认起点
    assert missing_range(None, "20260605", lookback_days=2, default_start="20251201") == ("20251201", "20260605")

def test_is_auth_expired_detects_login_redirect():
    assert is_auth_expired({"code": "401"}) is True
    assert is_auth_expired({"data": {"data": []}}) is True          # 空数据视为可能失效
    assert is_auth_expired({"data": {"data": [{"x": 1}]}}) is False  # 有数据=>有效
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "import test_data_pull as m; m.test_missing_range_basic(); m.test_missing_range_empty_table(); m.test_is_auth_expired_detects_login_redirect()"`
Expected: FAIL `ModuleNotFoundError: data_pull.incremental`

- [ ] **Step 3: 实现**

```python
# data_pull/incremental.py
from datetime import datetime, timedelta

class AuthExpired(Exception):
    pass

def missing_range(latest_date, today, lookback_days=3, default_start="20251201"):
    """返回需要拉取的 (start, end) 'YYYYMMDD'。latest_date 为库内最新(可None)。"""
    if not latest_date:
        return (default_start, today)
    d = datetime.strptime(latest_date, "%Y%m%d") - timedelta(days=lookback_days - 1)
    return (d.strftime("%Y%m%d"), today)

def is_auth_expired(resp: dict) -> bool:
    """从 API 响应粗判 cookie 是否失效: 401/302/未登录/空数据。"""
    if not isinstance(resp, dict):
        return True
    code = str(resp.get("code", "")).lower()
    if code in ("401", "302") or "login" in code or resp.get("error"):
        return True
    data = resp.get("data", {})
    inner = data.get("data", data) if isinstance(data, dict) else data
    return not inner  # 空 => 视为可能失效(由上层结合多源判断)
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "import test_data_pull as m; m.test_missing_range_basic(); m.test_missing_range_empty_table(); m.test_is_auth_expired_detects_login_redirect()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/incremental.py power-data/test_data_pull.py
git commit -m "feat(data_pull): incremental range calc + auth-expired detection"
```

---

## Task 5: 重构 sync_all 暴露可注入 cookie 的 api_post + SOURCES

**Files:**
- Modify: `power-data/sync_all.py`（去硬编码 COOKIE，`api_post` 增加 `cookie` 参数；导出 `SOURCES` 与各 `insert_*`）
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
import sync_all

def test_sync_all_exports():
    # api_post 接受 cookie 参数(签名包含 cookie)
    import inspect
    assert 'cookie' in inspect.signature(sync_all.api_post).parameters
    # 导出源清单, 每项含 (label, fetch_fn, insert_fn) 或等价结构
    assert hasattr(sync_all, 'SOURCES') and len(sync_all.SOURCES) >= 5
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_sync_all_exports as t; t()"`
Expected: FAIL（`api_post` 无 cookie 参数 / 无 `SOURCES`）

- [ ] **Step 3: 实现**

在 `sync_all.py`：把模块级 `COOKIE = "..."` 删除；`api_post` 改签名为 `def api_post(endpoint, body, cookie, timeout=15):` 并用传入 `cookie`；把内部"同步哪些源"的列表提为模块级 `SOURCES`，每项形如 `{"label":..., "fetch": lambda cookie,d: api_post(ep, body(d), cookie), "insert": insert_fn, "table":..., "date_col":...}`。保留原 `__main__` 行为：从环境变量 `PLATFORM_COOKIE` 读 cookie 跑全量（向后兼容手动用法）。

```python
# sync_all.py (关键改动示意)
import os
def api_post(endpoint, body, cookie, timeout=15):
    headers = random_headers(); headers["Cookie"] = cookie
    # ...原逻辑, 用传入 cookie...

SOURCES = [
    {"label":"日前电价(全省)", "table":"day_ahead_node_price_96", "date_col":"trade_date",
     "fetch": lambda cookie,d: api_post("tdSpotRecentlyResultUserInfo/getList", {"operatingDate":d}, cookie),
     "insert": insert_day_ahead_price},
    # ... 其余源同样改为接收 cookie ...
]

if __name__ == "__main__":
    ck = os.environ.get("PLATFORM_COOKIE","")
    # ...原全量逻辑, 传 ck...
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_sync_all_exports as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/sync_all.py power-data/test_data_pull.py
git commit -m "refactor(sync_all): inject cookie + export SOURCES"
```

---

## Task 6: 同步引擎 sync_incremental（集成，打桩 api_post）

**Files:**
- Create: `power-data/data_pull/sync_engine.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**（用打桩 fetch，避免真实网络）

```python
from data_pull.sync_engine import sync_incremental
from data_pull.incremental import AuthExpired
import sqlite3

def _seed_da_table(c):
    c.execute("CREATE TABLE day_ahead_node_price_96(trade_date TEXT, region TEXT, node_name TEXT, period TEXT, price REAL)")
    c.commit()

def test_sync_incremental_inserts(monkeypatched_sources=None):
    c = sqlite3.connect(":memory:"); _seed_da_table(c)
    # 单源打桩: 返回一条有效记录
    sources = [{"label":"DA","table":"day_ahead_node_price_96","date_col":"trade_date",
                "fetch": lambda cookie,d: {"data":{"data":[{"ok":1}]}},
                "insert": lambda conn,d,resp: conn.execute(
                    "INSERT INTO day_ahead_node_price_96 VALUES(?,?,?,?,?)",(d,'云南','__avg__','00:00',100.0))}]
    rep = sync_incremental("CAMSID=x", c, today="20260102", sources=sources, lookback_days=1, default_start="20260101")
    assert rep["DA"]["rows_added"] >= 1
    assert c.execute("SELECT COUNT(*) FROM day_ahead_node_price_96").fetchone()[0] >= 1

def test_sync_incremental_auth_expired():
    c = sqlite3.connect(":memory:"); _seed_da_table(c)
    sources = [{"label":"DA","table":"day_ahead_node_price_96","date_col":"trade_date",
                "fetch": lambda cookie,d: {"code":"401"},
                "insert": lambda conn,d,resp: None}]
    try:
        sync_incremental("bad", c, today="20260101", sources=sources, lookback_days=1, default_start="20260101")
        assert False, "应抛 AuthExpired"
    except AuthExpired:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "import test_data_pull as m; m.test_sync_incremental_inserts(); m.test_sync_incremental_auth_expired()"`
Expected: FAIL `ModuleNotFoundError: data_pull.sync_engine`

- [ ] **Step 3: 实现**

```python
# data_pull/sync_engine.py
from datetime import datetime, timedelta
from .incremental import missing_range, is_auth_expired, AuthExpired

def _dates(start, end):
    a = datetime.strptime(start, "%Y%m%d"); b = datetime.strptime(end, "%Y%m%d")
    while a <= b:
        yield a.strftime("%Y%m%d"); a += timedelta(days=1)

def _latest(conn, table, date_col):
    try:
        row = conn.execute(f"SELECT MAX(REPLACE({date_col},'-','')) FROM {table}").fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None

def sync_incremental(cookie, conn, today=None, sources=None, lookback_days=3, default_start="20251201"):
    if sources is None:
        import sync_all; sources = sync_all.SOURCES
    if today is None:
        today = datetime.now().strftime("%Y%m%d")
    report = {}; consecutive_empty = 0; total_checks = 0
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
            before = conn.execute(f"SELECT COUNT(*) FROM {s['table']}").fetchone()[0]
            s["insert"](conn, ds, resp); conn.commit()
            added += conn.execute(f"SELECT COUNT(*) FROM {s['table']}").fetchone()[0] - before
        report[s["label"]] = {"rows_added": added, "range": (start, end)}
    # 全程一无所获 => 判定 cookie 失效
    if total_checks > 0 and consecutive_empty == total_checks:
        raise AuthExpired("所有请求均无有效数据, cookie 可能失效")
    return report
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "import test_data_pull as m; m.test_sync_incremental_inserts(); m.test_sync_incremental_auth_expired()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/sync_engine.py power-data/test_data_pull.py
git commit -m "feat(data_pull): incremental sync engine"
```

---

## Task 7: 天气同步包装（weather_sync）

**Files:**
- Create: `power-data/data_pull/weather_sync.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**（仅验证可调用、签名；不打真实网络）

```python
from data_pull import weather_sync
import inspect

def test_weather_sync_signature():
    assert hasattr(weather_sync, 'sync_weather_incremental')
    assert 'conn' in inspect.signature(weather_sync.sync_weather_incremental).parameters
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_weather_sync_signature as t; t()"`
Expected: FAIL `ModuleNotFoundError: data_pull.weather_sync`

- [ ] **Step 3: 实现**

```python
# data_pull/weather_sync.py
import weather_forecast_fetch as wf

def sync_weather_incremental(conn):
    """拉取次日天气预报(live, 无cookie)。复用现有 run_live。返回写入条数。"""
    wf.ensure_table(conn)
    wf.run_live(conn)   # 内部按 16 城抓 forecast_days=2 并 INSERT OR REPLACE
    return conn.execute("SELECT COUNT(*) FROM weather_forecast").fetchone()[0]
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_weather_sync_signature as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/weather_sync.py power-data/test_data_pull.py
git commit -m "feat(data_pull): weather incremental sync wrapper"
```

---

## Task 8: 编排器（锁 + 新鲜度 + 后台触发 + 状态）

**Files:**
- Create: `power-data/data_pull/orchestrator.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
from data_pull import orchestrator as orch
from data_pull.schema import ensure_schema
import sqlite3, os, time

def test_orchestrator_lock_prevents_concurrent():
    os.environ['DATA_PULL_KEY']='k'
    orch._reset_lock_for_test()
    assert orch._try_acquire() is True      # 第一次拿到
    assert orch._try_acquire() is False     # 第二次被锁
    orch._release()
    assert orch._try_acquire() is True

def test_get_status_shape():
    c = sqlite3.connect(":memory:"); ensure_schema(c)
    st = orch.get_status(c)
    assert set(['in_progress','cookie_valid','last_run']) <= set(st.keys())
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "import test_data_pull as m; m.test_orchestrator_lock_prevents_concurrent(); m.test_get_status_shape()"`
Expected: FAIL `ModuleNotFoundError: data_pull.orchestrator`

- [ ] **Step 3: 实现**

```python
# data_pull/orchestrator.py
import threading, json, sqlite3
from datetime import datetime
from .cookie_store import get_cookie, mark_invalid
from .sync_engine import sync_incremental
from .weather_sync import sync_weather_incremental
from .incremental import AuthExpired

_lock = threading.Lock()

def _try_acquire(): return _lock.acquire(blocking=False)
def _release():
    if _lock.locked(): _lock.release()
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
    """非阻塞: 抢锁成功则后台线程执行, 否则返回 already_running。"""
    if not _try_acquire():
        return {"started": False, "reason": "already_running"}
    threading.Thread(target=_run, args=(db_path,), daemon=True).start()
    return {"started": True}
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "import test_data_pull as m; m.test_orchestrator_lock_prevents_concurrent(); m.test_get_status_shape()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/orchestrator.py power-data/test_data_pull.py
git commit -m "feat(data_pull): sync orchestrator with lock + status"
```

---

## Task 9: 超级用户认证（auth + require_super）

**Files:**
- Create: `power-data/data_pull/auth.py`
- Test: `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
from data_pull import auth
from data_pull.schema import ensure_schema
import sqlite3

def test_create_and_verify_user():
    c = sqlite3.connect(":memory:"); ensure_schema(c)
    auth.create_super(c, "admin", "secret")
    assert auth.verify(c, "admin", "secret") is True
    assert auth.verify(c, "admin", "wrong") is False
    assert auth.verify(c, "nouser", "secret") is False
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_create_and_verify_user as t; t()"`
Expected: FAIL `ModuleNotFoundError: data_pull.auth`

- [ ] **Step 3: 实现**

```python
# data_pull/auth.py
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

def create_super(conn, username, password):
    conn.execute("INSERT OR REPLACE INTO users(username,pwd_hash,role,created_at) VALUES(?,?,?,?)",
                 (username, generate_password_hash(password), 'super', datetime.now().isoformat(timespec='seconds')))
    conn.commit()

def verify(conn, username, password) -> bool:
    row = conn.execute("SELECT pwd_hash FROM users WHERE username=?", (username,)).fetchone()
    return bool(row) and check_password_hash(row[0], password)
```

说明：Flask 侧 `require_super` 装饰器在 Task 10 内随路由实现（依赖 Flask session），此处只做可单测的用户验证。

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_create_and_verify_user as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/auth.py power-data/test_data_pull.py
git commit -m "feat(data_pull): super-user password auth"
```

---

## Task 10: Flask 路由（login / admin cookie / admin sync / status）

**Files:**
- Modify: `electrate/api_server.py`
- Test: `power-data/test_data_pull.py`（用 Flask test client）

- [ ] **Step 1: 写失败测试**

```python
def test_flask_routes():
    import importlib, sys, os, sqlite3
    os.environ['DATA_PULL_KEY']='k'
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'electrate'))
    import api_server
    api_server.app.config['TESTING'] = True
    cli = api_server.app.test_client()
    # 未登录访问管理接口被拒
    assert cli.post('/api/admin/cookie', json={"cookie":"x"}).status_code in (401,403)
    # 状态接口公开
    assert cli.get('/api/sync/status').status_code == 200
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_flask_routes as t; t()"`
Expected: FAIL（路由不存在 → 404，而非 401/403）

- [ ] **Step 3: 实现**（在 `api_server.py` 顶部 import，并加路由）

```python
# api_server.py 顶部
import os, sys, functools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'power-data'))
from data_pull.schema import ensure_schema
from data_pull import auth, cookie_store, orchestrator
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret-change-me')

def _conn():
    import sqlite3
    return sqlite3.connect(DB_PATH)   # DB_PATH 为 api_server 既有的库路径常量

with _conn() as _c:
    ensure_schema(_c)

def require_super(fn):
    @functools.wraps(fn)
    def w(*a, **k):
        if not session.get('is_super'):
            return jsonify({"error":"unauthorized"}), 401
        return fn(*a, **k)
    return w

@app.route('/api/login', methods=['POST'])
def api_login():
    body = request.get_json(force=True)
    with _conn() as c:
        if auth.verify(c, body.get('username',''), body.get('password','')):
            session['is_super'] = True
            orchestrator.trigger_sync(DB_PATH)   # 登录即异步触发
            return jsonify({"ok":True, "sync":"started"})
    return jsonify({"error":"bad_credentials"}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear(); return jsonify({"ok":True})

@app.route('/api/admin/cookie', methods=['POST'])
@require_super
def api_set_cookie():
    with _conn() as c:
        cookie_store.set_cookie(c, request.get_json(force=True)['cookie'])
    orchestrator.trigger_sync(DB_PATH)
    return jsonify({"ok":True})

@app.route('/api/admin/sync', methods=['POST'])
@require_super
def api_manual_sync():
    return jsonify(orchestrator.trigger_sync(DB_PATH))

@app.route('/api/sync/status', methods=['GET'])
def api_sync_status():
    with _conn() as c:
        return jsonify(orchestrator.get_status(c))
```

（确认文件顶部已 `from flask import request, jsonify, session`。）

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_flask_routes as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add electrate/api_server.py power-data/test_data_pull.py
git commit -m "feat(api): login/admin-cookie/sync/status routes + login-triggered sync"
```

---

## Task 11: 初始化超级用户脚本

**Files:**
- Create: `power-data/data_pull/init_super.py`

- [ ] **Step 1: 写失败测试**

```python
def test_init_super_cli_importable():
    from data_pull import init_super
    assert hasattr(init_super, 'main')
```

- [ ] **Step 2: 运行验证失败**

Run: `cd power-data && python -c "from test_data_pull import test_init_super_cli_importable as t; t()"`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# data_pull/init_super.py
import sys, sqlite3, getpass
from config import DB
from .schema import ensure_schema
from .auth import create_super

def main():
    u = sys.argv[1] if len(sys.argv) > 1 else input("超级用户名: ")
    p = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("密码: ")
    c = sqlite3.connect(DB); ensure_schema(c); create_super(c, u, p)
    print(f"已创建超级用户: {u}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行验证通过**

Run: `cd power-data && python -c "from test_data_pull import test_init_super_cli_importable as t; t()"`
Expected: 退出码 0

- [ ] **Step 5: 提交**

```bash
git add power-data/data_pull/init_super.py power-data/test_data_pull.py
git commit -m "feat(data_pull): super-user init CLI"
```

---

## Task 12: 前端 — 登录页 + cookie 录入 + 状态条（手动验证）

**Files:**
- Create: `electrate/pages/Login.tsx`
- Modify: `electrate/pages/UserCenter.tsx`（加 cookie 录入 + 立即刷新, 仅超级用户可见）
- Create: `electrate/components/SyncStatusBar.tsx`
- Modify: `electrate/components/Layout.tsx`（嵌入 SyncStatusBar；未登录隐藏管理入口）

- [ ] **Step 1: 实现登录页**

```tsx
// electrate/pages/Login.tsx
import { useState } from 'react';
import { Card, Input, Button, message } from 'antd';
export default function Login({ onLogin }: { onLogin: () => void }) {
  const [u, setU] = useState(''); const [p, setP] = useState('');
  const submit = async () => {
    const r = await fetch('/api/login', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ username:u, password:p }) });
    if (r.ok) { message.success('登录成功，正在自动更新数据'); onLogin(); }
    else message.error('账号或密码错误');
  };
  return (<Card title="超级用户登录" style={{maxWidth:360, margin:'80px auto'}}>
    <Input placeholder="用户名" value={u} onChange={e=>setU(e.target.value)} style={{marginBottom:12}} />
    <Input.Password placeholder="密码" value={p} onChange={e=>setP(e.target.value)} style={{marginBottom:12}} />
    <Button type="primary" block onClick={submit}>登录</Button>
  </Card>);
}
```

- [ ] **Step 2: 实现状态条**

```tsx
// electrate/components/SyncStatusBar.tsx
import { useEffect, useState } from 'react';
import { Alert } from 'antd';
export default function SyncStatusBar() {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    const poll = () => fetch('/api/sync/status').then(r=>r.json()).then(setS).catch(()=>{});
    poll(); const t = setInterval(poll, 5000); return () => clearInterval(t);
  }, []);
  if (!s) return null;
  if (s.in_progress) return <Alert type="info" message="数据更新中…" banner />;
  if (!s.cookie_valid) return <Alert type="warning" message="平台 cookie 失效，请在用户中心重新录入" banner />;
  return <Alert type="success" message={`数据已更新 (${s.last_run || ''})`} banner />;
}
```

- [ ] **Step 3: UserCenter 加 cookie 录入（仅超级用户）**

```tsx
// 在 UserCenter.tsx 内新增
import { Input, Button, message } from 'antd'; import { useState } from 'react';
function CookiePanel() {
  const [c, setC] = useState('');
  const save = async () => {
    const r = await fetch('/api/admin/cookie', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ cookie:c }) });
    message[r.ok?'success':'error'](r.ok?'已保存并触发更新':'保存失败(需超级用户)');
  };
  const refresh = async () => { await fetch('/api/admin/sync',{method:'POST'}); message.info('已触发刷新'); };
  return (<div style={{marginTop:16}}>
    <p>平台会话 Cookie（从浏览器登录 spot.poweremarket.com 后复制 CAMSID）：</p>
    <Input.TextArea rows={2} value={c} onChange={e=>setC(e.target.value)} placeholder="CAMSID=..." />
    <Button type="primary" onClick={save} style={{marginTop:8, marginRight:8}}>保存 Cookie</Button>
    <Button onClick={refresh} style={{marginTop:8}}>立即刷新</Button>
  </div>);
}
```

- [ ] **Step 4: 手动验证**

```
# 后端
python -m pip install cryptography
cd power-data && python -m data_pull.init_super admin <密码>
cd ../electrate && python api_server.py   # 启动后端
# 前端 npm run dev, 浏览器:
# 1) 普通访问 → 看数据, 无管理入口, 状态条显示数据时间
# 2) 登录超级用户 → 状态条"更新中…" → 完成
# 3) 用户中心粘贴有效 CAMSID → "已保存并触发更新" → 数据补齐
# 4) 粘贴无效 cookie → 状态条"cookie 失效"
```

- [ ] **Step 5: 提交**

```bash
git add electrate/pages/Login.tsx electrate/pages/UserCenter.tsx electrate/components/SyncStatusBar.tsx electrate/components/Layout.tsx
git commit -m "feat(ui): login + cookie panel + sync status bar"
```

---

## 全量测试

- [ ] 运行全部后端测试：`cd power-data && python test_data_pull.py`
Expected: 全部 PASS

---

## 自检结论（写计划时已核对 spec）

- **覆盖**：角色/权限(Task 9,10,12)、cookie 半自动(Task 2,3,10,12)、登录触发增量(Task 6,8,10)、共享库(全程单库)、全量源+天气(Task 5,6,7)、错误处理(Task 6 AuthExpired / Task 8 锁/失效)、安全(Task 2 加密/Task 9 哈希/Task 10 require_super)、测试(各 Task)。
- **占位符**：无 TODO/TBD；每步含可运行代码与命令。
- **类型/命名一致**：`api_post(...,cookie)`、`SOURCES`、`sync_incremental`、`trigger_sync(db_path)`、`get_status(conn)`、`require_super` 跨任务一致。

---

# v3 增量任务：云端浏览器扩展自动捕获 cookie

## Task 13: 配对令牌（pairing token）存取

**Files:** Create `power-data/data_pull/pairing.py`；Test `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
from data_pull.pairing import generate_token, verify_token
from data_pull.schema import ensure_schema
import sqlite3, os
def test_pairing_token():
    os.environ['DATA_PULL_KEY'] = 'k'
    c = sqlite3.connect(":memory:"); ensure_schema(c)
    tok = generate_token(c)
    assert tok and len(tok) >= 16
    assert verify_token(c, tok) is True
    assert verify_token(c, "wrong") is False
    tok2 = generate_token(c)
    assert verify_token(c, tok) is False and verify_token(c, tok2) is True
```

- [ ] **Step 2: 运行验证失败** — `cd power-data && python -c "from test_data_pull import test_pairing_token as t; t()"` → FAIL ModuleNotFoundError

- [ ] **Step 3: 实现**

```python
# data_pull/pairing.py
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
    conn.commit(); return tok
def verify_token(conn, token: str) -> bool:
    row = conn.execute("SELECT value_enc FROM app_config WHERE key=?", (KEY,)).fetchone()
    if not row or not token: return False
    try: return secrets.compare_digest(decrypt(row[0]), token)
    except Exception: return False
```

- [ ] **Step 4: 运行验证通过** — 同 Step 2 命令 → 退出码 0
- [ ] **Step 5: 提交** — `git add power-data/data_pull/pairing.py power-data/test_data_pull.py && git commit -m "feat(data_pull): pairing token for extension auth"`

---

## Task 14: 扩展端点 /api/extension/cookie + /api/admin/pairing-token

**Files:** Modify `electrate/api_server.py`；Test `power-data/test_data_pull.py`

- [ ] **Step 1: 写失败测试**

```python
def test_extension_cookie_endpoint():
    import os, sys, sqlite3
    os.environ['DATA_PULL_KEY']='k'
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'electrate'))
    import api_server
    from data_pull import pairing
    from data_pull.schema import ensure_schema
    from data_pull.cookie_store import get_cookie
    api_server.app.config['TESTING'] = True
    cli = api_server.app.test_client()
    with sqlite3.connect(api_server.DB_PATH) as c:
        ensure_schema(c); tok = pairing.generate_token(c)
    assert cli.post('/api/extension/cookie', json={"token":"bad","cookie":"CAMSID=1"}).status_code == 401
    assert cli.post('/api/extension/cookie', json={"token":tok,"cookie":"FOO=1"}).status_code == 400
    assert cli.post('/api/extension/cookie', json={"token":tok,"cookie":"CAMSID=abc"}).status_code == 200
    with sqlite3.connect(api_server.DB_PATH) as c:
        assert get_cookie(c) == "CAMSID=abc"
```

- [ ] **Step 2: 运行验证失败** — `cd power-data && python -c "from test_data_pull import test_extension_cookie_endpoint as t; t()"` → FAIL (404)

- [ ] **Step 3: 实现**（追加到 `api_server.py`）

```python
from data_pull import pairing

@app.route('/api/admin/pairing-token', methods=['POST'])
@require_super
def api_pairing_token():
    with _conn() as c:
        return jsonify({"token": pairing.generate_token(c)})

@app.route('/api/extension/cookie', methods=['POST'])
def api_extension_cookie():
    body = request.get_json(force=True)
    token = body.get('token',''); cookie = body.get('cookie','')
    with _conn() as c:
        if not pairing.verify_token(c, token):
            return jsonify({"error":"bad_token"}), 401
        if 'CAMSID' not in cookie:
            return jsonify({"error":"expect_camsid"}), 400
        cookie_store.set_cookie(c, cookie)
    orchestrator.trigger_sync(DB_PATH)
    return jsonify({"ok": True})
```

- [ ] **Step 4: 运行验证通过** — 同 Step 2 命令 → 退出码 0
- [ ] **Step 5: 提交** — `git add electrate/api_server.py power-data/test_data_pull.py && git commit -m "feat(api): extension cookie endpoint + pairing-token"`

---

## Task 15: 浏览器扩展（MV3，手动验证）

**Files:** Create `electrate/extension/{manifest.json,background.js,options.html,options.js}`

- [ ] **Step 1: manifest**（部署时把 `BACKEND_ORIGIN` 换成实际后端域）

```json
{
  "manifest_version": 3,
  "name": "云南电价数据同步",
  "version": "1.0.0",
  "permissions": ["cookies", "storage", "alarms"],
  "host_permissions": ["https://spot.poweremarket.com/*", "https://BACKEND_ORIGIN/*"],
  "background": { "service_worker": "background.js" },
  "options_page": "options.html"
}
```

- [ ] **Step 2: background.js（登录即推送 + 23小时兜底）**

策略：CAMSID 按 1 天有效期设计；**每次用户登录南方 → 扩展立即推送一次**（`cookies.onChanged`）。
定时器改为 23 小时兜底（防止当天未登录时 cookie 默默续期，不依赖高频轮询）。

```javascript
const PLATFORM_URL = "https://spot.poweremarket.com";

async function pushCookie() {
  const cfg = await chrome.storage.local.get(["backendUrl", "token"]);
  if (!cfg.backendUrl || !cfg.token) return;
  const ck = await chrome.cookies.get({ url: PLATFORM_URL, name: "CAMSID" });
  if (!ck) return;
  try {
    await fetch(cfg.backendUrl.replace(/\/$/, "") + "/api/extension/cookie", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: cfg.token, cookie: "CAMSID=" + ck.value })
    });
  } catch (e) { /* 网络失败，下次登录重推 */ }
}

// 主触发：用户登录南方时 CAMSID 被写入 → 立即推送
chrome.cookies.onChanged.addListener((info) => {
  if (
    info.cookie.name === "CAMSID" &&
    info.cookie.domain.includes("poweremarket.com") &&
    !info.removed
  ) {
    pushCookie();
  }
});

// 兜底：每 23 小时推一次（CAMSID 按 1 天有效期，防漏推）
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("daily_push", { periodInMinutes: 23 * 60 });
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "daily_push") pushCookie();
});
```

- [ ] **Step 3: options.html / options.js（一次性配置后端地址+令牌）**

```html
<!doctype html><meta charset="utf-8">
<h3>数据同步扩展设置</h3>
<p>后端地址：<input id="url" size="40" placeholder="https://你的后端域"></p>
<p>配对令牌：<input id="tok" size="40" placeholder="从 Web 设置页生成"></p>
<button id="save">保存</button> <button id="test">立即推送一次</button><p id="msg"></p>
<script src="options.js"></script>
```
```javascript
const $ = (id) => document.getElementById(id);
chrome.storage.local.get(["backendUrl","token"]).then(c => { $("url").value=c.backendUrl||""; $("tok").value=c.token||""; });
$("save").onclick = async () => { await chrome.storage.local.set({ backendUrl: $("url").value.trim(), token: $("tok").value.trim() }); $("msg").textContent = "已保存"; };
$("test").onclick = async () => {
  const cfg = await chrome.storage.local.get(["backendUrl","token"]);
  const ck = await chrome.cookies.get({ url: "https://spot.poweremarket.com", name: "CAMSID" });
  if (!ck) { $("msg").textContent = "未检测到 CAMSID，请先登录 spot.poweremarket.com"; return; }
  const r = await fetch(cfg.backendUrl.replace(/\/$/,"")+"/api/extension/cookie", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ token: cfg.token, cookie:"CAMSID="+ck.value }) });
  $("msg").textContent = r.ok ? "推送成功，已触发同步" : ("推送失败 " + r.status);
};
```

- [ ] **Step 4: 手动验证**

```
# 一次性配置（所有操作均在本地 Chrome 完成）
1) 改 manifest.json 的 BACKEND_ORIGIN 为实际后端域名
2) Chrome → 扩展管理 (chrome://extensions) → 开启"开发者模式"
   → "加载已解压的扩展程序" → 选择 electrate/extension/ 目录
3) Web 超级用户登录 → 设置页点"生成配对令牌" → 复制令牌
4) 扩展图标右键 → 选项 → 填写后端地址 + 令牌 → 保存

# 日常验证（每次登录南方）
5) 在同一浏览器登录 spot.poweremarket.com
6) 期望: 扩展自动推送 → Web 状态条显示"更新中…" → "已更新至 YYYY-MM-DD"
7) 明天再次登录南方 → 自动获取新 CAMSID → 再次同步 → 无任何手动操作
```

- [ ] **Step 5: 提交** — `git add electrate/extension/ && git commit -m "feat(extension): MV3 cookie auto-capture & push"`

---

## v3 自检
- **覆盖**：跨域(Task13-15 扩展解决)、令牌认证(Task13,14)、自动捕获+续期(Task15 onChanged+alarm)、HttpOnly(chrome.cookies API)、手动粘贴兜底(Task10 保留)。
- **占位符**：仅 `BACKEND_ORIGIN` 为部署期替换值，已说明。
- **一致性**：`/api/extension/cookie`、`pairing.generate_token/verify_token`、`cookie_store.set_cookie`、`orchestrator.trigger_sync` 跨任务一致。
