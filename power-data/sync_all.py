#!/usr/bin/env python3
"""
电力数据同步脚本 v2 - API下载 → 自动入库
"""
import sys, json, os, time
from datetime import datetime, timedelta
import urllib.request
import sqlite3
import warnings
warnings.filterwarnings('ignore')

BASE_URL = "https://spot.poweremarket.com/uptspot/ma/spot/spottrade/scptp/sr/mp/spottrade"
DB_PATH = os.path.join(os.path.dirname(__file__), "power_market_v2.db")

# ---- 反爬措施 ----
import random
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
]
ACCEPT_LANGS = ["zh-CN,zh;q=0.9", "zh-CN,zh;q=0.8,en;q=0.6", "zh-CN,zh;q=0.9,en;q=0.7"]

def anti_block_delay():
    """随机延迟 0.5~2.0秒"""
    time.sleep(random.uniform(0.5, 2.0))

def random_headers(cookie):
    """随机化请求头"""
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": cookie,
        "Origin": "https://spot.poweremarket.com",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": random.choice(ACCEPT_LANGS),
    }

def api_post(endpoint, body, cookie, timeout=15):
    url = f"{BASE_URL}/{endpoint}"
    data = json.dumps(body).encode("utf-8")
    headers = random_headers(cookie)
    req = urllib.request.Request(url, method="POST", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

# ---- DB 操作 ----
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def insert_day_ahead_price(conn, trade_date, records):
    """日前电价(全省均价) → day_ahead_node_price_96"""
    if not records: return 0
    cur = conn.cursor()
    # 从 records[0] 的 userRecentlyPrice 字段获取96点电价
    count = 0
    for rec in records:
        price_str = rec.get("userRecentlyPrice", "")
        if not price_str: continue
        try:
            prices = json.loads(price_str) if isinstance(price_str, str) else price_str
        except:
            continue
        # 使用 __avg__ 作为 node_name
        date_dash = rec.get("operatingDate", trade_date)
        for period, price in prices.items():
            cur.execute("""
                INSERT OR REPLACE INTO day_ahead_node_price_96
                (trade_date, region, node_name, period, price)
                VALUES (?, ?, ?, ?, ?)
            """, (date_dash, "云南", "__avg__", period, float(price)))
            count += 1
    conn.commit()
    return count

def insert_load(conn, date_str, records):
    """统调负荷 96点 → hourly_load"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    for r in records:
        time_val = r.get("time", "")
        energy = r.get("energy", 0)
        hour = int(time_val[:2]) if ":" in time_val else 0
        date_key = date_str.replace("-", "")
        cur.execute("""
            INSERT OR REPLACE INTO hourly_load (date_key, period, load, region)
            VALUES (?, ?, ?, ?)
        """, (date_key, time_val, float(energy), "云南"))
        count += 1
    conn.commit()
    return count

def insert_gen_total(conn, date_str, records):
    """发电总出力 → hourly_generation + generation_forecast"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for r in records:
        time_val = r.get("time", "")
        t_energy = r.get("tEnergy", 0)
        y_energy = r.get("yEnergy", 0)
        # 存到 hourly_generation
        cur.execute("""
            INSERT OR REPLACE INTO hourly_generation (date_key, period, output, region)
            VALUES (?, ?, ?, ?)
        """, (date_key, time_val, float(t_energy), "南网"))
        count += 1
    conn.commit()
    return count

def insert_nonmarket(conn, date_str, records):
    """非市场出力 → hourly_nonmarket"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for r in records:
        cur.execute("""
            INSERT OR REPLACE INTO hourly_nonmarket (date_key, period, output, region)
            VALUES (?, ?, ?, ?)
        """, (date_key, r.get("time",""), float(r.get("energy",0)), r.get("exchange","云南")))
        count += 1
    conn.commit()
    return count

def insert_nonmarket_no_renew(conn, date_str, records):
    """非市场不含新能源"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for r in records:
        cur.execute("""
            INSERT OR REPLACE INTO hourly_nonmarket (date_key, period, output, region)
            VALUES (?, ?, ?, ?)
        """, (date_key, r.get("time",""), float(r.get("tEnergy",0)), "云南(不含新能源)"))
        count += 1
    conn.commit()
    return count

def insert_renewable(conn, date_str, records):
    """新能源出力(7类) → hourly_renewable (energy01 = 总出力)"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for r in records:
        energy01 = float(r.get("energy01", 0))
        cur.execute("""
            INSERT OR REPLACE INTO hourly_renewable (date_key, period, output, region)
            VALUES (?, ?, ?, ?)
        """, (date_key, r.get("time",""), energy01, "云南"))
        count += 1
    conn.commit()
    return count

def insert_hydro(conn, date_str, records):
    """水电预测 → hourly_hydro"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    for r in records:
        if r.get("areaName") != "云南": continue
        run_time = r.get("runTime", date_str.replace("-",""))
        output = float(r.get("output", 0))
        # hourly_hydro 需要96点，这里只有日均值
        # 暂时存到 hydro_forecast
        date_fmt = f"{run_time[:4]}-{run_time[4:6]}-{run_time[6:8]}"
        cur.execute("""
            INSERT OR REPLACE INTO hydro_forecast
            (publish_date, forecast_date, region, avg_output_mw)
            VALUES (?, ?, ?, ?)
        """, (run_time, run_time, "云南", output))
        count += 1
    conn.commit()
    return count

def insert_hydro_actual(conn, date_str, records):
    """水电出力96点 → hourly_hydro (mkWaterElecTicTotalOutput)"""
    if not records: return 0
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
        """, (date_key, r.get("time",""), float(t_energy), "云南"))
        count += 1
    conn.commit()
    return count

def insert_real_result(conn, date_str, records):
    if not records: return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for rec in records:
        if not isinstance(rec, dict): continue
        info_list = rec.get("infoList") or []
        for info in info_list:
            if not isinstance(info, dict): continue
            time_val = info.get("time", "")
            price = info.get("settlementPrice", 0)
            if time_val and price:
                hour = int(time_val[:2]) if ":" in time_val else 0
                try:
                    cur.execute("""
                        INSERT OR REPLACE INTO realtime_hourly_price
                        (date_key, hour, period, rt_price)
                        VALUES (?, ?, ?, ?)
                    """, (date_key, hour, time_val, float(price)))
                    count += 1
                except:
                    pass
    conn.commit()
    return count

def insert_load2(conn, date_str, records):
    """负荷(实际) → hourly_load (补充)"""
    if not records: return 0
    cur = conn.cursor()
    count = 0
    date_key = date_str.replace("-", "")
    for r in records:
        # 提取 activepowerXXXX 字段
        for k, v in r.items():
            if k.startswith("activepower") and isinstance(v, (int,float)):
                time_str = k[11:13] + ":" + k[13:15]  # activepower0030 → 00:30
                cur.execute("""
                    INSERT OR REPLACE INTO hourly_load (date_key, period, load, region)
                    VALUES (?, ?, ?, ?)
                """, (date_key, time_str, float(v), r.get("areaName","云南")))
                count += 1
    conn.commit()
    return count

# ---- SOURCES: 可导出的数据源列表 ----
# 每个条目: label, table, date_col, fetch(cookie, date_str)->dict, insert(conn, date_str, resp)->int
SOURCES = [
    {
        "label": "日前电价(全省)",
        "table": "day_ahead_node_price_96",
        "date_col": "trade_date",
        "fetch": lambda cookie, d: api_post("tdSpotRecentlyResultUserInfo/getList", {"operatingDate": d}, cookie),
        "insert": lambda conn, d, r: insert_day_ahead_price(conn, d, r.get("data", {}).get("data", r.get("data", []))),
    },
    {
        "label": "统调负荷",
        "table": "hourly_load",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("intePublishDayAutotuneCurve/getObj", {"exchange": "04", "runTime": d.replace("-", "")}, cookie),
        "insert": lambda conn, d, r: insert_load(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "发电总出力",
        "table": "hourly_generation",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("mkGenElecTotalPrediction/getObject", {"runTime": d.replace("-", "")}, cookie),
        "insert": lambda conn, d, r: insert_gen_total(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "非市场出力",
        "table": "hourly_nonmarket",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("intePublishNonmarketUnitCurve/getList", {"exchange": "04", "runTime": d.replace("-", "")}, cookie),
        "insert": lambda conn, d, r: insert_nonmarket(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "非市场不含新能源",
        "table": "hourly_nonmarket",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("mkXhNonMarketEleNewPowerPre/getList", {"runTime": d.replace("-", ""), "areaCode": "04"}, cookie),
        "insert": lambda conn, d, r: insert_nonmarket_no_renew(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "新能源出力",
        "table": "hourly_renewable",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("intePublishNewEnergyDay/getList", {"runTime": d.replace("-", ""), "exchange": "04", "dayType": "2", "dataType": "1"}, cookie),
        "insert": lambda conn, d, r: insert_renewable(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "水电预测",
        "table": "hydro_forecast",
        "date_col": "publish_date",
        "fetch": lambda cookie, d: api_post("mkWaterPowerWeekPredOutput/getListPage", {"pageNum": 1, "pageSize": 50, "runTime": d.replace("-", ""), "areaName": "云南"}, cookie),
        "insert": lambda conn, d, r: insert_hydro(conn, d, r.get("data", {}).get("data", {}).get("list", [])),
    },
    {
        "label": "水电出力96点",
        "table": "hourly_hydro",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("mkWaterElecTicTotalOutput/getObject", {"runTime": d.replace("-", ""), "areaNo": "04"}, cookie),
        "insert": lambda conn, d, r: insert_hydro_actual(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "实时+出力",
        "table": "realtime_hourly_price",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("tdSpotRealResultNodeInfo/getList", {"operatingDate": d}, cookie),
        "insert": lambda conn, d, r: insert_real_result(conn, d, r.get("data", {}).get("data", [])),
    },
    {
        "label": "负荷(实际)",
        "table": "hourly_load",
        "date_col": "date_key",
        "fetch": lambda cookie, d: api_post("intePublishVolumeUpCurve/getListPage", {"exchange": "04", "runTime": d.replace("-", "")}, cookie),
        "insert": lambda conn, d, r: insert_load2(conn, d, r.get("data", {}).get("data", {}).get("list", [])),
    },
]

# ---- 旧版 APIS 列表（兼容 sync_date 内部使用）----
def _build_apis(cookie):
    return [
        (s["label"],
         lambda d, s=s: s["fetch"](cookie, d),
         lambda c, d, r, s=s: s["insert"](c, d, r))
        for s in SOURCES
    ]

def sync_date(conn, date_str, cookie):
    print(f"\n📅 {date_str}")
    day_result = {}
    for name, api_fn, insert_fn in _build_apis(cookie):
        try:
            resp = api_fn(date_str)
            if "error" in resp:
                print(f"  ❌ {name}: {resp['error']}")
                day_result[name] = 0
            else:
                count = insert_fn(conn, date_str, resp)
                status = "✅" if count > 0 else "⚠️"
                print(f"  {status} {name}: 入库{count}条")
                day_result[name] = count
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            day_result[name] = 0
        anti_block_delay()  # 反爬：每次API调用后随机延迟
    return day_result

def sync_range(start_date, end_date, cookie, batch_size=21):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    conn = get_conn()
    all_results = {}
    total_days = (end - start).days + 1
    batch_count = (total_days + batch_size - 1) // batch_size

    print(f"{'='*50}")
    print(f"同步数据: {start_date} ~ {end_date} ({total_days}天, {batch_count}批)")
    print(f"单批最大: {batch_size}天, 每批间隔: 60秒")
    print(f"{'='*50}")

    current = start
    batch_no = 1
    days_in_batch = 0

    while current <= end:
        ds = current.strftime("%Y-%m-%d")
        all_results[ds] = sync_date(conn, ds, cookie)
        current += timedelta(days=1)
        days_in_batch += 1

        # 每批结束后休息60秒
        if days_in_batch >= batch_size and current <= end:
            print(f"\n⏸️  完成第{batch_no}批 ({days_in_batch}天)，休息60秒防封...")
            time.sleep(60)
            batch_no += 1
            days_in_batch = 0

    conn.close()

    # 汇总
    print(f"\n{'='*50}")
    print("📊 汇总")
    print(f"{'='*50}")
    total_inserted = sum(sum(v.values()) for v in all_results.values())
    api_totals = {}
    for dr in all_results.values():
        for api, cnt in dr.items():
            api_totals[api] = api_totals.get(api, 0) + cnt
    for api, cnt in sorted(api_totals.items()):
        print(f"  {api:20s} 共入库 {cnt:>6,} 条")

def gap_analysis():
    """分析数据缺口"""
    conn = get_conn()
    today = datetime.now().strftime("%Y%m%d")

    print(f"\n{'='*50}")
    print("📊 数据缺口分析")
    print(f"{'='*50}")

    tables = [
        ('day_ahead_node_price_96', 'trade_date', '日前电价'),
        ('hourly_load', 'date_key', '统调负荷'),
        ('hourly_renewable', 'date_key', '新能源出力'),
        ('hourly_generation', 'date_key', '发电总出力'),
        ('hourly_hydro', 'date_key', '水电出力'),
        ('hourly_nonmarket', 'date_key', '非市场出力'),
        ('realtime_hourly_price', 'date_key', '实时电价'),
        ('load_forecast', 'trade_date', '负荷预测'),
        ('renewable_forecast', 'forecast_date', '新能源预测'),
        ('weather_correction', 'date', '天气修正'),
    ]

    for tbl, dc, label in tables:
        latest = conn.execute(f"SELECT MAX({dc}) FROM {tbl}").fetchone()[0]
        days = conn.execute(f"SELECT COUNT(DISTINCT {dc}) FROM {tbl}").fetchone()[0]
        total = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

        if latest:
            if 'trade' in dc:
                latest_num = int(latest.replace('-', '')) if '-' in latest else int(latest)
                today_num = int(today)
                gap_days = max(0, today_num - latest_num)
            else:
                try:
                    today_num = int(today)
                    latest_num = int(latest)
                    gap_days = max(0, today_num - latest_num)
                except:
                    gap_days = "?"
        if gap_days == "?":
            status = "❓"
        else:
            status = "✅" if gap_days == 0 else ("🟡" if gap_days < 10 else "🔴")
        print(f"  {status}  {label:12s}  ~{latest}  {days:>3d}天  {total:>8,}行  " +
              (f"缺口{gap_days}天" if isinstance(gap_days, int) else "状态未知"))

    conn.close()

if __name__ == "__main__":
    cookie = os.environ.get("PLATFORM_COOKIE", "")
    if len(sys.argv) > 2:
        sync_range(sys.argv[1], sys.argv[2], cookie)
    elif len(sys.argv) == 2 and sys.argv[1] == "gap":
        gap_analysis()
    else:
        # 默认分析缺口
        gap_analysis()
        print("\n要同步所有数据，运行：")
        print("  PLATFORM_COOKIE='CAMSID=...' python3 sync_all.py 2026-03-22 2026-06-05")
