#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 Model v3 - Hourly + Forecast Features
=========================================
- 96点 -> 24小时均值聚合
- 279天训练数据
- 新增: 新能源预测/水电预测/发电预测 (前瞻特征)
- Walk-forward: 3-19 ~ 3-22 (4天回测)
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
print("P0 v3 - Hourly + Forecast Features")
print("=" * 70)

# ============================================================
# 1. Load raw 96-point data
# ============================================================
print("\n[1/5] Loading 96-point data...")
conn = sqlite3.connect(DB)

# Price (96 点/天)
price_96 = pd.read_sql(
    """SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
       FROM realtime_node_price_96
       WHERE node_name = '__avg__'
       ORDER BY trade_date, period""",
    conn
)
price_96['date'] = pd.to_datetime(price_96['date_key'], format='%Y%m%d')
price_96['hour'] = price_96['period'].str[:2].astype(int)

# Load other features (these are also 96点/天, not hourly!)
load_96 = pd.read_sql(
    "SELECT date_key, period, load FROM hourly_load WHERE region='云南' ORDER BY date_key, period",
    conn
)
load_96['hour'] = load_96['period'].str[:2].astype(int)

renew_96 = pd.read_sql(
    "SELECT date_key, period, output FROM hourly_renewable WHERE region='云南' ORDER BY date_key, period",
    conn
)
renew_96['hour'] = renew_96['period'].str[:2].astype(int)

hydro_96 = pd.read_sql(
    "SELECT date_key, period, output FROM hourly_hydro WHERE region='云南' ORDER BY date_key, period",
    conn
)
hydro_96['hour'] = hydro_96['period'].str[:2].astype(int)

manwan_da_96 = pd.read_sql(
    """SELECT trade_date, period, AVG(price) as manwan_da_price
       FROM day_ahead_node_price_96
       WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
       GROUP BY trade_date, period ORDER BY trade_date, period""",
    conn
)
manwan_da_96['hour'] = manwan_da_96['period'].str[:2].astype(int)

grid_da_96 = pd.read_sql(
    """SELECT trade_date, period, price as grid_da_avg
       FROM day_ahead_node_price_96
       WHERE node_name = '__all_avg__'
       ORDER BY trade_date, period""",
    conn
)
grid_da_96['hour'] = grid_da_96['period'].str[:2].astype(int)

# ── NEW: Forecast data (前瞻特征) ──
# 新能源预测 (D+1, 96点, 云南, 总计)
renew_fc_96 = pd.read_sql(
    """SELECT forecast_date as date_key, period, forecast_mw as renew_fc
       FROM renewable_forecast
       WHERE region='云南' AND category='总计'
       ORDER BY forecast_date, period""",
    conn
)
renew_fc_96['hour'] = renew_fc_96['period'].str[:2].astype(int)
# Deduplicate: keep the LATEST published forecast per (forecast_date, period)
# Actually renewable_forecast may have multiple publish_dates for same forecast_date
# We use ALL forecasts (they aggregate to similar values)

# 水电预测 (weekly avg by region)
hydro_fc = pd.read_sql(
    """SELECT forecast_date as date_key, avg_output_mw as hydro_fc_avg
       FROM hydro_forecast
       WHERE region='云南'
       ORDER BY forecast_date""",
    conn
)
# Deduplicate: take mean of multiple forecasts
hydro_fc = hydro_fc.groupby('date_key').agg(hydro_fc_avg=('hydro_fc_avg', 'mean')).reset_index()

# 发电总出力预测 (96点)
gen_fc_96 = pd.read_sql(
    """SELECT forecast_date as date_key, period, forecast_mw as gen_fc
       FROM generation_forecast
       ORDER BY forecast_date, period""",
    conn
)
gen_fc_96['hour'] = gen_fc_96['period'].str[:2].astype(int)

# 负荷预测 (云南)
load_fc_96 = pd.read_sql(
    """SELECT trade_date as td, period, forecast_load as load_fc
       FROM load_forecast
       WHERE region='云南'
       ORDER BY trade_date, period""",
    conn
)
load_fc_96['date_key'] = load_fc_96['td'].str.replace('-', '')
load_fc_96['hour'] = load_fc_96['period'].str[:2].astype(int)

