#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2 Model - Forward Prediction for 3-23 & 3-24
================================================
Uses P2 ensemble (GBR+LGB+XGB) trained on all available data.
3-23: DA price available, D-1 lags from 3-22 actuals
3-24: No DA, use D-1=3-23 predicted, D-2=3-22 actual
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
from sklearn.metrics import mean_absolute_error
import lightgbm as lgb
import xgboost as xgb

warnings.filterwarnings('ignore')
DB = 'F:/work/power-supply-v2/power/power-data/power_market_v2.db'
OUT = 'F:/work/power-supply-v2/power/power-data'

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def log(msg): print(f"  {msg}", flush=True)

print("=" * 70)
print("P2 Forward Prediction: March 23-24, 2026")
print("=" * 70)

# ============================================================
# 1. Load data (same as P2 pipeline, hourly aggregation)
# ============================================================
log("[1/5] Loading data...")
conn = sqlite3.connect(DB)

# RT price hourly (training target)
price = pd.read_sql("""
    SELECT REPLACE(trade_date,'-','') as date_key,
           SUBSTR(period,1,2) as hour, AVG(price) as rt_price
    FROM realtime_node_price_96 WHERE node_name='__avg__'
    GROUP BY trade_date, SUBSTR(period,1,2)
""", conn)
price['hour'] = price['hour'].astype(int)
price['date'] = pd.to_datetime(price['date_key'], format='%Y%m%d')

# DA price hourly
da = pd.read_sql("""
    SELECT REPLACE(trade_date,'-','') as date_key,
           SUBSTR(period,1,2) as hour, AVG(price) as da_price
    FROM day_ahead_node_price_96 WHERE node_name='__all_avg__'
    GROUP BY trade_date, SUBSTR(period,1,2)
""", conn)
da['hour'] = da['hour'].astype(int)

# Manwan DA
mw_da = pd.read_sql("""
    SELECT REPLACE(trade_date,'-','') as date_key,
           SUBSTR(period,1,2) as hour, AVG(price) as manwan_da
    FROM day_ahead_node_price_96
    WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
    GROUP BY trade_date, SUBSTR(period,1,2)
""", conn)
mw_da['hour'] = mw_da['hour'].astype(int)

# Yunnan supply-demand
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
# 2. Build feature matrix (same as P2)
# ============================================================
log("[2/5] Building features...")

df = price.merge(da, on=['date_key','hour'], how='left')
df = df.merge(mw_da, on=['date_key','hour'], how='left')
df = df.merge(load_yn, on=['date_key','hour'], how='left')
df = df.merge(renew_yn, on=['date_key','hour'], how='left')
df = df.merge(hydro_yn, on=['date_key','hour'], how='left')
df = df.merge(renew_fc, on=['date_key','hour'], how='left')
df = df.merge(load_fc, on=['date_key','hour'], how='left')
df = df.merge(section, on=['date_key','hour'], how='left')

df['yn_gap'] = df['yn_load'].fillna(0) - df['yn_renew'].fillna(0) - df['yn_hydro'].fillna(0)
df['spread'] = df['rt_price'] - df['da_price']

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

df = df.sort_values(['hour','date_key']).reset_index(drop=True)

def lag_h(df, col, new, n):
    df[new] = df.groupby('hour')[col].shift(n)
    return df

for n in [1,2,3,7]:
    df = lag_h(df, 'rt_price', f'rt_lag_{n}d', n)
for n in [1,2]:
    df = lag_h(df, 'yn_load', f'load_lag_{n}d', n)
    df = lag_h(df, 'yn_renew', f'renew_lag_{n}d', n)
    df = lag_h(df, 'yn_gap', f'gap_lag_{n}d', n)
df = lag_h(df, 'yn_hydro', 'hydro_lag_1d', 1)
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

