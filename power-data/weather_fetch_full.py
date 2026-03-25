#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weather Full History Fetch - Open-Meteo Archive API
=====================================================
获取2023-01-01 ~ 2026-02-22的完整历史天气数据
Open-Meteo免费,无API key,无次数限制
按城市批量拉取(每次最多1年),然后重新计算全部修正因子
"""
import urllib.request, urllib.parse, json, ssl, sqlite3, time, sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

DB = 'F:/work/power-supply-v2/power/power-data/power_market_v2.db'
ctx = ssl.create_default_context()

YUNNAN_CITIES = [
    ('曲靖', '101290401', 25.50, 103.80, 850, 320),
    ('红河', '101290301', 23.37, 103.38, 680, 210),
    ('楚雄', '101290801', 25.04, 101.55, 520, 140),
    ('大理', '101290201', 25.59, 100.23, 480, 260),
    ('昆明', '101290101', 24.88, 102.83, 310, 139),
    ('昭通', '101291001', 27.34, 103.72, 58, 25),
    ('保山', '101290501', 25.11, 99.17, 42, 18),
    ('文山', '101290601', 23.37, 104.24, 42, 17),
    ('普洱', '101290901', 22.83, 100.97, 35, 12),
    ('丽江', '101291401', 26.87, 100.23, 28, 22),
    ('临沧', '101291101', 23.89, 100.09, 28, 9),
    ('玉溪', '101290701', 24.35, 102.54, 18, 6),
    ('德宏', '101291501', 24.44, 98.58, 20, 8),
    ('西双版纳', '101291602', 22.00, 100.80, 12, 4),
    ('怒江', '101291201', 25.85, 98.85, 15, 12),
    ('迪庆', '101291305', 27.83, 99.71, 8, 18),
]

TOTAL_PV = sum(c[4] for c in YUNNAN_CITIES)
TOTAL_WIND = sum(c[5] for c in YUNNAN_CITIES)


def fetch_openmeteo_batch(lat, lon, start_date, end_date):
    params = urllib.parse.urlencode({
        'latitude': lat, 'longitude': lon,
        'start_date': start_date, 'end_date': end_date,
        'hourly': 'temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,wind_direction_10m,surface_pressure',
        'timezone': 'Asia/Shanghai'
    })
    url = f'https://archive-api.open-meteo.com/v1/archive?{params}'
    req = urllib.request.Request(url)
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, context=ctx, timeout=60)
            return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                raise


def compute_solar_factor(cloud_pct, hour):
    if hour < 7 or hour > 18:
        return 1.0
    cloud_frac = cloud_pct / 100.0
    ghi_ratio = 1.0 - 0.75 * (cloud_frac ** 3.4)
    ghi_ratio = max(0.15, min(1.0, ghi_ratio))
    return round(ghi_ratio / 0.80, 4)


def compute_wind_factor(wind_speed_ms):
    if wind_speed_ms < 3:
        power = 0.0
    elif wind_speed_ms < 12:
        power = ((wind_speed_ms - 3) / 9.0) ** 3
    elif wind_speed_ms <= 25:
        power = 1.0
    else:
        power = 0.0
    expected = ((5.5 - 3) / 9.0) ** 3
    return round(min(power / expected if expected > 0 else 1.0, 3.0), 4)


def main():
    conn = sqlite3.connect(DB)

    # Get existing data dates per city
    existing = set()
    try:
        rows = conn.execute("SELECT DISTINCT location_id, date FROM weather_hourly").fetchall()
        existing = {(r[0], r[1]) for r in rows}
        print(f"已有 {len(existing)} 条城市-日期记录")
    except:
        pass

    # Date range: 2023-01-01 to 2026-02-22 (what we're missing)
    # Split into yearly chunks for Open-Meteo (max ~2 years per request)
    periods = [
        ('2023-01-01', '2023-12-31'),
        ('2024-01-01', '2024-12-31'),
        ('2025-01-01', '2025-12-31'),
        ('2026-01-01', '2026-02-22'),
    ]

    total_new = 0
    for city_name, loc_id, lat, lon, pv, wind in YUNNAN_CITIES:
        for start, end in periods:
            # Check if we already have data for this range
            start_dk = start.replace('-', '')
            end_dk = end.replace('-', '')

            # Quick check: if first and last date exist, skip
            if (loc_id, start_dk) in existing and (loc_id, end_dk) in existing:
                continue

            try:
                print(f"  {city_name} {start}~{end}...", end='', flush=True)
                data = fetch_openmeteo_batch(lat, lon, start, end)
                hourly = data.get('hourly', {})
                times = hourly.get('time', [])
                temps = hourly.get('temperature_2m', [])
                humids = hourly.get('relative_humidity_2m', [])
                precips = hourly.get('precipitation', [])
                clouds = hourly.get('cloud_cover', [])
                winds = hourly.get('wind_speed_10m', [])
                wind_dirs = hourly.get('wind_direction_10m', [])
                pressures = hourly.get('surface_pressure', [])

                count = 0
                for i, t in enumerate(times):
                    dt_str = t[:10].replace('-', '')
                    hour = int(t[11:13])

                    if (loc_id, dt_str) in existing:
                        continue

                    conn.execute("""
                        INSERT OR REPLACE INTO weather_hourly
                        (city, location_id, date, hour, temp, humidity, precip, pressure,
                         wind_speed, wind_dir, wind_360, cloud, dew, icon, text_desc, source)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        city_name, loc_id, dt_str, hour,
                        temps[i] if i < len(temps) else None,
                        humids[i] if i < len(humids) else None,
                        precips[i] if i < len(precips) else None,
                        pressures[i] if i < len(pressures) else None,
                        winds[i] if i < len(winds) else None,  # Open-Meteo wind is already m/s
                        '',
                        wind_dirs[i] if i < len(wind_dirs) else 0,
                        clouds[i] if i < len(clouds) else 50,
                        None, '', '', 'open-meteo'
                    ))
                    count += 1

                conn.commit()
                total_new += count
                print(f" {count} 行")
                time.sleep(0.5)  # Be nice to the API

            except Exception as e:
                print(f" ERROR: {e}")
                time.sleep(2)

    print(f"\n新增 {total_new} 行天气数据")

    # ============================================================
    # Recompute ALL correction factors
    # ============================================================
    print("\n重新计算全部修正因子...")

    # Get all unique dates from weather_hourly
    all_dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM weather_hourly ORDER BY date").fetchall()]
    print(f"天气数据覆盖 {len(all_dates)} 天: {all_dates[0]} ~ {all_dates[-1]}")

    # Clear old corrections
    conn.execute("DELETE FROM weather_correction")
    conn.commit()

    pv_share = TOTAL_PV / (TOTAL_PV + TOTAL_WIND)
    wind_share = TOTAL_WIND / (TOTAL_PV + TOTAL_WIND)

    batch = []
    for di, date_str in enumerate(all_dates):
        for hour in range(24):
            solar_corrs = []
            wind_corrs = []
            cloud_vals = []
            wind_vals = []

            for city_name, loc_id, lat, lon, pv_cap, wind_cap in YUNNAN_CITIES:
                row = conn.execute(
                    "SELECT cloud, wind_speed FROM weather_hourly WHERE location_id=? AND date=? AND hour=?",
                    (loc_id, date_str, hour)
                ).fetchone()
                if row is None:
                    continue
                cloud = float(row[0]) if row[0] is not None else 50
                ws = float(row[1]) if row[1] is not None else 3

                sf = compute_solar_factor(cloud, hour)
                solar_corrs.append((sf, pv_cap))
                cloud_vals.append((cloud, pv_cap))

                wf = compute_wind_factor(ws)
                wind_corrs.append((wf, wind_cap))
                wind_vals.append((ws, wind_cap))

            if not solar_corrs:
                continue

            total_pv_w = sum(w for _, w in solar_corrs)
            total_wind_w = sum(w for _, w in wind_corrs)
            avg_solar = sum(s*w for s,w in solar_corrs) / total_pv_w if total_pv_w > 0 else 1.0
            avg_wind = sum(s*w for s,w in wind_corrs) / total_wind_w if total_wind_w > 0 else 1.0
            avg_cloud = sum(c*w for c,w in cloud_vals) / total_pv_w if total_pv_w > 0 else 50
            avg_ws = sum(s*w for s,w in wind_vals) / total_wind_w if total_wind_w > 0 else 5
            combined = pv_share * avg_solar + wind_share * avg_wind
            ghi_ratio = 1.0 - 0.75 * ((avg_cloud/100) ** 3.4)

            batch.append((date_str, hour, round(avg_solar,4), round(avg_wind,4),
                         round(combined,4), round(avg_cloud,1), round(avg_ws,2), round(ghi_ratio,4)))

        if (di + 1) % 100 == 0:
            conn.executemany("""INSERT OR REPLACE INTO weather_correction
                (date, hour, solar_correction, wind_correction, combined_correction,
                 avg_cloud, avg_wind_speed, avg_ghi_ratio) VALUES (?,?,?,?,?,?,?,?)""", batch)
            conn.commit()
            batch = []
            print(f"  {di+1}/{len(all_dates)} 天处理完毕")

    if batch:
        conn.executemany("""INSERT OR REPLACE INTO weather_correction
            (date, hour, solar_correction, wind_correction, combined_correction,
             avg_cloud, avg_wind_speed, avg_ghi_ratio) VALUES (?,?,?,?,?,?,?,?)""", batch)
        conn.commit()

    n_corr = conn.execute("SELECT COUNT(*) FROM weather_correction").fetchone()[0]
    n_days = conn.execute("SELECT COUNT(DISTINCT date) FROM weather_correction").fetchone()[0]
    print(f"\n完成! weather_correction: {n_corr} 行, {n_days} 天")

    # Spot check
    r = conn.execute("""SELECT date, AVG(combined_correction), AVG(avg_cloud)
        FROM weather_correction WHERE date IN ('20260322', '20260318', '20250701')
        GROUP BY date""").fetchall()
    print("\n抽样检查:")
    for row in r:
        print(f"  {row[0]}: combined={row[1]:.3f}, cloud={row[2]:.1f}%")

    conn.close()


if __name__ == '__main__':
    main()
