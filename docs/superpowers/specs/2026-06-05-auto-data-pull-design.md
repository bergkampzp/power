# 自动数据拉取功能 — 设计文档 (Spec)

**日期**: 2026-06-05 ｜ **状态**: 待用户审阅
**目标**: 把当前"手动粘贴 cookie → 手动跑脚本拉取日前电价等数据"的流程，改为"用户登录 electrate 后自动增量补齐必要数据"。

---

## 1. 已锁定的决策（来自 brainstorm）

| 维度 | 决策 |
|---|---|
| 认证模型 | **半自动 cookie**：用户提供一次平台会话 cookie(CAMSID)，系统在有效期内自动拉取，过期提醒重新提供。不做平台自动登录/验证码。 |
| 触发时机 | **登录即触发（增量补齐）**：用户登录 electrate 时后台异步检查"上次拉到哪天"并补齐缺失日期。不做 cron。 |
| 数据范围 | **共享同一份云南数据**：每个云南客户数据相同 → 单一共享 DB（`power_market_v2.db`），不按用户分库。 |
| 凭证范围 | **每用户独立 cookie**：每个用户带自己的平台账号 cookie（凭证隔离），但拉回的是同一份公共数据写入共享 DB；任一有效 cookie 即可刷新，互为兜底。 |
| 拉取内容 | `sync_all.py` 覆盖的全部源（日前电价/实时/统调负荷/负荷预测/非市场/新能源出力+预测/水电出力+预测/发电总出力 等）+ 天气源(`weather_forecast_fetch.py`)。 |
| 实现方式 | **A：Flask 后端内置后台线程** + 重构 `sync_all.py` 为可导入模块 + 同步锁 + 状态表。 |
| 鉴权范围 | **本功能内做最小用户名密码登录**（小而有界、接口可替换）。*[默认决策，待用户确认]* |

---

## 2. 架构总览

```
登录 → POST /api/login → [后台线程] sync_orchestrator ──┬─ sync_engine(用户cookie) → 共享DB
                              (全局锁 + 新鲜度判断)      └─ weather_sync(无cookie)   → 共享DB
前端轮询 GET /api/sync/status ← sync_status 表
设置页 POST /api/credentials/cookie → credential_store(加密)
```

新增/改动集中在 `electrate/` 后端 + `power-data/` 的脚本重构；共享 DB 增加几张小表。

---

## 3. 组件（单一职责 + 接口）

1. **auth**（新，最小）：`users(id, username, pwd_hash, created_at)`；`POST /api/login` / `POST /api/logout`；服务端会话。密码哈希（werkzeug）。仅为获得 `user_id`，刻意保持最小、可替换。
2. **credential_store**：表 `user_credentials(user_id, cookie_enc, status, updated_at)`；接口 `set_cookie(user_id, cookie)` / `get_cookie(user_id)` / `mark_invalid(user_id)` / `latest_valid_cookie()`。cookie 用对称加密(Fernet)存储，密钥来自环境变量 `DATA_PULL_KEY`，**不入库不入仓**；日志不打印 cookie 值。
3. **sync_engine**（重构 `sync_all.py`）：`sync_incremental(cookie, conn, sources=ALL, lookback_days=K) -> SyncReport`。
   - 用 `sync_all` 的 `tables=[(table, date_col, label)]` 清单，对每源求库内最新日期 → 拉取 `[最新-(K-1) .. 今天]`（回拉 K 天容纳修订）。
   - 检测 cookie 失效（响应跳登录页 / HTTP 401/302 / data 为空且无电价）→ 抛 `AuthExpired`。
   - 返回报告：每源 `{rows_added, date_range, status, error?}`。
