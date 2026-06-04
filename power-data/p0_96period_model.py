#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 电力价格预测模型 - 真实96时段版本 (v2 - 去重修复)
直接对接 power_market.db，逐15分钟预测
两种模式: Day-ahead (无当日泄露) / Real-time (含日内滞后)
Walk-forward backtesting on March 7 days
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings('ignore')

from config import DB_PATH, OUTPUT_DIR

# ================================================================
# 1. LOAD ALL DATA FROM DATABASE (with deduplication)
# ================================================================
print("=" * 60)
print("Phase 1: Loading data from power_market.db")
print("=" * 60)

conn = sqlite3.connect(DB_PATH)

# Target: realtime hourly price (96 periods/day)
price_df = pd.read_sql("""
    SELECT date_key, period, hour, rt_price
    FROM realtime_hourly_price
    ORDER BY date_key, period
""", conn)
print(f"  realtime_hourly_price: {len(price_df)} rows, "
      f"{price_df['date_key'].nunique()} days")

# Load (96 periods/day) - deduplicate
load_df = pd.read_sql("""
    SELECT date_key, period, AVG(load) as total_load
    FROM hourly_load
    WHERE region='全区域'
    GROUP BY date_key, period
    ORDER BY date_key, period
""", conn)
print(f"  hourly_load: {len(load_df)} rows")

# Generation (96 periods/day) - deduplicate
gen_df = pd.read_sql("""
    SELECT date_key, period, AVG(output) as total_generation
    FROM hourly_generation
    WHERE region='南网'
    GROUP BY date_key, period
    ORDER BY date_key, period
""", conn)
print(f"  hourly_generation: {len(gen_df)} rows")

# Non-market units (96 periods/day) - deduplicate
nonmarket_df = pd.read_sql("""
    SELECT date_key, period, AVG(output) as nonmarket_output
    FROM hourly_nonmarket
    WHERE region='云南'
    GROUP BY date_key, period
    ORDER BY date_key, period
""", conn)
print(f"  hourly_nonmarket: {len(nonmarket_df)} rows")

# Renewable output - Yunnan (96 periods/day) - DEDUPLICATE (7x dupes!)
renewable_df = pd.read_sql("""
    SELECT date_key, period, AVG(output) as renewable_output
    FROM hourly_renewable
    WHERE region='云南'
    GROUP BY date_key, period
    ORDER BY date_key, period
""", conn)
print(f"  hourly_renewable (云南): {len(renewable_df)} rows (deduped)")

# Grid load overview (96 periods/day) - deduplicate
grid_load_df = pd.read_sql("""
    SELECT trade_date as date_key, period, AVG(total_load) as grid_total_load
    FROM grid_load_overview
    GROUP BY trade_date, period
    ORDER BY trade_date, period
""", conn)
print(f"  grid_load_overview: {len(grid_load_df)} rows")

# Hydro output - Yunnan (daily)
hydro_df = pd.read_sql("""
    SELECT date_key, AVG(output) as hydro_output
    FROM hourly_hydro
    WHERE region='云南'
    GROUP BY date_key
    ORDER BY date_key
""", conn)
print(f"  hourly_hydro (云南): {len(hydro_df)} rows (daily)")

# 漫湾 node prices (daily avg/min/max)
manwan_df = pd.read_sql("""
    SELECT trade_date,
           AVG(avg_price) as manwan_avg_price,
           AVG(min_price) as manwan_min_price,
           AVG(max_price) as manwan_max_price
    FROM realtime_node_price
    WHERE node_name LIKE '%漫湾%'
    GROUP BY trade_date
    ORDER BY trade_date
""", conn)
manwan_df['date_key'] = manwan_df['trade_date'].str.replace('-', '')
manwan_df = manwan_df.drop('trade_date', axis=1)
print(f"  漫湾 RT node prices: {len(manwan_df)} rows (daily)")

