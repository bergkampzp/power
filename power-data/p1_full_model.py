#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1 Full Model - 4-Stage Optimization
=====================================
Stage 1: Data governance + feature enrichment (congestion, reserve, maintenance, forecast error)
Stage 2: DA-RT spread model (predict RT-DA deviation instead of RT directly)
Stage 5: Similar-day screening (fuzzy clustering)
Stage 4: Quantile regression (probabilistic prediction with P10/P50/P90)

Walk-forward: 3-19 ~ 3-22 (4 days)
"""
import sqlite3, warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

warnings.filterwarnings('ignore')

from config import DB, OUT_DIR

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

print("=" * 70)
print("P1 Full Model - Stage 1+2+5+4 Optimization")
print("=" * 70)

# ============================================================
# 1. Load raw 96-point data
# ============================================================
print("\n[1/6] Loading data...")
conn = sqlite3.connect(DB)

price_96 = pd.read_sql(
    """SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
       FROM realtime_node_price_96 WHERE node_name = '__avg__'
       ORDER BY trade_date, period""", conn)
price_96['date'] = pd.to_datetime(price_96['date_key'], format='%Y%m%d')
price_96['hour'] = price_96['period'].str[:2].astype(int)

load_96 = pd.read_sql(
    "SELECT date_key, period, load FROM hourly_load WHERE region='云南' ORDER BY date_key, period", conn)
load_96['hour'] = load_96['period'].str[:2].astype(int)

renew_96 = pd.read_sql(
    "SELECT date_key, period, output FROM hourly_renewable WHERE region='云南' ORDER BY date_key, period", conn)
renew_96['hour'] = renew_96['period'].str[:2].astype(int)

hydro_96 = pd.read_sql(
    "SELECT date_key, period, output FROM hourly_hydro WHERE region='云南' ORDER BY date_key, period", conn)
hydro_96['hour'] = hydro_96['period'].str[:2].astype(int)

manwan_da_96 = pd.read_sql(
    """SELECT trade_date, period, AVG(price) as manwan_da_price
       FROM day_ahead_node_price_96
       WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
       GROUP BY trade_date, period ORDER BY trade_date, period""", conn)
manwan_da_96['hour'] = manwan_da_96['period'].str[:2].astype(int)

grid_da_96 = pd.read_sql(
    """SELECT trade_date, period, price as grid_da_avg
       FROM day_ahead_node_price_96 WHERE node_name = '__all_avg__'
       ORDER BY trade_date, period""", conn)
grid_da_96['hour'] = grid_da_96['period'].str[:2].astype(int)

# Forecast data
renew_fc_96 = pd.read_sql(
    """SELECT forecast_date as date_key, period, forecast_mw as renew_fc
       FROM renewable_forecast WHERE region='云南' AND category='总计'
       ORDER BY forecast_date, period""", conn)
renew_fc_96['hour'] = renew_fc_96['period'].str[:2].astype(int)

hydro_fc = pd.read_sql(
    """SELECT forecast_date as date_key, avg_output_mw as hydro_fc_avg
       FROM hydro_forecast WHERE region='云南' ORDER BY forecast_date""", conn)
hydro_fc = hydro_fc.groupby('date_key').agg(hydro_fc_avg=('hydro_fc_avg', 'mean')).reset_index()

gen_fc_96 = pd.read_sql(
    """SELECT forecast_date as date_key, period, forecast_mw as gen_fc
       FROM generation_forecast ORDER BY forecast_date, period""", conn)
gen_fc_96['hour'] = gen_fc_96['period'].str[:2].astype(int)

load_fc_96 = pd.read_sql(
    """SELECT trade_date as td, period, forecast_load as load_fc
       FROM load_forecast WHERE region='云南' ORDER BY trade_date, period""", conn)
load_fc_96['date_key'] = load_fc_96['td'].str.replace('-', '')
load_fc_96['hour'] = load_fc_96['period'].str[:2].astype(int)

# ── STAGE 1 NEW: Congestion, Reserve, Maintenance, Transmission ──

# Section constraint (断面约束) - aggregate congestion per day
section = pd.read_sql(
    """SELECT trade_date, section_name, constraint_type, limit_value, period
       FROM section_constraint ORDER BY trade_date, period""", conn)
section['hour'] = section['period'].str[:2].astype(int)

# System reserve (云南备用)
reserve = pd.read_sql(
    """SELECT trade_date, period, reserve_type, reserve_value
       FROM system_reserve WHERE region='云南'
       ORDER BY trade_date, period""", conn)
reserve['hour'] = reserve['period'].str[:2].astype(int)

# Maintenance plan (检修容量) - count active maintenance per day
maint = pd.read_sql(
    """SELECT trade_date, COUNT(*) as maint_count FROM maintenance_plan
       GROUP BY trade_date ORDER BY trade_date""", conn)

# Transmission channel (输电通道容量)
channel = pd.read_sql(
    """SELECT trade_date, channel_name, capacity FROM transmission_channel
       ORDER BY trade_date""", conn)

# Inter-provincial line (省间联络线潮流)
interline = pd.read_sql(
    """SELECT trade_date, line_name, power_flow, period FROM inter_provincial_line
       ORDER BY trade_date, period""", conn)
interline['hour'] = interline['period'].str[:2].astype(int)

conn.close()
print("  Data loaded.")

# ============================================================
# 2. Aggregate to hourly (96 -> 24)
# ============================================================
print("[2/6] Aggregate to hourly...")

price_hourly = price_96.groupby(['date_key', 'hour']).agg(
    rt_price=('rt_price', 'mean'), date=('date', 'first')).reset_index()
price_hourly['period'] = price_hourly['hour'].apply(lambda h: f"{h:02d}:00")

load_h = load_96.groupby(['date_key', 'hour']).agg(load=('load', 'mean')).reset_index()
renew_h = renew_96.groupby(['date_key', 'hour']).agg(renewable=('output', 'mean')).reset_index()
hydro_h = hydro_96.groupby(['date_key', 'hour']).agg(hydro=('output', 'mean')).reset_index()

manwan_h = manwan_da_96.groupby(['trade_date', 'hour']).agg(
    manwan_da_price=('manwan_da_price', 'mean')).reset_index()
manwan_h['date_key'] = pd.to_datetime(manwan_h['trade_date']).dt.strftime('%Y%m%d')

grid_h = grid_da_96.groupby(['trade_date', 'hour']).agg(
    grid_da_avg=('grid_da_avg', 'mean')).reset_index()
grid_h['date_key'] = pd.to_datetime(grid_h['trade_date']).dt.strftime('%Y%m%d')

renew_fc_h = renew_fc_96.groupby(['date_key', 'hour']).agg(renew_fc=('renew_fc', 'mean')).reset_index()
gen_fc_h = gen_fc_96.groupby(['date_key', 'hour']).agg(gen_fc=('gen_fc', 'mean')).reset_index()
load_fc_h = load_fc_96.groupby(['date_key', 'hour']).agg(load_fc=('load_fc', 'mean')).reset_index()

# ── STAGE 1: Aggregate new features to hourly ──

# Section constraint: number of binding sections per hour, total limit
section['date_key'] = section['trade_date'].str.replace('-', '')
section_h = section.groupby(['date_key', 'hour']).agg(
    n_sections=('section_name', 'nunique'),
    total_limit=('limit_value', 'sum'),
    avg_limit=('limit_value', 'mean'),
).reset_index()

# Reserve: pivot to get up/down per hour
reserve['date_key'] = reserve['trade_date'].str.replace('-', '')
reserve_up = reserve[reserve['reserve_type'].str.contains('正')].groupby(
    ['date_key', 'hour']).agg(reserve_up=('reserve_value', 'mean')).reset_index()
reserve_down = reserve[reserve['reserve_type'].str.contains('负')].groupby(
    ['date_key', 'hour']).agg(reserve_down=('reserve_value', 'mean')).reset_index()

# Maintenance: daily count
maint['date_key'] = maint['trade_date'].str.replace('-', '')

# Transmission channel: pivot to get Yunnan-related capacity
channel['date_key'] = channel['trade_date'].str.replace('-', '')
# Sum total transmission capacity per day
channel_daily = channel.groupby('date_key').agg(
    total_channel_cap=('capacity', 'sum')).reset_index()

# Inter-provincial line: hourly power flow
interline['date_key'] = interline['trade_date'].str.replace('-', '')
interline_h = interline.groupby(['date_key', 'hour']).agg(
    total_flow=('power_flow', 'sum'),
    n_lines=('line_name', 'nunique'),
).reset_index()

# ── Merge everything ──
df = price_hourly[['date_key', 'period', 'hour', 'rt_price', 'date']].copy()
df = df.merge(load_h[['date_key', 'hour', 'load']], on=['date_key', 'hour'], how='left')
df = df.merge(renew_h[['date_key', 'hour', 'renewable']], on=['date_key', 'hour'], how='left')
df = df.merge(hydro_h[['date_key', 'hour', 'hydro']], on=['date_key', 'hour'], how='left')
df.rename(columns={'load': 'total_load'}, inplace=True)
df = df.merge(manwan_h[['date_key', 'hour', 'manwan_da_price']], on=['date_key', 'hour'], how='left')
df = df.merge(grid_h[['date_key', 'hour', 'grid_da_avg']], on=['date_key', 'hour'], how='left')

# Forecast features
df = df.merge(renew_fc_h[['date_key', 'hour', 'renew_fc']], on=['date_key', 'hour'], how='left')
df = df.merge(gen_fc_h[['date_key', 'hour', 'gen_fc']], on=['date_key', 'hour'], how='left')
df = df.merge(load_fc_h[['date_key', 'hour', 'load_fc']], on=['date_key', 'hour'], how='left')
df = df.merge(hydro_fc[['date_key', 'hydro_fc_avg']], on='date_key', how='left')

# Stage 1 new features
df = df.merge(section_h[['date_key', 'hour', 'n_sections', 'total_limit', 'avg_limit']],
              on=['date_key', 'hour'], how='left')
df = df.merge(reserve_up[['date_key', 'hour', 'reserve_up']], on=['date_key', 'hour'], how='left')
df = df.merge(reserve_down[['date_key', 'hour', 'reserve_down']], on=['date_key', 'hour'], how='left')
df = df.merge(maint[['date_key', 'maint_count']], on='date_key', how='left')
df = df.merge(channel_daily[['date_key', 'total_channel_cap']], on='date_key', how='left')
df = df.merge(interline_h[['date_key', 'hour', 'total_flow']], on=['date_key', 'hour'], how='left')

# ============================================================
# 3. Build features
# ============================================================
print("[3/6] Building features...")

df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)

# Time
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)

# Seasonal
df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
df['woy_sin'] = np.sin(2 * np.pi * df['week_of_year'] / 52)
df['woy_cos'] = np.cos(2 * np.pi * df['week_of_year'] / 52)
df['is_wet_season'] = df['month'].isin([6, 7, 8, 9, 10]).astype(int)
df['is_transition'] = df['month'].isin([5, 11]).astype(int)
df['quarter'] = df['date'].dt.quarter
df['q1'] = (df['quarter'] == 1).astype(int)
df['q2'] = (df['quarter'] == 2).astype(int)
df['q3'] = (df['quarter'] == 3).astype(int)
df['q4'] = (df['quarter'] == 4).astype(int)
df['wet_x_hour'] = df['is_wet_season'] * df['hour']
df['wet_x_hour_sin'] = df['is_wet_season'] * df['hour_sin']
df['day_of_year'] = df['date'].dt.dayofyear
df['doy_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
df['doy_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)

# Gap
df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)

# Forecast-derived
df['fc_gap'] = df['load_fc'].fillna(0) - df['renew_fc'].fillna(0) - df['hydro_fc_avg'].fillna(0)
df['renew_fc_vs_lag'] = df['renew_fc'].fillna(0) - df['renewable'].fillna(0)
df['load_fc_vs_lag'] = df['load_fc'].fillna(0) - df['total_load'].fillna(0)
df['renew_fc_share'] = np.where(df['gen_fc'] > 0, df['renew_fc'].fillna(0) / df['gen_fc'], 0)

# ── STAGE 1: New derived features ──
# Reserve ratio (reserve_up / load)
df['reserve_ratio'] = np.where(df['total_load'] > 0,
    df['reserve_up'].fillna(0) / df['total_load'], 0)
# Channel capacity change (vs D-1, using lag)
# Interline flow ratio
df['flow_to_cap'] = np.where(df['total_channel_cap'] > 0,
    df['total_flow'].fillna(0) / df['total_channel_cap'], 0)

# ── STAGE 1.4: Forecast error lag (D-1 forecast error) ──
# This will be computed after lags are set up

# Sort for lag
df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)

# Lag features
def add_lag_by_hour(df, col, new_col, n_days):
    df[new_col] = df.groupby('hour')[col].shift(n_days)
    return df

for lag in [1, 2, 3, 7]:
    df = add_lag_by_hour(df, 'rt_price', f'price_lag_{lag}d', lag)

for lag in [1, 2]:
    df = add_lag_by_hour(df, 'total_load', f'load_lag_{lag}d', lag)
    df = add_lag_by_hour(df, 'renewable', f'renew_lag_{lag}d', lag)

df = add_lag_by_hour(df, 'hydro', 'hydro_lag_1d', 1)
df = add_lag_by_hour(df, 'gap', 'gap_lag_1d', 1)
df = add_lag_by_hour(df, 'gap', 'gap_lag_2d', 2)

# Stage 1 lags
df = add_lag_by_hour(df, 'total_channel_cap', 'channel_cap_lag1d', 1)
df['channel_cap_change'] = df['total_channel_cap'].fillna(0) - df['channel_cap_lag1d'].fillna(0)
df = add_lag_by_hour(df, 'maint_count', 'maint_lag1d', 1)
df['maint_change'] = df['maint_count'].fillna(0) - df['maint_lag1d'].fillna(0)
df = add_lag_by_hour(df, 'reserve_up', 'reserve_up_lag1d', 1)
df['reserve_change'] = df['reserve_up'].fillna(0) - df['reserve_up_lag1d'].fillna(0)

# Stage 1.4: Forecast error D-1 (how wrong was yesterday's renewable forecast?)
# renew_fc is today's forecast; renew_lag_1d is yesterday's actual
# We need: yesterday's forecast vs yesterday's actual
df = add_lag_by_hour(df, 'renew_fc', 'renew_fc_lag1d', 1)
df['renew_fc_error_1d'] = df['renew_fc_lag1d'].fillna(0) - df['renew_lag_1d'].fillna(0)

# Moving averages
for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = (
        df.groupby('hour')['rt_price']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean()))
    df[f'price_std_{w}d'] = (
        df.groupby('hour')['rt_price']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0)))

df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

# Previous-day daily aggregates
daily = df.groupby('date_key').agg(
    daily_avg_price=('rt_price', 'mean'),
    daily_max_price=('rt_price', 'max'),
    daily_min_price=('rt_price', 'min'),
    daily_std_price=('rt_price', 'std'),
    daily_avg_load=('total_load', 'mean'),
    daily_avg_renew=('renewable', 'mean'),
    daily_avg_gap=('gap', 'mean'),
).reset_index()
daily.columns = ['date_key'] + [f'prevday_{c}' for c in daily.columns[1:]]

all_dates = sorted(df['date_key'].unique())
date_shift = {d: all_dates[i-1] if i > 0 else None for i, d in enumerate(all_dates)}
daily['date_key_target'] = daily['date_key'].map(date_shift)
daily = daily.dropna(subset=['date_key_target'])
daily = daily.drop('date_key', axis=1).rename(columns={'date_key_target': 'date_key'})
df = df.merge(daily, on='date_key', how='left')

df['prev_period_to_daily_ratio'] = np.where(
    df['prevday_daily_avg_price'] > 0,
    df['price_lag_1d'] / df['prevday_daily_avg_price'], 1.0)

# Manwan DA
df = add_lag_by_hour(df, 'manwan_da_price', 'manwan_da_lag1d', 1)
df = add_lag_by_hour(df, 'manwan_da_price', 'manwan_da_prev', 1)
df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_prev']

# ── STAGE 2: DA-RT spread target ──
df['da_rt_spread'] = df['rt_price'] - df['grid_da_avg'].fillna(0)

df = df.sort_values(['date_key', 'hour']).reset_index(drop=True)
print(f"  Feature matrix: {len(df)} rows x {df.shape[1]} cols, {df['date_key'].nunique()} days")

# ============================================================
# 4. Feature lists
# ============================================================
FEATURES = [
    # Time (25)
    'hour', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos',
    'month_sin', 'month_cos',
    'week_of_year', 'woy_sin', 'woy_cos',
    'is_wet_season', 'is_transition',
    'q1', 'q2', 'q3', 'q4',
    'wet_x_hour', 'wet_x_hour_sin',
    'day_of_year', 'doy_sin', 'doy_cos',
    # Price history (10)
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d',
    'price_momentum_3d',
    # Load/Renew/Hydro lags (5)
    'load_lag_1d', 'load_lag_2d',
    'renew_lag_1d', 'renew_lag_2d',
    'hydro_lag_1d',
    # Gap history (3)
    'gap_lag_1d', 'gap_lag_2d', 'gap_change',
    # DA prices (4)
    'manwan_da_price', 'manwan_da_lag1d', 'manwan_da_change', 'grid_da_avg',
    # Previous-day stats (8)
    'prevday_daily_avg_price', 'prevday_daily_max_price',
    'prevday_daily_min_price', 'prevday_daily_std_price',
    'prevday_daily_avg_load', 'prevday_daily_avg_renew', 'prevday_daily_avg_gap',
    'prev_period_to_daily_ratio',
    # Forecast (8)
    'renew_fc', 'hydro_fc_avg', 'gen_fc', 'load_fc',
    'fc_gap', 'renew_fc_vs_lag', 'load_fc_vs_lag', 'renew_fc_share',
    # ── STAGE 1 NEW: Grid constraint features (12) ──
    'n_sections', 'total_limit', 'avg_limit',          # congestion
    'reserve_up', 'reserve_down', 'reserve_ratio',     # reserve
    'reserve_change', 'reserve_up_lag1d',               # reserve dynamics
    'maint_count', 'maint_change',                      # maintenance
    'total_channel_cap', 'channel_cap_change',          # transmission capacity
    'total_flow', 'flow_to_cap',                        # inter-provincial flow
    # ── STAGE 1.4: Forecast error ──
    'renew_fc_error_1d',                                # D-1 forecast error
]

feat_active = [f for f in FEATURES if f in df.columns]
print(f"  Active features: {len(feat_active)}/{len(FEATURES)}")

# ============================================================
# 5. STAGE 5: Similar-day screening function
# ============================================================
def find_similar_days(df, test_date, k=30):
    """Find K most similar historical days based on key features."""
    test_dt = pd.to_datetime(test_date, format='%Y%m%d')
    test_row = df[df['date_key'] == test_date]
    if len(test_row) == 0:
        return None

    # Daily profile of the test date (from available D-1 info)
    daily_profiles = df.groupby('date_key').agg(
        avg_load=('total_load', 'mean'),
        avg_renew=('renewable', 'mean'),
        avg_hydro=('hydro', 'mean'),
        avg_gap=('gap', 'mean'),
        is_weekend=('is_weekend', 'first'),
        month=('month', 'first'),
        is_wet=('is_wet_season', 'first'),
        avg_da=('grid_da_avg', 'mean'),
    ).dropna()

    if test_date not in daily_profiles.index:
        return None

    target = daily_profiles.loc[test_date]
    hist = daily_profiles[daily_profiles.index < test_date].copy()
    if len(hist) < k:
        return None

    # Normalize and compute distance
    for col in ['avg_load', 'avg_renew', 'avg_hydro', 'avg_gap', 'avg_da']:
        std = hist[col].std()
        if std > 0:
            hist[f'{col}_n'] = (hist[col] - hist[col].mean()) / std
            target_n = (target[col] - hist[col].mean()) / std
        else:
            hist[f'{col}_n'] = 0
            target_n = 0
        hist[f'{col}_dist'] = (hist[f'{col}_n'] - target_n) ** 2

    # Season match bonus (same wet/dry = distance * 0.5)
    hist['season_match'] = (hist['is_wet'] == target['is_wet']).astype(float)
    hist['weekend_match'] = (hist['is_weekend'] == target['is_weekend']).astype(float)

    # Total distance
    dist_cols = [c for c in hist.columns if c.endswith('_dist')]
    hist['total_dist'] = hist[dist_cols].sum(axis=1)
    # Penalty for different season
    hist['total_dist'] = hist['total_dist'] * np.where(hist['season_match'] == 1, 0.5, 2.0)
    hist['total_dist'] = hist['total_dist'] * np.where(hist['weekend_match'] == 1, 0.8, 1.2)

    similar = hist.nsmallest(k, 'total_dist')
    return similar.index.tolist()

# ============================================================
# 6. Walk-forward: 3-19 ~ 3-22
# ============================================================
print("\n[4/6] Walk-forward prediction (3-19~3-22)...\n")

test_dates = ['20260319', '20260320', '20260321', '20260322']
results = []
results_spread = []

for test_date in test_dates:
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date

    # ── STAGE 5: Similar-day filtering ──
    similar_days = find_similar_days(df, test_date, k=40)
    if similar_days:
        # Use similar days + recent 30 days
        recent_30 = sorted(df[train_mask]['date_key'].unique())[-30:]
        all_train_days = list(set(similar_days) | set(recent_30))
        train_mask_filtered = df['date_key'].isin(all_train_days)
    else:
        train_mask_filtered = train_mask

    X_train = df.loc[train_mask_filtered, feat_active].fillna(0)
    y_train = df.loc[train_mask_filtered, 'rt_price']
    X_test = df.loc[test_mask, feat_active].fillna(0)
    y_test = df.loc[test_mask, 'rt_price']

    valid_train = y_train.notna()
    X_train, y_train = X_train[valid_train], y_train[valid_train]

    if len(X_train) < 24 or len(X_test) == 0:
        print(f"  SKIP {test_date}")
        continue

    n_similar = len(similar_days) if similar_days else 0
    n_train_days = X_train.shape[0] // 24

    # Sample weights: time decay + seasonal
    train_dates_col = df.loc[y_train.index, 'date']
    test_dt = pd.to_datetime(test_date, format='%Y%m%d')
    days_ago = (test_dt - train_dates_col).dt.days.values.astype(float)

    half_life = 45.0  # shorter for similar-day approach
    w_time = np.exp(-np.log(2) * days_ago / half_life)

    train_months = train_dates_col.dt.month.values
    test_is_dry = test_dt.month in [11, 12, 1, 2, 3, 4, 5]
    if test_is_dry:
        same_season = np.isin(train_months, [11, 12, 1, 2, 3, 4, 5])
    else:
        same_season = np.isin(train_months, [6, 7, 8, 9, 10])
    w_season = np.where(same_season, 2.0, 0.5)

    sample_weight = w_time * w_season
    sample_weight = sample_weight / sample_weight.mean()

    # ── Model A: Direct RT prediction ──
    model_rt = GradientBoostingRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.04,
        subsample=0.85, min_samples_leaf=4, random_state=42)
    model_rt.fit(X_train, y_train, sample_weight=sample_weight)
    preds_rt = model_rt.predict(X_test)

    # ── STAGE 2: Model B: DA-RT spread prediction ──
    y_train_spread = df.loc[y_train.index, 'da_rt_spread']
    valid_spread = y_train_spread.notna()
    if valid_spread.sum() > 24:
        model_spread = GradientBoostingRegressor(
            n_estimators=500, max_depth=6, learning_rate=0.04,
            subsample=0.85, min_samples_leaf=4, random_state=42)
        model_spread.fit(X_train[valid_spread], y_train_spread[valid_spread],
                         sample_weight=sample_weight[valid_spread.values])
        preds_spread = model_spread.predict(X_test)
        # Final = DA + predicted spread
        da_test = df.loc[test_mask, 'grid_da_avg'].fillna(0).values
        preds_da_rt = da_test + preds_spread
    else:
        preds_da_rt = preds_rt  # fallback

    # ── STAGE 4: Quantile predictions (P10/P90) ──
    model_q10 = GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.85, min_samples_leaf=5, random_state=42,
        loss='quantile', alpha=0.10)
    model_q90 = GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.85, min_samples_leaf=5, random_state=42,
        loss='quantile', alpha=0.90)
    model_q10.fit(X_train, y_train, sample_weight=sample_weight)
    model_q90.fit(X_train, y_train, sample_weight=sample_weight)
    preds_q10 = model_q10.predict(X_test)
    preds_q90 = model_q90.predict(X_test)

    # ── Ensemble: 0.5*direct + 0.5*spread ──
    preds_ensemble = 0.5 * preds_rt + 0.5 * preds_da_rt

    mae_rt = mean_absolute_error(y_test, preds_rt)
    mae_spread = mean_absolute_error(y_test, preds_da_rt)
    mae_ensemble = mean_absolute_error(y_test, preds_ensemble)
    r2_ens = r2_score(y_test, preds_ensemble)

    # Coverage: how many actuals fall in [P10, P90]?
    actual_arr = y_test.values
    coverage = np.mean((actual_arr >= preds_q10) & (actual_arr <= preds_q90)) * 100
    avg_width = np.mean(preds_q90 - preds_q10)

    results.append({
        'date': test_date,
        'actual': actual_arr,
        'pred_rt': preds_rt,
        'pred_spread': preds_da_rt,
        'pred_ensemble': preds_ensemble,
        'pred_q10': preds_q10,
        'pred_q90': preds_q90,
        'hour': df.loc[test_mask, 'hour'].values,
        'mae_rt': mae_rt,
        'mae_spread': mae_spread,
        'mae_ensemble': mae_ensemble,
        'r2': r2_ens,
        'coverage': coverage,
        'avg_width': avg_width,
        'n_similar': n_similar,
        'n_train': n_train_days,
    })

    print(f"  {test_date}: RT={mae_rt:.1f} Spread={mae_spread:.1f} "
          f"Ensemble={mae_ensemble:.1f} R2={r2_ens:.3f} "
          f"Coverage={coverage:.0f}% Width={avg_width:.0f} "
          f"(similar={n_similar}, train={n_train_days}d)")

# ============================================================
# 7. Plot: 4-panel chart with confidence intervals
# ============================================================
print("\n[5/6] Generating chart...")

n = len(results)
fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.suptitle('P1 Full Model - Stage 1+2+5+4\n'
             '(+congestion/reserve/maint + DA-RT spread + similar-day + quantile)',
             fontsize=13, fontweight='bold', y=0.99)
axes_flat = axes.flatten()

for i, res in enumerate(results):
    ax = axes_flat[i]
    actual = res['actual']
    pred = res['pred_ensemble']
    q10 = res['pred_q10']
    q90 = res['pred_q90']
    hours = res['hour']

    order = np.argsort(hours)
    actual, pred, q10, q90 = actual[order], pred[order], q10[order], q90[order]
    x = np.arange(len(actual))

    # Confidence band
    ax.fill_between(x, q10, q90, alpha=0.20, color='orange', label='P10-P90 CI')
    ax.plot(x, actual, 'b-o', ms=5, lw=2.5, label='实时电价', zorder=4)
    ax.plot(x, pred, 'r--s', ms=4, lw=2.0, label='集成预测', alpha=0.9, zorder=3)

    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 3)], fontsize=9)
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylabel('电价 (元/MWh)', fontsize=10)
    ax.set_xlabel('时间', fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

    date_str = f"2026-{res['date'][4:6]}-{res['date'][6:8]}"
    mae = res['mae_ensemble']
    color = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
    ax.set_title(f"{date_str}  MAE:{mae:.1f}  R2:{res['r2']:.3f}  "
                 f"CI:{res['coverage']:.0f}%", fontsize=11, fontweight='bold')
    ax.text(0.97, 0.95,
            f"RT:{res['mae_rt']:.0f}\nSpread:{res['mae_spread']:.0f}\n"
            f"Ens:{mae:.0f}\nCI:{res['coverage']:.0f}%",
            transform=ax.transAxes, fontsize=9, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.4', facecolor=color, alpha=0.3,
                      edgecolor=color, linewidth=1.5))
    ax.legend(fontsize=8, loc='upper left')

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(f'{OUT_DIR}/p1_full_march19_22.png', dpi=150, bbox_inches='tight')
print(f"  Chart saved: p1_full_march19_22.png")

# ============================================================
# 8. Summary
# ============================================================
print("\n[6/6] Summary")
print("=" * 90)
print(f"{'Date':>10s}  {'RT':>6s}  {'Spread':>6s}  {'Ensemble':>8s}  {'R2':>6s}  "
      f"{'CI%':>4s}  {'Width':>5s}  {'Similar':>7s}  {'Train':>5s}")
print("-" * 90)
for r in results:
    print(f"{r['date']:>10s}  {r['mae_rt']:6.1f}  {r['mae_spread']:6.1f}  "
          f"{r['mae_ensemble']:8.1f}  {r['r2']:6.3f}  "
          f"{r['coverage']:4.0f}  {r['avg_width']:5.0f}  "
          f"{r['n_similar']:7d}  {r['n_train']:5d}")

avg_rt = np.mean([r['mae_rt'] for r in results])
avg_sp = np.mean([r['mae_spread'] for r in results])
avg_en = np.mean([r['mae_ensemble'] for r in results])
avg_cov = np.mean([r['coverage'] for r in results])
print("-" * 90)
print(f"{'Avg':>10s}  {avg_rt:6.1f}  {avg_sp:6.1f}  {avg_en:8.1f}  "
      f"{'':>6s}  {avg_cov:4.0f}")

# Feature importance
if results:
    imp = model_rt.feature_importances_
    imp_df = sorted(zip(feat_active, imp), key=lambda x: -x[1])
    print("\nTop 20 Feature Importance:")
    for fname, fval in imp_df[:20]:
        bar = '#' * int(fval * 200)
        print(f"  {fname:30s} {fval*100:5.2f}% {bar}")
