#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4 Hybrid Model - Adaptive Switching: P2(normal) + P3(anomaly)
===============================================================
Core logic:
  1. Train both P2-style (direct RT prediction) and P3-style (spread prediction)
  2. Detect anomaly signals from D-1 features
  3. Normal days: use P2 ensemble (GBR+LGB)
  4. Anomaly days: blend P3 spread correction
  5. Output: 10-day backtest with comparison
"""
import sqlite3, warnings, sys
import pandas as pd
import numpy as np

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

from config import DB, OUT_DIR

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def log(msg): print(f"  {msg}", flush=True)

print("=" * 70)
print("P4 Hybrid Model - Adaptive P2/P3 Switching")
print("=" * 70)

# ============================================================
# 1. Load all data
# ============================================================
log("[1/6] Loading data...")
conn = sqlite3.connect(DB)

# RT price hourly
price_rt = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour, AVG(price) as rt_price
    FROM realtime_node_price_96 WHERE node_name='__avg__'
    GROUP BY trade_date, SUBSTR(period, 1, 2)
""", conn)
price_rt['hour'] = price_rt['hour'].astype(int)

# DA price hourly
price_da = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour, AVG(price) as da_price
    FROM day_ahead_node_price_96 WHERE node_name='__all_avg__'
    GROUP BY trade_date, SUBSTR(period, 1, 2)
""", conn)
price_da['hour'] = price_da['hour'].astype(int)

# Manwan DA
manwan_da = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key,
           SUBSTR(period, 1, 2) as hour, AVG(price) as manwan_da
    FROM day_ahead_node_price_96
    WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
    GROUP BY trade_date, SUBSTR(period, 1, 2)
""", conn)
manwan_da['hour'] = manwan_da['hour'].astype(int)

# Yunnan load/renew/hydro
load_yn = pd.read_sql("SELECT date_key, SUBSTR(period,1,2) as hour, AVG(load) as yn_load FROM hourly_load WHERE region='云南' GROUP BY date_key, SUBSTR(period,1,2)", conn)
renew_yn = pd.read_sql("SELECT date_key, SUBSTR(period,1,2) as hour, AVG(output) as yn_renew FROM hourly_renewable WHERE region='云南' GROUP BY date_key, SUBSTR(period,1,2)", conn)
hydro_yn = pd.read_sql("SELECT date_key, SUBSTR(period,1,2) as hour, AVG(output) as yn_hydro FROM hourly_hydro WHERE region='云南' GROUP BY date_key, SUBSTR(period,1,2)", conn)
for t in [load_yn, renew_yn, hydro_yn]: t['hour'] = t['hour'].astype(int)

# Forecasts
renew_fc = pd.read_sql("SELECT forecast_date as date_key, SUBSTR(period,1,2) as hour, AVG(forecast_mw) as renew_forecast FROM renewable_forecast GROUP BY forecast_date, SUBSTR(period,1,2)", conn)
renew_fc['hour'] = renew_fc['hour'].astype(int)

load_fc = pd.read_sql("SELECT REPLACE(trade_date,'-','') as date_key, SUBSTR(period,1,2) as hour, AVG(forecast_load) as load_forecast FROM load_forecast WHERE region='云南' GROUP BY REPLACE(trade_date,'-',''), SUBSTR(period,1,2)", conn)
load_fc['hour'] = load_fc['hour'].astype(int)

# Section constraints
section = pd.read_sql("SELECT REPLACE(trade_date,'-','') as date_key, SUBSTR(period,1,2) as hour, AVG(limit_value) as avg_limit, COUNT(*) as n_constraints FROM section_constraint GROUP BY REPLACE(trade_date,'-',''), SUBSTR(period,1,2)", conn)
section['hour'] = section['hour'].astype(int)

conn.close()

# ============================================================
# 2. Build unified feature matrix
# ============================================================
log("[2/6] Building features...")

df = price_rt.merge(price_da, on=['date_key','hour'], how='inner')
df['date'] = pd.to_datetime(df['date_key'], format='%Y%m%d')
df['spread'] = df['rt_price'] - df['da_price']

# Merge all
for src, cols in [(load_yn, None), (renew_yn, None), (hydro_yn, None),
                  (manwan_da, None), (renew_fc, None), (load_fc, None), (section, None)]:
    df = df.merge(src, on=['date_key','hour'], how='left')