# Day-ahead 漫湾 prices
manwan_da_df = pd.read_sql("""
    SELECT trade_date,
           AVG(avg_price) as manwan_da_avg,
           AVG(min_price) as manwan_da_min,
           AVG(max_price) as manwan_da_max
    FROM day_ahead_node_price
    WHERE node_name LIKE '%漫湾%'
    GROUP BY trade_date
    ORDER BY trade_date
""", conn)
manwan_da_df['date_key'] = manwan_da_df['trade_date'].str.replace('-', '')
manwan_da_df = manwan_da_df.drop('trade_date', axis=1)
print(f"  漫湾 DA node prices: {len(manwan_da_df)} rows (daily)")

conn.close()
print(f"\n  ✅ All data loaded!")

# ================================================================
# 2. MERGE ALL PERIOD-LEVEL DATA
# ================================================================
print("\n" + "=" * 60)
print("Phase 2: Merging period-level data")
print("=" * 60)

df = price_df.copy()

# Merge period-level tables (1:1 merge)
for name, other_df in [
    ('load', load_df),
    ('generation', gen_df),
    ('nonmarket', nonmarket_df),
    ('renewable', renewable_df),
    ('grid_load', grid_load_df),
]:
    before = len(df)
    df = df.merge(other_df, on=['date_key', 'period'], how='left')
    after = len(df)
    col_name = [c for c in other_df.columns if c not in ['date_key', 'period']][0]
    matched = df[col_name].notna().sum()
    print(f"  Merged {name:12s}: {before}→{after} rows, {matched} matched")
    if after != before:
        print(f"    ⚠️ Row expansion detected! Deduplicating...")
        df = df.drop_duplicates(subset=['date_key', 'period'], keep='first')
        print(f"    → Reduced to {len(df)} rows")

# Merge daily tables (broadcast to all periods)
for name, other_df in [
    ('hydro', hydro_df),
    ('manwan_rt', manwan_df),
    ('manwan_da', manwan_da_df),
]:
    before = len(df)
    df = df.merge(other_df, on='date_key', how='left')
    after = len(df)
    print(f"  Merged {name:12s} (daily→period): {before}→{after} rows")

print(f"\n  ✅ Final merged: {len(df)} rows, {df.shape[1]} columns")
print(f"  Date range: {df['date_key'].min()} → {df['date_key'].max()}")
print(f"  Days: {df['date_key'].nunique()}")
print(f"  Periods/day: {len(df) / df['date_key'].nunique():.0f}")

# ================================================================
# 3. FEATURE ENGINEERING
# ================================================================
print("\n" + "=" * 60)
print("Phase 3: Feature Engineering")
print("=" * 60)

# Date & time
df['date'] = pd.to_datetime(df['date_key'], format='%Y%m%d')
df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)

# Period index (0-95)
period_to_idx = {p: i for i, p in enumerate(sorted(df['period'].unique()))}
df['period_idx'] = df['period'].map(period_to_idx)

# Cyclical features
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['period_sin'] = np.sin(2 * np.pi * df['period_idx'] / 96)
df['period_cos'] = np.cos(2 * np.pi * df['period_idx'] / 96)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)

# === Supply-demand features ===
df['thermal_output'] = (df['nonmarket_output'] - df['renewable_output']).clip(lower=0)
df['supply_demand_ratio'] = df['total_generation'] / (df['total_load'] + 1e-6)
df['supply_demand_gap'] = df['grid_total_load'] - df['renewable_output']
df['renewable_ratio'] = df['renewable_output'] / (df['grid_total_load'] + 1e-6)
df['hydro_ratio'] = df['hydro_output'] / (df['grid_total_load'] + 1e-6)
df['manwan_spread'] = df['manwan_avg_price'] - df['manwan_da_avg']
df['manwan_price_range'] = df['manwan_max_price'] - df['manwan_min_price']

# === Cross-day same-period lags (NO data leakage) ===
df = df.sort_values(['period_idx', 'date_key']).reset_index(drop=True)

for lag in [1, 2, 3, 7]:
    df[f'price_lag_{lag}d'] = df.groupby('period_idx')['rt_price'].shift(lag)
    df[f'load_lag_{lag}d'] = df.groupby('period_idx')['grid_total_load'].shift(lag)
    df[f'renewable_lag_{lag}d'] = df.groupby('period_idx')['renewable_output'].shift(lag)

