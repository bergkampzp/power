#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL v2: Import 10 months data into power_market_v2.db
- Node prices: only 漫湾 detail + all-node avg/min/max per period
- Other tables: full import
"""
import sqlite3, os, re, glob, warnings
import pandas as pd
import numpy as np
from datetime import datetime

warnings.filterwarnings('ignore')

DB_PATH = 'F:/work/power-supply-v2/power/power-data/power_market_v2.db'
BASE = 'F:/work/power-supply-v2/power/power-data/powper-data-3-26'
POWPER = os.path.join(BASE, 'powper-data')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")

PERIODS_96 = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def extract_date_from_filename(filename):
    m = re.search(r'(\d{4})[-]?(\d{2})[-]?(\d{2})', filename)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.search(r'(\d{2})-(\d{2})-(\d{2})', filename)
    if m:
        y = int(m.group(1))
        year = 2000 + y if y < 50 else 1900 + y
        return f"{year}{m.group(2)}{m.group(3)}"
    return None

def date_dash(dk):
    if len(dk) == 8:
        return f"{dk[:4]}-{dk[4:6]}-{dk[6:8]}"
    return dk

# ============================================================
# 1. Import 实时运行信息 (hourly tables)
# ============================================================
def import_realtime_operation():
    base = os.path.join(POWPER, '实时运行信息查询', 'extracted')
    if not os.path.exists(base):
        log("SKIP: 实时运行信息查询/extracted not found")
        return

    folders = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    log(f"实时运行信息: {len(folders)} date folders")

    regions_6 = ['全区域', '广东', '广西', '云南', '贵州', '海南']

    file_configs = {
        '实际运行信息-统调负荷': ('hourly_load', 'load', 'wide_regions'),
        '发电总出力': ('hourly_generation', 'output', 'wide_today_prev'),
        '非市场机组总出力': ('hourly_nonmarket', 'output', 'wide_today_prev'),
        '新能源总出力': ('hourly_renewable', 'output', 'wide_today_prev'),
        '水电总出力': ('hourly_hydro', 'output', 'wide_today_prev'),
    }

    table_counts = {t: 0 for _, (t, _, _) in file_configs.items()}

    for fi, folder in enumerate(folders):
        dk = extract_date_from_filename(folder)
        if not dk:
            continue

        output_dir = os.path.join(base, folder, 'output')
        if not os.path.exists(output_dir):
            continue

        for pattern, (table, col, ftype) in file_configs.items():
            matches = [f for f in os.listdir(output_dir) if pattern in f and f.endswith('.xls')]
            if not matches:
                continue

            # Skip if already imported
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date_key=?", (dk,))
            if cur.fetchone()[0] > 0:
                continue

            try:
                df = pd.read_excel(os.path.join(output_dir, matches[0]))
                if len(df) < 2:
                    continue

                rows = []
                if ftype == 'wide_regions':
                    # Columns: 序号 | 时刻 | 全区域 | 广东 | 广西 | 云南 | 贵州 | 海南
                    for _, row in df.iterrows():
                        period = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        if not period or '时刻' in period:
                            continue
                        for i, region in enumerate(regions_6):
                            ci = i + 2
                            if ci < len(row) and pd.notna(row.iloc[ci]):
                                try:
                                    rows.append((dk, period, region, float(row.iloc[ci])))
                                except (ValueError, TypeError):
                                    pass

                elif ftype == 'wide_today_prev':
                    # Find "当日" columns by checking column names for date or region
                    cols = df.columns.tolist()
                    today_cols = []
                    for ci, c in enumerate(cols[2:], 2):
                        cs = str(c)
                        # Match columns containing the date
                        if dk[:8] in cs.replace('-', ''):
                            for r in regions_6:
                                if r in cs:
                                    today_cols.append((ci, r))
                                    break

                    if not today_cols:
                        # Fallback: take even-indexed columns (当日 columns)
                        for ci in range(2, min(len(cols), 14), 2):
                            cs = str(cols[ci])
                            for r in regions_6:
                                if r in cs:
                                    today_cols.append((ci, r))
                                    break

                    for _, row in df.iterrows():
                        period = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        if not period or '时刻' in period:
                            continue
                        for ci, region in today_cols:
                            if pd.notna(row.iloc[ci]):
                                try:
                                    rows.append((dk, period, region, float(row.iloc[ci])))
                                except (ValueError, TypeError):
                                    pass

                if rows:
                    cur.executemany(
                        f"INSERT INTO {table} (date_key, period, region, {col}) VALUES (?,?,?,?)",
                        rows
                    )
                    table_counts[table] += len(rows)

            except Exception:
                pass

        if (fi + 1) % 50 == 0:
            conn.commit()
            log(f"  progress: {fi+1}/{len(folders)} folders")

    conn.commit()
    for t, cnt in table_counts.items():
        log(f"  {t}: +{cnt} rows")

# ============================================================
# 2. Import 信息披露 (forecasts, reserve, maintenance, etc.)
# ============================================================
def import_disclosure():
    base = os.path.join(POWPER, '信息披露', 'extracted')
    if not os.path.exists(base):
        log("SKIP: 信息披露/extracted not found")
        return

    folders = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    log(f"信息披露: {len(folders)} date folders")

    counts = {'system_reserve': 0, 'load_forecast': 0, 'unit_status': 0,
              'inter_provincial_line': 0, 'transmission_channel': 0}

    for fi, folder in enumerate(folders):
        dk = extract_date_from_filename(folder)
        if not dk:
            continue
        dd = date_dash(dk)
        output_dir = os.path.join(base, folder, 'output')
        if not os.path.exists(output_dir):
            continue
        files = os.listdir(output_dir)

        # --- 备用信息 → system_reserve ---
        for rf in [f for f in files if '备用信息' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM system_reserve WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, rf))
                rows = []
                for _, row in df.iterrows():
                    region = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    rtype = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
                    if not region or region == '所属区域':
                        continue
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 3
                        if ci < len(row) and pd.notna(row.iloc[ci]):
                            try:
                                rows.append((dd, rtype, period, float(row.iloc[ci]), 'MW', region))
                            except (ValueError, TypeError):
                                pass
                if rows:
                    cur.executemany("INSERT INTO system_reserve (trade_date, reserve_type, period, reserve_value, unit, region) VALUES (?,?,?,?,?,?)", rows)
                    counts['system_reserve'] += len(rows)
            except Exception:
                pass

        # --- 统调负荷 → load_forecast ---
        for lf in [f for f in files if '统调负荷' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM load_forecast WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, lf))
                rows = []
                for _, row in df.iterrows():
                    period = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    if not period or '时刻' in period:
                        continue
                    val = row.iloc[2]
                    if pd.notna(val):
                        try:
                            rows.append((dd, period, float(val), None, 'MW'))
                        except (ValueError, TypeError):
                            pass
                if rows:
                    cur.executemany("INSERT INTO load_forecast (trade_date, period, forecast_load, actual_load, unit) VALUES (?,?,?,?,?)", rows)
                    counts['load_forecast'] += len(rows)
            except Exception:
                pass

        # --- 必开必停机组名单 → unit_status ---
        for uf in [f for f in files if '必开必停机组名单' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM unit_status WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, uf))
                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    unit = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ''
                    must_type = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ''
                    if unit:
                        rows.append((dd, unit, 'generator', must_type, None, None, must_type, None))
                if rows:
                    cur.executemany("INSERT INTO unit_status (trade_date, unit_name, unit_type, status, capacity, available_capacity, must_run_type, outage_type) VALUES (?,?,?,?,?,?,?,?)", rows)
                    counts['unit_status'] += len(rows)
            except Exception:
                pass

        # --- 区外联络线 → inter_provincial_line ---
        for lnf in [f for f in files if '区外联络线' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM inter_provincial_line WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, lnf))
                rows = []
                for _, row in df.iterrows():
                    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    if not name or name == '区外联络线':
                        continue
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 2
                        if ci < len(row) and pd.notna(row.iloc[ci]):
                            try:
                                rows.append((dd, name, None, float(row.iloc[ci]), None, period))
                            except (ValueError, TypeError):
                                pass
                if rows:
                    cur.executemany("INSERT INTO inter_provincial_line (trade_date, line_name, direction, power_flow, capacity, period) VALUES (?,?,?,?,?,?)", rows)
                    counts['inter_provincial_line'] += len(rows)
            except Exception:
                pass

        # --- 输电通道可用容量 → transmission_channel ---
        for cf in [f for f in files if '输电通道可用容量' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM transmission_channel WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, cf))
                rows = []
                for _, row in df.iterrows():
                    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    cap = row.iloc[2] if pd.notna(row.iloc[2]) else None
                    if not name or name == '通道名称':
                        continue
                    try:
                        rows.append((dd, name, None, float(cap), None, 'daily'))
                    except (ValueError, TypeError):
                        pass
                if rows:
                    cur.executemany("INSERT INTO transmission_channel (trade_date, channel_name, power_flow, capacity, utilization_rate, period) VALUES (?,?,?,?,?,?)", rows)
                    counts['transmission_channel'] += len(rows)
            except Exception:
                pass

        if (fi + 1) % 50 == 0:
            conn.commit()
            log(f"  progress: {fi+1}/{len(folders)}")

    conn.commit()
    for t, cnt in counts.items():
        log(f"  {t}: +{cnt} rows")

# ============================================================
# 3. Import 实时运行信息 extras (断面/稳定/通道/检修)
# ============================================================
def import_realtime_extras():
    base = os.path.join(POWPER, '实时运行信息查询', 'extracted')
    if not os.path.exists(base):
        return

    folders = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    counts = {'section_constraint': 0, 'peak_reserve_info': 0, 'stability_section_info': 0, 'maintenance_plan': 0}

    for fi, folder in enumerate(folders):
        dk = extract_date_from_filename(folder)
        if not dk:
            continue
        dd = date_dash(dk)
        output_dir = os.path.join(base, folder, 'output')
        if not os.path.exists(output_dir):
            continue
        files = os.listdir(output_dir)

        # --- 实际输电断面约束 → section_constraint ---
        for scf in [f for f in files if '实际输电断面约束' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM section_constraint WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, scf))
                rows = []
                for _, row in df.iterrows():
                    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    dtype = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ''
                    if not name or name == '通道名称':
                        continue
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 3
                        if ci < len(row) and pd.notna(row.iloc[ci]):
                            try:
                                rows.append((dd, 'realtime', name, dtype, float(row.iloc[ci]), None, None, period, ''))
                            except (ValueError, TypeError):
                                pass
                if rows:
                    cur.executemany("INSERT INTO section_constraint (trade_date, market_type, section_name, constraint_type, limit_value, actual_value, congestion_degree, period, region) VALUES (?,?,?,?,?,?,?,?,?)", rows)
                    counts['section_constraint'] += len(rows)
            except Exception:
                pass

        # --- 高峰正备用 → peak_reserve_info ---
        for prf in [f for f in files if '高峰正备用' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM peak_reserve_info WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, prf))
                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    region = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    val = row.iloc[3] if len(row) > 3 and pd.notna(row.iloc[3]) else None
                    if val:
                        try:
                            rows.append((dd, 'peak', '正备用', float(val), 'MW', region))
                        except (ValueError, TypeError):
                            pass
                if rows:
                    cur.executemany("INSERT INTO peak_reserve_info (trade_date, period, reserve_type, reserve_value, unit, region) VALUES (?,?,?,?,?,?)", rows)
                    counts['peak_reserve_info'] += len(rows)
            except Exception:
                pass

        # --- 稳定断面 → stability_section_info ---
        for ssf in [f for f in files if '稳定断面信息' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM stability_section_info WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, ssf))
                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    rate = row.iloc[2] if pd.notna(row.iloc[2]) else None
                    if name and rate:
                        try:
                            rows.append((dd, name, None, None, None, float(rate)))
                        except (ValueError, TypeError):
                            pass
                if rows:
                    cur.executemany("INSERT INTO stability_section_info (trade_date, section_name, direction, stability_limit, unit, max_load_rate) VALUES (?,?,?,?,?,?)", rows)
                    counts['stability_section_info'] += len(rows)
            except Exception:
                pass

        # --- 检修执行计划 → maintenance_plan ---
        for mpf in [f for f in files if '检修' in f and '改造' in f and f.endswith('.xls')]:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM maintenance_plan WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue
                df = pd.read_excel(os.path.join(output_dir, mpf))
                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    voltage = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ''
                    equip = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else ''
                    etype = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ''
                    start = str(row.iloc[5]).strip() if len(row) > 5 and pd.notna(row.iloc[5]) else ''
                    end = str(row.iloc[6]).strip() if len(row) > 6 and pd.notna(row.iloc[6]) else ''
                    if equip:
                        rows.append((dd, equip, start, end, '检修执行', etype, voltage, '', ''))
                if rows:
                    cur.executemany("INSERT INTO maintenance_plan (trade_date, unit_name, start_time, end_time, description, status, voltage_level, actual_start_time, actual_end_time) VALUES (?,?,?,?,?,?,?,?,?)", rows)
                    counts['maintenance_plan'] += len(rows)
            except Exception:
                pass

        if (fi + 1) % 50 == 0:
            conn.commit()

    conn.commit()
    for t, cnt in counts.items():
        log(f"  {t}: +{cnt} rows")

# ============================================================
# 4. Import node prices - OPTIMIZED
#    Only: 漫湾 4 nodes detail + all-node avg/min/max per period
# ============================================================
def import_node_prices():
    MANWAN_NODES = ['漫湾厂.220kVⅠ母', '漫湾厂.220kVⅡ母', '漫湾厂.500kV#1M', '漫湾厂.500kV#2M']

    configs = [
        ('realtime_node_price_96', '实时节点电价', [
            os.path.join(POWPER, '实时节点电价'),
            os.path.join(BASE, '实时节点电价'),
        ]),
        ('day_ahead_node_price_96', '日前节点电价', [
            os.path.join(POWPER, '日前节点电价'),
            os.path.join(BASE, '日前节点电价2-3月'),
        ]),
    ]

    for table, keyword, dirs in configs:
        total = 0
        skipped = 0

        for d in dirs:
            if not os.path.exists(d):
                continue
            xlsx_files = sorted([f for f in os.listdir(d) if '节点电价' in f and f.endswith('.xlsx')])
            log(f"  {table} from {os.path.basename(d)}: {len(xlsx_files)} files")

            for fi, fname in enumerate(xlsx_files):
                dk = extract_date_from_filename(fname)
                if not dk:
                    continue
                dd = date_dash(dk)

                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    skipped += 1
                    continue

                try:
                    df = pd.read_excel(os.path.join(d, fname))
                    if len(df) < 2:
                        continue

                    # Identify period columns (starting from col 2)
                    n_period_cols = min(96, len(df.columns) - 2)
                    if n_period_cols < 1:
                        continue

                    rows = []

                    # 1. Extract 漫湾 nodes in detail
                    for _, row in df.iterrows():
                        node = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        region = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
                        if node in MANWAN_NODES:
                            for pi in range(n_period_cols):
                                ci = pi + 2
                                val = row.iloc[ci]
                                if pd.notna(val):
                                    try:
                                        rows.append((dd, region, node, PERIODS_96[pi], float(val)))
                                    except (ValueError, TypeError, IndexError):
                                        pass

                    # 2. Compute all-node avg/min/max per period
                    # Build numeric matrix (nodes x periods)
                    data_rows = []
                    for _, row in df.iterrows():
                        node = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        if node == '节点名称' or node == '':
                            continue
                        vals = []
                        for pi in range(n_period_cols):
                            ci = pi + 2
                            v = row.iloc[ci]
                            try:
                                vals.append(float(v) if pd.notna(v) else np.nan)
                            except (ValueError, TypeError):
                                vals.append(np.nan)
                        data_rows.append(vals)

                    if data_rows:
                        mat = np.array(data_rows)
                        for pi in range(n_period_cols):
                            col = mat[:, pi]
                            valid = col[~np.isnan(col)]
                            if len(valid) > 0:
                                rows.append((dd, '全网', '__avg__', PERIODS_96[pi], float(np.mean(valid))))
                                rows.append((dd, '全网', '__min__', PERIODS_96[pi], float(np.min(valid))))
                                rows.append((dd, '全网', '__max__', PERIODS_96[pi], float(np.max(valid))))

                    if rows:
                        cur.executemany(
                            f"INSERT INTO {table} (trade_date, region, node_name, period, price) VALUES (?,?,?,?,?)",
                            rows
                        )
                        total += len(rows)

                except Exception:
                    pass

                if (fi + 1) % 20 == 0:
                    conn.commit()
                    log(f"    progress: {fi+1}/{len(xlsx_files)}")

            conn.commit()
        log(f"  {table}: +{total} rows, {skipped} skipped")

# ============================================================
# 5. Import demand data
# ============================================================
def import_demand():
    configs = [
        ('realtime_demand', '实时交易结果', [os.path.join(POWPER, '实时交易结果用电册')]),
        ('day_ahead_demand', '日前交易', [
            os.path.join(POWPER, '日前用电册'),
            os.path.join(BASE, '日前用电侧数据2-3月'),
        ]),
    ]

    for table, keyword, dirs in configs:
        total = 0
        for d in dirs:
            if not os.path.exists(d):
                continue
            # Skip duplicate files (1).xls etc
            xls_files = sorted(set(
                f for f in os.listdir(d)
                if keyword in f and f.endswith('.xls') and '(' not in f
            ))
            log(f"  {table} from {os.path.basename(d)}: {len(xls_files)} files")

            for fname in xls_files:
                dk = extract_date_from_filename(fname)
                if not dk:
                    continue
                dd = date_dash(dk)

                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    continue

                try:
                    df = pd.read_excel(os.path.join(d, fname))
                    if len(df) < 2:
                        continue
                    rows = []
                    for _, row in df.iterrows():
                        period = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
                        price = row.iloc[1] if pd.notna(row.iloc[1]) else None
                        if not period or '时刻' in period or '时段' in period:
                            continue
                        if price is not None:
                            try:
                                rows.append((dd, period, float(price), None))
                            except (ValueError, TypeError):
                                pass
                    if rows:
                        cur.executemany(f"INSERT INTO {table} (trade_date, period, demand, price) VALUES (?,?,?,?)", rows)
                        total += len(rows)
                except Exception:
                    pass

            conn.commit()
        log(f"  {table}: +{total} rows")

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    log("=" * 60)
    log("ETL v2 Import Start")
    log("=" * 60)

    log("\n[1/5] 实时运行信息 → hourly_load/gen/nonmarket/renewable/hydro...")
    import_realtime_operation()

    log("\n[2/5] 信息披露 → reserve/forecast/units/lines/channels...")
    import_disclosure()

    log("\n[3/5] 实时运行extras → section/peak/stability/maintenance...")
    import_realtime_extras()

    log("\n[4/5] 节点电价 → 漫湾detail + 全网avg (optimized)...")
    import_node_prices()

    log("\n[5/5] 需求数据 → RT/DA demand...")
    import_demand()

    # Final summary
    log("\n" + "=" * 60)
    log("DATABASE SUMMARY")
    log("=" * 60)

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    total_rows = 0
    for t in tables:
        if t == 'sqlite_sequence':
            continue
        cur.execute(f"SELECT COUNT(*) FROM [{t}]")
        cnt = cur.fetchone()[0]
        total_rows += cnt
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info([{t}])").fetchall()]
        date_col = 'date_key' if 'date_key' in cols else ('trade_date' if 'trade_date' in cols else None)
        if date_col and cnt > 0:
            cur.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM [{t}]")
            dr = cur.fetchone()
            status = "✅" if cnt > 0 else "⭕"
            log(f"  {status} {t:35s} {cnt:>10,} rows  ({dr[0]} ~ {dr[1]})")
        else:
            status = "⭕" if cnt == 0 else "✅"
            log(f"  {status} {t:35s} {cnt:>10,} rows")

    log(f"\n  TOTAL: {total_rows:,} rows across {len(tables)} tables")
    conn.close()
    log("\nETL v2 Complete!")
