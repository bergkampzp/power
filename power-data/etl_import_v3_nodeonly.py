#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL v3: Fast node price import only
- 漫湾 (4节点): 保留96时段详细数据
- 其他节点: 按96时段求平均，只保1条均价线
- 全网: avg/min/max (3条线)
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
MANWAN_NODES = ['漫湾厂.220kVⅠ母', '漫湾厂.220kVⅡ母', '漫湾厂.500kV#1M', '漫湾厂.500kV#2M']

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def extract_date(fname):
    m = re.search(r'(\d{4})[-]?(\d{2})[-]?(\d{2})', fname)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return None

def date_dash(dk):
    if len(dk) == 8:
        return f"{dk[:4]}-{dk[4:6]}-{dk[6:8]}"
    return dk

# ============================================================
# Node Price Import - SIMPLIFIED
# ============================================================
def import_node_prices_v3():
    """
    漫湾: 4节点 × 96时段
    其他: 1条聚合均价线 × 96时段
    全网: 3条(avg/min/max) × 96时段
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

            for fi, fname in enumerate(xlsx_files):
                dk = extract_date(fname)
                if not dk:
                    continue
                dd = date_dash(dk)

                # Skip if exists
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE trade_date=?", (dd,))
                if cur.fetchone()[0] > 0:
                    skipped += 1
                    continue

                try:
                    df = pd.read_excel(os.path.join(d, fname))
                    if len(df) < 2:
                        continue

                    # Check period columns
                    n_periods = min(96, len(df.columns) - 2)
                    if n_periods < 1:
                        continue

                    rows = []

                    # 1️⃣ Extract 漫湾 nodes (detail)
                    for _, row in df.iterrows():
                        node = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        region = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
                        if node in MANWAN_NODES:
                            for pi in range(n_periods):
                                ci = pi + 2
                                val = row.iloc[ci]
                                if pd.notna(val):
                                    try:
                                        rows.append((dd, region, node, PERIODS_96[pi], float(val)))
                                    except (ValueError, TypeError, IndexError):
                                        pass

                    # 2️⃣ 其他节点: 按时段求平均 (other_nodes_avg)
                    other_data = []
                    for _, row in df.iterrows():
                        node = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        if node == '节点名称' or node in MANWAN_NODES or node == '':
                            continue
                        vals = []
                        for pi in range(n_periods):
                            ci = pi + 2
                            v = row.iloc[ci]
                            try:
                                vals.append(float(v) if pd.notna(v) else np.nan)
                            except (ValueError, TypeError):
                                vals.append(np.nan)
                        other_data.append(vals)

                    if other_data:
                        mat = np.array(other_data)
                        for pi in range(n_periods):
                            col = mat[:, pi]
                            valid = col[~np.isnan(col)]
                            if len(valid) > 0:
                                # 其他节点只保留平均价
                                rows.append((dd, '云南', '__other_nodes_avg__', PERIODS_96[pi], float(np.mean(valid))))

                    # 3️⃣ 全网统计 (avg/min/max from ALL nodes)
                    all_data = []
                    for _, row in df.iterrows():
                        node = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                        if node == '节点名称' or node == '':
                            continue
                        vals = []
                        for pi in range(n_periods):
                            ci = pi + 2
                            v = row.iloc[ci]
                            try:
                                vals.append(float(v) if pd.notna(v) else np.nan)
                            except (ValueError, TypeError):
                                vals.append(np.nan)
                        all_data.append(vals)

                    if all_data:
                        mat = np.array(all_data)
                        for pi in range(n_periods):
                            col = mat[:, pi]
                            valid = col[~np.isnan(col)]
                            if len(valid) > 0:
                                rows.append((dd, '全网', '__all_avg__', PERIODS_96[pi], float(np.mean(valid))))
                                rows.append((dd, '全网', '__all_min__', PERIODS_96[pi], float(np.min(valid))))
                                rows.append((dd, '全网', '__all_max__', PERIODS_96[pi], float(np.max(valid))))

                    # Insert all rows
                    if rows:
                        cur.executemany(
                            f"INSERT INTO {table} (trade_date, region, node_name, period, price) VALUES (?,?,?,?,?)",
                            rows
                        )
                        total += len(rows)

                except Exception as e:
                    pass

                # Commit every 20 files
                if (fi + 1) % 20 == 0:
                    conn.commit()
                    log(f"    progress: {fi+1}/{len(xlsx_files)} ({total} rows)")

            conn.commit()

        log(f"  {table}: +{total} rows, {skipped} skipped")
        log(f"    Data structure: 漫湾(4节点×96) + 其他(1均价×96) + 全网(3统计×96)")

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    log("=" * 60)
    log("ETL v3: Fast Node Price Import (Simplified)")
    log("=" * 60)
    log("\nStrategy:")
    log("  漫湾: 4个母线 × 96时段 (详细)")
    log("  其他: 1条均价线 × 96时段 (聚合)")
    log("  全网: 3条统计线 × 96时段 (avg/min/max)")
    log("=" * 60)

    log("\n[1/1] 节点电价导入...")
    import_node_prices_v3()

    # Summary
    log("\n" + "=" * 60)
    log("DATABASE SUMMARY")
    log("=" * 60)

    cur = conn.cursor()

    for table in ['realtime_node_price_96', 'day_ahead_node_price_96']:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        cnt = cur.fetchone()[0]
        if cnt > 0:
            cur.execute(f"SELECT MIN(trade_date), MAX(trade_date) FROM {table}")
            dr = cur.fetchone()
            cur.execute(f"SELECT DISTINCT node_name FROM {table} ORDER BY node_name")
            nodes = [r[0] for r in cur.fetchall()]
            log(f"\n✅ {table}: {cnt:,} rows")
            log(f"   日期范围: {dr[0]} ~ {dr[1]}")
            log(f"   节点数: {len(nodes)}")
            log(f"   节点列表: {', '.join(nodes[:10])}{'...' if len(nodes) > 10 else ''}")

    conn.close()
    log("\n✅ ETL v3 Complete!")
    log("\n后续导入：需要时运行完整ETL或增量导入其他表")