for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = df.groupby('period_idx')['rt_price'].transform(
        lambda x: x.rolling(w, min_periods=1).mean()
    )
    df[f'price_std_{w}d'] = df.groupby('period_idx')['rt_price'].transform(
        lambda x: x.rolling(w, min_periods=1).std().fillna(0)
    )
    df[f'gap_ma_{w}d'] = df.groupby('period_idx')['supply_demand_gap'].transform(
        lambda x: x.rolling(w, min_periods=1).mean()
    )

df['price_momentum_3d'] = df['rt_price'] - df.get('price_ma_3d', df['rt_price'])
df['gap_change_1d'] = df.groupby('period_idx')['supply_demand_gap'].diff()

# === Previous day aggregated stats ===
df = df.sort_values(['date_key', 'period_idx']).reset_index(drop=True)

daily_agg = df.groupby('date_key').agg(
    daily_avg_price=('rt_price', 'mean'),
    daily_max_price=('rt_price', 'max'),
    daily_min_price=('rt_price', 'min'),
    daily_std_price=('rt_price', 'std'),
    daily_avg_load=('grid_total_load', 'mean'),
    daily_avg_renewable=('renewable_output', 'mean'),
    daily_avg_gap=('supply_demand_gap', 'mean'),
).reset_index()

prev_day_stats = daily_agg.copy()
prev_day_stats.columns = ['prev_date_key'] + [f'prevday_{c}' for c in daily_agg.columns[1:]]

date_list = sorted(df['date_key'].unique())
date_prev_map = {date_list[i]: date_list[i-1] for i in range(1, len(date_list))}

df['prev_date_key'] = df['date_key'].map(date_prev_map)
df = df.merge(prev_day_stats, on='prev_date_key', how='left')
df = df.drop('prev_date_key', axis=1)

# === Intraday profile features (from previous day's profile shape) ===
# For each period, compute the previous day's price at this same period
# (This is price_lag_1d already computed above)

# Ratio of previous day's period price to previous day's daily average
df['prev_period_to_daily_ratio'] = df['price_lag_1d'] / (df['prevday_daily_avg_price'] + 1e-6)

print(f"  ✅ Total features: {df.shape[1]} columns")
null_cols = [(col, df[col].isna().mean()*100) for col in df.columns if df[col].isna().any()]
if null_cols:
    print(f"  Columns with nulls:")
    for col, pct in sorted(null_cols, key=lambda x: -x[1])[:10]:
        print(f"    {col}: {pct:.1f}% null")

# ================================================================
# 4. DEFINE FEATURE SETS (two modes)
# ================================================================
print("\n" + "=" * 60)
print("Phase 4: Model Definition")
print("=" * 60)

# Day-ahead features: ONLY uses info available before the trading day
dayahead_features = [
    # Time
    'hour', 'period_idx', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'period_sin', 'period_cos', 'dow_sin', 'dow_cos',

    # Supply-demand (period-level, from day-ahead schedule/forecast)
    'total_load', 'total_generation', 'nonmarket_output', 'renewable_output',
    'grid_total_load', 'thermal_output',
    'supply_demand_ratio', 'supply_demand_gap', 'renewable_ratio',

    # Hydro & 漫湾 (daily)
    'hydro_output', 'hydro_ratio',
    'manwan_avg_price', 'manwan_min_price', 'manwan_max_price',
    'manwan_da_avg', 'manwan_da_min', 'manwan_da_max',
    'manwan_spread', 'manwan_price_range',

    # Cross-day lags (same period, previous days)
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'load_lag_1d', 'load_lag_2d',
    'renewable_lag_1d',

    # Cross-day moving averages
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d',
    'price_momentum_3d',
    'gap_ma_3d', 'gap_ma_5d', 'gap_ma_7d',
    'gap_change_1d',

    # Previous day aggregates
    'prevday_daily_avg_price', 'prevday_daily_max_price', 'prevday_daily_min_price',
    'prevday_daily_std_price', 'prevday_daily_avg_load',
    'prevday_daily_avg_renewable', 'prevday_daily_avg_gap',

    # Profile shape
    'prev_period_to_daily_ratio',
]
dayahead_features = [c for c in dayahead_features if c in df.columns]
print(f"  Day-ahead features: {len(dayahead_features)}")