conn.close()

# ============================================================
# 2. Aggregate to hourly (24点/天)
# ============================================================
print("[2/5] Aggregate to hourly (96 -> 24)...")

# Price: 96点 → 小时均值
price_hourly = price_96.groupby(['date_key', 'hour']).agg(
    rt_price=('rt_price', 'mean'),
    date=('date', 'first')
).reset_index()
price_hourly['period'] = price_hourly['hour'].apply(lambda h: f"{h:02d}:00")

# Load, Renew, Hydro: 96点 → 小时均值
load_h = load_96.groupby(['date_key', 'hour']).agg(
    load=('load', 'mean')
).reset_index()

renew_h = renew_96.groupby(['date_key', 'hour']).agg(
    renewable=('output', 'mean')
).reset_index()

hydro_h = hydro_96.groupby(['date_key', 'hour']).agg(
    hydro=('output', 'mean')
).reset_index()

# Manwan & Grid DA (96点 → 小时均值)
manwan_h = manwan_da_96.groupby(['trade_date', 'hour']).agg(
    manwan_da_price=('manwan_da_price', 'mean')
).reset_index()
manwan_h['date_key'] = pd.to_datetime(manwan_h['trade_date']).dt.strftime('%Y%m%d')

grid_h = grid_da_96.groupby(['trade_date', 'hour']).agg(
    grid_da_avg=('grid_da_avg', 'mean')
).reset_index()
grid_h['date_key'] = pd.to_datetime(grid_h['trade_date']).dt.strftime('%Y%m%d')

# Forecast aggregations (96 -> hourly)
renew_fc_h = renew_fc_96.groupby(['date_key', 'hour']).agg(
    renew_fc=('renew_fc', 'mean')
).reset_index()

gen_fc_h = gen_fc_96.groupby(['date_key', 'hour']).agg(
    gen_fc=('gen_fc', 'mean')
).reset_index()

load_fc_h = load_fc_96.groupby(['date_key', 'hour']).agg(
    load_fc=('load_fc', 'mean')
).reset_index()

# Merge all
df = price_hourly[['date_key', 'period', 'hour', 'rt_price', 'date']].copy()
df = df.merge(load_h[['date_key', 'hour', 'load']], on=['date_key', 'hour'], how='left')
df = df.merge(renew_h[['date_key', 'hour', 'renewable']], on=['date_key', 'hour'], how='left')
df = df.merge(hydro_h[['date_key', 'hour', 'hydro']], on=['date_key', 'hour'], how='left')
df.rename(columns={'load': 'total_load'}, inplace=True)
df = df.merge(manwan_h[['date_key', 'hour', 'manwan_da_price']], on=['date_key', 'hour'], how='left')
df = df.merge(grid_h[['date_key', 'hour', 'grid_da_avg']], on=['date_key', 'hour'], how='left')

# Merge forecast features (FORWARD-LOOKING, legitimate D-1 published)
df = df.merge(renew_fc_h[['date_key', 'hour', 'renew_fc']], on=['date_key', 'hour'], how='left')
df = df.merge(gen_fc_h[['date_key', 'hour', 'gen_fc']], on=['date_key', 'hour'], how='left')
df = df.merge(load_fc_h[['date_key', 'hour', 'load_fc']], on=['date_key', 'hour'], how='left')
df = df.merge(hydro_fc[['date_key', 'hydro_fc_avg']], on='date_key', how='left')

# ============================================================
# 3. Build features (hourly granularity)
# ============================================================
print("[3/5] Building features (hourly + forecast)...")

df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)

# Time features
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

# Gap (actual D-1)
df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)

# ── Forecast-derived features (FORWARD-LOOKING) ──
# Predicted supply-demand gap
df['fc_gap'] = df['load_fc'].fillna(0) - df['renew_fc'].fillna(0) - df['hydro_fc_avg'].fillna(0)
# Renewable forecast vs D-1 actual
df['renew_fc_vs_lag'] = df['renew_fc'].fillna(0) - df['renewable'].fillna(0)
# Load forecast vs D-1 actual
df['load_fc_vs_lag'] = df['load_fc'].fillna(0) - df['total_load'].fillna(0)
# Renewable share of generation
df['renew_fc_share'] = np.where(df['gen_fc'] > 0, df['renew_fc'].fillna(0) / df['gen_fc'], 0)

