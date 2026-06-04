#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速测试：仅预测3-19一天的小时粒度结果"""
import sqlite3, warnings
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

warnings.filterwarnings('ignore')

from config import DB

print("快速测试: 3-19 小时粒度预测")
conn = sqlite3.connect(DB)

# Load price (96点)
price_96 = pd.read_sql(
    """SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
       FROM realtime_node_price_96
       WHERE node_name = '__avg__'
       ORDER BY trade_date, period""",
    conn
)
price_96['date'] = pd.to_datetime(price_96['date_key'], format='%Y%m%d')
price_96['hour'] = price_96['period'].str[:2].astype(int)

# Load load/renew/hydro
load = pd.read_sql("SELECT date_key, period, load FROM hourly_load WHERE region='全区域' ORDER BY date_key, period", conn)
load['hour'] = load['period'].str[:2].astype(int)

# Aggregate to hourly
price_h = price_96.groupby(['date_key', 'hour']).agg(rt_price=('rt_price', 'mean'), date=('date', 'first')).reset_index()
load_h = load.groupby('date_key', level=0).agg(load=('load', 'first')).reset_index() if 'hour' not in load.columns else load

print(f"Price hourly rows: {len(price_h)}")
print(f"Load data rows: {len(load)}")

# Simple test: just check data availability
print("\n3-19数据检查:")
test_date = '20260319'
price_319 = price_h[price_h['date_key'] == test_date]
load_319 = load[load['date_key'] == test_date]

print(f"  Price: {len(price_319)} rows (expect 24)")
print(f"  Load:  {len(load_319)} rows (expect 24)")
print(f"  Price sample: {price_319['rt_price'].values[:6]}")
print(f"  Load sample:  {load_319['load'].values[:6]}")

conn.close()
print("\n✅ 数据读取成功")
