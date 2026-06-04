#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 模型 - 24小时电价对比图 (匹配v3.3图表风格)
从96时段聚合到24小时，生成与v3.3完全一致的图表
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
import warnings
warnings.filterwarnings('ignore')

from config import DB_PATH, OUTPUT_DIR

# ================================================================
# 1. LOAD & MERGE (same as p0_96period_model.py)
# ================================================================
print("Loading data...")
conn = sqlite3.connect(DB_PATH)

price_df = pd.read_sql("SELECT date_key, period, hour, rt_price FROM realtime_hourly_price ORDER BY date_key, period", conn)

load_df = pd.read_sql("SELECT date_key, period, AVG(load) as total_load FROM hourly_load WHERE region='全区域' GROUP BY date_key, period", conn)
gen_df = pd.read_sql("SELECT date_key, period, AVG(output) as total_generation FROM hourly_generation WHERE region='南网' GROUP BY date_key, period", conn)
nonmarket_df = pd.read_sql("SELECT date_key, period, AVG(output) as nonmarket_output FROM hourly_nonmarket WHERE region='云南' GROUP BY date_key, period", conn)
renewable_df = pd.read_sql("SELECT date_key, period, AVG(output) as renewable_output FROM hourly_renewable WHERE region='云南' GROUP BY date_key, period", conn)
grid_load_df = pd.read_sql("SELECT trade_date as date_key, period, AVG(total_load) as grid_total_load FROM grid_load_overview GROUP BY trade_date, period", conn)
hydro_df = pd.read_sql("SELECT date_key, AVG(output) as hydro_output FROM hourly_hydro WHERE region='云南' GROUP BY date_key", conn)

manwan_df = pd.read_sql("""
    SELECT trade_date, AVG(avg_price) as manwan_avg_price, AVG(min_price) as manwan_min_price, AVG(max_price) as manwan_max_price
    FROM realtime_node_price WHERE node_name LIKE '%漫湾%' GROUP BY trade_date
""", conn)
manwan_df['date_key'] = manwan_df['trade_date'].str.replace('-', '')
manwan_df = manwan_df.drop('trade_date', axis=1)

manwan_da_df = pd.read_sql("""
    SELECT trade_date, AVG(avg_price) as manwan_da_avg, AVG(min_price) as manwan_da_min, AVG(max_price) as manwan_da_max
    FROM day_ahead_node_price WHERE node_name LIKE '%漫湾%' GROUP BY trade_date
""", conn)
manwan_da_df['date_key'] = manwan_da_df['trade_date'].str.replace('-', '')
manwan_da_df = manwan_da_df.drop('trade_date', axis=1)

conn.close()

# Merge
df = price_df.copy()
for other_df in [load_df, gen_df, nonmarket_df, renewable_df, grid_load_df]:
    df = df.merge(other_df, on=['date_key', 'period'], how='left')
for other_df in [hydro_df, manwan_df, manwan_da_df]:
    df = df.merge(other_df, on='date_key', how='left')

print(f"Merged: {len(df)} rows, {df['date_key'].nunique()} days, {len(df)//df['date_key'].nunique()} periods/day")

# ================================================================
# 2. FEATURE ENGINEERING (same as before)
# ================================================================
df['date'] = pd.to_datetime(df['date_key'], format='%Y%m%d')
df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)

period_to_idx = {p: i for i, p in enumerate(sorted(df['period'].unique()))}
df['period_idx'] = df['period'].map(period_to_idx)

df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['period_sin'] = np.sin(2 * np.pi * df['period_idx'] / 96)
df['period_cos'] = np.cos(2 * np.pi * df['period_idx'] / 96)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)

df['thermal_output'] = (df['nonmarket_output'] - df['renewable_output']).clip(lower=0)
df['supply_demand_ratio'] = df['total_generation'] / (df['total_load'] + 1e-6)
df['supply_demand_gap'] = df['grid_total_load'] - df['renewable_output']
df['renewable_ratio'] = df['renewable_output'] / (df['grid_total_load'] + 1e-6)
df['hydro_ratio'] = df['hydro_output'] / (df['grid_total_load'] + 1e-6)
df['manwan_spread'] = df['manwan_avg_price'] - df['manwan_da_avg']
df['manwan_price_range'] = df['manwan_max_price'] - df['manwan_min_price']

df = df.sort_values(['period_idx', 'date_key']).reset_index(drop=True)

for lag in [1, 2, 3, 7]:
    df[f'price_lag_{lag}d'] = df.groupby('period_idx')['rt_price'].shift(lag)
    df[f'load_lag_{lag}d'] = df.groupby('period_idx')['grid_total_load'].shift(lag)
    df[f'renewable_lag_{lag}d'] = df.groupby('period_idx')['renewable_output'].shift(lag)

