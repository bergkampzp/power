#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3 Model - DA-RT Spread + Renewable Forecast Error + Simplified Ensemble
=========================================================================
Step 1: Target = RT - DA spread (not absolute RT price)
Step 2: Renewable forecast error features (D-1 forecast vs actual)
Step 3: LGB/XGB ensemble (no LSTM, simpler = better with limited data)
Step 4: Section constraint + maintenance features
10-day backtest: March 13-22, 2026
"""
import sqlite3, warnings, sys
import pandas as pd
import numpy as np

# Fix encoding for Windows
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

try:
    import lightgbm as lgb
    HAS_LGB = True
except:
    HAS_LGB = False

warnings.filterwarnings('ignore')

DB = 'F:/work/power-supply-v2/power/power-data/power_market_v2.db'
OUT_DIR = 'F:/work/power-supply-v2/power/power-data'

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def log(msg): print(f"  {msg}", flush=True)

# ============================================================
# 1. Load Data
# ============================================================
print("=" * 70)
print("P3 Model - DA-RT Spread + Forecast Error + Simplified Ensemble")
print("=" * 70)

conn = sqlite3.connect(DB)

# RT price (target source) - 全网加权平均
log("[1/7] Loading price data...")
price_rt = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour,
           AVG(price) as rt_price
    FROM realtime_node_price_96
    WHERE node_name = '__avg__'
    GROUP BY trade_date, SUBSTR(period, 1, 2)
    ORDER BY trade_date, hour
""", conn)
price_rt['hour'] = price_rt['hour'].astype(int)

# DA price (全网日前均价) - Step 1 core: this is the KNOWN baseline
price_da = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour,
           AVG(price) as da_price
    FROM day_ahead_node_price_96
    WHERE node_name = '__all_avg__'
    GROUP BY trade_date, SUBSTR(period, 1, 2)
    ORDER BY trade_date, hour
""", conn)
price_da['hour'] = price_da['hour'].astype(int)

# Manwan DA price
manwan_da = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour,
           AVG(price) as manwan_da
    FROM day_ahead_node_price_96
    WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
    GROUP BY trade_date, SUBSTR(period, 1, 2)
    ORDER BY trade_date, hour
""", conn)
manwan_da['hour'] = manwan_da['hour'].astype(int)

# Load (云南)
load_yn = pd.read_sql("""
    SELECT date_key, SUBSTR(period, 1, 2) as hour, AVG(load) as yn_load
    FROM hourly_load WHERE region='云南'
    GROUP BY date_key, SUBSTR(period, 1, 2)
""", conn)
load_yn['hour'] = load_yn['hour'].astype(int)

# Renewable (云南)
renew_yn = pd.read_sql("""
    SELECT date_key, SUBSTR(period, 1, 2) as hour, AVG(output) as yn_renew
    FROM hourly_renewable WHERE region='云南'
    GROUP BY date_key, SUBSTR(period, 1, 2)
""", conn)
renew_yn['hour'] = renew_yn['hour'].astype(int)

# Hydro (云南)
hydro_yn = pd.read_sql("""
    SELECT date_key, SUBSTR(period, 1, 2) as hour, AVG(output) as yn_hydro
    FROM hourly_hydro WHERE region='云南'
    GROUP BY date_key, SUBSTR(period, 1, 2)
""", conn)
hydro_yn['hour'] = hydro_yn['hour'].astype(int)

# Step 2: Renewable forecast (云南)
log("[2/7] Loading renewable forecast data...")
renew_fc = pd.read_sql("""
    SELECT forecast_date as date_key,
           SUBSTR(period, 1, 2) as hour,
           AVG(forecast_mw) as renew_forecast
    FROM renewable_forecast
    WHERE category LIKE '%合计%' OR category LIKE '%总%'
    GROUP BY forecast_date, SUBSTR(period, 1, 2)
""", conn)
# If no match on category, try all
if len(renew_fc) == 0:
    renew_fc = pd.read_sql("""
        SELECT forecast_date as date_key,
               SUBSTR(period, 1, 2) as hour,
               AVG(forecast_mw) as renew_forecast
        FROM renewable_forecast
        GROUP BY forecast_date, SUBSTR(period, 1, 2)
    """, conn)