for w in [3,5,7]:
    df[f'rt_ma_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())

df['rt_std_5d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(5, min_periods=2).std().fillna(0))

# Forecast error
df = lag_h(df, 'yn_renew', 'renew_actual_lag1', 1)
df = lag_h(df, 'renew_forecast', 'renew_fc_lag1', 1)
df['renew_fc_error_lag1'] = df['renew_fc_lag1'] - df['renew_actual_lag1']
df['renew_fc_vs_lag1'] = df['renew_forecast'] - df['renew_actual_lag1']
df['load_fc_vs_lag1'] = df['load_forecast'] - df['load_lag_1d']

df['da_manwan_spread'] = df['manwan_da'] - df['da_price']
df = lag_h(df, 'da_price', 'da_lag_1d', 1)
df['da_change'] = df['da_price'] - df['da_lag_1d']

# Prev day stats
daily = df.groupby('date_key').agg(
    prev_avg_rt=('rt_price','mean'), prev_std_rt=('rt_price','std'),
    prev_avg_gap=('yn_gap','mean'),
).reset_index()
all_dates = sorted(df['date_key'].unique())
date_shift = {d: all_dates[i-1] if i>0 else None for i,d in enumerate(all_dates)}
daily['dk'] = daily['date_key'].map(date_shift)
daily = daily.dropna(subset=['dk']).drop('date_key',axis=1).rename(columns={'dk':'date_key'})
df = df.merge(daily, on='date_key', how='left')

df = df.sort_values(['date_key','hour']).reset_index(drop=True)

FEATURES = [
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
features = [f for f in FEATURES if f in df.columns]
log(f"Features: {len(features)}")

# ============================================================
# 3. Train on ALL data up to 3-22
# ============================================================
log("[3/5] Training P2 ensemble on all data...")

train_mask = df['date_key'] <= '20260322'
X_train = df.loc[train_mask, features].fillna(0)
y_train = df.loc[train_mask, 'rt_price']
valid = y_train.notna()
X_train, y_train = X_train[valid], y_train[valid]

# Time decay weights
train_dates_dt = df.loc[y_train.index, 'date']
ref_dt = pd.to_datetime('20260323', format='%Y%m%d')
days_ago = (ref_dt - train_dates_dt).dt.days.values.astype(float)
w_time = np.exp(-np.log(2) * days_ago / 60.0)
same_season = np.isin(train_dates_dt.dt.month.values, [11,12,1,2,3,4,5])
w_season = np.where(same_season, 2.0, 0.5)
sw = w_time * w_season; sw = sw / sw.mean()

log(f"  Training samples: {len(X_train)} ({len(X_train)//24} days)")

# GBR
gbr = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                 subsample=0.85, min_samples_leaf=5, random_state=42)
gbr.fit(X_train, y_train, sample_weight=sw)
log("  GBR trained")

# LGB
lgb_model = lgb.LGBMRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                subsample=0.85, min_child_samples=5, random_state=42, verbose=-1)
lgb_model.fit(X_train, y_train, sample_weight=sw)
log("  LGB trained")

# XGB
xgb_model = xgb.XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                               subsample=0.85, min_child_weight=5, random_state=42, verbosity=0)
xgb_model.fit(X_train, y_train, sample_weight=sw)
log("  XGB trained")

# DA-RT Spread model (for blend)
y_train_spread = df.loc[train_mask & valid, 'spread']
gbr_sp = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                    subsample=0.85, min_samples_leaf=5, random_state=42)
sp_valid = y_train_spread.notna()
gbr_sp.fit(X_train[sp_valid], y_train_spread[sp_valid], sample_weight=sw[sp_valid.values])
log("  Spread model trained")

# ============================================================
# 4. Build prediction rows for 3-23 and 3-24
# ============================================================
log("[4/5] Building prediction features for 3-23 & 3-24...")

# Get D-1 (3-22) actual data for lag features
d22 = df[df['date_key'] == '20260322'].sort_values('hour')