4. **weather_sync**（包 `weather_forecast_fetch`）：`sync_weather_incremental(conn)`；调 Open-Meteo forecast(live)，无 cookie，始终可刷；带 `publish_date` 入库（gate-legal）。
5. **sync_orchestrator**：`trigger_sync(user_id)`：
   - 抢**全局内存锁**（仅允许一个同步在跑）；已在跑 → 返回当前状态。
   - **新鲜度判断**：若市场数据已到期望最新（如日前已到次日）→ 跳过市场拉取。
   - 取该用户 cookie；无/失效 → 记录"需 cookie"，仍执行 weather_sync。
   - 后台线程跑 engine + weather；`AuthExpired` → `mark_invalid` + 状态置 `cookie_invalid`。
   - 写 `sync_status`（汇总）与 `sync_runs`（逐次日志）。
6. **endpoints**：
   - `POST /api/login`：验证 → 建会话 → **异步** `trigger_sync(user)` → 返回"同步已启动"。
   - `POST /api/credentials/cookie`：保存该用户 cookie（设置页粘贴）→ 可选立即触发。
   - `GET /api/sync/status`：返回 `{in_progress, last_run, per_source_latest, cookie_valid, errors}`。
7. **前端**：登录页（复用 `UserCenter` 壳）；设置页 cookie 粘贴框 + 有效性指示 + "如何从浏览器获取 CAMSID"指引；顶部同步状态条（更新中 / 已更新至 X / cookie 失效请更新）。

---

## 4. 数据流

登录 → `/api/login`（验证、建会话）→ `orchestrator.trigger_sync(user)`[后台] → 抢锁 → 新鲜度判断 → 取 cookie → `sync_engine` 拉缺失（市场，写共享 DB）+ `weather_sync` → 更新 `sync_status`/`sync_runs` → 释放锁。前端轮询 `/api/sync/status` 显示进度/结果。cookie 失效 → UI 提示去设置页粘贴新 cookie → `/api/credentials/cookie` → 重新触发。

---

## 5. 错误处理

- **cookie 失效** → `AuthExpired` → 标记无效、状态 `cookie_invalid`、UI 提示该用户重粘贴；天气仍拉取；其他用户有效 cookie 仍能刷。
- **并发触发** → 全局锁；第二者返回 `in_progress`。
- **分源失败** → 该源记录错误，其余继续（部分成功）。
- **重启中断** → 内存锁随重启释放；`sync_runs` 标记未完成；下次登录重新触发（`INSERT OR REPLACE` + 增量，幂等）。
- **限流/网络** → 复用 `sync_all` 随机延时 + 增加重试。
- **无有效 cookie 且数据陈旧** → 不刷新；UI 显示"数据截至 X，需有效 cookie 更新"。

---

## 6. 安全

- cookie 对称加密存储（密钥来自环境变量，不入仓）；日志脱敏不打印 cookie。
- 密码哈希存储。
- SQLite 单写：同步锁同时充当写串行化。

---

## 7. 范围边界（YAGNI）

- 不做 cron（仅登录触发）。
- 不做按用户分库（数据共享）。
- 不做平台自动登录/验证码。
- 鉴权只做最小用户名密码（不做 OAuth/SSO/找回密码等）。
- 复用现有脚本，重构最小化（`sync_all` → 可导入；`weather_forecast_fetch` 已可用）。

---

## 8. 测试

- **单元**：cookie 加解密往返；增量区间计算（给定各表最新日 → 预期缺失区间）；`AuthExpired` 检测（mock 响应）；新鲜度判断；锁防并发。
- **集成**：`sync_engine` 对临时 DB（打桩 `api_post`）→ 入库；失效路径 → 标记无效；编排器并发 → 第二者得 `in_progress`。
- **手动**：真实登录 + 粘贴 cookie → 观察增量拉取与状态条。

---

## 9. 受影响 / 新增文件（预估）

- 重构：`power-data/sync_all.py` → 抽出可导入的 `sync_incremental` + 抽离硬编码 cookie。
- 新增：`power-data/sync_service.py`（credential_store + orchestrator + 锁/状态），或置于 `electrate/` 后端。
- 改动：`electrate/api_server.py`（login / credentials / sync status 路由 + 登录触发）。
- 前端：登录页、设置页 cookie 录入、状态条（`electrate/` TSX）。
- DB：新增表 `users` / `user_credentials` / `sync_status` / `sync_runs`。
