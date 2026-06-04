#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 P0 v2.2 模型对比图 (279天+季节特征)
类似v3.3参考图格式的对比
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

# ============================================================
# Load & Build Features
# ============================================================
conn = sqlite3.connect(DB)

# 1. Price (279天 from __avg__)
price = pd.read_sql(
    """SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
       FROM realtime_node_price_96
       WHERE node_name = '__avg__'
       ORDER BY trade_date, period""",
    conn
)
price['date'] = pd.to_datetime(price['date_key'], format='%Y%m%d')

# 2. Load, Renewable, Hydro
load = pd.read_sql(
    "SELECT date_key, period, load FROM hourly_load WHERE region='全区域' ORDER BY date_key, period",
    conn
)
renew = pd.read_sql(
    "SELECT date_key, period, output FROM hourly_renewable WHERE region='云南' ORDER BY date_key, period",
    conn
)
hydro = pd.read_sql(
    "SELECT date_key, period, output FROM hourly_hydro WHERE region='云南' ORDER BY date_key, period",
    conn
)

# 3. Manwan DA price
manwan_da = pd.read_sql(
    """SELECT trade_date, period, AVG(price) as manwan_da_price
       FROM day_ahead_node_price_96
       WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
       GROUP BY trade_date, period ORDER BY trade_date, period""",
    conn
)

grid_da = pd.read_sql(
    """SELECT trade_date, period, price as grid_da_avg
       FROM day_ahead_node_price_96
       WHERE node_name = '__all_avg__'
       ORDER BY trade_date, period""",
    conn
)

conn.close()

# Build feature matrix
df = price.copy()
df = df.merge(load.rename(columns={'load': 'total_load'}), on=['date_key', 'period'], how='left')
df = df.merge(renew.rename(columns={'output': 'renewable'}), on=['date_key', 'period'], how='left')
df = df.merge(hydro.rename(columns={'output': 'hydro'}), on=['date_key', 'period'], how='left')

period_map = {f"{h:02d}:{m:02d}": h * 4 + i
              for h in range(24)
              for i, m in enumerate([0, 15, 30, 45])}
df['period_idx'] = df['period'].map(period_map).fillna(0).astype(int)

# Time features
df['hour'] = df['period_idx'] // 4
df['minute_slot'] = df['period_idx'] % 4
df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['period_sin'] = np.sin(2 * np.pi * df['period_idx'] / 96)
df['period_cos'] = np.cos(2 * np.pi * df['period_idx'] / 96)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)

# Seasonal features
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
df['wet_x_period_sin'] = df['is_wet_season'] * df['period_sin']
df['day_of_year'] = df['date'].dt.dayofyear
df['doy_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
df['doy_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)

# Gap
df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)

df = df.sort_values(['period_idx', 'date_key']).reset_index(drop=True)

# Lag features
def add_lag_by_period(df, col, new_col, n_days):
    df[new_col] = df.groupby('period_idx')[col].shift(n_days)
    return df

for lag in [1, 2, 3, 7]:
    df = add_lag_by_period(df, 'rt_price', f'price_lag_{lag}d', lag)
for lag in [1, 2]:
    df = add_lag_by_period(df, 'total_load', f'load_lag_{lag}d', lag)
    df = add_lag_by_period(df, 'renewable', f'renew_lag_{lag}d', lag)
df = add_lag_by_period(df, 'hydro', 'hydro_lag_1d', 1)
df = add_lag_by_period(df, 'gap', 'gap_lag_1d', 1)
df = add_lag_by_period(df, 'gap', 'gap_lag_2d', 2)

# Moving averages
for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = (
        df.groupby('period_idx')['rt_price']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
    )
    df[f'price_std_{w}d'] = (
        df.groupby('period_idx')['rt_price']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0))
    )

df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

# Previous-day aggregates
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

# Manwan DA
manwan_da['date'] = pd.to_datetime(manwan_da['trade_date'])
manwan_da['date_key'] = manwan_da['date'].dt.strftime('%Y%m%d')
df = df.merge(
    manwan_da[['date_key', 'period', 'manwan_da_price']],
    on=['date_key', 'period'], how='left'
)
df = add_lag_by_period(df, 'manwan_da_price', 'manwan_da_lag1d', 1)

grid_da['date_key'] = pd.to_datetime(grid_da['trade_date']).dt.strftime('%Y%m%d')
df = df.merge(
    grid_da[['date_key', 'period', 'grid_da_avg']],
    on=['date_key', 'period'], how='left'
)

df = add_lag_by_period(df, 'manwan_da_price', 'manwan_da_prev', 1)
df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_prev']

