#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 March 7-Day: Actual vs Predicted Price Chart
Style matching v3.3 intraday chart format
"""

import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from sklearn.ensemble import GradientBoostingRegressor
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. Load data & build features (same as p0_feature_optimization.py)
# ============================================================
from config import OUTPUT_DIR
DATA_PATH = os.path.join(OUTPUT_DIR, 'market_data.json')

with open(DATA_PATH, 'r') as f:
    raw = json.load(f)

df = pd.DataFrame({
    'date': pd.to_datetime(raw['dates']),
    'price': raw['price'],
    'min_price': raw['min_price'],
    'max_price': raw['max_price'],
    'solar': raw['solar'],
    'renewable': raw['renewable'],
    'load': raw['load'],
    'demand': raw['demand'],
})
df = df.sort_values('date').reset_index(drop=True)

# Feature engineering (P0)
df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)
df['day_sin'] = np.sin(2 * np.pi * df['day'] / 31)
df['day_cos'] = np.cos(2 * np.pi * df['day'] / 31)

df['supply_demand_gap'] = df['load'] - df['renewable']
df['renewable_ratio'] = df['renewable'] / df['load']
df['load_renewable_diff_pct'] = (df['load'] - df['renewable']) / df['load']
df['price_range'] = df['max_price'] - df['min_price']
df['price_volatility'] = df['price_range'] / (df['price'] + 1e-6)
df['price_skew'] = (df['price'] - df['min_price']) / (df['price_range'] + 1e-6)

for lag in [1, 2, 3, 7]:
    df[f'price_lag_{lag}'] = df['price'].shift(lag)
    df[f'gap_lag_{lag}'] = df['supply_demand_gap'].shift(lag)

df['gap_change'] = df['supply_demand_gap'].diff()
df['gap_change_pct'] = df['supply_demand_gap'].pct_change()

for w in [3, 5, 7]:
    df[f'price_ma_{w}'] = df['price'].rolling(w, min_periods=1).mean()
    df[f'price_std_{w}'] = df['price'].rolling(w, min_periods=1).std().fillna(0)
    df[f'gap_ma_{w}'] = df['supply_demand_gap'].rolling(w, min_periods=1).mean()
    df[f'load_ma_{w}'] = df['load'].rolling(w, min_periods=1).mean()

df['price_change'] = df['price'].diff()
df['price_change_pct'] = df['price'].pct_change()
df['price_momentum_3'] = df['price'] - df['price_ma_3']
df['demand_price_ratio'] = df['demand'] / (df['price'] + 1e-6)
for lag in [1, 2]:
    df[f'demand_lag_{lag}'] = df['demand'].shift(lag)

df_clean = df.dropna().copy()

p0_features = [
    'dayofweek', 'day', 'month', 'is_weekend',
    'dow_sin', 'dow_cos', 'day_sin', 'day_cos',
    'solar', 'renewable', 'load',
    'supply_demand_gap', 'renewable_ratio', 'load_renewable_diff_pct',
    'gap_lag_1', 'gap_lag_2', 'gap_change', 'gap_change_pct',
    'gap_ma_3', 'gap_ma_5',
    'price_lag_1', 'price_lag_2', 'price_lag_3', 'price_lag_7',
    'price_ma_3', 'price_ma_5', 'price_ma_7',
    'price_std_3', 'price_std_7',
    'price_change', 'price_change_pct', 'price_momentum_3',
    'price_range', 'price_volatility', 'price_skew',
    'demand', 'demand_lag_1', 'demand_lag_2', 'demand_price_ratio',
    'load_ma_3', 'load_ma_5', 'load_ma_7',
]
p0_features = [c for c in p0_features if c in df_clean.columns]

# ============================================================
# 2. Walk-forward prediction for March 7 days
# ============================================================
march_mask = df_clean['date'].dt.month == 3
march_data = df_clean[march_mask]
test_dates = sorted(march_data['date'].unique())[-7:]

daily_results = []
for test_date in test_dates:
    train_mask = df_clean['date'] < test_date
    test_mask = df_clean['date'] == test_date
    if train_mask.sum() < 5:
        continue
    X_train = df_clean.loc[train_mask, p0_features].fillna(0)
    y_train = df_clean.loc[train_mask, 'price']
    X_test = df_clean.loc[test_mask, p0_features].fillna(0)
    y_test = df_clean.loc[test_mask, 'price']
    if len(X_test) == 0:
        continue

    model = GradientBoostingRegressor(
        n_estimators=150, max_depth=4, learning_rate=0.1,
        subsample=0.8, random_state=42
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)[0]
    actual = y_test.values[0]

    row = df_clean[test_mask].iloc[0]
    daily_results.append({
        'date': test_date,
        'actual': actual,
        'predicted': pred,
        'min_price': row['min_price'],
        'max_price': row['max_price'],
        'mae': abs(actual - pred),
        'solar': row['solar'],
        'load': row['load'],
        'gap': row['supply_demand_gap'],
    })

res = pd.DataFrame(daily_results)

# ============================================================
# 3. Synthesize intraday curves from daily stats
#    Using typical Yunnan price profile shape
# ============================================================
hours = np.arange(0, 24, 0.25)  # 15-min intervals like v3.3

def generate_intraday_curve(avg_price, min_price, max_price, solar, load, seed=42):
    """
    Generate a realistic 96-point intraday price curve
    based on typical Yunnan grid pattern:
    - Morning peak (06:00-09:00): high prices
    - Solar trough (11:00-15:00): low prices (solar flood)
    - Evening peak (17:00-21:00): high prices
    - Night (22:00-05:00): moderate prices
    """
    rng = np.random.RandomState(seed)
    t = hours

    # Base profile shape (normalized 0-1)
    # Morning ramp
    morning = 0.7 * np.exp(-0.5 * ((t - 7) / 2) ** 2)
    # Solar dip (stronger when more solar)
    solar_factor = min(solar / 12000, 1.3)
    solar_dip = -0.5 * solar_factor * np.exp(-0.5 * ((t - 13) / 2.5) ** 2)
    # Evening peak
    evening = 0.9 * np.exp(-0.5 * ((t - 18.5) / 2) ** 2)
    # Night baseline
    night = 0.3 * (1 + 0.15 * np.sin(2 * np.pi * t / 24 - np.pi/2))

    # Combined shape
    shape = night + morning + solar_dip + evening
    shape = shape - shape.min()
    shape = shape / (shape.max() + 1e-6)

    # Scale to actual price range
    curve = min_price + shape * (max_price - min_price)

    # Adjust mean to match actual average
    curve = curve * (avg_price / (curve.mean() + 1e-6))

    # Add small noise
    noise = rng.normal(0, (max_price - min_price) * 0.03, len(t))
    curve = curve + noise
    curve = np.clip(curve, 0, max_price * 1.2)

    return curve

# ============================================================
# 4. Plot - matching v3.3 style
# ============================================================
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

n_days = len(res)
n_cols = 2
n_rows = (n_days + 1) // 2

fig = plt.figure(figsize=(16, 4.2 * n_rows + 1.2))
gs = GridSpec(n_rows, n_cols, figure=fig, hspace=0.38, wspace=0.25)

fig.suptitle('P0 v3.3 Model - March 7-Day Price Prediction vs Actual\n'
             '(Intraday curves synthesized from daily stats + typical Yunnan profile)',
             fontsize=15, fontweight='bold', y=0.98)

total_mae = res['mae'].mean()

for idx, (_, row) in enumerate(res.iterrows()):
    r, c = divmod(idx, n_cols)
    ax = fig.add_subplot(gs[r, c])

    date_str = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
    mae = row['mae']

    # Generate intraday curves
    actual_curve = generate_intraday_curve(
        row['actual'], row['min_price'], row['max_price'],
        row['solar'], row['load'], seed=42 + idx
    )

    # Predicted curve: use predicted avg, slightly narrower range
    pred_range_factor = 0.85  # predicted range narrower (model is smoother)
    pred_min = row['predicted'] - (row['actual'] - row['min_price']) * pred_range_factor
    pred_max = row['predicted'] + (row['max_price'] - row['actual']) * pred_range_factor
    pred_min = max(pred_min, 0)

    predicted_curve = generate_intraday_curve(
        row['predicted'], pred_min, pred_max,
        row['solar'], row['load'], seed=100 + idx
    )

    # Time axis labels
    time_labels = [f'{int(h):02d}:00' for h in range(0, 24, 3)]
    time_ticks = [h * 4 for h in range(0, 24, 3)]  # index in 15-min array

    # Plot
    ax.plot(actual_curve, 'b-o', markersize=1.5, linewidth=1.8,
            label='Actual Price', zorder=3)
    ax.plot(predicted_curve, 'r--s', markersize=1.5, linewidth=1.6,
            label='Predicted Price', alpha=0.9, zorder=2)

    # Shaded area between
    ax.fill_between(range(len(hours)), actual_curve, predicted_curve,
                    alpha=0.15, color='gray', zorder=1)

    ax.set_xticks(time_ticks)
    ax.set_xticklabels(time_labels, fontsize=8, rotation=0)
    ax.set_xlim(0, len(hours) - 1)
    ax.set_ylabel('Price (yuan/MWh)', fontsize=9)
    ax.set_xlabel('Time', fontsize=9)

    # Title with MAE
    color = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
    ax.set_title(f'{date_str}  MAE:{mae:.1f}', fontsize=12, fontweight='bold', color='black')

    # MAE badge
    ax.text(0.97, 0.95, f'MAE: {mae:.1f}',
            transform=ax.transAxes, fontsize=10, fontweight='bold',
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.3, edgecolor=color))

    ax.legend(fontsize=8, loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

# If odd number of days, remove last empty subplot
if n_days % 2 == 1:
    fig.add_subplot(gs[n_rows - 1, 1])
    ax_summary = fig.add_subplot(gs[n_rows - 1, 1])

    # Summary bar chart
    dates_short = [pd.to_datetime(d).strftime('%m-%d') for d in res['date']]
    colors = ['#228B22' if m < 40 else ('#FF8C00' if m < 80 else '#DC143C') for m in res['mae']]
    bars = ax_summary.bar(dates_short, res['mae'], color=colors, alpha=0.8, edgecolor='gray')

    for bar, mae_val in zip(bars, res['mae']):
        ax_summary.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 1,
                       f'{mae_val:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax_summary.axhline(y=total_mae, color='red', linestyle='--', linewidth=1.5, alpha=0.7)
    ax_summary.text(len(dates_short) - 0.5, total_mae + 2,
                   f'Avg MAE: {total_mae:.1f}', fontsize=10, color='red', fontweight='bold',
                   ha='right')

    ax_summary.set_ylabel('MAE (yuan/MWh)', fontsize=10)
    ax_summary.set_title('Daily MAE Summary', fontsize=12, fontweight='bold')
    ax_summary.grid(True, alpha=0.3, axis='y')

output_path = os.path.join(OUTPUT_DIR, 'p0_march_7day_intraday.png')
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print(f"Chart saved: {output_path}")
print(f"Average MAE: {total_mae:.1f} yuan/MWh")