# Derived
df['yn_gap'] = df['yn_load'].fillna(0) - df['yn_renew'].fillna(0) - df['yn_hydro'].fillna(0)

# Time
df['dayofweek'] = df['date'].dt.dayofweek
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5,6]).astype(int)
df['hour_sin'] = np.sin(2*np.pi*df['hour']/24)
df['hour_cos'] = np.cos(2*np.pi*df['hour']/24)
df['dow_sin'] = np.sin(2*np.pi*df['dayofweek']/7)
df['dow_cos'] = np.cos(2*np.pi*df['dayofweek']/7)
df['is_wet_season'] = df['month'].isin([6,7,8,9,10]).astype(int)
df['month_sin'] = np.sin(2*np.pi*df['month']/12)
df['month_cos'] = np.cos(2*np.pi*df['month']/12)

# Sort for lags
df = df.sort_values(['hour','date_key']).reset_index(drop=True)

def lag_h(df, col, new, n):
    df[new] = df.groupby('hour')[col].shift(n)
    return df

# RT & spread lags
for n in [1,2,3,7]:
    df = lag_h(df, 'rt_price', f'rt_lag_{n}d', n)
    df = lag_h(df, 'spread', f'spread_lag_{n}d', n)

# Moving averages
for w in [3,5,7]:
    df[f'rt_ma_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
    df[f'spread_ma_{w}d'] = df.groupby('hour')['spread'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())

df['rt_std_5d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(5, min_periods=2).std().fillna(0))
df['spread_std_5d'] = df.groupby('hour')['spread'].transform(lambda x: x.shift(1).rolling(5, min_periods=2).std().fillna(0))

# Supply-demand lags
for n in [1,2]:
    df = lag_h(df, 'yn_load', f'load_lag_{n}d', n)
    df = lag_h(df, 'yn_renew', f'renew_lag_{n}d', n)
    df = lag_h(df, 'yn_gap', f'gap_lag_{n}d', n)
df = lag_h(df, 'yn_hydro', 'hydro_lag_1d', 1)
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

# Forecast error features
df = lag_h(df, 'yn_renew', 'renew_actual_lag1', 1)
df = lag_h(df, 'renew_forecast', 'renew_fc_lag1', 1)
df['renew_fc_error_lag1'] = df['renew_fc_lag1'] - df['renew_actual_lag1']
df['renew_fc_vs_lag1'] = df['renew_forecast'] - df['renew_actual_lag1']
df['load_fc_vs_lag1'] = df['load_forecast'] - df['load_lag_1d']

# DA features
df['da_manwan_spread'] = df['manwan_da'] - df['da_price']
df = lag_h(df, 'da_price', 'da_lag_1d', 1)
df['da_change'] = df['da_price'] - df['da_lag_1d']

# Previous day aggregates
daily = df.groupby('date_key').agg(
    prev_avg_spread=('spread','mean'), prev_max_spread=('spread','max'),
    prev_avg_rt=('rt_price','mean'), prev_std_rt=('rt_price','std'),
    prev_avg_gap=('yn_gap','mean'),
).reset_index()
all_dates = sorted(df['date_key'].unique())
date_shift = {d: all_dates[i-1] if i>0 else None for i,d in enumerate(all_dates)}
daily['dk'] = daily['date_key'].map(date_shift)
daily = daily.dropna(subset=['dk']).drop('date_key', axis=1).rename(columns={'dk':'date_key'})
df = df.merge(daily, on='date_key', how='left')

# Anomaly signal features (for switching logic)
df['abs_spread_lag1'] = df['spread_lag_1d'].abs()
df['spread_volatility'] = df['spread_std_5d']
df['da_rt_divergence_lag1'] = df['abs_spread_lag1'] / (df['rt_lag_1d'].abs() + 1)

df = df.sort_values(['date_key','hour']).reset_index(drop=True)

# ============================================================
# 3. Feature lists for P2 (RT target) and P3 (spread target)
# ============================================================

# P2 features: predict RT directly
P2_FEATURES = [
    'hour','dayofweek','month','is_weekend','hour_sin','hour_cos','dow_sin','dow_cos',
    'is_wet_season','month_sin','month_cos',
    'da_price','manwan_da','da_manwan_spread','da_change',
    'rt_lag_1d','rt_lag_2d','rt_lag_3d','rt_lag_7d',
    'rt_ma_3d','rt_ma_5d','rt_ma_7d','rt_std_5d',
    'load_lag_1d','load_lag_2d','renew_lag_1d','renew_lag_2d','hydro_lag_1d',
    'gap_lag_1d','gap_change',
    'renew_forecast','load_forecast',
    'renew_fc_vs_lag1','load_fc_vs_lag1','renew_fc_error_lag1',
    'avg_limit','n_constraints',
    'prev_avg_rt','prev_std_rt','prev_avg_gap',
]

# P3 features: predict spread (RT - DA)
P3_FEATURES = [
    'hour','dayofweek','month','is_weekend','hour_sin','hour_cos','dow_sin','dow_cos',
    'is_wet_season','month_sin','month_cos',
    'da_price','manwan_da','da_manwan_spread','da_change',
    'spread_lag_1d','spread_lag_2d','spread_lag_3d','spread_lag_7d',
    'spread_ma_3d','spread_ma_5d','spread_ma_7d','spread_std_5d',
    'rt_lag_1d','rt_lag_7d',
    'load_lag_1d','renew_lag_1d','hydro_lag_1d',
    'gap_lag_1d','gap_change',
    'renew_forecast','load_forecast',
    'renew_fc_vs_lag1','load_fc_vs_lag1','renew_fc_error_lag1',
    'avg_limit','n_constraints',
    'prev_avg_spread','prev_max_spread','prev_avg_rt',
]

p2_feats = [f for f in P2_FEATURES if f in df.columns]
p3_feats = [f for f in P3_FEATURES if f in df.columns]
log(f"P2 features: {len(p2_feats)}, P3 features: {len(p3_feats)}")

# ============================================================
# 4. Walk-forward with adaptive switching
# ============================================================
log("[3/6] Walk-forward with adaptive switching (3-13 ~ 3-22)...")

test_dates = [f'2026031{i}' for i in range(3,10)] + ['20260320','20260321','20260322']

results = []
for td in test_dates:
    train_mask = df['date_key'] < td
    test_mask = df['date_key'] == td

    X_train_p2 = df.loc[train_mask, p2_feats].fillna(0)
    X_train_p3 = df.loc[train_mask, p3_feats].fillna(0)
    y_train_rt = df.loc[train_mask, 'rt_price']
    y_train_spread = df.loc[train_mask, 'spread']

    X_test_p2 = df.loc[test_mask, p2_feats].fillna(0)
    X_test_p3 = df.loc[test_mask, p3_feats].fillna(0)
    y_test_rt = df.loc[test_mask, 'rt_price']
    da_test = df.loc[test_mask, 'da_price'].values

    valid_rt = y_train_rt.notna()
    valid_sp = y_train_spread.notna()

    if valid_rt.sum() < 24 or len(X_test_p2) == 0:
        continue

    # Sample weights
    train_dates_dt = df.loc[y_train_rt[valid_rt].index, 'date']
    test_dt = pd.to_datetime(td, format='%Y%m%d')
    days_ago = (test_dt - train_dates_dt).dt.days.values.astype(float)
    w_time = np.exp(-np.log(2) * days_ago / 60.0)
    same_season = np.isin(train_dates_dt.dt.month.values, [11,12,1,2,3,4,5])
    w_season = np.where(same_season, 2.0, 0.5)
    sw = w_time * w_season
    sw = sw / sw.mean()

    # ── P2 branch: predict RT directly ──
    gbr_p2 = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                        subsample=0.85, min_samples_leaf=5, random_state=42)
    gbr_p2.fit(X_train_p2[valid_rt], y_train_rt[valid_rt], sample_weight=sw)
    p2_gbr = gbr_p2.predict(X_test_p2)

    if HAS_LGB:
        lgb_p2 = lgb.LGBMRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                     subsample=0.85, min_child_samples=5, random_state=42, verbose=-1)
        lgb_p2.fit(X_train_p2[valid_rt], y_train_rt[valid_rt], sample_weight=sw)
        p2_lgb = lgb_p2.predict(X_test_p2)
    else:
        p2_lgb = p2_gbr

    p2_pred = 0.5 * p2_gbr + 0.5 * p2_lgb

    # ── P3 branch: predict spread, then RT = DA + spread ──
    sw_sp = sw[:valid_sp[valid_rt].sum()] if len(sw) >= valid_sp.sum() else sw
    gbr_p3 = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                        subsample=0.85, min_samples_leaf=5, random_state=42)
    gbr_p3.fit(X_train_p3[valid_sp], y_train_spread[valid_sp], sample_weight=sw[:valid_sp.sum()])
    p3_spread = gbr_p3.predict(X_test_p3)

    if HAS_LGB:
        lgb_p3 = lgb.LGBMRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                     subsample=0.85, min_child_samples=5, random_state=42, verbose=-1)
        lgb_p3.fit(X_train_p3[valid_sp], y_train_spread[valid_sp], sample_weight=sw[:valid_sp.sum()])
        p3_spread_lgb = lgb_p3.predict(X_test_p3)
        p3_spread_ens = 0.5 * p3_spread + 0.5 * p3_spread_lgb
    else:
        p3_spread_ens = p3_spread

    p3_pred = da_test + p3_spread_ens

    # ── Anomaly detection: compute switching weight ──
    # Signals from D-1 data:
    test_row = df.loc[test_mask].iloc[0]
    abs_spread_prev = abs(test_row.get('prev_avg_spread', 0) or 0)
    max_spread_prev = abs(test_row.get('prev_max_spread', 0) or 0)
    spread_vol = test_row.get('spread_std_5d', 0) or 0
    da_change_abs = abs(test_row.get('da_change', 0) or 0)

    # Anomaly score: higher = more likely anomalous day
    # Thresholds based on training data distribution
    train_spreads = df.loc[train_mask, 'spread'].dropna()
    spread_p75 = train_spreads.abs().quantile(0.75)
    spread_p90 = train_spreads.abs().quantile(0.90)

    anomaly_score = 0.0
    if abs_spread_prev > spread_p75: anomaly_score += 0.3
    if max_spread_prev > spread_p90: anomaly_score += 0.3
    if spread_vol > train_spreads.abs().std(): anomaly_score += 0.2
    if da_change_abs > 100: anomaly_score += 0.2

    anomaly_score = min(anomaly_score, 1.0)

    # Adaptive blend: w_p3 = anomaly_score (0=pure P2, 1=pure P3)
    # But cap P3 weight at 0.6 to avoid full P3 takeover
    w_p3 = min(anomaly_score * 0.8, 0.6)
    w_p2 = 1.0 - w_p3

    p4_pred = w_p2 * p2_pred + w_p3 * p3_pred

    # Metrics
    mae_p2 = mean_absolute_error(y_test_rt, p2_pred)
    mae_p3 = mean_absolute_error(y_test_rt, p3_pred)
    mae_da = mean_absolute_error(y_test_rt, da_test)
    mae_p4 = mean_absolute_error(y_test_rt, p4_pred)
    r2_p4 = r2_score(y_test_rt, p4_pred)

    results.append({
        'date': td,
        'actual': y_test_rt.values,
        'p2_pred': p2_pred,
        'p3_pred': p3_pred,
        'p4_pred': p4_pred,
        'da_price': da_test,
        'hours': df.loc[test_mask, 'hour'].values,
        'mae_p2': mae_p2, 'mae_p3': mae_p3,
        'mae_da': mae_da, 'mae_p4': mae_p4,
        'r2': r2_p4,
        'anomaly_score': anomaly_score,
        'w_p3': w_p3,
    })

    mode = "ANOMALY" if w_p3 > 0.2 else "NORMAL"
    log(f"  {td}: P4={mae_p4:.1f} (P2={mae_p2:.1f} P3={mae_p3:.1f} DA={mae_da:.1f}) "
        f"anom={anomaly_score:.2f} w_p3={w_p3:.2f} [{mode}] R2={r2_p4:.3f}")