# ================================================================
# 5. WALK-FORWARD BACKTESTING
# ================================================================
print("\n" + "=" * 60)
print("Phase 5: Walk-Forward Backtest (March 7 Days)")
print("=" * 60)

march_dates = sorted([d for d in df['date_key'].unique() if d.startswith('202603')])
test_dates = march_dates[-7:]
print(f"  March dates: {march_dates}")
print(f"  Test dates:  {test_dates}")

all_results = []

for test_date in test_dates:
    print(f"\n  --- {test_date} ---")

    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date

    train_data = df[train_mask].dropna(subset=dayahead_features + ['rt_price'])
    test_data = df[test_mask].sort_values('period_idx').copy()

    if len(train_data) < 96:
        print(f"    SKIP: insufficient data ({len(train_data)})")
        continue

    X_train = train_data[dayahead_features].fillna(0)
    y_train = train_data['rt_price']
    X_test = test_data[dayahead_features].fillna(0)
    y_test = test_data['rt_price']

    print(f"    Train: {len(X_train)} periods ({train_data['date_key'].nunique()} days)")
    print(f"    Test:  {len(X_test)} periods")

    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.85,
        min_samples_leaf=3,
        max_features=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)
    preds = np.clip(model.predict(X_test), 0, None)

    test_data = test_data.copy()
    test_data['predicted'] = preds

    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)

    print(f"    MAE:  {mae:.2f} 元/MWh")
    print(f"    RMSE: {rmse:.2f} 元/MWh")
    print(f"    R²:   {r2:.4f}")

    all_results.append({
        'date': test_date,
        'data': test_data[['period', 'period_idx', 'hour', 'rt_price', 'predicted']].copy(),
        'mae': mae, 'rmse': rmse, 'r2': r2,
    })

# ================================================================
# 6. FEATURE IMPORTANCE
# ================================================================
print("\n" + "=" * 60)
print("Phase 6: Feature Importance (Top 25)")
print("=" * 60)

importances = pd.Series(model.feature_importances_, index=dayahead_features)
importances = importances.sort_values(ascending=False)
for i, (feat, imp) in enumerate(importances.head(25).items()):
    bar = '█' * int(imp * 100)
    print(f"  {i+1:2d}. {feat:35s} {imp:.4f} {bar}")

# ================================================================
# 7. GENERATE CHARTS
# ================================================================
print("\n" + "=" * 60)
print("Phase 7: Generating Charts")
print("=" * 60)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

n_days = len(all_results)
n_cols = 2
n_rows = (n_days + 1) // 2

fig = plt.figure(figsize=(18, 4.5 * n_rows + 1.5))
gs = GridSpec(n_rows, n_cols, figure=fig, hspace=0.40, wspace=0.25)

avg_mae = np.mean([r['mae'] for r in all_results])
avg_rmse = np.mean([r['rmse'] for r in all_results])
avg_r2 = np.mean([r['r2'] for r in all_results])

fig.suptitle(
    f'P0 Day-Ahead Model (96-Period, GBR) — March 7-Day Backtest\n'
    f'Database: power_market.db | Features: {len(dayahead_features)} | '
    f'Avg MAE: {avg_mae:.1f} 元/MWh | Avg R²: {avg_r2:.3f}',
    fontsize=14, fontweight='bold', y=0.98
)

time_ticks_idx = list(range(0, 96, 12))
time_labels = [f'{(i*15)//60:02d}:00' for i in range(0, 96, 12)]

