#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL: Import forecast data into power_market_v2.db
=================================================
Key tables:
  1. renewable_forecast  - 新能源总出力(周) - D+1~D+7 wind/solar forecast 96 periods
  2. hydro_forecast      - 水电周预测出力    - weekly hydro forecast by region
  3. generation_forecast  - 发电总出力预测    - total generation forecast 96 periods

Data source: 信息披露/extracted/信息批露YY-MM-DD/output/
264 directories, 2025-06-01 ~ 2026-03-22
"""
import sqlite3, os, glob, re, time
import xlrd

from config import DB
from config import POWPER_BASE as _PB
BASE_DIR = os.path.join(_PB, 'powper-data', '信息披露', 'extracted')

def log(msg):
    print(f"  {msg}", flush=True)

def safe_float(v):
    try:
        return float(str(v).strip())
    except:
        return None

def parse_date_from_dirname(dirname):
    """Extract date from directory name like '信息批露25-06-01' or '信息批露26-03-22'"""
    m = re.search(r'(\d{2})-(\d{2})-(\d{2})$', dirname)
    if m:
        yy, mm, dd = m.groups()
        year = int(yy) + 2000
        return f"{year}{mm}{dd}"
    return None

def get_all_dirs():
    """Get all date directories sorted"""
    dirs = sorted(glob.glob(os.path.join(BASE_DIR, '信息批露*')))
    result = []
    for d in dirs:
        date_key = parse_date_from_dirname(os.path.basename(d))
        if date_key:
            result.append((date_key, d))
    return result

# ============================================================
# Create tables
# ============================================================
def create_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS renewable_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publish_date TEXT NOT NULL,      -- 发布日期 YYYYMMDD
            forecast_date TEXT NOT NULL,     -- 预测目标日期 YYYYMMDD
            period TEXT NOT NULL,            -- 时刻 HH:MM
            region TEXT NOT NULL,            -- 区域
            category TEXT NOT NULL,          -- 总计/风电/光伏
            forecast_mw REAL,               -- 预测出力 MW
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hydro_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publish_date TEXT NOT NULL,
            forecast_date TEXT NOT NULL,
            region TEXT NOT NULL,
            avg_output_mw REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS generation_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publish_date TEXT NOT NULL,
            forecast_date TEXT NOT NULL,
            period TEXT NOT NULL,
            region TEXT NOT NULL,
            forecast_mw REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Indexes for fast lookup
    conn.execute("CREATE INDEX IF NOT EXISTS idx_renew_fc_date ON renewable_forecast(forecast_date, period, region, category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hydro_fc_date ON hydro_forecast(forecast_date, region)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gen_fc_date ON generation_forecast(forecast_date, period, region)")
    conn.commit()
    log("Tables created")

# ============================================================
# Import 新能源总出力（周）
# ============================================================
def import_renewable_forecast(conn, date_key, output_dir):
    """Import weekly renewable energy forecast (wind + solar + total)"""
    pattern = os.path.join(output_dir, f'{date_key}新能源总出力*周*')
    files = glob.glob(pattern)
    if not files:
        return 0

    filepath = files[0]
    try:
        wb = xlrd.open_workbook(filepath)
    except:
        return 0

    rows_inserted = 0
    sheet_map = {'总计': '总计', '风电': '风电', '光伏': '光伏'}

    for sheet_name, category in sheet_map.items():
        try:
            ws = wb.sheet_by_name(sheet_name)
        except:
            continue

        if ws.nrows < 2:
            continue

        # Parse headers to get forecast dates
        headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
        forecast_dates = []
        for h in headers[3:]:  # Skip 序号, 所属区域, 时刻
            m = re.search(r'(\d{8})', h)
            if m:
                forecast_dates.append(m.group(1))

        if not forecast_dates:
            continue

        batch = []
        for r in range(1, ws.nrows):
            region = str(ws.cell_value(r, 1)).strip()
            if region != '云南':  # Only import Yunnan for model
                continue
            period = str(ws.cell_value(r, 2)).strip()

            for col_offset, fc_date in enumerate(forecast_dates):
                val = safe_float(ws.cell_value(r, 3 + col_offset))
                if val is not None:
                    batch.append((date_key, fc_date, period, region, category, val))

        if batch:
            conn.executemany(
                "INSERT INTO renewable_forecast(publish_date, forecast_date, period, region, category, forecast_mw) VALUES (?,?,?,?,?,?)",
                batch
            )
            rows_inserted += len(batch)

    return rows_inserted

# ============================================================
# Import 水电周预测出力
# ============================================================
def import_hydro_forecast(conn, date_key, output_dir):
    """Import weekly hydro forecast (daily average by region)"""
    pattern = os.path.join(output_dir, f'{date_key}水电周预测出力*')
    files = glob.glob(pattern)
    if not files:
        return 0

    filepath = files[0]
    try:
        wb = xlrd.open_workbook(filepath)
        ws = wb.sheet_by_index(0)
    except:
        return 0

    if ws.nrows < 2:
        return 0

    batch = []
    for r in range(1, ws.nrows):
        try:
            fc_date = str(ws.cell_value(r, 1)).strip()
            region = str(ws.cell_value(r, 2)).strip()
            avg_mw = safe_float(ws.cell_value(r, 3))
        except:
            continue

        if region != '云南':
            continue

        # Normalize date
        fc_date = fc_date.replace('-', '').strip()
        if len(fc_date) == 8 and avg_mw is not None:
            batch.append((date_key, fc_date, region, avg_mw))

    if batch:
        conn.executemany(
            "INSERT INTO hydro_forecast(publish_date, forecast_date, region, avg_output_mw) VALUES (?,?,?,?)",
            batch
        )
    return len(batch)

# ============================================================
# Import 发电总出力预测
# ============================================================
def import_generation_forecast(conn, date_key, output_dir):
    """Import total generation output forecast (96 periods)"""
    pattern = os.path.join(output_dir, f'{date_key}发电总出力预测*')
    files = glob.glob(pattern)
    if not files:
        return 0

    filepath = files[0]
    try:
        wb = xlrd.open_workbook(filepath)
        ws = wb.sheet_by_index(0)
    except:
        return 0

    if ws.nrows < 2:
        return 0

    # Parse headers for forecast dates
    headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
    forecast_dates = []
    for h in headers:
        m = re.search(r'(\d{8})', h)
        if m:
            forecast_dates.append(m.group(1))

    batch = []
    for r in range(1, ws.nrows):
        try:
            region = str(ws.cell_value(r, 1)).strip()
            period = str(ws.cell_value(r, 2)).strip()
        except:
            continue

        for col_idx, fc_date in enumerate(forecast_dates):
            val = safe_float(ws.cell_value(r, 3 + col_idx))
            if val is not None:
                batch.append((date_key, fc_date, period, region, val))

    if batch:
        conn.executemany(
            "INSERT INTO generation_forecast(publish_date, forecast_date, period, region, forecast_mw) VALUES (?,?,?,?,?)",
            batch
        )
    return len(batch)

# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("ETL: Import Forecast Data")
    print("=" * 60)

    conn = sqlite3.connect(DB)
    create_tables(conn)

    # Clear existing data for re-import
    for t in ['renewable_forecast', 'hydro_forecast', 'generation_forecast']:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    log("Cleared existing forecast data")

    all_dirs = get_all_dirs()
    log(f"Found {len(all_dirs)} date directories")

    total_renew = 0
    total_hydro = 0
    total_gen = 0
    t0 = time.time()

    for i, (date_key, dirpath) in enumerate(all_dirs):
        output_dir = os.path.join(dirpath, 'output')
        if not os.path.isdir(output_dir):
            continue

        n_r = import_renewable_forecast(conn, date_key, output_dir)
        n_h = import_hydro_forecast(conn, date_key, output_dir)
        n_g = import_generation_forecast(conn, date_key, output_dir)

        total_renew += n_r
        total_hydro += n_h
        total_gen += n_g

        if (i + 1) % 50 == 0:
            conn.commit()
            elapsed = time.time() - t0
            log(f"  [{i+1}/{len(all_dirs)}] {date_key}  renew={total_renew} hydro={total_hydro} gen={total_gen}  ({elapsed:.0f}s)")

    conn.commit()
    elapsed = time.time() - t0

    print()
    print("=" * 60)
    print(f"DONE in {elapsed:.1f}s")
    print(f"  renewable_forecast: {total_renew:,} rows")
    print(f"  hydro_forecast:     {total_hydro:,} rows")
    print(f"  generation_forecast:{total_gen:,} rows")
    print("=" * 60)

    # Verify
    for t in ['renewable_forecast', 'hydro_forecast', 'generation_forecast']:
        cur = conn.execute(f"SELECT COUNT(*), MIN(forecast_date), MAX(forecast_date) FROM {t}")
        r = cur.fetchone()
        print(f"  {t}: {r[0]:,} rows, {r[1]} ~ {r[2]}")

    conn.close()

if __name__ == '__main__':
    main()
