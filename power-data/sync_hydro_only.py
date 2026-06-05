#!/usr/bin/env python3
"""
仅同步水电出力96点数据 (hourly_hydro)
调用 mkWaterElecTicTotalOutput/getObject API
补数据范围: 20260323 ~ 20260605
反爬: 每次调用后随机延迟0.5~2秒, 每21天后休息60秒
"""
import sys, json, os, time, random
from datetime import datetime, timedelta
import urllib.request
import sqlite3
import warnings
warnings.filterwarnings('ignore')

COOKIE = "CAMSID=B4B9D828DE104B41CAFD30F1A53B4099"
BASE_URL = "https://spot.poweremarket.com/uptspot/ma/spot/spottrade/scptp/sr/mp/spottrade"
DB_PATH = os.path.join(os.path.dirname(__file__), "power_market_v2.db")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
]
ACCEPT_LANGS = ["zh-CN,zh;q=0.9", "zh-CN,zh;q=0.8,en;q=0.6", "zh-CN,zh;q=0.9,en;q=0.7"]

def anti_block_delay():
    time.sleep(random.uniform(0.5, 2.0))

def random_headers():
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": COOKIE,
        "Origin": "https://spot.poweremarket.com",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": random.choice(ACCEPT_LANGS),
    }

def api_post(endpoint, body, timeout=15):
    url = f"{BASE_URL}/{endpoint}"
    data = json.dumps(body).encode("utf-8")
    headers = random_headers()
    req = urllib.request.Request(url, method="POST", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def insert_hydro_actual(conn, date_str, records):
    """水电出力96点 → hourly_hydro"""
    if not records:
        return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for r in records:
        t_energy = r.get("tEnergy", 0)
        if t_energy == "" or t_energy is None:
            continue
        cur.execute("""
            INSERT OR REPLACE INTO hourly_hydro (date_key, period, output, region)
            VALUES (?, ?, ?, ?)
        """, (date_key, r.get("time", ""), float(t_energy), "云南"))
        count += 1
    conn.commit()
    return count

def sync_hydro_date(conn, date_str):
    """同步单日水电出力96点数据"""
    date_key = date_str.replace("-", "")
    resp = api_post("mkWaterElecTicTotalOutput/getObject", {
        "runTime": date_key,
        "areaNo": "04"
    })
    if "error" in resp:
        print(f"  ❌ {date_key}: {resp['error']}")
        return 0
    count = insert_hydro_actual(conn, date_str, resp.get("data", {}).get("data", []))
    status = "✅" if count > 0 else "⚠️"
    print(f"  {status} {date_key}: 入库{count}条")
    return count

def main():
    # 日期范围: 2026-03-23 ~ 2026-06-05
    start_date = datetime(2026, 3, 23)
    end_date = datetime(2026, 6, 5)
    total_days = (end_date - start_date).days + 1
    batch_size = 21

    print(f"{'='*60}")
    print(f"水电出力96点数据同步")
    print(f"范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} ({total_days}天)")
    print(f"每{ batch_size }天一批, 批间休息60秒")
    print(f"{'='*60}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    current = start_date
    batch_no = 1
    days_in_batch = 0
    total_ok = 0
    total_fail = 0

    while current <= end_date:
        ds = current.strftime("%Y-%m-%d")
        count = sync_hydro_date(conn, ds)
        if count > 0:
            total_ok += 1
        else:
            total_fail += 1
        current += timedelta(days=1)
        days_in_batch += 1

        # 反爬延迟 (每次API调用后)
        anti_block_delay()

        # 每批结束后休息60秒
        if days_in_batch >= batch_size and current <= end_date:
            print(f"\n⏸️  完成第{batch_no}批 ({days_in_batch}天), 休息60秒防封...")
            time.sleep(60)
            batch_no += 1
            days_in_batch = 0

    conn.close()

    print(f"\n{'='*60}")
    print(f"✅ 同步完成! 成功:{total_ok}天, 失败:{total_fail}天")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