# Get DA prices for 3-23
conn = sqlite3.connect(DB)
da_23 = pd.read_sql("""
    SELECT SUBSTR(period,1,2) as hour, AVG(price) as da_price
    FROM day_ahead_node_price_96 WHERE node_name='__all_avg__' AND trade_date='2026-03-23'
    GROUP BY SUBSTR(period,1,2)
""", conn)
da_23['hour'] = da_23['hour'].astype(int)

mw_23 = pd.read_sql("""
    SELECT SUBSTR(period,1,2) as hour, AVG(price) as manwan_da
    FROM day_ahead_node_price_96
    WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
    AND trade_date='2026-03-23'
    GROUP BY SUBSTR(period,1,2)
""", conn)
mw_23['hour'] = mw_23['hour'].astype(int)
conn.close()

# D-7 (3-16) data for rt_lag_7d
d16 = df[df['date_key'] == '20260316'].sort_values('hour')
d21 = df[df['date_key'] == '20260321'].sort_values('hour')
d20 = df[df['date_key'] == '20260320'].sort_values('hour')

predictions = {}

for pred_date, pred_dk, dow in [('2026-03-23', '20260323', 0), ('2026-03-24', '20260324', 1)]:
    log(f"\n  Predicting {pred_date} (dow={dow})...")
    rows = []

    for h in range(24):
        row = {}
        row['hour'] = h
        row['dayofweek'] = dow  # Monday=0, Tuesday=1
        row['month'] = 3
        row['is_weekend'] = 0
        row['hour_sin'] = np.sin(2*np.pi*h/24)
        row['hour_cos'] = np.cos(2*np.pi*h/24)
        row['dow_sin'] = np.sin(2*np.pi*dow/7)
        row['dow_cos'] = np.cos(2*np.pi*dow/7)
        row['is_wet_season'] = 0
        row['month_sin'] = np.sin(2*np.pi*3/12)
        row['month_cos'] = np.cos(2*np.pi*3/12)

        if pred_dk == '20260323':
            # D-1 = 3-22 (actual)
            d1 = d22[d22['hour']==h]
            d2 = d21[d21['hour']==h]
            d3 = d20[d20['hour']==h]
            d7 = d16[d16['hour']==h]

            row['rt_lag_1d'] = d1['rt_price'].values[0] if len(d1)>0 else 300
            row['rt_lag_2d'] = d2['rt_price'].values[0] if len(d2)>0 else 300
            row['rt_lag_3d'] = d3['rt_price'].values[0] if len(d3)>0 else 300
            row['rt_lag_7d'] = d7['rt_price'].values[0] if len(d7)>0 else 300

            # Load/renew/hydro lags from 3-22
            row['load_lag_1d'] = d1['yn_load'].values[0] if len(d1)>0 and pd.notna(d1['yn_load'].values[0]) else 31000
            row['load_lag_2d'] = d2['yn_load'].values[0] if len(d2)>0 and pd.notna(d2['yn_load'].values[0]) else 31000
            row['renew_lag_1d'] = d1['yn_renew'].values[0] if len(d1)>0 and pd.notna(d1['yn_renew'].values[0]) else 11000
            row['renew_lag_2d'] = d2['yn_renew'].values[0] if len(d2)>0 and pd.notna(d2['yn_renew'].values[0]) else 11000
            row['hydro_lag_1d'] = d1['yn_hydro'].values[0] if len(d1)>0 and pd.notna(d1['yn_hydro'].values[0]) else 25000
            row['gap_lag_1d'] = d1['yn_gap'].values[0] if len(d1)>0 and pd.notna(d1['yn_gap'].values[0]) else -5000
            gap2 = d2['yn_gap'].values[0] if len(d2)>0 and pd.notna(d2['yn_gap'].values[0]) else -5000
            row['gap_change'] = row['gap_lag_1d'] - gap2

            # DA for 3-23
            da_row = da_23[da_23['hour']==h]
            row['da_price'] = da_row['da_price'].values[0] if len(da_row)>0 else 200
            mw_row = mw_23[mw_23['hour']==h]
            row['manwan_da'] = mw_row['manwan_da'].values[0] if len(mw_row)>0 else row['da_price']

            # MA from recent history
            recent = df[(df['hour']==h) & (df['date_key']>='20260318') & (df['date_key']<='20260322')]
            row['rt_ma_3d'] = recent['rt_price'].tail(3).mean() if len(recent)>=3 else row['rt_lag_1d']
            row['rt_ma_5d'] = recent['rt_price'].tail(5).mean() if len(recent)>=5 else row['rt_lag_1d']
            row['rt_ma_7d'] = df[(df['hour']==h) & (df['date_key']>='20260316') & (df['date_key']<='20260322')]['rt_price'].mean()
            row['rt_std_5d'] = recent['rt_price'].tail(5).std() if len(recent)>=5 else 50

            # Forecast features
            row['renew_forecast'] = d1['renew_forecast'].values[0] if len(d1)>0 and pd.notna(d1.get('renew_forecast', pd.Series([np.nan])).values[0]) else 11000
            row['load_forecast'] = d1['load_forecast'].values[0] if len(d1)>0 and pd.notna(d1.get('load_forecast', pd.Series([np.nan])).values[0]) else 31000
            row['renew_fc_vs_lag1'] = 0
            row['load_fc_vs_lag1'] = 0
            row['renew_fc_error_lag1'] = 0

            # Section constraints (use latest)
            row['avg_limit'] = d1['avg_limit'].values[0] if len(d1)>0 and 'avg_limit' in d1.columns and pd.notna(d1['avg_limit'].values[0]) else 2000
            row['n_constraints'] = d1['n_constraints'].values[0] if len(d1)>0 and 'n_constraints' in d1.columns and pd.notna(d1['n_constraints'].values[0]) else 50

            # Prev day stats (from 3-22)
            row['prev_avg_rt'] = d22['rt_price'].mean()
            row['prev_std_rt'] = d22['rt_price'].std()
            row['prev_avg_gap'] = d22['yn_gap'].mean() if 'yn_gap' in d22.columns else -5000

        else:  # 3-24: use 3-23 predicted as D-1
            p23 = predictions['20260323']
            row['rt_lag_1d'] = p23[h]  # predicted 3-23
            row['rt_lag_2d'] = d22[d22['hour']==h]['rt_price'].values[0] if len(d22[d22['hour']==h])>0 else 300
            d15 = df[df['date_key']=='20260315'].sort_values('hour')
            row['rt_lag_3d'] = d21[d21['hour']==h]['rt_price'].values[0] if len(d21[d21['hour']==h])>0 else 300
            d17 = df[df['date_key']=='20260317'].sort_values('hour')
            row['rt_lag_7d'] = d17[d17['hour']==h]['rt_price'].values[0] if len(d17[d17['hour']==h])>0 else 300

            row['load_lag_1d'] = d22[d22['hour']==h]['yn_load'].values[0] if len(d22[d22['hour']==h])>0 else 31000
            row['load_lag_2d'] = d21[d21['hour']==h]['yn_load'].values[0] if len(d21[d21['hour']==h])>0 else 31000
            row['renew_lag_1d'] = d22[d22['hour']==h]['yn_renew'].values[0] if len(d22[d22['hour']==h])>0 else 11000
            row['renew_lag_2d'] = d21[d21['hour']==h]['yn_renew'].values[0] if len(d21[d21['hour']==h])>0 else 11000
            row['hydro_lag_1d'] = d22[d22['hour']==h]['yn_hydro'].values[0] if len(d22[d22['hour']==h])>0 else 25000
            gap1 = d22[d22['hour']==h]['yn_gap'].values[0] if len(d22[d22['hour']==h])>0 else -5000
            gap2 = d21[d21['hour']==h]['yn_gap'].values[0] if len(d21[d21['hour']==h])>0 else -5000
            row['gap_lag_1d'] = gap1
            row['gap_change'] = gap1 - gap2

            # No DA for 3-24, use 3-23 DA as proxy
            da_row = da_23[da_23['hour']==h]
            row['da_price'] = da_row['da_price'].values[0] * 0.95 if len(da_row)>0 else 200  # slight discount
            mw_row = mw_23[mw_23['hour']==h]
            row['manwan_da'] = mw_row['manwan_da'].values[0] * 0.95 if len(mw_row)>0 else row['da_price']

            row['rt_ma_3d'] = np.mean([p23[h], row['rt_lag_2d'], row['rt_lag_3d']])
            row['rt_ma_5d'] = row['rt_ma_3d']
            row['rt_ma_7d'] = row['rt_ma_3d']
            row['rt_std_5d'] = 80

            row['renew_forecast'] = row['renew_lag_1d']
            row['load_forecast'] = row['load_lag_1d']
            row['renew_fc_vs_lag1'] = 0
            row['load_fc_vs_lag1'] = 0
            row['renew_fc_error_lag1'] = 0
            row['avg_limit'] = 2000
            row['n_constraints'] = 50
            row['prev_avg_rt'] = np.mean(list(p23.values()))
            row['prev_std_rt'] = np.std(list(p23.values()))
            row['prev_avg_gap'] = gap1

        row['da_manwan_spread'] = row['manwan_da'] - row['da_price']
        row['da_change'] = 0  # approximate

        rows.append(row)

    pred_df = pd.DataFrame(rows)
    X_pred = pred_df[features].fillna(0)

    # Ensemble prediction
    p_gbr = gbr.predict(X_pred)
    p_lgb = lgb_model.predict(X_pred)
    p_xgb = xgb_model.predict(X_pred)

    # Spread model
    p_spread = gbr_sp.predict(X_pred)
    da_arr = pred_df['da_price'].values
    p_sp_rt = da_arr + p_spread

    # P2 ensemble: GBR:25% + LGB:25% + XGB:20% + Spread:30%
    p_ensemble = 0.25 * p_gbr + 0.25 * p_lgb + 0.20 * p_xgb + 0.30 * p_sp_rt

    # Clip to reasonable range
    p_ensemble = np.clip(p_ensemble, 0, 1200)

    predictions[pred_dk] = {h: p_ensemble[h] for h in range(24)}

    log(f"  {pred_date}: avg={np.mean(p_ensemble):.1f}, min={np.min(p_ensemble):.1f}, max={np.max(p_ensemble):.1f}")
    log(f"    GBR avg={np.mean(p_gbr):.1f}, LGB avg={np.mean(p_lgb):.1f}, XGB avg={np.mean(p_xgb):.1f}, Spread avg={np.mean(p_sp_rt):.1f}")