for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = df.groupby('period_idx')['rt_price'].transform(lambda x: x.rolling(w, min_periods=1).mean())
    df[f'price_std_{w}d'] = df.groupby('period_idx')['rt_price'].transform(lambda x: x.rolling(w, min_periods=1).std().fillna(0))
    df[f'gap_ma_{w}d'] = df.groupby('period_idx')['supply_demand_gap'].transform(lambda x: x.rolling(w, min_periods=1).mean())

df['price_momentum_3d'] = df['rt_price'] - df.get('price_ma_3d', df['rt_price'])
df['gap_change_1d'] = df.groupby('period_idx')['supply_demand_gap'].diff()

df = df.sort_values(['date_key', 'period_idx']).reset_index(drop=True)

daily_agg = df.groupby('date_key').agg(
    daily_avg_price=('rt_price', 'mean'), daily_max_price=('rt_price', 'max'),
    daily_min_price=('rt_price', 'min'), daily_std_price=('rt_price', 'std'),
    daily_avg_load=('grid_total_load', 'mean'), daily_avg_renewable=('renewable_output', 'mean'),
    daily_avg_gap=('supply_demand_gap', 'mean'),
).reset_index()

prev_day_stats = daily_agg.copy()
prev_day_stats.columns = ['prev_date_key'] + [f'prevday_{c}' for c in daily_agg.columns[1:]]
date_list = sorted(df['date_key'].unique())
date_prev_map = {date_list[i]: date_list[i-1] for i in range(1, len(date_list))}
df['prev_date_key'] = df['date_key'].map(date_prev_map)
df = df.merge(prev_day_stats, on='prev_date_key', how='left')
df = df.drop('prev_date_key', axis=1)
df['prev_period_to_daily_ratio'] = df['price_lag_1d'] / (df['prevday_daily_avg_price'] + 1e-6)

# ================================================================
# 3. FEATURES
# ================================================================
feature_cols = [
    'hour', 'period_idx', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'period_sin', 'period_cos', 'dow_sin', 'dow_cos',
    'total_load', 'total_generation', 'nonmarket_output', 'renewable_output',
    'grid_total_load', 'thermal_output',
    'supply_demand_ratio', 'supply_demand_gap', 'renewable_ratio',
    'hydro_output', 'hydro_ratio',
    'manwan_avg_price', 'manwan_min_price', 'manwan_max_price',
    'manwan_da_avg', 'manwan_da_min', 'manwan_da_max',
    'manwan_spread', 'manwan_price_range',
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'load_lag_1d', 'load_lag_2d',
    'renewable_lag_1d',
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d',
    'price_momentum_3d',
    'gap_ma_3d', 'gap_ma_5d', 'gap_ma_7d',
    'gap_change_1d',
    'prevday_daily_avg_price', 'prevday_daily_max_price', 'prevday_daily_min_price',
    'prevday_daily_std_price', 'prevday_daily_avg_load',
    'prevday_daily_avg_renewable', 'prevday_daily_avg_gap',
    'prev_period_to_daily_ratio',
]
feature_cols = [c for c in feature_cols if c in df.columns]

# ================================================================
# 4. PREDICT 7 DAYS (03-04 to 03-10, matching v3.3)
# ================================================================
test_dates = ['20260304', '20260305', '20260306', '20260307',
              '20260308', '20260309', '20260310']

print(f"\nPredicting {len(test_dates)} days: {test_dates}")

all_results = []

for test_date in test_dates:
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date
    train_data = df[train_mask].dropna(subset=feature_cols + ['rt_price'])
    test_data = df[test_mask].sort_values('period_idx').copy()

    if len(train_data) < 96 or len(test_data) == 0:
        print(f"  {test_date}: SKIP")
        continue

    X_train = train_data[feature_cols].fillna(0)
    y_train = train_data['rt_price']
    X_test = test_data[feature_cols].fillna(0)

    model = GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.85, min_samples_leaf=3, max_features=0.8, random_state=42,
    )
    model.fit(X_train, y_train)
    test_data['predicted'] = np.clip(model.predict(X_test), 0, None)

    # Aggregate to hourly (average 4 periods per hour)
    hourly = test_data.groupby('hour').agg(
        actual=('rt_price', 'mean'),
        predicted=('predicted', 'mean'),
    ).reset_index()

    mae_hourly = mean_absolute_error(hourly['actual'], hourly['predicted'])
    print(f"  {test_date}: MAE={mae_hourly:.1f} 元/MWh (24h)")

    all_results.append({
        'date': test_date,
        'hourly': hourly,
        'mae': mae_hourly,
    })

