#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 v2 vs v3.3 对标图
March 4-10 (same 7 days as v3.3 chart)
Style matches v3.3 exactly: blue actual, red dashed predicted, gray fill
"""
import sqlite3, warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings('ignore')

from config import DB
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

PERIODS_96 = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]]
period_map = {p: i for i, p in enumerate(PERIODS_96)}

# ============================================================
# 1. Load & build features (same as p0_model_v2.py)
# ============================================================
def load_and_build():
    conn = sqlite3.connect(DB)
    price = pd.read_sql("SELECT date_key, period, rt_price FROM realtime_hourly_price ORDER BY date_key, period", conn)
    price['date'] = pd.to_datetime(price['date_key'], format='%Y%m%d')
    load = pd.read_sql("SELECT date_key, period, load FROM hourly_load WHERE region='全区域' ORDER BY date_key, period", conn)
    renew = pd.read_sql("SELECT date_key, period, output FROM hourly_renewable WHERE region='云南' ORDER BY date_key, period", conn)
    hydro = pd.read_sql("SELECT date_key, period, output FROM hourly_hydro WHERE region='云南' ORDER BY date_key, period", conn)
    manwan_da = pd.read_sql("""
        SELECT trade_date, period, AVG(price) as manwan_da_price
        FROM day_ahead_node_price_96
        WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
        GROUP BY trade_date, period ORDER BY trade_date, period
    """, conn)
    grid_da = pd.read_sql("""
        SELECT trade_date, period, price as grid_da_avg
        FROM day_ahead_node_price_96 WHERE node_name = '__all_avg__'
        ORDER BY trade_date, period
    """, conn)
    conn.close()

    df = price.copy()
    df = df.merge(load.rename(columns={'load': 'total_load'}), on=['date_key', 'period'], how='left')
    df = df.merge(renew.rename(columns={'output': 'renewable'}), on=['date_key', 'period'], how='left')
    df = df.merge(hydro.rename(columns={'output': 'hydro'}), on=['date_key', 'period'], how='left')

    df['period_idx'] = df['period'].map(period_map).fillna(0).astype(int)
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
    df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)

    df = df.sort_values(['period_idx', 'date_key']).reset_index(drop=True)

    def lag(df, col, new, n):
        df[new] = df.groupby('period_idx')[col].shift(n)
        return df

    for l in [1, 2, 3, 7]: df = lag(df, 'rt_price', f'price_lag_{l}d', l)
    for l in [1, 2]: df = lag(df, 'total_load', f'load_lag_{l}d', l)
    for l in [1, 2]: df = lag(df, 'renewable', f'renew_lag_{l}d', l)
    df = lag(df, 'hydro', 'hydro_lag_1d', 1)
    df = lag(df, 'gap', 'gap_lag_1d', 1)
    df = lag(df, 'gap', 'gap_lag_2d', 2)

    for w in [3, 5, 7]:
        df[f'price_ma_{w}d'] = df.groupby('period_idx')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
        df[f'price_std_{w}d'] = df.groupby('period_idx')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0))

    df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
    df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

    daily = df.groupby('date_key').agg(
        daily_avg_price=('rt_price', 'mean'), daily_max_price=('rt_price', 'max'),
        daily_min_price=('rt_price', 'min'), daily_std_price=('rt_price', 'std'),
        daily_avg_load=('total_load', 'mean'), daily_avg_renew=('renewable', 'mean'),
        daily_avg_gap=('gap', 'mean'),
    ).reset_index()
    daily.columns = ['date_key'] + [f'prevday_{c}' for c in daily.columns[1:]]
    all_dates = sorted(df['date_key'].unique())
    date_shift = {d: all_dates[i-1] if i > 0 else None for i, d in enumerate(all_dates)}
    daily['dk_target'] = daily['date_key'].map(date_shift)
    daily = daily.dropna(subset=['dk_target']).drop('date_key', axis=1).rename(columns={'dk_target': 'date_key'})
    df = df.merge(daily, on='date_key', how='left')
    df['prev_period_to_daily_ratio'] = np.where(df['prevday_daily_avg_price'] > 0, df['price_lag_1d'] / df['prevday_daily_avg_price'], 1.0)

    manwan_da['date_key'] = pd.to_datetime(manwan_da['trade_date']).dt.strftime('%Y%m%d')
    df = df.merge(manwan_da[['date_key', 'period', 'manwan_da_price']], on=['date_key', 'period'], how='left')
    df = lag(df, 'manwan_da_price', 'manwan_da_lag1d', 1)
    df = lag(df, 'manwan_da_price', 'manwan_da_prev', 1)
    df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_prev']

    grid_da['date_key'] = pd.to_datetime(grid_da['trade_date']).dt.strftime('%Y%m%d')
    df = df.merge(grid_da[['date_key', 'period', 'grid_da_avg']], on=['date_key', 'period'], how='left')

    df = df.sort_values(['date_key', 'period_idx']).reset_index(drop=True)
    return df

# ============================================================
# 2. Predict March 4-10 (same as v3.3)
# ============================================================
FEATURES = [
    'hour', 'minute_slot', 'period_idx', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'period_sin', 'period_cos', 'dow_sin', 'dow_cos',
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d', 'price_momentum_3d',
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

# v3.3 MAE values for comparison
V33_MAE = {
    '20260304': 128.0, '20260305': 26.0, '20260306': 36.9,
    '20260307': 16.7, '20260308': 37.9, '20260309': 112.0, '20260310': 146.2,
}

print("Loading data...", flush=True)
df = load_and_build()

test_dates = ['20260304', '20260305', '20260306', '20260307', '20260308', '20260309', '20260310']
features = [f for f in FEATURES if f in df.columns]
print(f"Features: {len(features)}", flush=True)

results = []
for td in test_dates:
    train = df[df['date_key'] < td]
    test = df[df['date_key'] == td]
    X_tr = train[features].fillna(0)
    y_tr = train['rt_price'].dropna()
    X_tr = X_tr.loc[y_tr.index]
    X_te = test[features].fillna(0)
    y_te = test['rt_price']

    model = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.85, min_samples_leaf=5, random_state=42)
    model.fit(X_tr, y_tr)
    preds = model.predict(X_te)
    mae = mean_absolute_error(y_te, preds)

    order = np.argsort(test['period_idx'].values)
    results.append({
        'date': td,
        'actual': y_te.values[order],
        'predicted': preds[order],
        'mae': mae,
        'v33_mae': V33_MAE.get(td, None),
    })
    print(f"  {td}: P0v2 MAE={mae:.1f}  v3.3 MAE={V33_MAE.get(td, '?')}", flush=True)

# ============================================================
# 3. Plot - exact v3.3 style
# ============================================================
print("Generating chart...", flush=True)

fig = plt.figure(figsize=(16, 18))

# 7 subplots (4 rows × 2 cols, last row has 1 + summary)
from matplotlib.gridspec import GridSpec
gs = GridSpec(4, 2, figure=fig, hspace=0.38, wspace=0.25)

fig.suptitle('P0 v2 模型 - 实时电价预测 vs 实际电价 (3月4-10日)\n'
             '零泄露 | 96时段 | Walk-Forward | 对标v3.3',
             fontsize=14, fontweight='bold', y=0.98)

# Hour tick positions (every 3 hours)
xt = list(range(0, 96, 12))  # 0,12,24,...84
xl = [f"{h:02d}:00" for h in range(0, 24, 3)]

for i, res in enumerate(results):
    r, c = divmod(i, 2)
    if i < 6:
        ax = fig.add_subplot(gs[r, c])
    else:
        ax = fig.add_subplot(gs[3, 0])

    x = np.arange(96)
    actual = res['actual'][:96]
    pred = res['predicted'][:96]

    ax.plot(x, actual, 'b-o', ms=2, lw=1.8, label='实际电价', zorder=3)
    ax.plot(x, pred, 'r--s', ms=2, lw=1.6, label='预测电价', alpha=0.9, zorder=2)
    ax.fill_between(x, actual, pred, alpha=0.15, color='gray')

    ax.set_xticks(xt)
    ax.set_xticklabels(xl, fontsize=8)
    ax.set_xlim(0, 95)
    ax.set_ylabel('电价(元/MWh)', fontsize=9)
    ax.set_xlabel('时间', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

    date_str = f"2026-{res['date'][4:6]}-{res['date'][6:8]}"
    mae = res['mae']
    v33 = res['v33_mae']
    improve = ((v33 - mae) / v33 * 100) if v33 else 0

    color = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
    ax.set_title(f"{date_str}  MAE:{mae:.1f}  (v3.3: {v33})", fontsize=11, fontweight='bold')

    # MAE badge with improvement
    badge_text = f'MAE:{mae:.1f}\n↓{improve:.0f}%' if improve > 0 else f'MAE:{mae:.1f}\n↑{-improve:.0f}%'
    badge_color = '#228B22' if improve > 0 else '#DC143C'
    ax.text(0.97, 0.95, badge_text, transform=ax.transAxes, fontsize=9, fontweight='bold',
            va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=badge_color, alpha=0.25, edgecolor=badge_color))
    ax.legend(fontsize=7, loc='upper left')

# Summary bar chart (bottom right)
ax_sum = fig.add_subplot(gs[3, 1])
dates_s = [f"03-{r['date'][6:8]}" for r in results]
p0_maes = [r['mae'] for r in results]
v33_maes = [r['v33_mae'] for r in results]

x_bar = np.arange(len(dates_s))
w = 0.35
bars1 = ax_sum.bar(x_bar - w/2, v33_maes, w, color='#4169E1', alpha=0.7, label='v3.3 参考', edgecolor='gray')
bars2 = ax_sum.bar(x_bar + w/2, p0_maes, w, color='#DC143C', alpha=0.7, label='P0 v2 零泄露', edgecolor='gray')

for bar, m in zip(bars1, v33_maes):
    ax_sum.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{m:.0f}', ha='center', va='bottom', fontsize=7, color='#4169E1')
for bar, m in zip(bars2, p0_maes):
    ax_sum.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{m:.1f}', ha='center', va='bottom', fontsize=7, color='#DC143C')

avg_v33 = np.mean(v33_maes)
avg_p0 = np.mean(p0_maes)
ax_sum.axhline(avg_v33, color='#4169E1', ls='--', lw=1.2, alpha=0.6)
ax_sum.axhline(avg_p0, color='#DC143C', ls='--', lw=1.2, alpha=0.6)
ax_sum.text(6.5, avg_v33 + 2, f'v3.3 均值:{avg_v33:.1f}', ha='right', fontsize=9, color='#4169E1', fontweight='bold')
ax_sum.text(6.5, avg_p0 + 2, f'P0v2 均值:{avg_p0:.1f}', ha='right', fontsize=9, color='#DC143C', fontweight='bold')

ax_sum.set_xticks(x_bar)
ax_sum.set_xticklabels(dates_s, fontsize=9)
ax_sum.set_ylabel('MAE (元/MWh)', fontsize=10)
ax_sum.set_title(f'MAE对比: P0v2 vs v3.3  (↓{(1-avg_p0/avg_v33)*100:.0f}%)', fontsize=12, fontweight='bold')
ax_sum.legend(fontsize=9)
ax_sum.grid(True, alpha=0.3, axis='y')

out = os.path.join(OUT_DIR, 'p0_v2_vs_v33_march4_10.png')
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print(f"\nChart saved: {out}", flush=True)

# Summary table
print("\n" + "=" * 55)
print(f"{'日期':8s} {'v3.3 MAE':>10s} {'P0v2 MAE':>10s} {'改善':>8s}")
print("-" * 55)
for r in results:
    v33 = r['v33_mae']
    p0 = r['mae']
    imp = f"↓{(v33-p0)/v33*100:.0f}%" if p0 < v33 else f"↑{(p0-v33)/v33*100:.0f}%"
    print(f"{r['date']:8s} {v33:>10.1f} {p0:>10.1f} {imp:>8s}")
print("-" * 55)
print(f"{'平均':8s} {avg_v33:>10.1f} {avg_p0:>10.1f} ↓{(1-avg_p0/avg_v33)*100:.0f}%")
print("=" * 55)