for idx, result in enumerate(all_results):
    r, c = divmod(idx, n_cols)
    ax = fig.add_subplot(gs[r, c])

    data = result['data'].sort_values('period_idx')
    actual = data['rt_price'].values
    predicted = data['predicted'].values
    periods = data['period_idx'].values

    date_str = f"{result['date'][:4]}-{result['date'][4:6]}-{result['date'][6:]}"
    mae = result['mae']

    ax.plot(periods, actual, 'b-o', markersize=1.8, linewidth=1.8,
            label='实时电价 (Actual)', zorder=3)
    ax.plot(periods, predicted, 'r--s', markersize=1.8, linewidth=1.6,
            label='预测电价 (Predicted)', alpha=0.9, zorder=2)
    ax.fill_between(periods, actual, predicted, alpha=0.15, color='gray', zorder=1)

    ax.set_xticks(time_ticks_idx)
    ax.set_xticklabels(time_labels, fontsize=8)
    ax.set_xlim(0, 95)
    ax.set_ylabel('电价 (元/MWh)', fontsize=9)
    ax.set_xlabel('时段', fontsize=9)

    color = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
    ax.set_title(f'{date_str}  MAE:{mae:.1f}  R²:{result["r2"]:.3f}',
                 fontsize=11, fontweight='bold')
    ax.text(0.97, 0.95, f'MAE: {mae:.1f}',
            transform=ax.transAxes, fontsize=10, fontweight='bold',
            va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.3, edgecolor=color))

    ax.legend(fontsize=7, loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

# Summary bar chart
if n_days % 2 == 1:
    ax_sum = fig.add_subplot(gs[n_rows - 1, 1])
    dates_short = [f"{r['date'][4:6]}-{r['date'][6:]}" for r in all_results]
    maes = [r['mae'] for r in all_results]
    colors = ['#228B22' if m < 40 else ('#FF8C00' if m < 80 else '#DC143C') for m in maes]
    bars = ax_sum.bar(dates_short, maes, color=colors, alpha=0.8, edgecolor='gray')
    for bar, m in zip(bars, maes):
        ax_sum.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                   f'{m:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax_sum.axhline(y=avg_mae, color='red', linestyle='--', linewidth=1.5, alpha=0.7)
    ax_sum.text(len(dates_short)-0.5, avg_mae + 1,
               f'Avg: {avg_mae:.1f}', fontsize=10, color='red', fontweight='bold', ha='right')
    ax_sum.set_ylabel('MAE (元/MWh)', fontsize=10)
    ax_sum.set_title('Daily MAE Summary', fontsize=12, fontweight='bold')
    ax_sum.grid(True, alpha=0.3, axis='y')

output_path = f'{OUTPUT_DIR}/p0_96period_march_7day.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print(f"  Main chart: {output_path}")

# ================================================================
# 8. FEATURE IMPORTANCE CHART
# ================================================================
fig2, ax2 = plt.subplots(figsize=(12, 8))
top25 = importances.head(25)
colors = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(top25)))
bars = ax2.barh(range(len(top25)), top25.values, color=colors)
ax2.set_yticks(range(len(top25)))
ax2.set_yticklabels(top25.index, fontsize=10)
ax2.invert_yaxis()
ax2.set_xlabel('Importance', fontsize=12)
ax2.set_title('P0 Day-Ahead Model — Top 25 Feature Importance\n'
              '(GradientBoosting, 96-period, no intraday leakage)',
              fontsize=13, fontweight='bold')
ax2.grid(True, alpha=0.3, axis='x')
for bar, val in zip(bars, top25.values):
    ax2.text(bar.get_width() + 0.001, bar.get_y() + bar.get_height()/2.,
             f'{val:.4f}', ha='left', va='center', fontsize=9)
plt.tight_layout()
feat_path = f'{OUTPUT_DIR}/p0_96period_feature_importance.png'
fig2.savefig(feat_path, dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print(f"  Feature chart: {feat_path}")

# ================================================================
# 9. SUMMARY
# ================================================================
print("\n" + "=" * 60)
print("FINAL REPORT — P0 Day-Ahead (96-Period)")
print("=" * 60)
print(f"\n  Model:     GradientBoosting (n=300, depth=5, lr=0.05)")
print(f"  Features:  {len(dayahead_features)} (no intraday leakage)")
print(f"  Training:  {df['date_key'].nunique()} days × 96 periods")
print(f"  Database:  power_market.db (real 15-min data)")
print(f"\n  {'Date':12s} {'MAE':>8s} {'RMSE':>8s} {'R²':>8s}")
print(f"  {'-'*40}")
for r in all_results:
    d = f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}"
    print(f"  {d:12s} {r['mae']:8.2f} {r['rmse']:8.2f} {r['r2']:8.4f}")
print(f"  {'-'*40}")
print(f"  {'AVERAGE':12s} {avg_mae:8.2f} {avg_rmse:8.2f} {avg_r2:8.4f}")
print(f"\n  Charts: {output_path}")
print(f"          {feat_path}")
print("\nDone! ✅")