# ================================================================
# 5. PLOT (matching v3.3 style exactly)
# ================================================================
print("\nGenerating chart...")

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

n_days = len(all_results)
n_cols = 2
n_rows = (n_days + 1) // 2

fig = plt.figure(figsize=(16, 4.2 * n_rows + 1.2))
gs = GridSpec(n_rows, n_cols, figure=fig, hspace=0.35, wspace=0.25)

avg_mae = np.mean([r['mae'] for r in all_results])

fig.suptitle(
    f'模型v3.3 P0优化 - 实时电价与预测电价对比',
    fontsize=16, fontweight='bold', y=0.98
)

for idx, result in enumerate(all_results):
    r, c = divmod(idx, n_cols)
    ax = fig.add_subplot(gs[r, c])

    hourly = result['hourly']
    hours = hourly['hour'].values
    actual = hourly['actual'].values
    predicted = hourly['predicted'].values
    mae = result['mae']

    date_str = f"{result['date'][:4]}-{result['date'][4:6]}-{result['date'][6:]}"

    # Plot: match v3.3 style exactly
    ax.plot(hours, actual, 'b-o', markersize=5, linewidth=2.0,
            label='实时电价', zorder=3)
    ax.plot(hours, predicted, 'r--s', markersize=5, linewidth=2.0,
            label='预测电价', zorder=2)

    # Gray shaded area between curves
    ax.fill_between(hours, actual, predicted, alpha=0.2, color='gray', zorder=1)

    # Axis formatting
    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 24, 3)], fontsize=9)
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylabel('电价(元/MWh)', fontsize=10)
    ax.set_xlabel('时段', fontsize=10)

    # Title with MAE (matching v3.3 format)
    ax.set_title(f'{date_str}  MAE:{mae:.1f}', fontsize=13, fontweight='bold')

    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

# If odd, fill last subplot with summary
if n_days % 2 == 1:
    ax_sum = fig.add_subplot(gs[n_rows - 1, 1])

    dates_short = [f"{r['date'][4:6]}-{r['date'][6:]}" for r in all_results]
    maes = [r['mae'] for r in all_results]

    # Color coding
    colors_bar = []
    for m in maes:
        if m < 20:
            colors_bar.append('#228B22')
        elif m < 40:
            colors_bar.append('#FF8C00')
        else:
            colors_bar.append('#DC143C')

    bars = ax_sum.bar(dates_short, maes, color=colors_bar, alpha=0.85, edgecolor='gray', linewidth=0.8)
    for bar, m in zip(bars, maes):
        ax_sum.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.8,
                   f'{m:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax_sum.axhline(y=avg_mae, color='red', linestyle='--', linewidth=1.8, alpha=0.7)
    ax_sum.text(len(dates_short) - 0.3, avg_mae + 1.5,
               f'平均: {avg_mae:.1f}', fontsize=11, color='red', fontweight='bold', ha='right')

    ax_sum.set_ylabel('MAE (元/MWh)', fontsize=11)
    ax_sum.set_title('每日MAE汇总', fontsize=13, fontweight='bold')
    ax_sum.grid(True, alpha=0.3, axis='y')
    ax_sum.set_ylim(bottom=0)

output_path = f'{OUTPUT_DIR}/p0_v33_style_hourly_comparison.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print(f"\n✅ Chart saved: {output_path}")

# Print summary table
print(f"\n{'='*50}")
print(f"  v3.3风格 24小时预测对比 — 结果汇总")
print(f"{'='*50}")
print(f"  {'日期':12s} {'P0 MAE':>10s} {'v3.3 MAE':>10s} {'对比':>8s}")
print(f"  {'-'*44}")

v33_maes = {'20260304': 128.0, '20260305': 26.0, '20260306': 36.9,
            '20260307': 16.7, '20260308': 37.9, '20260309': 112.0, '20260310': 146.2}

for r in all_results:
    d = f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}"
    p0_mae = r['mae']
    v33_mae = v33_maes.get(r['date'], None)
    if v33_mae:
        delta = ((p0_mae - v33_mae) / v33_mae) * 100
        symbol = '↓' if delta < 0 else '↑'
        print(f"  {d:12s} {p0_mae:10.1f} {v33_mae:10.1f} {symbol}{abs(delta):.0f}%")
    else:
        print(f"  {d:12s} {p0_mae:10.1f} {'—':>10s}")

print(f"  {'-'*44}")
print(f"  {'平均':12s} {avg_mae:10.1f} {np.mean(list(v33_maes.values())):10.1f}")
print(f"\nDone! ✅")
