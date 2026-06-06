# 自动数据拉取功能 — 产品 & 技术设计文档 (Spec v2 · 简化版)

**日期**: 2026-06-05 ｜ **状态**: 待审阅 → 任务拆分
**目标**: 把"手动粘贴 cookie → 手动跑脚本拉取日前电价等数据"，改为"**超级用户**登录后自动增量补齐数据；其他客户只读浏览"。

> v2 变更：**取消多用户凭证隔离**。改为**单一超级用户**持有唯一平台 cookie、负责更新数据；其余客户只浏览。认证与凭证大幅简化。

---

# 第一部分 · 产品文档（@产品经理）

## 1. 角色与权限

| 角色 | 能做什么 | 认证 |
|---|---|---|
| **超级用户（运营管理员，唯一）** | 粘贴/更新平台 cookie；触发/手动刷新数据拉取；查看同步状态 | 需登录（账号密码） |
| **普通客户（浏览者）** | 只读浏览电价/预测/图表 | 无需登录（应用内只读） |

唯一一份云南公共数据，全体客户共享浏览；只有超级用户能写入/刷新。

## 2. 关键用户流程

**A. 超级用户更新数据**
1. 超级用户登录 → 系统**自动后台增量补齐**（检查"上次拉到哪天"→拉缺失日期，异步不阻塞）。
2. 顶部状态条显示：更新中… / 已更新至 X 日 / cookie 失效请更新。
3. cookie 失效时 → 去设置页粘贴新 cookie（含"如何从浏览器获取 CAMSID"指引）→ 自动重试。
4. 可点"立即刷新"手动触发。

**B. 普通客户浏览**
- 打开应用即看最新已入库数据；不触发任何拉取；看不到 cookie/同步管理入口。

## 3. 验收标准
- 超级用户登录后无需任何手动脚本，数据自动补齐到最新可得日期。
- cookie 过期有明确提示与重新录入入口；录入后能恢复拉取。
- 天气源（无需 cookie）始终可刷新。
- 普通客户全程只读，无写入/管理能力。
- 拉取过程不阻塞界面；状态可见。

## 4. 范围边界（YAGNI）
不做：多用户/多租户、按用户分库、cron 定时、平台自动登录/验证码、找回密码/SSO。

---

# 第二部分 · 技术文档（@技术架构师）

## 5. 已锁定决策

| 维度 | 决策 |
|---|---|
| 认证 | 半自动 cookie：超级用户提供一次平台 cookie，有效期内自动拉取，过期提醒。 |
| 触发 | 超级用户**登录即触发增量补齐** + 手动"立即刷新"。普通客户浏览不触发。 |
| 数据 | 单一共享 DB（`power_market_v2.db`），全体共享，不分库。 |
| 凭证 | **单一全局 cookie**（超级用户持有），加密存储。 |
| 拉取内容 | `sync_all.py` 全部源 + 天气源（`weather_forecast_fetch.py`）。 |
| 实现 | Flask 后端内置后台线程 + 重构 `sync_all` 为可导入模块 + 同步锁 + 状态表。 |

## 6. 架构总览

```
超级用户登录/刷新 → POST /api/admin/sync → [后台线程] orchestrator ─┬─ sync_engine(全局cookie) → 共享DB
                                  (全局锁 + 新鲜度判断)            └─ weather_sync(无cookie)  → 共享DB
任何人 → GET /api/sync/status ← sync_status 表
超级用户 → POST /api/admin/cookie → cookie_store(加密)
普通客户 → 现有只读 /api/* 数据接口
```

## 7. 组件（单一职责 + 接口）