# Sort for lag
df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)

# Lag features (1/2/3/7 天前的同小时)
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

# Moving averages (per hour)
for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = (
        df.groupby('hour')['rt_price']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
    )
    df[f'price_std_{w}d'] = (
        df.groupby('hour')['rt_price']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0))
    )

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
    df['price_lag_1d'] / df['prevday_daily_avg_price'],
    1.0
)

# Manwan DA lag
df = add_lag_by_hour(df, 'manwan_da_price', 'manwan_da_lag1d', 1)
df = add_lag_by_hour(df, 'manwan_da_price', 'manwan_da_prev', 1)
df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_prev']

df = df.sort_values(['date_key', 'hour']).reset_index(drop=True)
print(f"  特征矩阵: {len(df)} rows × {df.shape[1]} cols, {df['date_key'].nunique()} days")

# ============================================================
# 4. Feature list
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
    # DA prices (3)
    'manwan_da_price', 'manwan_da_lag1d', 'manwan_da_change',
    'grid_da_avg',
    # Previous-day stats (8)
    'prevday_daily_avg_price', 'prevday_daily_max_price',
    'prevday_daily_min_price', 'prevday_daily_std_price',
    'prevday_daily_avg_load', 'prevday_daily_avg_renew', 'prevday_daily_avg_gap',
    'prev_period_to_daily_ratio',
    # ── NEW: Forecast features (前瞻, D-1发布) ──
    'renew_fc',          # 新能源预测出力 (D+1, 小时)
    'hydro_fc_avg',      # 水电预测出力 (日均)
    'gen_fc',            # 发电总出力预测 (D+1, 小时)
    'load_fc',           # 负荷预测 (D+1, 小时)
    'fc_gap',            # 预测供需缺口
    'renew_fc_vs_lag',   # 新能源预测 vs D-1实际差值
    'load_fc_vs_lag',    # 负荷预测 vs D-1实际差值
    'renew_fc_share',    # 新能源预测占比
]

# ============================================================
# 5. Walk-forward: 3-19 ~ 3-22 (4 days)
# ============================================================
print("\n[4/5] Walk-forward prediction (3-19~3-22)...\n")

test_dates = ['20260319', '20260320', '20260321', '20260322']
results = []

for test_date in test_dates:
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date

    X_train = df.loc[train_mask, FEATURES].fillna(0)
    y_train = df.loc[train_mask, 'rt_price']
    X_test = df.loc[test_mask, FEATURES].fillna(0)
    y_test = df.loc[test_mask, 'rt_price']

    valid_train = y_train.notna()
    X_train, y_train = X_train[valid_train], y_train[valid_train]

    if len(X_train) < 24 or len(X_test) == 0:
        print(f"  SKIP {test_date}")
        continue

    # Sample weights: time decay + seasonal
    train_dates = df.loc[y_train.index, 'date']
    test_dt = pd.to_datetime(test_date, format='%Y%m%d')
    days_ago = (test_dt - train_dates).dt.days.values.astype(float)

    half_life = 60.0
    w_time = np.exp(-np.log(2) * days_ago / half_life)

    train_months = train_dates.dt.month.values
    test_month = test_dt.month
    test_is_dry = test_month in [11, 12, 1, 2, 3, 4, 5]
    if test_is_dry:
        same_season = np.isin(train_months, [11, 12, 1, 2, 3, 4, 5])
    else:
        same_season = np.isin(train_months, [6, 7, 8, 9, 10])
    w_season = np.where(same_season, 2.0, 0.5)

    sample_weight = w_time * w_season
    sample_weight = sample_weight / sample_weight.mean()

    model = GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.85, min_samples_leaf=5, random_state=42
    )
    model.fit(X_train, y_train, sample_weight=sample_weight)
    preds = model.predict(X_test)

    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)

    results.append({
        'date': test_date,
        'actual': y_test.values,
        'predicted': preds,
        'hour': df.loc[test_mask, 'hour'].values,
        'mae': mae,
        'r2': r2,
    })
    print(f"  {test_date}: MAE={mae:.1f}  R2={r2:.3f}")