# ============================================================
# 5. Chart: 10-day comparison
# ============================================================
log("\n[5/6] Generating charts...")

n = len(results)
n_rows = (n + 1) // 2
fig, axes = plt.subplots(n_rows, 2, figsize=(18, 4.5 * n_rows + 1.5))
fig.suptitle('P4 Hybrid Model - Adaptive P2/P3 Switching\n'
             'Normal: P2 (direct RT) | Anomaly: blend P3 (DA+spread)',
             fontsize=13, fontweight='bold', y=0.99)

axes_flat = axes.flatten()

for i, res in enumerate(results):
    ax = axes_flat[i]
    hrs = res['hours']
    order = np.argsort(hrs)
    actual = res['actual'][order]
    p4 = res['p4_pred'][order]
    da = res['da_price'][order]
    x = np.arange(len(actual))

    ax.plot(x, actual, 'b-o', ms=3, lw=2.2, label='RT actual', zorder=3)
    ax.plot(x, p4, 'r-s', ms=3, lw=1.8, label=f'P4 (MAE={res["mae_p4"]:.1f})', zorder=2)
    ax.plot(x, da, 'g--', lw=1.2, alpha=0.5, label=f'DA (MAE={res["mae_da"]:.1f})', zorder=1)
    ax.fill_between(x, actual, p4, alpha=0.12, color='gray')

    ax.set_xticks(list(range(0,24,3)))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0,24,3)], fontsize=8)
    ax.set_xlim(-0.5, len(x)-0.5)
    ax.set_ylabel('yuan/MWh', fontsize=9)
    ax.set_xlabel('hour', fontsize=9)
    ax.grid(True, alpha=0.3, ls='--')

    date_str = f"{res['date'][:4]}-{res['date'][4:6]}-{res['date'][6:8]}"
    best_of_3 = min(res['mae_p4'], res['mae_da'])
    improve_da = (res['mae_da'] - res['mae_p4']) / res['mae_da'] * 100

    mode = "ANOM" if res['w_p3'] > 0.2 else "NORM"
    color = '#228B22' if improve_da > 5 else ('#FF8C00' if improve_da > -5 else '#DC143C')

    ax.set_title(f"{date_str}  P4:{res['mae_p4']:.1f}  P2:{res['mae_p2']:.1f}  P3:{res['mae_p3']:.1f}  DA:{res['mae_da']:.1f}",
                 fontsize=9, fontweight='bold')
    ax.text(0.97, 0.95, f'{mode}\nw_p3={res["w_p3"]:.1f}\nvs DA {improve_da:+.0f}%',
            transform=ax.transAxes, fontsize=8, fontweight='bold', va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.3, edgecolor=color))
    ax.legend(fontsize=7, loc='upper left')

