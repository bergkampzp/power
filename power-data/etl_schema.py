#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL Step 1: Create extended database schema
- Copy original tables
- Add missing fields to existing tables
- Create new tables for 96-period node prices, reserves, constraints, etc.
"""
import sqlite3, shutil, os

from config import DB_PATH

# SRC_DB: 旧版 reference database (不再存在)
# DST_DB: 新版 power_market_v2.db
SRC_DB = DB_PATH
DST_DB = DB_PATH

# Copy original DB as starting point
if os.path.exists(DST_DB):
    os.remove(DST_DB)
shutil.copy2(SRC_DB, DST_DB)
print(f"Copied {SRC_DB} -> {DST_DB}")

conn = sqlite3.connect(DST_DB)
cur = conn.cursor()

# ============================================================
# 1. Extend existing tables with missing fields
# ============================================================
extensions = {
    # system_reserve: add region, reserve_type if not present
    'system_reserve': [
        ("region", "TEXT"),
    ],
    # inter_provincial_line: add line_name
    'inter_provincial_line': [
        ("line_name", "TEXT"),
    ],
    # maintenance_plan: add voltage_level, actual_start, actual_end, equipment_type_detail
    'maintenance_plan': [
        ("voltage_level", "TEXT"),
        ("actual_start_time", "TEXT"),
        ("actual_end_time", "TEXT"),
    ],
    # unit_status: add must_run_type, outage_type
    'unit_status': [
        ("must_run_type", "TEXT"),
        ("outage_type", "TEXT"),
    ],
    # peak_reserve_info: add region
    'peak_reserve_info': [
        ("region", "TEXT"),
    ],
    # stability_section_info: add max_load_rate
    'stability_section_info': [
        ("max_load_rate", "REAL"),
    ],
    # section_constraint: add region
    'section_constraint': [
        ("region", "TEXT"),
    ],
}

for table, cols in extensions.items():
    # Get existing columns
    cur.execute(f"PRAGMA table_info([{table}])")
    existing = {row[1] for row in cur.fetchall()}
    for col_name, col_type in cols:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE [{table}] ADD COLUMN [{col_name}] {col_type}")
            print(f"  ALTER {table}: +{col_name} ({col_type})")
        else:
            print(f"  SKIP {table}.{col_name} (exists)")

# ============================================================
# 2. Create new tables
# ============================================================
new_tables = """
-- 96-period realtime node price (per node per period)
CREATE TABLE IF NOT EXISTS realtime_node_price_96 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    region TEXT,
    node_name TEXT NOT NULL,
    period TEXT NOT NULL,
    price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 96-period day-ahead node price
CREATE TABLE IF NOT EXISTS day_ahead_node_price_96 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    region TEXT,
    node_name TEXT NOT NULL,
    period TEXT NOT NULL,
    price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Unit output constraints (96-period)
CREATE TABLE IF NOT EXISTS unit_output_constraint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    region TEXT,
    plant_name TEXT,
    unit_name TEXT,
    constraint_type TEXT,
    period TEXT,
    value REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cross-province priority plan limits
CREATE TABLE IF NOT EXISTS cross_province_limit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    category_name TEXT,
    lower_limit REAL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Mid-long term cross-province plan
CREATE TABLE IF NOT EXISTS mid_long_term_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    section_name TEXT,
    period TEXT,
    sender_output REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Non-market renewable capacity
CREATE TABLE IF NOT EXISTS nonmarket_renewable_cap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    region TEXT,
    capacity_mw REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market dispatch intervention
CREATE TABLE IF NOT EXISTS market_dispatch_intervention (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    region TEXT,
    name TEXT,
    intervention_start TEXT,
    intervention_end TEXT,
    before_max REAL,
    before_min REAL,
    after_max REAL,
    after_min REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Price weight info
CREATE TABLE IF NOT EXISTS price_weight_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    region TEXT,
    plant_name TEXT,
    unit_name TEXT,
    time_period TEXT,
    segment_no INTEGER,
    start_capacity REAL,
    end_capacity REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Realtime hourly price (extend: add region field for clarity)
-- Already has: id, date_key, period, hour, rt_price

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_rt96_date_node ON realtime_node_price_96(trade_date, node_name);
CREATE INDEX IF NOT EXISTS idx_rt96_date_period ON realtime_node_price_96(trade_date, period);
CREATE INDEX IF NOT EXISTS idx_da96_date_node ON day_ahead_node_price_96(trade_date, node_name);
CREATE INDEX IF NOT EXISTS idx_da96_date_period ON day_ahead_node_price_96(trade_date, period);
CREATE INDEX IF NOT EXISTS idx_hourly_load_date ON hourly_load(date_key, period);
CREATE INDEX IF NOT EXISTS idx_hourly_gen_date ON hourly_generation(date_key, period);
CREATE INDEX IF NOT EXISTS idx_hourly_renew_date ON hourly_renewable(date_key, period);
CREATE INDEX IF NOT EXISTS idx_hourly_hydro_date ON hourly_hydro(date_key, period);
CREATE INDEX IF NOT EXISTS idx_rt_price_date ON realtime_hourly_price(date_key, period);
"""

cur.executescript(new_tables)
print("  Executed all CREATE TABLE/INDEX statements")
conn.commit()

conn.commit()

# Verify
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nTotal tables: {len(tables)}")
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{t}]")
    cnt = cur.fetchone()[0]
    cur.execute(f"PRAGMA table_info([{t}])")
    cols = [r[1] for r in cur.fetchall()]
    print(f"  {t}: {cnt} rows, cols={cols}")

conn.close()
print("\nSchema creation complete!")
