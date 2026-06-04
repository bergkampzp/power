#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL Step 2: Import 10 months of data into power_market_v2.db
Processes all data sources in priority order (P0 → P1 → P2)
"""
import sqlite3, os, re, glob, traceback
import pandas as pd
import numpy as np
from datetime import datetime

from config import DB_PATH
from config import POWPER_BASE as BASE
POWPER = os.path.join(BASE, 'powper-data')

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")

stats = {}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def extract_date_from_filename(filename):
    """Extract date from various filename formats."""
    # Pattern: YYYYMMDD or YYYY-MM-DD
    m = re.search(r'(\d{4})[-]?(\d{2})[-]?(\d{2})', filename)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    # Pattern: YY-MM-DD
    m = re.search(r'(\d{2})-(\d{2})-(\d{2})', filename)
    if m:
        y = int(m.group(1))
        year = 2000 + y if y < 50 else 1900 + y
        return f"{year}{m.group(2)}{m.group(3)}"
    return None

def extract_date_dash(date_key):
    """Convert YYYYMMDD -> YYYY-MM-DD"""
    if len(date_key) == 8:
        return f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}"
    return date_key

PERIODS_96 = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]]

# ============================================================
# P0-1: Import 实时运行信息 (actual hourly data)
# ============================================================
def import_realtime_operation():
    """Import from 实时运行信息查询/extracted/ into:
    - hourly_load, hourly_generation, hourly_nonmarket,
    - hourly_renewable, hourly_hydro
    """
    base = os.path.join(POWPER, '实时运行信息查询', 'extracted')
    if not os.path.exists(base):
        log("SKIP: 实时运行信息查询/extracted not found")
        return

    folders = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    log(f"实时运行信息: {len(folders)} date folders")

    regions_6 = ['全区域', '广东', '广西', '云南', '贵州', '海南']

    # File patterns and their target tables
    file_configs = {
        '实际运行信息-统调负荷': {'table': 'hourly_load', 'col_name': 'load', 'type': 'wide_regions'},
        '发电总出力': {'table': 'hourly_generation', 'col_name': 'output', 'type': 'wide_today_prev'},
        '非市场机组总出力': {'table': 'hourly_nonmarket', 'col_name': 'output', 'type': 'wide_today_prev'},
        '新能源总出力': {'table': 'hourly_renewable', 'col_name': 'output', 'type': 'wide_today_prev'},
        '水电总出力': {'table': 'hourly_hydro', 'col_name': 'output', 'type': 'wide_today_prev'},
    }

    for table_info in file_configs.values():
        stats[table_info['table']] = {'inserted': 0, 'skipped': 0, 'errors': 0}

    for folder in folders:
        date_key = extract_date_from_filename(folder)
        if not date_key:
            continue

        output_dir = os.path.join(base, folder, 'output')
        if not os.path.exists(output_dir):
            continue

        for file_pattern, cfg in file_configs.items():
            # Find matching file
            matches = [f for f in os.listdir(output_dir) if file_pattern in f and f.endswith('.xls')]
            if not matches:
                continue

            filepath = os.path.join(output_dir, matches[0])
            try:
                df = pd.read_excel(filepath)
                if len(df) == 0:
                    continue

                table = cfg['table']
                col_name = cfg['col_name']
                rows_to_insert = []

                if cfg['type'] == 'wide_regions':
                    # Format: 序号 | 时刻 | 全区域 | 广东 | 广西 | 云南 | 贵州 | 海南
                    for _, row in df.iterrows():
                        period = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                        if not period or period == '时刻':
                            continue
                        for i, region in enumerate(regions_6):
                            if i + 2 < len(df.columns):
                                val = row.iloc[i + 2]
                                if pd.notna(val):
                                    try:
                                        rows_to_insert.append((date_key, period, region, float(val)))
                                    except (ValueError, TypeError):
                                        pass

                elif cfg['type'] == 'wide_today_prev':
                    # Format: 序号 | 时刻 | 当日全区域 | 前日全区域 | 当日广东 | 前日广东 ...
                    # Take only "当日" columns (even indices after 时刻)
                    cols = df.columns.tolist()
                    today_region_cols = []
                    for ci, c in enumerate(cols[2:], 2):
                        c_str = str(c)
                        if date_key[:8] in c_str:
                            # Extract region name
                            for r in regions_6:
                                if r in c_str:
                                    today_region_cols.append((ci, r))
                                    break

                    if not today_region_cols:
                        # Fallback: take every other column starting from 2
                        for ci in range(2, min(len(cols), 14), 2):
                            c_str = str(cols[ci])
                            for r in regions_6:
                                if r in c_str:
                                    today_region_cols.append((ci, r))
                                    break

                    for _, row in df.iterrows():
                        period = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                        if not period or period == '时刻':
                            continue
                        for ci, region in today_region_cols:
                            val = row.iloc[ci]
                            if pd.notna(val):
                                try:
                                    rows_to_insert.append((date_key, period, region, float(val)))
                                except (ValueError, TypeError):
                                    pass

                if rows_to_insert:
                    # Check for existing data
                    cur = conn.cursor()
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date_key=?", (date_key,))
                    existing = cur.fetchone()[0]
                    if existing > 0:
                        stats[table]['skipped'] += len(rows_to_insert)
                        continue

                    cur.executemany(
                        f"INSERT INTO {table} (date_key, period, region, {col_name}) VALUES (?, ?, ?, ?)",
                        rows_to_insert
                    )
                    stats[table]['inserted'] += len(rows_to_insert)

            except Exception as e:
                stats[cfg['table']]['errors'] += 1

    conn.commit()
    for table, s in stats.items():
        if s['inserted'] > 0 or s['errors'] > 0:
            log(f"  {table}: +{s['inserted']} inserted, {s['skipped']} skipped, {s['errors']} errors")

# ============================================================
# P0-2: Import 信息披露 (day-ahead forecasts)
# ============================================================
def import_disclosure():
    """Import from 信息披露/extracted/ into:
    - load_forecast (统调负荷 as forecast)
    - system_reserve (备用信息)
    - maintenance_plan (机组检修 + 输变电检修)
    - unit_status (必开必停)
    - peak_reserve_info (高峰正备用)
    - day_ahead_hydro_unit_limit (水电机组群)
    """
    base = os.path.join(POWPER, '信息披露', 'extracted')
    if not os.path.exists(base):
        log("SKIP: 信息披露/extracted not found")
        return

    folders = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    log(f"信息披露: {len(folders)} date folders")

    table_stats = {
        'system_reserve': 0,
        'maintenance_plan': 0,
        'unit_status': 0,
        'inter_provincial_line': 0,
        'transmission_channel': 0,
        'load_forecast': 0,
    }

    for folder in folders:
        date_key = extract_date_from_filename(folder)
        if not date_key:
            continue
        date_dash = extract_date_dash(date_key)

        output_dir = os.path.join(base, folder, 'output')
        if not os.path.exists(output_dir):
            continue

        files = os.listdir(output_dir)

        # --- 备用信息 → system_reserve ---
        reserve_files = [f for f in files if '备用信息' in f and f.endswith('.xls')]
        for rf in reserve_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, rf))
                if len(df) == 0:
                    continue
                # Check existing
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM system_reserve WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    region = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                    rtype = str(row.iloc[2]) if pd.notna(row.iloc[2]) else None
                    if not region or region == '所属区域':
                        continue
                    # 96 period columns start at index 3
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 3
                        if ci < len(row):
                            val = row.iloc[ci]
                            if pd.notna(val):
                                try:
                                    rows.append((date_dash, rtype, period, float(val), 'MW', region))
                                except (ValueError, TypeError):
                                    pass

                if rows:
                    cur.executemany(
                        "INSERT INTO system_reserve (trade_date, reserve_type, period, reserve_value, unit, region) VALUES (?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['system_reserve'] += len(rows)
            except Exception:
                pass

        # --- 统调负荷 (信息披露) → load_forecast ---
        load_files = [f for f in files if '统调负荷' in f and f.endswith('.xls')]
        for lf in load_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, lf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM load_forecast WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                regions_6 = ['全区域', '广东', '广西', '云南', '贵州', '海南']
                for _, row in df.iterrows():
                    period = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                    if not period or period == '时刻':
                        continue
                    # Take 全区域 (index 2)
                    val = row.iloc[2]
                    if pd.notna(val):
                        try:
                            rows.append((date_dash, period, float(val), None, 'MW'))
                        except (ValueError, TypeError):
                            pass

                if rows:
                    cur.executemany(
                        "INSERT INTO load_forecast (trade_date, period, forecast_load, actual_load, unit) VALUES (?,?,?,?,?)",
                        rows
                    )
                    table_stats['load_forecast'] += len(rows)
            except Exception:
                pass

        # --- 必开必停机组名单 → unit_status ---
        unit_files = [f for f in files if '必开必停机组名单' in f and f.endswith('.xls')]
        for uf in unit_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, uf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM unit_status WHERE trade_date=? AND must_run_type IS NOT NULL", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    region = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
                    plant = str(row.iloc[2]) if pd.notna(row.iloc[2]) else ''
                    unit = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ''
                    must_type = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ''
                    rows.append((date_dash, unit, 'generator', must_type, None, None, must_type, None))

                if rows:
                    cur.executemany(
                        "INSERT INTO unit_status (trade_date, unit_name, unit_type, status, capacity, available_capacity, must_run_type, outage_type) VALUES (?,?,?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['unit_status'] += len(rows)
            except Exception:
                pass

        # --- 区外联络线 → inter_provincial_line ---
        line_files = [f for f in files if '区外联络线' in f and f.endswith('.xls')]
        for lnf in line_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, lnf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM inter_provincial_line WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    line_name = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                    if not line_name or line_name == '区外联络线':
                        continue
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 2
                        if ci < len(row):
                            val = row.iloc[ci]
                            if pd.notna(val):
                                try:
                                    rows.append((date_dash, line_name, None, float(val), None, period))
                                except (ValueError, TypeError):
                                    pass

                if rows:
                    cur.executemany(
                        "INSERT INTO inter_provincial_line (trade_date, line_name, direction, power_flow, capacity, period) VALUES (?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['inter_provincial_line'] += len(rows)
            except Exception:
                pass

        # --- 输电通道可用容量 → transmission_channel ---
        channel_files = [f for f in files if '输电通道可用容量' in f and f.endswith('.xls')]
        for cf in channel_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, cf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM transmission_channel WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    name = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                    cap = row.iloc[2] if pd.notna(row.iloc[2]) else None
                    if not name or name == '通道名称':
                        continue
                    try:
                        rows.append((date_dash, name, None, float(cap), None, 'daily'))
                    except (ValueError, TypeError):
                        pass

                if rows:
                    cur.executemany(
                        "INSERT INTO transmission_channel (trade_date, channel_name, power_flow, capacity, utilization_rate, period) VALUES (?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['transmission_channel'] += len(rows)
            except Exception:
                pass

        # --- 机组检修信息 → maintenance_plan ---
        maint_files = [f for f in files if '机组检修信息' in f and f.endswith('.xls')]
        for mf in maint_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, mf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM maintenance_plan WHERE trade_date=? AND description='total_capacity'", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    cap = row.iloc[2] if len(row) > 2 and pd.notna(row.iloc[2]) else None
                    if cap:
                        conn.execute(
                            "INSERT INTO maintenance_plan (trade_date, unit_name, start_time, end_time, description, status) VALUES (?,?,?,?,?,?)",
                            (date_dash, '南方区域', None, None, 'total_capacity', str(cap))
                        )
                        table_stats['maintenance_plan'] += 1
            except Exception:
                pass

    conn.commit()
    for t, cnt in table_stats.items():
        log(f"  {t}: +{cnt} rows")

# ============================================================
# P0-3: Import 实时运行信息 - section constraints, peak reserve, etc.
# ============================================================
def import_realtime_extras():
    """Import section_constraint, peak_reserve_info, stability_section_info,
    transmission_channel (actual), line_transformer_load from 实时运行信息查询."""
    base = os.path.join(POWPER, '实时运行信息查询', 'extracted')
    if not os.path.exists(base):
        return

    folders = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])

    table_stats = {
        'section_constraint': 0,
        'peak_reserve_info': 0,
        'stability_section_info': 0,
        'transmission_channel': 0,
        'line_transformer_load': 0,
        'maintenance_plan': 0,
    }

    for folder in folders:
        date_key = extract_date_from_filename(folder)
        if not date_key:
            continue
        date_dash = extract_date_dash(date_key)

        output_dir = os.path.join(base, folder, 'output')
        if not os.path.exists(output_dir):
            continue
        files = os.listdir(output_dir)

        # --- 实际输电断面约束 → section_constraint ---
        sc_files = [f for f in files if '实际输电断面约束' in f and f.endswith('.xls')]
        for scf in sc_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, scf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM section_constraint WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    section = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                    dtype = str(row.iloc[2]) if pd.notna(row.iloc[2]) else None
                    region = str(row.iloc[3]) if pd.notna(row.iloc[3]) else None
                    if not section or section == '通道名称':
                        continue
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 4
                        if ci < len(row):
                            val = row.iloc[ci]
                            if pd.notna(val):
                                try:
                                    rows.append((date_dash, 'realtime', section, dtype, float(val), None, None, period, region))
                                except (ValueError, TypeError):
                                    pass

                if rows:
                    cur.executemany(
                        "INSERT INTO section_constraint (trade_date, market_type, section_name, constraint_type, limit_value, actual_value, congestion_degree, period, region) VALUES (?,?,?,?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['section_constraint'] += len(rows)
            except Exception:
                pass

        # --- 高峰正备用信息 → peak_reserve_info ---
        pr_files = [f for f in files if '高峰正备用' in f and f.endswith('.xls')]
        for prf in pr_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, prf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM peak_reserve_info WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    region = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
                    date_val = str(row.iloc[2]) if pd.notna(row.iloc[2]) else date_dash
                    cap = row.iloc[3] if pd.notna(row.iloc[3]) else None
                    if cap:
                        try:
                            rows.append((date_dash, 'peak', '正备用', float(cap), 'MW', region))
                        except (ValueError, TypeError):
                            pass

                if rows:
                    cur.executemany(
                        "INSERT INTO peak_reserve_info (trade_date, period, reserve_type, reserve_value, unit, region) VALUES (?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['peak_reserve_info'] += len(rows)
            except Exception:
                pass

        # --- 稳定断面信息 → stability_section_info ---
        ss_files = [f for f in files if '稳定断面信息' in f and f.endswith('.xls')]
        for ssf in ss_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, ssf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM stability_section_info WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    name = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
                    rate = row.iloc[2] if pd.notna(row.iloc[2]) else None
                    if name and rate:
                        try:
                            rows.append((date_dash, name, None, None, None, float(rate)))
                        except (ValueError, TypeError):
                            pass

                if rows:
                    cur.executemany(
                        "INSERT INTO stability_section_info (trade_date, section_name, direction, stability_limit, unit, max_load_rate) VALUES (?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['stability_section_info'] += len(rows)
            except Exception:
                pass

        # --- 重要通道实际输电 → transmission_channel ---
        tc_files = [f for f in files if '重要通道实际输电' in f and f.endswith('.xls')]
        for tcf in tc_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, tcf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM transmission_channel WHERE trade_date=? AND period != 'daily'", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    name = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                    if not name or name == '通道名称':
                        continue
                    for pi, period in enumerate(PERIODS_96):
                        ci = pi + 3
                        if ci < len(row):
                            val = row.iloc[ci]
                            if pd.notna(val):
                                try:
                                    rows.append((date_dash, name, float(val), None, None, period))
                                except (ValueError, TypeError):
                                    pass

                if rows:
                    cur.executemany(
                        "INSERT INTO transmission_channel (trade_date, channel_name, power_flow, capacity, utilization_rate, period) VALUES (?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['transmission_channel'] += len(rows)
            except Exception:
                pass

        # --- 检修（含改造）执行计划 → maintenance_plan ---
        mp_files = [f for f in files if '检修' in f and '改造' in f and f.endswith('.xls')]
        for mpf in mp_files:
            try:
                df = pd.read_excel(os.path.join(output_dir, mpf))
                if len(df) == 0:
                    continue
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM maintenance_plan WHERE trade_date=? AND description='检修执行'", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                rows = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or str(row.iloc[0]) == '序号':
                        continue
                    region = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
                    voltage = str(row.iloc[2]) if pd.notna(row.iloc[2]) else ''
                    equip = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ''
                    etype = str(row.iloc[4]) if pd.notna(row.iloc[4]) else ''
                    plan_start = str(row.iloc[5]) if pd.notna(row.iloc[5]) else ''
                    plan_end = str(row.iloc[6]) if pd.notna(row.iloc[6]) else ''
                    actual_start = str(row.iloc[7]) if len(row) > 7 and pd.notna(row.iloc[7]) else ''
                    actual_end = str(row.iloc[8]) if len(row) > 8 and pd.notna(row.iloc[8]) else ''

                    rows.append((date_dash, equip, plan_start, plan_end, '检修执行', etype, voltage, actual_start, actual_end))

                if rows:
                    cur.executemany(
                        "INSERT INTO maintenance_plan (trade_date, unit_name, start_time, end_time, description, status, voltage_level, actual_start_time, actual_end_time) VALUES (?,?,?,?,?,?,?,?,?)",
                        rows
                    )
                    table_stats['maintenance_plan'] += len(rows)
            except Exception:
                pass

    conn.commit()
    for t, cnt in table_stats.items():
        log(f"  {t}: +{cnt} rows")

# ============================================================
# P0-4: Import node prices (RT and DA)
# ============================================================
def import_node_prices():
    """Import 96-period node prices from XLSX files.
    Sources: powper-data/实时节点电价/ and powper-data/日前节点电价/
    Also: top-level 实时节点电价/, 日前节点电价2-3月/
    """
    configs = [
        ('realtime_node_price_96', [
            os.path.join(POWPER, '实时节点电价'),
            os.path.join(BASE, '实时节点电价'),
        ]),
        ('day_ahead_node_price_96', [
            os.path.join(POWPER, '日前节点电价'),
            os.path.join(BASE, '日前节点电价2-3月'),
        ]),
    ]

    for table, dirs in configs:
        total = 0
        skipped = 0

        for d in dirs:
            if not os.path.exists(d):
                continue

            xlsx_files = sorted([f for f in os.listdir(d) if '节点电价' in f and f.endswith('.xlsx')])
            log(f"  {table} from {os.path.basename(d)}: {len(xlsx_files)} files")

            for fname in xlsx_files:
                date_key = extract_date_from_filename(fname)
                if not date_key:
                    continue
                date_dash = extract_date_dash(date_key)

                # Check existing
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    skipped += 1
                    continue

                try:
                    df = pd.read_excel(os.path.join(d, fname))
                    if len(df) < 2:
                        continue

                    # Row 0 is header: 地区 | 节点名称 | 00:00 | 00:15 | ...
                    # Data starts from row 1
                    rows = []
                    for _, row in df.iterrows():
                        region = str(row.iloc[0]) if pd.notna(row.iloc[0]) else None
                        node = str(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                        if not node or node == '节点名称' or region == '地区':
                            continue

                        for pi, period in enumerate(PERIODS_96):
                            ci = pi + 2
                            if ci < len(row):
                                val = row.iloc[ci]
                                if pd.notna(val):
                                    try:
                                        rows.append((date_dash, region, node, period, float(val)))
                                    except (ValueError, TypeError):
                                        pass

                    if rows:
                        cur.executemany(
                            f"INSERT INTO {table} (trade_date, region, node_name, period, price) VALUES (?,?,?,?,?)",
                            rows
                        )
                        total += len(rows)

                except Exception as e:
                    pass

            conn.commit()

        log(f"  {table}: +{total} rows inserted, {skipped} dates skipped")

# ============================================================
# P0-5: Import demand data (RT and DA)
# ============================================================
def import_demand():
    """Import realtime_demand and day_ahead_demand from XLS files."""
    configs = [
        ('realtime_demand', '实时交易结果', [
            os.path.join(POWPER, '实时交易结果用电册'),
        ]),
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
            xls_files = sorted([f for f in os.listdir(d)
                              if keyword in f and f.endswith('.xls') and '(1)' not in f])
            log(f"  {table} from {os.path.basename(d)}: {len(xls_files)} files")

            for fname in xls_files:
                date_key = extract_date_from_filename(fname)
                if not date_key:
                    continue
                date_dash = extract_date_dash(date_key)

                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE trade_date=?", (date_dash,))
                if cur.fetchone()[0] > 0:
                    continue

                try:
                    df = pd.read_excel(os.path.join(d, fname))
                    if len(df) < 2:
                        continue

                    rows = []
                    for _, row in df.iterrows():
                        period = str(row.iloc[0]) if pd.notna(row.iloc[0]) else None
                        price_val = row.iloc[1] if pd.notna(row.iloc[1]) else None
                        if not period or '时刻' in str(period):
                            continue
                        if price_val is not None:
                            try:
                                rows.append((date_dash, period, float(price_val), None))
                            except (ValueError, TypeError):
                                pass

                    if rows:
                        cur.executemany(
                            f"INSERT INTO {table} (trade_date, period, demand, price) VALUES (?,?,?,?)",
                            rows
                        )
                        total += len(rows)

                except Exception:
                    pass

            conn.commit()
        log(f"  {table}: +{total} rows")

# ============================================================
# MAIN EXECUTION
# ============================================================
if __name__ == '__main__':
    log("=" * 60)
    log("ETL Import Start - 10 months data → power_market_v2.db")
    log("=" * 60)

    log("\n[P0-1] Importing 实时运行信息 (hourly_load/gen/nonmarket/renewable/hydro)...")
    import_realtime_operation()

    log("\n[P0-2] Importing 信息披露 (reserve/forecast/maintenance/units)...")
    import_disclosure()

    log("\n[P0-3] Importing 实时运行信息 extras (sections/constraints/channels)...")
    import_realtime_extras()

    log("\n[P0-4] Importing node prices (96-period RT & DA)...")
    import_node_prices()

    log("\n[P0-5] Importing demand data (RT & DA)...")
    import_demand()

    # Final summary
    log("\n" + "=" * 60)
    log("FINAL DATABASE SUMMARY")
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
        # Get date range
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info([{t}])").fetchall()]
        date_col = 'date_key' if 'date_key' in cols else ('trade_date' if 'trade_date' in cols else None)
        if date_col and cnt > 0:
            cur.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM [{t}]")
            dr = cur.fetchone()
            status = "✅" if cnt > 0 else "⭕"
            log(f"  {status} {t}: {cnt:>8,} rows  ({dr[0]} ~ {dr[1]})")
        else:
            status = "⭕" if cnt == 0 else "✅"
            log(f"  {status} {t}: {cnt:>8,} rows")

    log(f"\n  TOTAL: {total_rows:,} rows across {len(tables)} tables")
    conn.close()
    log("ETL Import Complete!")
