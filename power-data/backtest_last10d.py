#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2 快速回测 - 最后10天 (纯GBR - 不含LGB/XGB, 避免环境兼容问题)
"""
import sys, warnings, os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

from config import DB, OUT_DIR
import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

print("=" * 70)
print("P2 回测 - 最后10天 (GBR)", flush=True)
print("=" * 70, flush=True)

# Load
print("\n[1] Loading data...", flush=True)
conn = sqlite3.connect(DB)
price_96 = pd.read_sql("""SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
       FROM realtime_node_price_96 WHERE node_name = '__avg__' ORDER BY trade_date, period""", conn)
price_96['date'] = pd.to_datetime(price_96['date_key'], format='%Y%m%d')
price_96['hour'] = price_96['period'].str[:2].astype(int)
load_96 = pd.read_sql("SELECT date_key, period, load FROM hourly_load WHERE region='云南'", conn)
load_96['hour'] = load_96['period'].str[:2].astype(int)
renew_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_renewable WHERE region='云南'", conn)
renew_96['hour'] = renew_96['period'].str[:2].astype(int)
hydro_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_hydro WHERE region='云南'", conn)
hydro_96['hour'] = hydro_96['period'].str[:2].astype(int)
manwan_da_96 = pd.read_sql("""SELECT trade_date, period, AVG(price) as manwan_da_price
       FROM day_ahead_node_price_96 WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
       GROUP BY trade_date, period""", conn)
manwan_da_96['hour'] = manwan_da_96['period'].str[:2].astype(int)
grid_da_96 = pd.read_sql("SELECT trade_date, period, price as grid_da_avg FROM day_ahead_node_price_96 WHERE node_name='__all_avg__'", conn)
grid_da_96['hour'] = grid_da_96['period'].str[:2].astype(int)
renew_fc_96 = pd.read_sql("SELECT forecast_date as date_key, period, forecast_mw as renew_fc FROM renewable_forecast WHERE region='云南' AND category='总计'", conn)
renew_fc_96['hour'] = renew_fc_96['period'].str[:2].astype(int)
hydro_fc = pd.read_sql("SELECT forecast_date as date_key, avg_output_mw as hydro_fc_avg FROM hydro_forecast WHERE region='云南'", conn)
hydro_fc = hydro_fc.groupby('date_key').agg(hydro_fc_avg=('hydro_fc_avg', 'mean')).reset_index()
gen_fc_96 = pd.read_sql("SELECT forecast_date as date_key, period, forecast_mw as gen_fc FROM generation_forecast", conn)
gen_fc_96['hour'] = gen_fc_96['period'].str[:2].astype(int)
load_fc_96 = pd.read_sql("SELECT trade_date as td, period, forecast_load as load_fc FROM load_forecast WHERE region='云南'", conn)
load_fc_96['date_key'] = load_fc_96['td'].str.replace('-', '')
load_fc_96['hour'] = load_fc_96['period'].str[:2].astype(int)
section = pd.read_sql("SELECT trade_date, section_name, limit_value, period FROM section_constraint", conn)
section['hour'] = section['period'].str[:2].astype(int)
reserve = pd.read_sql("SELECT trade_date, period, reserve_type, reserve_value FROM system_reserve WHERE region='云南'", conn)
reserve['hour'] = reserve['period'].str[:2].astype(int)
maint = pd.read_sql("SELECT trade_date, COUNT(*) as maint_count FROM maintenance_plan GROUP BY trade_date", conn)
channel = pd.read_sql("SELECT trade_date, capacity FROM transmission_channel", conn)
interline = pd.read_sql("SELECT trade_date, power_flow, period FROM inter_provincial_line", conn)
interline['hour'] = interline['period'].str[:2].astype(int)
weather_corr = pd.read_sql("""SELECT date, hour, solar_correction, wind_correction, combined_correction FROM weather_correction""", conn)
weather_corr['date_key'] = weather_corr['date'].str.replace('-', '')
conn.close()
print(f"  Price: {len(price_96)} rows, {price_96['date_key'].nunique()} days", flush=True)

# Aggregate
print("[2] Aggregating...", flush=True)
price_h = price_96.groupby(['date_key','hour']).agg(rt_price=('rt_price','mean'),date=('date','first')).reset_index()
load_h = load_96.groupby(['date_key','hour']).agg(load=('load','mean')).reset_index()
renew_h = renew_96.groupby(['date_key','hour']).agg(renewable=('output','mean')).reset_index()
hydro_h = hydro_96.groupby(['date_key','hour']).agg(hydro=('output','mean')).reset_index()
manwan_h = manwan_da_96.groupby(['trade_date','hour']).agg(manwan_da_price=('manwan_da_price','mean')).reset_index()
manwan_h['date_key'] = pd.to_datetime(manwan_h['trade_date']).dt.strftime('%Y%m%d')
grid_h = grid_da_96.groupby(['trade_date','hour']).agg(grid_da_avg=('grid_da_avg','mean')).reset_index()
grid_h['date_key'] = pd.to_datetime(grid_h['trade_date']).dt.strftime('%Y%m%d')
renew_fc_h = renew_fc_96.groupby(['date_key','hour']).agg(renew_fc=('renew_fc','mean')).reset_index()
gen_fc_h = gen_fc_96.groupby(['date_key','hour']).agg(gen_fc=('gen_fc','mean')).reset_index()
load_fc_h = load_fc_96.groupby(['date_key','hour']).agg(load_fc=('load_fc','mean')).reset_index()
section['date_key'] = section['trade_date'].str.replace('-','')
section_h = section.groupby(['date_key','hour']).agg(n_sections=('section_name','nunique'),avg_limit=('limit_value','mean')).reset_index()
reserve['date_key'] = reserve['trade_date'].str.replace('-','')
res_up = reserve[reserve['reserve_type'].str.contains('正')].groupby(['date_key','hour']).agg(reserve_up=('reserve_value','mean')).reset_index()
res_dn = reserve[reserve['reserve_type'].str.contains('负')].groupby(['date_key','hour']).agg(reserve_down=('reserve_value','mean')).reset_index()
maint['date_key'] = maint['trade_date'].str.replace('-','')
channel['date_key'] = channel['trade_date'].str.replace('-','')
chan_d = channel.groupby('date_key').agg(total_chan_cap=('capacity','sum')).reset_index()
interline['date_key'] = interline['trade_date'].str.replace('-','')
inter_h = interline.groupby(['date_key','hour']).agg(total_flow=('power_flow','sum')).reset_index()

df = price_h[['date_key','hour','rt_price','date']].copy()
for src, cols, on in [
    (load_h,['load'],['date_key','hour']),(renew_h,['renewable'],['date_key','hour']),
    (hydro_h,['hydro'],['date_key','hour']),(manwan_h,['manwan_da_price'],['date_key','hour']),
    (grid_h,['grid_da_avg'],['date_key','hour']),(renew_fc_h,['renew_fc'],['date_key','hour']),
    (gen_fc_h,['gen_fc'],['date_key','hour']),(load_fc_h,['load_fc'],['date_key','hour']),
    (hydro_fc,['hydro_fc_avg'],['date_key']),(section_h,['n_sections','avg_limit'],['date_key','hour']),
    (res_up,['reserve_up'],['date_key','hour']),(res_dn,['reserve_down'],['date_key','hour']),
    (maint,['maint_count'],['date_key']),(chan_d,['total_chan_cap'],['date_key']),
    (inter_h,['total_flow'],['date_key','hour']),
    (weather_corr,['solar_correction','wind_correction','combined_correction'],['date_key','hour']),
]:
    df = df.merge(src[on+cols], on=on, how='left')
df.rename(columns={'load':'total_load'}, inplace=True)

# Features
print("[3] Features...", flush=True)
df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5,6]).astype(int)
df['hour_sin'] = np.sin(2*np.pi*df['hour']/24)
df['hour_cos'] = np.cos(2*np.pi*df['hour']/24)
df['dow_sin'] = np.sin(2*np.pi*df['dayofweek']/7)
df['dow_cos'] = np.cos(2*np.pi*df['dayofweek']/7)
df['month_sin'] = np.sin(2*np.pi*df['month']/12)
df['month_cos'] = np.cos(2*np.pi*df['month']/12)
df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
df['woy_sin'] = np.sin(2*np.pi*df['week_of_year']/52)
df['woy_cos'] = np.cos(2*np.pi*df['week_of_year']/52)
df['is_wet_season'] = df['month'].isin([6,7,8,9,10]).astype(int)
df['is_transition'] = df['month'].isin([5,11]).astype(int)
df['quarter'] = df['date'].dt.quarter
for q in [1,2,3,4]: df[f'q{q}']=(df['quarter']==q).astype(int)
df['wet_x_hour'] = df['is_wet_season']*df['hour']
df['day_of_year'] = df['date'].dt.dayofyear
df['doy_sin'] = np.sin(2*np.pi*df['day_of_year']/365)
df['doy_cos'] = np.cos(2*np.pi*df['day_of_year']/365)
df['gap'] = df['total_load'].fillna(0)-df['renewable'].fillna(0)-df['hydro'].fillna(0)
df['fc_gap'] = df['load_fc'].fillna(0)-df['renew_fc'].fillna(0)-df['hydro_fc_avg'].fillna(0)
df['renew_fc_vs_lag'] = df['renew_fc'].fillna(0)-df['renewable'].fillna(0)
df['load_fc_vs_lag'] = df['load_fc'].fillna(0)-df['total_load'].fillna(0)
df['renew_fc_share'] = np.where(df['gen_fc']>0, df['renew_fc'].fillna(0)/df['gen_fc'], 0)
df['reserve_ratio'] = np.where(df['total_load']>0, df['reserve_up'].fillna(0)/df['total_load'], 0)
df['flow_to_cap'] = np.where(df['total_chan_cap']>0, df['total_flow'].fillna(0)/df['total_chan_cap'], 0)
df = df.sort_values(['hour','date_key']).reset_index(drop=True)

def lag_h(d, col, new, n):
    d[new] = d.groupby('hour')[col].shift(n); return d
for lag in [1,2,3,7]: df = lag_h(df,'rt_price',f'price_lag_{lag}d',lag)
for lag in [1,2]:
    df = lag_h(df,'total_load',f'load_lag_{lag}d',lag)
    df = lag_h(df,'renewable',f'renew_lag_{lag}d',lag)
df = lag_h(df,'hydro','hydro_lag_1d',1)
df = lag_h(df,'gap','gap_lag_1d',1); df = lag_h(df,'gap','gap_lag_2d',2)
df = lag_h(df,'total_chan_cap','chan_lag1d',1)
df['chan_change'] = df['total_chan_cap'].fillna(0)-df['chan_lag1d'].fillna(0)
df = lag_h(df,'maint_count','maint_lag1d',1)
df['maint_change'] = df['maint_count'].fillna(0)-df['maint_lag1d'].fillna(0)
df = lag_h(df,'reserve_up','reserve_up_lag1d',1)
df['reserve_change'] = df['reserve_up'].fillna(0)-df['reserve_up_lag1d'].fillna(0)
df = lag_h(df,'renew_fc','renew_fc_lag1d',1)
df['renew_fc_error_1d'] = df['renew_fc_lag1d'].fillna(0)-df['renew_lag_1d'].fillna(0)
for w in [3,5,7]:
    df[f'price_ma_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w,min_periods=1).mean())
    df[f'price_std_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w,min_periods=1).std().fillna(0))
df['price_momentum_3d'] = df['price_lag_1d']-df['price_ma_3d']
df['gap_change'] = df['gap_lag_1d']-df['gap_lag_2d']
daily_agg = df.groupby('date_key').agg(d_avg=('rt_price','mean'),d_max=('rt_price','max'),d_min=('rt_price','min'),d_std=('rt_price','std'),d_load=('total_load','mean'),d_renew=('renewable','mean'),d_gap=('gap','mean')).reset_index()
daily_agg.columns=['date_key']+[f'prevday_{c}' for c in daily_agg.columns[1:]]
all_dates = sorted(df['date_key'].unique())
ds={d:all_dates[i-1] if i>0 else None for i,d in enumerate(all_dates)}
daily_agg['dk_target']=daily_agg['date_key'].map(ds)
daily_agg=daily_agg.dropna(subset=['dk_target']).drop('date_key',axis=1).rename(columns={'dk_target':'date_key'})
df=df.merge(daily_agg,on='date_key',how='left')
df['prev_ratio'] = np.where(df['prevday_d_avg']>0, df['price_lag_1d']/df['prevday_d_avg'],1.0)
df = lag_h(df,'manwan_da_price','manwan_da_lag1d',1)
df['manwan_da_change'] = df['manwan_da_price']-df['manwan_da_lag1d']
df['da_rt_spread'] = df['rt_price']-df['grid_da_avg'].fillna(0)
df = df.sort_values(['date_key','hour']).reset_index(drop=True)

FEATURES = ['hour','dayofweek','day','month','is_weekend','hour_sin','hour_cos','dow_sin','dow_cos',
    'month_sin','month_cos','week_of_year','woy_sin','woy_cos','is_wet_season','is_transition',
    'q1','q2','q3','q4','wet_x_hour','day_of_year','doy_sin','doy_cos',
    'price_lag_1d','price_lag_2d','price_lag_3d','price_lag_7d',
    'price_ma_3d','price_ma_5d','price_ma_7d','price_std_3d','price_std_7d','price_momentum_3d',
    'load_lag_1d','load_lag_2d','renew_lag_1d','renew_lag_2d','hydro_lag_1d',
    'gap_lag_1d','gap_lag_2d','gap_change','manwan_da_price','manwan_da_lag1d','manwan_da_change',
    'grid_da_avg','prevday_d_avg','prevday_d_max','prevday_d_min','prevday_d_std',
    'prevday_d_load','prevday_d_renew','prevday_d_gap','prev_ratio',
    'renew_fc','hydro_fc_avg','gen_fc','load_fc','fc_gap','renew_fc_vs_lag','load_fc_vs_lag',
    'renew_fc_share','n_sections','avg_limit','reserve_up','reserve_down','reserve_ratio',
    'reserve_change','reserve_up_lag1d','maint_count','maint_change',
    'total_chan_cap','chan_change','total_flow','flow_to_cap','renew_fc_error_1d',
    'solar_correction','wind_correction','combined_correction']

feat = [f for f in FEATURES if f in df.columns]
print(f"  Features: {len(feat)} active, {len(df)} rows, {df['date_key'].nunique()} days", flush=True)

# Walk-forward
test_dates = ['20260313','20260314','20260315','20260316','20260317',
              '20260318','20260319','20260320','20260321','20260322']
results = []
print("\n[4] Walk-forward...", flush=True)
print(f"{'Date':>10s}  {'MAE':>6s}  {'R2':>5s}  {'Actual':>7s}  {'Pred':>7s}  {'Bias':>6s}", flush=True)
print("-"*55, flush=True)

for test_date in test_dates:
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date
    X_tr = df.loc[train_mask, feat].fillna(0).values
    y_tr = df.loc[train_mask, 'rt_price'].values
    X_te = df.loc[test_mask, feat].fillna(0).values
    y_te = df.loc[test_mask, 'rt_price'].values
    valid = ~np.isnan(y_tr)
    X_tr, y_tr = X_tr[valid], y_tr[valid]
    if len(X_tr)<48 or len(X_te)==0:
        print(f"  SKIP {test_date}"); continue
    
    # Recency weights
    train_d = df.loc[train_mask, 'date']
    test_dt = pd.to_datetime(test_date, format='%Y%m%d')
    days_ago = (test_dt - train_d[train_d.notna()]).dt.days.values.astype(float)
    w = np.exp(-np.log(2)*days_ago/45.0)
    tm = train_d.dt.month.values
    dry = np.isin(tm, [11,12,1,2,3,4,5])
    w *= np.where(dry,2.0,0.5); w /= w.mean()
    
    # GBR (200 estimators for speed)
    gbr = GradientBoostingRegressor(n_estimators=200, max_depth=5, learning_rate=0.05,
                                     subsample=0.8, min_samples_leaf=5, random_state=42)
    gbr.fit(X_tr, y_tr, sample_weight=w)
    pred = gbr.predict(X_te)
    
    mae = mean_absolute_error(y_te, pred)
    r2 = r2_score(y_te, pred)
    bias = np.mean(pred - y_te)
    
    results.append({'date':test_date,'actual':y_te.copy(),'pred':pred.copy(),
                     'hour':df.loc[test_mask,'hour'].values.copy(),'mae':mae,'r2':r2,'bias':bias})
    print(f"  {test_date}: {mae:6.1f} {r2:5.3f} {y_te.mean():7.1f} {pred.mean():7.1f} {bias:+6.1f}", flush=True)

# Summary
print("\n" + "="*70, flush=True)
print("SUMMARY", flush=True)
print("="*70, flush=True)
maes = [r['mae'] for r in results]
r2s = [r['r2'] for r in results]
biases = [r['bias'] for r in results]
print(f"  Average MAE: {np.mean(maes):.1f} (Yuan/MWh)")
print(f"  Min MAE:    {min(maes):.1f}")
print(f"  Max MAE:    {max(maes):.1f}")
print(f"  Average R²: {np.mean(r2s):.3f}")
print(f"  Average Bias: {np.mean(biases):+.1f} (positive = over-predict)")
print(f"  MAE Std:    {np.std(maes):.1f}")
print(f"  Best day:   {test_dates[np.argmin(maes)]} (MAE={min(maes):.1f})")
print(f"  Worst day:  {test_dates[np.argmax(maes)]} (MAE={max(maes):.1f})")

# Chart
print("\n[5] Chart...", flush=True)
n_res = len(results)
n_rows = (n_res+1)//2
fig, axes = plt.subplots(n_rows, 2, figsize=(20, 4.5*n_rows+1))
fig.suptitle('P2 最后10天回测 - GBR 预测 vs 实际', fontsize=14, fontweight='bold')

for i, res in enumerate(results):
    ax = axes.flatten()[i]
    order = np.argsort(res['hour'])
    actual = res['actual'][order]
    pred = res['pred'][order]
    x = np.arange(24)
    ax.plot(x, actual, 'b-o', ms=5, lw=2.5, label='Actual', zorder=4)
    ax.plot(x, pred, 'r--s', ms=4, lw=2, label='Predicted', zorder=3)
    mae = res['mae']
    ax.fill_between(x, np.minimum(actual,pred), np.maximum(actual,pred),
                    alpha=0.15, color='red', label=f'Error (MAE={mae:.1f})')
    ax.set_xticks(range(0,24,3))
    ax.set_xticklabels([f'{h:02d}:00' for h in range(0,24,3)])
    ax.set_xlim(-0.5,23.5)
    ax.set_ylabel('Price (Yuan/MWh)')
    ax.grid(True, alpha=0.3, ls='--')
    c = '#228B22' if mae<40 else ('#FF8C00' if mae<80 else '#DC143C')
    ax.set_title(f"2026-{res['date'][4:6]}-{res['date'][6:8]}  MAE={mae:.1f}  R²={res['r2']:.3f}  Bias={res['bias']:+.1f}",
                 fontsize=11, fontweight='bold', color=c)
    ax.legend(fontsize=8, loc='upper left')

for j in range(n_res, len(axes.flatten())):
    axes.flatten()[j].set_visible(False)
plt.tight_layout(rect=[0,0,1,0.96])
path = f'{OUT_DIR}/backtest_last10d.png'
plt.savefig(path, dpi=150, bbox_inches='tight')
print(f"  Saved: {path}", flush=True)

# Feature importance
imp = sorted(zip(feat, gbr.feature_importances_), key=lambda x:-x[1])
print("\nTop 15 Feature Importance:", flush=True)
for f_name, f_val in imp[:15]:
    print(f"  {f_name:30s} {f_val*100:5.2f}%", flush=True)

print("\n✅ Done!", flush=True)