renew_fc['hour'] = renew_fc['hour'].astype(int)

# Load forecast (云南)
load_fc = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour,
           AVG(forecast_load) as load_forecast
    FROM load_forecast
    WHERE region='云南'
    GROUP BY REPLACE(trade_date, '-', ''), SUBSTR(period, 1, 2)
""", conn)
load_fc['hour'] = load_fc['hour'].astype(int)

# Step 4: Section constraint summary
log("[3/7] Loading section constraint data...")
section = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour,
           AVG(limit_value) as avg_limit,
           MIN(limit_value) as min_limit,
           COUNT(*) as n_constraints
    FROM section_constraint
    GROUP BY REPLACE(trade_date, '-', ''), SUBSTR(period, 1, 2)
""", conn)
section['hour'] = section['hour'].astype(int)

# Maintenance: daily count (no capacity column available)
log("[4/7] Loading maintenance data...")
maint = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           COUNT(*) as maint_count
    FROM maintenance_plan
    GROUP BY REPLACE(trade_date, '-', '')
""", conn)

conn.close()

# ============================================================
# 2. Merge & Build Features
# ============================================================
log("[5/7] Building feature matrix...")

df = price_rt.merge(price_da, on=['date_key', 'hour'], how='inner')
df['date'] = pd.to_datetime(df['date_key'], format='%Y%m%d')

# Step 1: TARGET = RT - DA spread
df['spread'] = df['rt_price'] - df['da_price']

# Merge supply-demand
df = df.merge(load_yn, on=['date_key', 'hour'], how='left')
df = df.merge(renew_yn, on=['date_key', 'hour'], how='left')
df = df.merge(hydro_yn, on=['date_key', 'hour'], how='left')
df = df.merge(manwan_da, on=['date_key', 'hour'], how='left')

# Step 2: Merge forecasts
df = df.merge(renew_fc, on=['date_key', 'hour'], how='left')
df = df.merge(load_fc, on=['date_key', 'hour'], how='left')

# Step 4: Merge section constraints
df = df.merge(section, on=['date_key', 'hour'], how='left')
df = df.merge(maint, on=['date_key'], how='left')

# Supply-demand gap
df['yn_gap'] = df['yn_load'].fillna(0) - df['yn_renew'].fillna(0) - df['yn_hydro'].fillna(0)

# Time features
df['dayofweek'] = df['date'].dt.dayofweek
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)

# Season
df['is_wet_season'] = df['month'].isin([6, 7, 8, 9, 10]).astype(int)
df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

# Sort for lag
df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)

def lag_by_hour(df, col, new_col, n):
    df[new_col] = df.groupby('hour')[col].shift(n)
    return df

# Price & spread lags
for n in [1, 2, 3, 7]:
    df = lag_by_hour(df, 'rt_price', f'rt_lag_{n}d', n)
    df = lag_by_hour(df, 'spread', f'spread_lag_{n}d', n)

# Spread moving averages
for w in [3, 5, 7]:
    df[f'spread_ma_{w}d'] = (
        df.groupby('hour')['spread']
        .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
    )

df['spread_std_5d'] = (
    df.groupby('hour')['spread']
    .transform(lambda x: x.shift(1).rolling(5, min_periods=2).std().fillna(0))
)

# Supply-demand lags
for n in [1, 2]:
    df = lag_by_hour(df, 'yn_load', f'load_lag_{n}d', n)
    df = lag_by_hour(df, 'yn_renew', f'renew_lag_{n}d', n)
    df = lag_by_hour(df, 'yn_gap', f'gap_lag_{n}d', n)
df = lag_by_hour(df, 'yn_hydro', 'hydro_lag_1d', 1)
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

# Step 2: Forecast error features (D-1 forecast vs D-1 actual)
df = lag_by_hour(df, 'yn_renew', 'renew_actual_lag1', 1)
df = lag_by_hour(df, 'renew_forecast', 'renew_fc_lag1', 1)
df['renew_fc_error_lag1'] = df['renew_fc_lag1'] - df['renew_actual_lag1']  # positive = over-forecast
df['renew_fc_error_pct_lag1'] = np.where(
    df['renew_actual_lag1'] > 100,
    df['renew_fc_error_lag1'] / df['renew_actual_lag1'],
    0
)

# Current day forecast vs D-1 actual (forecast change signal)
df['renew_fc_vs_lag1'] = df['renew_forecast'] - df['renew_actual_lag1']
df['load_fc_vs_lag1'] = df['load_forecast'] - df['load_lag_1d']

# DA price features
df['da_manwan_spread'] = df['manwan_da'] - df['da_price']  # Manwan premium
df = lag_by_hour(df, 'da_price', 'da_lag_1d', 1)
df['da_change'] = df['da_price'] - df['da_lag_1d']

# Previous day stats
daily = df.groupby('date_key').agg(
    daily_avg_spread=('spread', 'mean'),
    daily_max_spread=('spread', 'max'),
    daily_avg_rt=('rt_price', 'mean'),
    daily_avg_gap=('yn_gap', 'mean'),
).reset_index()
daily.columns = ['date_key'] + [f'prev_{c}' for c in daily.columns[1:]]

all_dates = sorted(df['date_key'].unique())
date_shift = {d: all_dates[i-1] if i > 0 else None for i, d in enumerate(all_dates)}
daily['dk_target'] = daily['date_key'].map(date_shift)
daily = daily.dropna(subset=['dk_target']).drop('date_key', axis=1).rename(columns={'dk_target': 'date_key'})
df = df.merge(daily, on='date_key', how='left')

df = df.sort_values(['date_key', 'hour']).reset_index(drop=True)

# ============================================================
# 3. Feature List
# ============================================================
FEATURES = [
    # Time (10)
    'hour', 'dayofweek', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos',
    'month_sin', 'month_cos',
    # Season (2)
    'is_wet_season',
    # DA price (known, Step 1 core) (4)
    'da_price', 'manwan_da', 'da_manwan_spread', 'da_change',
    # Spread history (9)
    'spread_lag_1d', 'spread_lag_2d', 'spread_lag_3d', 'spread_lag_7d',
    'spread_ma_3d', 'spread_ma_5d', 'spread_ma_7d',
    'spread_std_5d',
    # RT price history (4)
    'rt_lag_1d', 'rt_lag_2d', 'rt_lag_3d', 'rt_lag_7d',
    # Supply-demand lags (6)
    'load_lag_1d', 'load_lag_2d',
    'renew_lag_1d', 'renew_lag_2d',
    'hydro_lag_1d',
    'gap_lag_1d',
    'gap_change',
    # Step 2: Forecast features (6)
    'renew_forecast', 'load_forecast',
    'renew_fc_error_lag1', 'renew_fc_error_pct_lag1',
    'renew_fc_vs_lag1', 'load_fc_vs_lag1',
    # Step 4: Section constraint + maintenance (4)
    'avg_limit', 'min_limit', 'n_constraints',
    'maint_count',
    # Previous day aggregates (4)
    'prev_daily_avg_spread', 'prev_daily_max_spread',
    'prev_daily_avg_rt', 'prev_daily_avg_gap',
]

features = [f for f in FEATURES if f in df.columns]
log(f"Features: {len(features)} active out of {len(FEATURES)}")
log(f"Total rows: {len(df)}, days: {df['date_key'].nunique()}")

# ============================================================
# 4. Walk-forward: predict SPREAD, then RT = DA + spread
# ============================================================
log("[6/7] Walk-forward prediction (3-13 ~ 3-22)...")

test_dates = [f'2026031{i}' for i in range(3, 10)] + ['20260320', '20260321', '20260322']

results = []
for td in test_dates:
    train_mask = df['date_key'] < td
    test_mask = df['date_key'] == td

    X_train = df.loc[train_mask, features].fillna(0)
    y_train_spread = df.loc[train_mask, 'spread']
    X_test = df.loc[test_mask, features].fillna(0)
    y_test_spread = df.loc[test_mask, 'spread']
    y_test_rt = df.loc[test_mask, 'rt_price']
    da_test = df.loc[test_mask, 'da_price'].values

    valid = y_train_spread.notna()
    X_train, y_train_spread = X_train[valid], y_train_spread[valid]

    if len(X_train) < 24 or len(X_test) == 0:
        log(f"  SKIP {td}")
        continue

    # Time decay + season weights
    train_dates_dt = df.loc[y_train_spread.index, 'date']
    test_dt = pd.to_datetime(td, format='%Y%m%d')
    days_ago = (test_dt - train_dates_dt).dt.days.values.astype(float)
    w_time = np.exp(-np.log(2) * days_ago / 60.0)
    train_months = train_dates_dt.dt.month.values
    same_season = np.isin(train_months, [11, 12, 1, 2, 3, 4, 5])
    w_season = np.where(same_season, 2.0, 0.5)
    sw = w_time * w_season
    sw = sw / sw.mean()

    # Step 3: Simplified ensemble - GBR + LGB + XGB (no LSTM)
    # Model A: GBR
    gbr = GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.85, min_samples_leaf=5, random_state=42
    )
    gbr.fit(X_train, y_train_spread, sample_weight=sw)
    p_gbr_spread = gbr.predict(X_test)

    # Model B: LightGBM
    if HAS_LGB:
        lgb_model = lgb.LGBMRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, min_child_samples=5, random_state=42, verbose=-1
        )
        lgb_model.fit(X_train, y_train_spread, sample_weight=sw)
        p_lgb_spread = lgb_model.predict(X_test)
    else:
        p_lgb_spread = p_gbr_spread

    # Model C: GBR with different params (acts as pseudo-XGB)
    xgb_proxy = GradientBoostingRegressor(
        n_estimators=400, max_depth=4, learning_rate=0.03,
        subsample=0.8, min_samples_leaf=8, random_state=123
    )
    xgb_proxy.fit(X_train, y_train_spread, sample_weight=sw)
    p_xgb_spread = xgb_proxy.predict(X_test)

    # Ensemble: equal weight for simplicity
    p_spread = (0.35 * p_gbr_spread + 0.35 * p_lgb_spread + 0.30 * p_xgb_spread)

    # Step 1 core: RT = DA + predicted_spread
    p_rt = da_test + p_spread

    # Also compute: naive DA baseline
    mae_ensemble = mean_absolute_error(y_test_rt, p_rt)
    mae_da_only = mean_absolute_error(y_test_rt, da_test)
    r2 = r2_score(y_test_rt, p_rt)

    # Individual model RT predictions
    mae_gbr = mean_absolute_error(y_test_rt, da_test + p_gbr_spread)
    mae_lgb = mean_absolute_error(y_test_rt, da_test + p_lgb_spread)
    mae_xgb = mean_absolute_error(y_test_rt, da_test + p_xgb_spread)

    results.append({
        'date': td,
        'actual': y_test_rt.values,
        'predicted': p_rt,
        'da_price': da_test,
        'spread_actual': y_test_spread.values,
        'spread_pred': p_spread,
        'hours': df.loc[test_mask, 'hour'].values,
        'mae': mae_ensemble,
        'mae_da': mae_da_only,
        'mae_gbr': mae_gbr,
        'mae_lgb': mae_lgb,
        'mae_xgb': mae_xgb,
        'r2': r2,
    })

    improve = (mae_da_only - mae_ensemble) / mae_da_only * 100
    log(f"  {td}: Ensemble MAE={mae_ensemble:.1f} (DA-only={mae_da_only:.1f}, improve={improve:+.1f}%)  "
        f"GBR={mae_gbr:.1f} LGB={mae_lgb:.1f} XGB={mae_xgb:.1f}  R2={r2:.3f}")

# Feature importance
if results:
    importances = gbr.feature_importances_
    feat_imp = sorted(zip(features, importances), key=lambda x: -x[1])
    log("\n  Top 15 feature importance:")
    for f, imp in feat_imp[:15]:
        log(f"    {f:30s} {imp*100:5.2f}%")

# ============================================================
# 5. Plot: 10-day comparison chart
# ============================================================
log("\n[7/7] Generating charts...")

n = len(results)
n_cols = 2
n_rows = (n + 1) // 2

fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 4.5 * n_rows + 1.5))
fig.suptitle('P3 Model - DA-RT Spread Prediction + Forecast Error Features\n'
             'RT = DA + predicted_spread | LGB/GBR/XGB Ensemble | 10-day backtest',
             fontsize=13, fontweight='bold', y=0.99)

axes_flat = axes.flatten()
hours_tick = list(range(0, 24, 3))
hours_label = [f"{h:02d}:00" for h in range(0, 24, 3)]

for i, res in enumerate(results):
    ax = axes_flat[i]
    actual = res['actual']
    pred = res['predicted']
    da = res['da_price']
    hrs = res['hours']

    order = np.argsort(hrs)
    actual = actual[order]
    pred = pred[order]
    da = da[order]
    x = np.arange(len(actual))

    # Plot: actual (blue), predicted (red), DA baseline (green dashed)
    ax.plot(x, actual, 'b-o', ms=3, lw=2.2, label='RT actual', zorder=3)
    ax.plot(x, pred, 'r-s', ms=3, lw=1.8, label=f'P3 pred (MAE={res["mae"]:.1f})', zorder=2)
    ax.plot(x, da, 'g--^', ms=2.5, lw=1.2, alpha=0.6, label=f'DA only (MAE={res["mae_da"]:.1f})', zorder=1)
    ax.fill_between(x, actual, pred, alpha=0.12, color='gray')

    ax.set_xticks(hours_tick)
    ax.set_xticklabels(hours_label, fontsize=8)
    ax.set_xlim(-0.5, len(x) - 0.5)
    ax.set_ylabel('price (yuan/MWh)', fontsize=9)
    ax.set_xlabel('hour', fontsize=9)
    ax.grid(True, alpha=0.3, ls='--')

    date_str = f"{res['date'][:4]}-{res['date'][4:6]}-{res['date'][6:8]}"
    improve = (res['mae_da'] - res['mae']) / res['mae_da'] * 100
    color = '#228B22' if improve > 10 else ('#FF8C00' if improve > 0 else '#DC143C')

    ax.set_title(f"{date_str}  MAE:{res['mae']:.1f}  R2:{res['r2']:.3f}  vs DA:{res['mae_da']:.1f}",
                 fontsize=10, fontweight='bold')
    ax.text(0.97, 0.95, f'vs DA\n{improve:+.0f}%', transform=ax.transAxes,
            fontsize=10, fontweight='bold', va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.3, edgecolor=color))
    ax.legend(fontsize=7, loc='upper left')

# Hide unused
for j in range(n, len(axes_flat)):
    axes_flat[j].set_visible(False)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(f'{OUT_DIR}/p3_spread_10day.png', dpi=150, bbox_inches='tight')
log(f"  Saved: p3_spread_10day.png")

# Summary table
print("\n" + "=" * 100)
print(f"{'Date':>10}  {'GBR':>7}  {'LGB':>7}  {'XGB':>7}  {'Ensem':>7}  {'DA-only':>7}  {'Improve':>8}  {'R2':>6}")
print("-" * 100)
for r in results:
    imp = (r['mae_da'] - r['mae']) / r['mae_da'] * 100
    print(f"  {r['date']:>8}  {r['mae_gbr']:7.1f}  {r['mae_lgb']:7.1f}  {r['mae_xgb']:7.1f}  "
          f"{r['mae']:7.1f}  {r['mae_da']:7.1f}  {imp:+7.1f}%  {r['r2']:6.3f}")

avg_mae = np.mean([r['mae'] for r in results])
avg_da = np.mean([r['mae_da'] for r in results])
avg_imp = (avg_da - avg_mae) / avg_da * 100
print("-" * 100)
print(f"  {'Avg':>8}  {np.mean([r['mae_gbr'] for r in results]):7.1f}  "
      f"{np.mean([r['mae_lgb'] for r in results]):7.1f}  "
      f"{np.mean([r['mae_xgb'] for r in results]):7.1f}  "
      f"{avg_mae:7.1f}  {avg_da:7.1f}  {avg_imp:+7.1f}%")
print("=" * 100)