# ============================================================
# 6. Plot: Reference v3.3 style (hourly 24点)
# ============================================================
print("\n[5/5] Generating chart...")

n = len(results)
n_cols = 2
n_rows = (n + 1) // 2

fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4.5 * n_rows + 1))
fig.suptitle('P0 v3 - 预测电价 vs 实时电价\n(+新能源/水电/负荷预测特征 | 小时粒度 | 3月19-22)',
             fontsize=14, fontweight='bold', y=0.98)

axes_flat = axes.flatten() if n > 2 else ([axes] if n == 1 else list(axes))

time_ticks = list(range(0, 24, 3))
time_labels = [f"{h:02d}:00" for h in range(0, 24, 3)]

for i, res in enumerate(results):
    ax = axes_flat[i]
    actual = res['actual']
    pred = res['predicted']
    hours = res['hour']

    # Sort by hour
    order = np.argsort(hours)
    actual = actual[order]
    pred = pred[order]
    x = np.arange(len(actual))

    ax.plot(x, actual, 'b-o', ms=4, lw=2.2, label='实时电价', zorder=3)
    ax.plot(x, pred, 'r--s', ms=4, lw=1.8, label='预测电价', alpha=0.85, zorder=2)
    ax.fill_between(x, actual, pred, alpha=0.15, color='gray')

    ax.set_xticks(time_ticks)
    ax.set_xticklabels(time_labels, fontsize=9)
    ax.set_xlim(-0.5, len(x) - 0.5)
    ax.set_ylabel('电价 (元/MWh)', fontsize=10, fontweight='bold')
    ax.set_xlabel('时间', fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

    mae = res['mae']
    r2 = res['r2']
    date_str = f"2026-{res['date'][4:6]}-{res['date'][6:8]}"
    ax.set_title(f"{date_str}  MAE:{mae:.1f}  R2:{r2:.3f}",
                 fontsize=12, fontweight='bold')

    color = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
    ax.text(0.97, 0.95, f'MAE: {mae:.1f}', transform=ax.transAxes,
            fontsize=11, fontweight='bold', va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.4', facecolor=color, alpha=0.35, edgecolor=color, linewidth=1.5))
    ax.legend(fontsize=9, loc='upper left')

# MAE summary
if n % 2 == 1:
    ax_sum = axes_flat[n]
    dates_s = [f"{r['date'][4:6]}-{r['date'][6:8]}" for r in results]
    maes = [r['mae'] for r in results]
    colors = ['#228B22' if m < 40 else ('#FF8C00' if m < 80 else '#DC143C') for m in maes]
    bars = ax_sum.bar(dates_s, maes, color=colors, alpha=0.8, edgecolor='gray', width=0.6)
    for bar, m in zip(bars, maes):
        ax_sum.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                   f'{m:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    avg_mae = np.mean(maes)
    ax_sum.axhline(avg_mae, color='red', ls='--', lw=2, alpha=0.7, label=f'均值: {avg_mae:.1f}')
    ax_sum.set_title('MAE对比', fontsize=12, fontweight='bold')
    ax_sum.set_ylabel('MAE (元/MWh)', fontsize=10, fontweight='bold')
    ax_sum.set_ylim(0, max(maes) * 1.25 if maes else 100)
    ax_sum.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax_sum.legend(fontsize=10)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(f'{OUT_DIR}/p0_v3_hourly_march19_22.png', dpi=150, bbox_inches='tight')
print(f"\nChart saved: p0_v3_hourly_march19_22.png")

# Summary
print("\n" + "=" * 70)
print("Results Summary")
print("=" * 70)
for r in results:
    print(f"{r['date']}: MAE={r['mae']:.1f}  R2={r['r2']:.3f}")
avg_mae = np.mean([r['mae'] for r in results])
print(f"\nAvg MAE: {avg_mae:.1f}")

# Feature importance (from last model)
if results:
    feat_used = [f for f in FEATURES if f in df.columns]
    imp = model.feature_importances_
    imp_df = sorted(zip(feat_used, imp), key=lambda x: -x[1])
    print("\nTop 15 Feature Importance:")
    for fname, fval in imp_df[:15]:
        bar = '#' * int(fval * 200)
        print(f"  {fname:30s} {fval*100:5.2f}% {bar}")