df = df.sort_values(['date_key', 'period_idx']).reset_index(drop=True)

# ============================================================
# Feature list
# ============================================================
FEATURES = [
    'hour', 'minute_slot', 'period_idx', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'period_sin', 'period_cos', 'dow_sin', 'dow_cos',
    'month_sin', 'month_cos',
    'week_of_year', 'woy_sin', 'woy_cos',
    'is_wet_season', 'is_transition',
    'q1', 'q2', 'q3', 'q4',
    'wet_x_hour', 'wet_x_period_sin',
    'day_of_year', 'doy_sin', 'doy_cos',
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d',
    'price_momentum_3d',
    'load_lag_1d', 'load_lag_2d',
    'renew_lag_1d', 'renew_lag_2d',
    'hydro_lag_1d',
    'gap_lag_1d', 'gap_lag_2d', 'gap_change',
    'manwan_da_price', 'manwan_da_lag1d', 'manwan_da_change',
    'grid_da_avg',
    'prevday_daily_avg_price', 'prevday_daily_max_price',
    'prevday_daily_min_price', 'prevday_daily_std_price',
    'prevday_daily_avg_load', 'prevday_daily_avg_renew', 'prevday_daily_avg_gap',
    'prev_period_to_daily_ratio',
]

# ============================================================
# Walk-forward prediction: March 4-10
# ============================================================
march_dates = sorted([d for d in df['date_key'].unique() if d.startswith('202603')])
test_dates = [d for d in march_dates if d <= '20260310'][:7]  # 3/4-3/10

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

    if len(X_train) < 96 or len(X_test) == 0:
        print(f"SKIP {test_date}")
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
        'period': df.loc[test_mask, 'period'].values,
        'period_idx': df.loc[test_mask, 'period_idx'].values,
        'mae': mae,
        'r2': r2,
    })
    print(f"{test_date}: MAE={mae:.1f}")

# ============================================================
# Plot: v3.3 style
# ============================================================
n = len(results)
n_cols = 2
n_rows = (n + 1) // 2

fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4.2 * n_rows + 1))
fig.suptitle('P0 v2.2 模型 - 预测电价 vs 实时电价\n(279天+季节特征+时间衰减 | 零泄露 | 96时段)',
             fontsize=14, fontweight='bold', y=0.98)

axes_flat = axes.flatten() if n > 2 else ([axes] if n == 1 else list(axes))

time_ticks = list(range(0, 96, 12))
time_labels = [f"{h:02d}:00" for h in range(0, 24, 3)]

for i, res in enumerate(results):
    ax = axes_flat[i]
    actual = res['actual']
    pred = res['predicted']
    pidx = res['period_idx']

    order = np.argsort(pidx)
    actual = actual[order]
    pred = pred[order]
    x = np.arange(len(actual))

    ax.plot(x, actual, 'b-o', ms=2.5, lw=2.2, label='实时电价', zorder=3)
    ax.plot(x, pred, 'r--s', ms=2.5, lw=1.8, label='预测电价', alpha=0.85, zorder=2)
    ax.fill_between(x, actual, pred, alpha=0.15, color='gray')

    ax.set_xticks(time_ticks)
    ax.set_xticklabels(time_labels, fontsize=9)
    ax.set_xlim(-1, len(x))
    ax.set_ylabel('电价 (元/MWh)', fontsize=10, fontweight='bold')
    ax.set_xlabel('时间', fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

    mae = res['mae']
    r2 = res['r2']
    date_str = f"{res['date'][:4]}-{res['date'][4:6]}-{res['date'][6:8]}"
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
        ax_sum.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{m:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    avg_mae = np.mean(maes)
    ax_sum.axhline(avg_mae, color='red', ls='--', lw=2, alpha=0.7, label=f'均值: {avg_mae:.1f}')
    ax_sum.set_title('MAE对比', fontsize=12, fontweight='bold')
    ax_sum.set_ylabel('MAE (元/MWh)', fontsize=10, fontweight='bold')
    ax_sum.set_ylim(0, max(maes) * 1.2)
    ax_sum.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax_sum.legend(fontsize=10)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(f'{OUT_DIR}/p0_v2_2_march4_10.png', dpi=150, bbox_inches='tight')
print(f"Chart saved: p0_v2_2_march4_10.png")

# Print summary
print("\n=== Summary ===")
for r in results:
    print(f"{r['date']}: MAE={r['mae']:.1f}  R2={r['r2']:.3f}")
print(f"Average MAE: {np.mean([r['mae'] for r in results]):.1f}")