# ============================================================
# 5. Plot predictions
# ============================================================
log("\n[5/5] Generating prediction chart...")

fig, axes = plt.subplots(1, 2, figsize=(18, 6))
fig.suptitle('P2 Model - Forward Prediction: March 23-24, 2026\n'
             'GBR+LGB+XGB+Spread Ensemble | Trained on all data through 3-22',
             fontsize=13, fontweight='bold')

hours = list(range(24))
hour_labels = [f"{h:02d}:00" for h in range(0, 24, 3)]
hour_ticks = list(range(0, 24, 3))

for idx, (pred_dk, title_extra) in enumerate([('20260323', 'DA price available'), ('20260324', 'DA extrapolated from 3-23')]):
    ax = axes[idx]
    pred_vals = [predictions[pred_dk][h] for h in hours]

    # DA baseline
    if pred_dk == '20260323':
        da_vals = [da_23[da_23['hour']==h]['da_price'].values[0] if len(da_23[da_23['hour']==h])>0 else 0 for h in hours]
    else:
        da_vals = [da_23[da_23['hour']==h]['da_price'].values[0]*0.95 if len(da_23[da_23['hour']==h])>0 else 0 for h in hours]

    # D-1 actual (3-22) for reference
    d22_vals = [d22[d22['hour']==h]['rt_price'].values[0] if len(d22[d22['hour']==h])>0 else 0 for h in hours]

    ax.plot(hours, pred_vals, 'r-s', ms=5, lw=2.5, label=f'P2 Predicted (avg={np.mean(pred_vals):.0f})', zorder=3)
    ax.plot(hours, da_vals, 'g--^', ms=4, lw=1.5, alpha=0.7, label=f'DA price (avg={np.mean(da_vals):.0f})', zorder=2)
    ax.plot(hours, d22_vals, 'b:o', ms=3, lw=1.2, alpha=0.5, label=f'3-22 RT actual (ref)', zorder=1)

    ax.fill_between(hours, [p*0.8 for p in pred_vals], [p*1.2 for p in pred_vals],
                    alpha=0.1, color='red', label='+-20% range')

    ax.set_xticks(hour_ticks)
    ax.set_xticklabels(hour_labels, fontsize=9)
    ax.set_xlabel('Hour', fontsize=11)
    ax.set_ylabel('Price (yuan/MWh)', fontsize=11)
    ax.set_xlim(-0.5, 23.5)
    ax.grid(True, alpha=0.3, ls='--')
    ax.legend(fontsize=9, loc='upper left')

    date_str = f"2026-{pred_dk[4:6]}-{pred_dk[6:8]}"
    confidence = 'HIGH' if pred_dk == '20260323' else 'MEDIUM'
    ax.set_title(f'{date_str} Prediction ({title_extra})\nConfidence: {confidence}',
                 fontsize=11, fontweight='bold')

    # Annotate peak/valley
    peak_h = hours[np.argmax(pred_vals)]
    valley_h = hours[np.argmin(pred_vals)]
    ax.annotate(f'Peak: {max(pred_vals):.0f}', xy=(peak_h, max(pred_vals)),
                fontsize=9, fontweight='bold', color='red',
                xytext=(peak_h+1, max(pred_vals)+30),
                arrowprops=dict(arrowstyle='->', color='red'))
    ax.annotate(f'Valley: {min(pred_vals):.0f}', xy=(valley_h, min(pred_vals)),
                fontsize=9, fontweight='bold', color='blue',
                xytext=(valley_h+1, min(pred_vals)-40),
                arrowprops=dict(arrowstyle='->', color='blue'))

