#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
次日数值天气预报抓取器 (leakage-safe, 带发布时间)
=================================================
把天气从"事后实况修正"升级为"次日预测特征"。数据源 Open-Meteo (免费, 无key):
  - live     : api.open-meteo.com/v1/forecast (forecast_days=2) → 取"今天发布、覆盖明天"
  - backfill : historical-forecast-api.open-meteo.com → 取过去"当时的预报" (回测用)

关键: 入库带 publish_date(发布日) 与 forecast_date(目标日), 保证 publish_date < forecast_date,
即 DA[D+1] 报价闸口前真实可得 → 无泄漏。变量含辐照水平 GHI(shortwave_radiation) +
direct/diffuse + 轮毂高度风速 wind_speed_100m。按 16 地州装机权重可聚合到全省。

用法:
  python weather_forecast_fetch.py live
  python weather_forecast_fetch.py backfill 2026-02-01 2026-02-28
  python weather_forecast_fetch.py agg 20260210      # 查看某目标日全省加权驱动预报
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import sqlite3
import datetime as dt
import requests
from config import DB

# 16 地州: 经纬度 + 光伏/风电装机权重(MW, 用于全省加权聚合)
CITIES = {
    "曲靖": (25.49, 103.80, 850, 320), "红河": (23.36, 103.38, 680, 210),
    "楚雄": (25.03, 101.53, 520, 140), "大理": (25.59, 100.27, 480, 260),
    "昆明": (25.04, 102.71, 310, 139), "昭通": (27.34, 103.72, 58, 25),
    "保山": (25.12, 99.17, 42, 18), "文山": (23.39, 104.24, 42, 17),
    "普洱": (22.79, 100.97, 35, 12), "丽江": (26.88, 100.23, 28, 22),
    "临沧": (23.89, 100.09, 28, 9), "玉溪": (24.35, 102.55, 18, 6),
    "德宏": (24.43, 98.59, 20, 8), "西双版纳": (22.01, 100.80, 12, 4),
    "怒江": (25.82, 98.86, 15, 12), "迪庆": (27.83, 99.70, 8, 18),
}
HOURLY = ("shortwave_radiation,direct_radiation,diffuse_radiation,"
          "temperature_2m,cloud_cover,precipitation,wind_speed_10m,wind_speed_100m")
_VARS = ['shortwave_radiation', 'direct_radiation', 'diffuse_radiation',
         'temperature_2m', 'cloud_cover', 'precipitation', 'wind_speed_10m', 'wind_speed_100m']


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_forecast (
            city TEXT, publish_date TEXT, forecast_date TEXT, hour INTEGER,
            ghi REAL, direct REAL, diffuse REAL, temp REAL, cloud REAL,
            precip REAL, wind10 REAL, wind100 REAL, source TEXT, created_at TEXT,
            PRIMARY KEY (city, publish_date, forecast_date, hour)
        )""")
    conn.commit()


def _rows_from_hourly(city, h, source, publish_mode):
    """把 Open-Meteo hourly 响应转成入库行。publish_mode: 'today' | 'prev_day'。"""
    t = h['time']
    today = dt.date.today().isoformat()
    out = []
    for i, ts in enumerate(t):
        fdate, hh = ts[:10], int(ts[11:13])
        if publish_mode == 'today':          # live: 发布日=今天, 只留次日及以后
            pub = today
            if fdate <= today:
                continue
        else:                                # backfill: 假定 D-1 发布(短预见期, 闸口可得)
            pub = (dt.date.fromisoformat(fdate) - dt.timedelta(days=1)).isoformat()
        g = lambda k: h.get(k, [None] * len(t))[i]
        out.append((city, pub.replace('-', ''), fdate.replace('-', ''), hh,
                    g('shortwave_radiation'), g('direct_radiation'), g('diffuse_radiation'),
                    g('temperature_2m'), g('cloud_cover'), g('precipitation'),
                    g('wind_speed_10m'), g('wind_speed_100m'), source,
                    dt.datetime.now().isoformat(timespec='seconds')))
    return out


def _fetch(url, lat, lon, extra, retries=3):
    p = {"latitude": lat, "longitude": lon, "hourly": HOURLY,
         "timezone": "Asia/Shanghai", **extra}
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=p, timeout=45)
            r.raise_for_status()
            return r.json().get("hourly", {})
        except Exception as e:
            last = e
    raise last


def run_live(conn):
    ensure_table(conn)
    n = 0
    for city, (lat, lon, _s, _w) in CITIES.items():
        try:
            h = _fetch("https://api.open-meteo.com/v1/forecast", lat, lon, {"forecast_days": 2})
            rows = _rows_from_hourly(city, h, "open-meteo-forecast", 'today')
            conn.executemany("INSERT OR REPLACE INTO weather_forecast VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
        except Exception as e:
            print(f"  {city} 失败: {e}")
    conn.commit()
    print(f"[live] 写入次日预报 {n} 行 ({len(CITIES)} 城)")


def run_backfill(conn, start, end):
    ensure_table(conn)
    n = 0
    for city, (lat, lon, _s, _w) in CITIES.items():
        try:
            h = _fetch("https://historical-forecast-api.open-meteo.com/v1/forecast", lat, lon,
                       {"start_date": start, "end_date": end})
            rows = _rows_from_hourly(city, h, "open-meteo-hist-forecast", 'prev_day')
            conn.executemany("INSERT OR REPLACE INTO weather_forecast VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
        except Exception as e:
            print(f"  {city} 失败: {e}")
    conn.commit()
    print(f"[backfill] {start}~{end} 写入历史预报 {n} 行 ({len(CITIES)} 城)")


def province_aggregate(conn, forecast_date):
    """按装机权重把各城预报聚合到全省: 光伏权重→GHI, 风电权重→wind100。返回逐小时 DataFrame。"""
    import pandas as pd
    df = pd.read_sql("SELECT * FROM weather_forecast WHERE forecast_date=?",
                     conn, params=[forecast_date.replace('-', '')])
    if df.empty:
        return df
    w = {c: (s, wd) for c, (la, lo, s, wd) in CITIES.items()}
    df['sw'] = df['city'].map(lambda c: w.get(c, (0, 0))[0])
    df['ww'] = df['city'].map(lambda c: w.get(c, (0, 0))[1])
    def wavg(g, val, wt):
        ww = g[wt].sum()
        return (g[val] * g[wt]).sum() / ww if ww else g[val].mean()
    out = df.groupby('hour').apply(
        lambda g: pd.Series({
            'ghi_prov': wavg(g, 'ghi', 'sw'),
            'wind100_prov': wavg(g, 'wind100', 'ww'),
            'temp_prov': g['temp'].mean(),
            'cloud_prov': g['cloud'].mean(),
            'publish_date': g['publish_date'].iloc[0],
        })).reset_index()
    return out


if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "live"
    if cmd == "live":
        run_live(conn)
    elif cmd == "backfill":
        run_backfill(conn, sys.argv[2], sys.argv[3])
    elif cmd == "agg":
        agg = province_aggregate(conn, sys.argv[2])
        print(f"全省加权驱动预报 (目标日 {sys.argv[2]}):")
        print(agg.to_string(index=False) if len(agg) else "  无数据, 先 backfill/live")
    conn.close()