1. **auth（最小，单超级用户）**：`users(id, username, pwd_hash, role)`，初期仅 1 个 `role=super` 账号（密码哈希，werkzeug）；`POST /api/login`、`/api/logout`、服务端会话；管理接口加 `@require_super` 装饰器。
2. **cookie_store（单值）**：表 `app_config(key, value_enc, status, updated_at)`，键 `platform_cookie`；接口 `set_cookie(c)`/`get_cookie()`/`mark_invalid()`；对称加密(Fernet)，密钥来自环境变量 `DATA_PULL_KEY`（不入仓）；日志脱敏。
3. **sync_engine（重构 `sync_all.py`）**：`sync_incremental(cookie, conn, lookback_days=K) -> SyncReport`；用 `tables=[(table,date_col,label)]` 求每源最新日期→拉 `[最新-(K-1)..今天]`；检测 cookie 失效（跳登录/401/302/空）抛 `AuthExpired`；返回每源 `{rows_added,date_range,status,error?}`。
4. **weather_sync**：包 `weather_forecast_fetch` live，无 cookie，始终可刷，带 `publish_date` 入库。
5. **sync_orchestrator**：`trigger_sync()`：抢**全局内存锁**（已在跑→返回状态）→新鲜度判断（已最新则跳市场）→取全局 cookie→后台线程跑 engine+weather→`AuthExpired` 则 `mark_invalid`→写 `sync_status`/`sync_runs`。
6. **endpoints**：`POST /api/login`（超级用户登录→异步 `trigger_sync`）、`POST /api/admin/cookie`（@super，粘贴 cookie，可立即触发）、`POST /api/admin/sync`（@super，手动刷新）、`GET /api/sync/status`（公开）。
7. **前端**：超级用户登录页；设置页 cookie 录入+有效性指示+CAMSID 获取指引+"立即刷新"按钮；顶部同步状态条；普通客户视图隐藏管理入口。

## 8. 数据流
超级用户登录 → `/api/login`（验证、会话）→ `trigger_sync()`[后台] → 锁→新鲜度→取 cookie → `sync_engine` 拉缺失（写共享 DB）+ `weather_sync` → 写状态 → 释放锁。前端轮询 `/api/sync/status`。cookie 失效 → UI 提示 → 设置页录入 → 重触发。

## 9. 错误处理
- cookie 失效 → `AuthExpired` → 标记无效、状态 `cookie_invalid`、UI 提示重录；天气仍拉。
- 并发 → 全局锁，第二者返回 `in_progress`。
- 分源失败 → 记录并继续（部分成功）。
- 重启中断 → 锁随重启释放；`sync_runs` 标记未完成；下次触发幂等（`INSERT OR REPLACE`+增量）。
- 限流/网络 → 复用 `sync_all` 随机延时 + 重试。

## 10. 安全
cookie 加密存储（密钥环境变量，不入仓）；密码哈希；日志不打印 cookie；管理接口 `@require_super`；SQLite 单写由同步锁串行化。

## 11. 测试
- 单元：cookie 加解密往返；增量区间计算（mock 最新日→缺失区间）；`AuthExpired` 检测；新鲜度判断；锁防并发；`@require_super` 拦截。
- 集成：engine 对临时 DB（打桩 `api_post`）→入库；失效路径→标记无效；普通客户访问管理接口被拒。
- 手动：超级用户登录→自动增量；过期→录入恢复；普通客户只读。

## 12. 受影响 / 新增文件（预估）
- 重构 `power-data/sync_all.py` → 可导入 `sync_incremental` + 去硬编码 cookie。
- 新增 `power-data/sync_service.py`（cookie_store + orchestrator + 锁 + 状态）。
- 改 `electrate/api_server.py`（login / admin cookie / admin sync / sync status + 登录触发 + `@require_super`）。
- 前端：登录页、设置页（cookie 录入 + 刷新）、状态条、管理入口权限控制（`electrate/` TSX）。
- DB 新增表：`users`、`app_config`、`sync_status`、`sync_runs`。

---

# 第三部分 · v3 增量：云端 + 浏览器扩展自动捕获 cookie

> **架构评审已确认决策（2026-06-05）**
> - ✅ **服务器**：已有 Linux 云端服务器，Flask + SQLite 部署。
> - ✅ **CAMSID 有效期**：按 1 天保守估计。策略：**每次登录南方均获取一次、触发一次同步**（不依赖 cookie 续期；每日登录即每日同步，无需定时任务）。
> - ✅ **扩展分发**：Chrome 开发者模式加载未打包扩展（MVP 最快，无需上架商店）。
> - ✅ **多运营员工**：单一全局 cookie OK，最后推送的 CAMSID 生效。

**部署形态**: 云端 Linux 服务器，运营用本机 Chrome 浏览器。
**cookie 获取（主）**: 浏览器扩展每次登录南方自动推送；**手动粘贴保留为兜底**。