for j in range(n, len(axes_flat)):
    axes_flat[j].set_visible(False)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(f'{OUT_DIR}/p4_hybrid_10day.png', dpi=150, bbox_inches='tight')
log(f"  Saved: p4_hybrid_10day.png")

# ============================================================
# 6. Summary table
# ============================================================
print("\n" + "=" * 110)
print(f"{'Date':>10} {'P2':>7} {'P3':>7} {'P4':>7} {'DA':>7} {'Best':>7} {'Anom':>5} {'w_p3':>5} {'Mode':>6} {'vs DA':>7} {'R2':>6}")
print("-" * 110)

wins_p4 = 0
wins_da = 0
for r in results:
    best = min(r['mae_p4'], r['mae_da'])
    imp = (r['mae_da'] - r['mae_p4']) / r['mae_da'] * 100
    mode = "ANOM" if r['w_p3'] > 0.2 else "NORM"
    winner = "P4" if r['mae_p4'] <= r['mae_da'] else "DA"
    if winner == "P4": wins_p4 += 1
    else: wins_da += 1
    print(f"  {r['date']:>8} {r['mae_p2']:7.1f} {r['mae_p3']:7.1f} {r['mae_p4']:7.1f} "
          f"{r['mae_da']:7.1f} {best:7.1f} {r['anomaly_score']:5.2f} {r['w_p3']:5.2f} "
          f"{mode:>6} {imp:+6.1f}% {r['r2']:6.3f}")

avg_p2 = np.mean([r['mae_p2'] for r in results])
avg_p3 = np.mean([r['mae_p3'] for r in results])
avg_p4 = np.mean([r['mae_p4'] for r in results])
avg_da = np.mean([r['mae_da'] for r in results])
avg_best = np.mean([min(r['mae_p4'], r['mae_da']) for r in results])
avg_imp = (avg_da - avg_p4) / avg_da * 100

print("-" * 110)
print(f"  {'Avg':>8} {avg_p2:7.1f} {avg_p3:7.1f} {avg_p4:7.1f} {avg_da:7.1f} {avg_best:7.1f} "
      f"{'':>5} {'':>5} {'':>6} {avg_imp:+6.1f}%")
print(f"\n  P4 wins: {wins_p4}/{len(results)} days | DA wins: {wins_da}/{len(results)} days")
print(f"  Oracle best (always pick winner): avg MAE = {avg_best:.1f}")
print("=" * 110)