plt.tight_layout(rect=[0, 0, 1, 0.93])
plt.savefig(f'{OUT}/p2_predict_mar23_24.png', dpi=150, bbox_inches='tight')
log(f"  Saved: p2_predict_mar23_24.png")

# Print hourly predictions
print("\n" + "=" * 70)
print("HOURLY PREDICTIONS")
print("=" * 70)
print(f"{'Hour':>6} | {'3-23 Pred':>10} {'3-23 DA':>10} | {'3-24 Pred':>10} {'3-24 DA*':>10}")
print("-" * 70)
for h in range(24):
    da23_h = da_23[da_23['hour']==h]['da_price'].values[0] if len(da_23[da_23['hour']==h])>0 else 0
    print(f"  {h:02d}:00 | {predictions['20260323'][h]:10.1f} {da23_h:10.1f} | "
          f"{predictions['20260324'][h]:10.1f} {da23_h*0.95:10.1f}")
print("-" * 70)
print(f"  {'Avg':>5} | {np.mean([predictions['20260323'][h] for h in range(24)]):10.1f} "
      f"{da_23['da_price'].mean():10.1f} | "
      f"{np.mean([predictions['20260324'][h] for h in range(24)]):10.1f} "
      f"{da_23['da_price'].mean()*0.95:10.1f}")
print("=" * 70)
print("* 3-24 DA is extrapolated from 3-23 DA (x0.95)")