## 13. 为什么需要扩展
云端服务受浏览器跨域隔离，读不到 `spot.poweremarket.com` 的 cookie（CAMSID 为 HttpOnly，页面 JS 无法读取）。唯一稳妥方案 = 浏览器扩展（`chrome.cookies` API 可读 HttpOnly）。

## 14. CAMSID 获取策略
- **有效期假设**：1 天（未实测，保守值）。
- **触发时机**：`cookies.onChanged` 监听到 CAMSID 被写入（即用户登录南方时）立即推送——**不等过期，不依赖定时轮询**。
- **效果**：运营每天登录一次南方 → 扩展自动推送一次 → 后端拉取当天数据 → 无需任何手动操作。
- **多运营员工**：多人均装扩展，各自登录南方时均会推送，最后推送的 CAMSID 生效，数据始终保持最新。

## 15. 新增组件
- **pairing_token**：超级用户在设置页生成配对令牌，加密存 `app_config(key='pairing_token')`，供扩展认证（与浏览器 session 隔离，故用令牌）。可重置。
- **`POST /api/extension/cookie`（令牌认证）**：`{token, cookie}` → 校验令牌 → `cookie_store.set_cookie` → `trigger_sync`。只接受 CAMSID。
- **`POST /api/admin/pairing-token`（@super）**：生成并返回配对令牌（明文仅在生成时返回一次）。
- **Chrome 扩展（MV3，开发者模式加载）**：
  - `host_permissions`：`spot.poweremarket.com` + 后端域
  - `permissions`：`cookies`、`storage`、`alarms`
  - `background.js`：监听 `cookies.onChanged` → CAMSID 写入时立即推送
  - `options.html/js`：填写后端地址 + 配对令牌（一次性配置）
  - **安装方式**：Chrome → 扩展管理 → 开发者模式 → 加载已解压扩展

## 16. 完整流程（一次配置，每日免手动）

```
【一次性配置】
1. 服务器设置环境变量 DATA_PULL_KEY + FLASK_SECRET
2. 运行 python -m data_pull.init_super admin <密码>
3. 超级用户登录 Web → 设置页点"生成配对令牌" → 复制令牌
4. Chrome → 扩展管理 → 开发者模式 → 加载 electrate/extension/
5. 扩展 options 页填写后端地址 + 令牌 → 保存

【日常自动运行（零操作）】
运营登录 spot.poweremarket.com
    ↓ 扩展 cookies.onChanged 嗅到 CAMSID
    ↓ POST /api/extension/cookie {token, cookie}
    ↓ 后端校验令牌 → 加密存储
    ↓ trigger_sync() 后台线程
    ↓ sync_engine 拉昨日至今缺失数据
    ↓ weather_sync 拉次日天气预报
    ↓ 状态条"已更新至 YYYY-MM-DD"
```

## 17. 架构图

```
运营的 Chrome 浏览器
  ├── spot.poweremarket.com (登录南方，产生 CAMSID)
  └── electrate Web App
        └── 状态条 [轮询 /api/sync/status]

Chrome 扩展 (MV3, 开发者模式)
  └── cookies.onChanged(CAMSID)
        └── POST /api/extension/cookie + pairing_token
                        │
                        ▼ HTTPS
云端服务器 (Linux)
  ├── Flask api_server.py
  │     ├── /api/extension/cookie  ← 令牌校验
  │     ├── /api/login             ← @require_super, 触发同步
  │     ├── /api/admin/*           ← @require_super
  │     ├── /api/sync/status       ← 公开
  │     └── /api/price/*           ← 公开只读
  │
  ├── sync_orchestrator (后台线程, 全局锁)
  │     ├── sync_engine(cookie)    ← sync_all.SOURCES
  │     │     日前/实时/负荷/新能源/水电...
  │     └── weather_sync()         ← Open-Meteo (免费,无cookie)
  │
  └── power_market_v2.db (SQLite, 共享)
        ├── 电价/负荷/新能源/水电/天气 (客户只读)
        └── users / app_config / sync_status / sync_runs (管理)
```

## 18. 安全
令牌加密存储，可随时重置；`/api/extension/cookie` 只接受 CAMSID 名称；
合规：扩展读取运营本人会话、推送至自有服务，无账号密码存储，ToS 风险低。
