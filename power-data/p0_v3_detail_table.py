#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate detailed hourly comparison table for P0 v3"""
import sqlite3, warnings
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
warnings.filterwarnings('ignore')

DB = 'F:/work/power-supply-v2/power/power-data/power_market_v2.db'
conn = sqlite3.connect(DB)

# Load data
price_96 = pd.read_sql("SELECT REPLACE(trade_date,'-','') as date_key, period, price as rt_price FROM realtime_node_price_96 WHERE node_name='__avg__'", conn)
price_96['date'] = pd.to_datetime(price_96['date_key'], format='%Y%m%d')
price_96['hour'] = price_96['period'].str[:2].astype(int)

load_96 = pd.read_sql("SELECT date_key, period, load FROM hourly_load WHERE region='云南'", conn)
load_96['hour'] = load_96['period'].str[:2].astype(int)
renew_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_renewable WHERE region='云南'", conn)
renew_96['hour'] = renew_96['period'].str[:2].astype(int)
hydro_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_hydro WHERE region='云南'", conn)
hydro_96['hour'] = hydro_96['period'].str[:2].astype(int)

manwan_da_96 = pd.read_sql("""SELECT trade_date, period, AVG(price) as manwan_da_price
   FROM day_ahead_node_price_96
   WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M')
   GROUP BY trade_date, period""", conn)
manwan_da_96['hour'] = manwan_da_96['period'].str[:2].astype(int)

grid_da_96 = pd.read_sql("SELECT trade_date, period, price as grid_da_avg FROM day_ahead_node_price_96 WHERE node_name='__all_avg__'", conn)
grid_da_96['hour'] = grid_da_96['period'].str[:2].astype(int)

renew_fc_96 = pd.read_sql("SELECT forecast_date as date_key, period, forecast_mw as renew_fc FROM renewable_forecast WHERE region='云南' AND category='总计'", conn)
renew_fc_96['hour'] = renew_fc_96['period'].str[:2].astype(int)
hydro_fc = pd.read_sql("SELECT forecast_date as date_key, avg_output_mw as hydro_fc_avg FROM hydro_forecast WHERE region='云南'", conn)
hydro_fc = hydro_fc.groupby('date_key').agg(hydro_fc_avg=('hydro_fc_avg','mean')).reset_index()
gen_fc_96 = pd.read_sql("SELECT forecast_date as date_key, period, forecast_mw as gen_fc FROM generation_forecast", conn)
gen_fc_96['hour'] = gen_fc_96['period'].str[:2].astype(int)
load_fc_96 = pd.read_sql("SELECT trade_date as td, period, forecast_load as load_fc FROM load_forecast WHERE region='云南'", conn)
load_fc_96['date_key'] = load_fc_96['td'].str.replace('-','')
load_fc_96['hour'] = load_fc_96['period'].str[:2].astype(int)
conn.close()

# Aggregate to hourly
price_h = price_96.groupby(['date_key','hour']).agg(rt_price=('rt_price','mean'), date=('date','first')).reset_index()
price_h['period'] = price_h['hour'].apply(lambda h: f'{h:02d}:00')
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

df = price_h[['date_key','period','hour','rt_price','date']].copy()
df = df.merge(load_h[['date_key','hour','load']], on=['date_key','hour'], how='left')
df = df.merge(renew_h[['date_key','hour','renewable']], on=['date_key','hour'], how='left')
df = df.merge(hydro_h[['date_key','hour','hydro']], on=['date_key','hour'], how='left')
df.rename(columns={'load':'total_load'}, inplace=True)
df = df.merge(manwan_h[['date_key','hour','manwan_da_price']], on=['date_key','hour'], how='left')
df = df.merge(grid_h[['date_key','hour','grid_da_avg']], on=['date_key','hour'], how='left')
df = df.merge(renew_fc_h[['date_key','hour','renew_fc']], on=['date_key','hour'], how='left')
df = df.merge(gen_fc_h[['date_key','hour','gen_fc']], on=['date_key','hour'], how='left')
df = df.merge(load_fc_h[['date_key','hour','load_fc']], on=['date_key','hour'], how='left')
df = df.merge(hydro_fc[['date_key','hydro_fc_avg']], on='date_key', how='left')

# All features
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
for q in [1,2,3,4]: df[f'q{q}'] = (df['quarter']==q).astype(int)
df['wet_x_hour'] = df['is_wet_season']*df['hour']
df['wet_x_hour_sin'] = df['is_wet_season']*df['hour_sin']
df['day_of_year'] = df['date'].dt.dayofyear
df['doy_sin'] = np.sin(2*np.pi*df['day_of_year']/365)
df['doy_cos'] = np.cos(2*np.pi*df['day_of_year']/365)
df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)
df['fc_gap'] = df['load_fc'].fillna(0) - df['renew_fc'].fillna(0) - df['hydro_fc_avg'].fillna(0)
df['renew_fc_vs_lag'] = df['renew_fc'].fillna(0) - df['renewable'].fillna(0)
df['load_fc_vs_lag'] = df['load_fc'].fillna(0) - df['total_load'].fillna(0)
df['renew_fc_share'] = np.where(df['gen_fc']>0, df['renew_fc'].fillna(0)/df['gen_fc'], 0)

df = df.sort_values(['hour','date_key']).reset_index(drop=True)
def add_lag(df, col, new, n):
    df[new] = df.groupby('hour')[col].shift(n)
    return df
for lag in [1,2,3,7]: df = add_lag(df,'rt_price',f'price_lag_{lag}d',lag)
for lag in [1,2]:
    df = add_lag(df,'total_load',f'load_lag_{lag}d',lag)
    df = add_lag(df,'renewable',f'renew_lag_{lag}d',lag)
df = add_lag(df,'hydro','hydro_lag_1d',1)
df = add_lag(df,'gap','gap_lag_1d',1)
df = add_lag(df,'gap','gap_lag_2d',2)
for w in [3,5,7]:
    df[f'price_ma_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w,min_periods=1).mean())
    df[f'price_std_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w,min_periods=1).std().fillna(0))
df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

daily = df.groupby('date_key').agg(
    daily_avg_price=('rt_price','mean'), daily_max_price=('rt_price','max'),
    daily_min_price=('rt_price','min'), daily_std_price=('rt_price','std'),
    daily_avg_load=('total_load','mean'), daily_avg_renew=('renewable','mean'),
    daily_avg_gap=('gap','mean')
).reset_index()
daily.columns = ['date_key'] + [f'prevday_{c}' for c in daily.columns[1:]]
all_dates = sorted(df['date_key'].unique())
date_shift = {d: all_dates[i-1] if i>0 else None for i,d in enumerate(all_dates)}
daily['dkt'] = daily['date_key'].map(date_shift)
daily = daily.dropna(subset=['dkt']).drop('date_key',axis=1).rename(columns={'dkt':'date_key'})
df = df.merge(daily, on='date_key', how='left')
df['prev_period_to_daily_ratio'] = np.where(df['prevday_daily_avg_price']>0, df['price_lag_1d']/df['prevday_daily_avg_price'], 1.0)
df = add_lag(df,'manwan_da_price','manwan_da_lag1d',1)
df = add_lag(df,'manwan_da_price','manwan_da_prev',1)
df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_prev']
df = df.sort_values(['date_key','hour']).reset_index(drop=True)

FEATURES = [
    'hour','dayofweek','day','month','is_weekend',
    'hour_sin','hour_cos','dow_sin','dow_cos',
    'month_sin','month_cos','week_of_year','woy_sin','woy_cos',
    'is_wet_season','is_transition','q1','q2','q3','q4',
    'wet_x_hour','wet_x_hour_sin','day_of_year','doy_sin','doy_cos',
    'price_lag_1d','price_lag_2d','price_lag_3d','price_lag_7d',
    'price_ma_3d','price_ma_5d','price_ma_7d','price_std_3d','price_std_7d','price_momentum_3d',
    'load_lag_1d','load_lag_2d','renew_lag_1d','renew_lag_2d','hydro_lag_1d',
    'gap_lag_1d','gap_lag_2d','gap_change',
    'manwan_da_price','manwan_da_lag1d','manwan_da_change','grid_da_avg',
    'prevday_daily_avg_price','prevday_daily_max_price','prevday_daily_min_price','prevday_daily_std_price',
    'prevday_daily_avg_load','prevday_daily_avg_renew','prevday_daily_avg_gap','prev_period_to_daily_ratio',
    'renew_fc','hydro_fc_avg','gen_fc','load_fc','fc_gap','renew_fc_vs_lag','load_fc_vs_lag','renew_fc_share',
]

# Walk-forward and collect results
test_dates = ['20260319','20260320','20260321','20260322']
all_rows = []

for td in test_dates:
    train_m = df['date_key'] < td
    test_m = df['date_key'] == td
    X_tr = df.loc[train_m, FEATURES].fillna(0)
    y_tr = df.loc[train_m, 'rt_price']
    X_te = df.loc[test_m, FEATURES].fillna(0)
    y_te = df.loc[test_m, 'rt_price']
    valid = y_tr.notna()
    X_tr, y_tr = X_tr[valid], y_tr[valid]

    train_dates_col = df.loc[y_tr.index, 'date']
    test_dt = pd.to_datetime(td, format='%Y%m%d')
    days_ago = (test_dt - train_dates_col).dt.days.values.astype(float)
    w_time = np.exp(-np.log(2)*days_ago/60.0)
    train_months = train_dates_col.dt.month.values
    same_season = np.isin(train_months, [11,12,1,2,3,4,5])
    w_season = np.where(same_season, 2.0, 0.5)
    sw = w_time * w_season
    sw = sw / sw.mean()

    mdl = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                     subsample=0.85, min_samples_leaf=5, random_state=42)
    mdl.fit(X_tr, y_tr, sample_weight=sw)
    preds = mdl.predict(X_te)

    test_df = df.loc[test_m].copy()
    test_df['predicted'] = preds
    test_df['error'] = preds - test_df['rt_price'].values
    test_df = test_df.sort_values('hour')

    for _, row in test_df.iterrows():
        all_rows.append({
            'date': td,
            'hour': int(row['hour']),
            'actual': row['rt_price'],
            'predicted': row['predicted'],
            'error': row['error'],
            'renew_fc': row.get('renew_fc', 0) if pd.notna(row.get('renew_fc', None)) else 0,
            'load_fc': row.get('load_fc', 0) if pd.notna(row.get('load_fc', None)) else 0,
            'hydro_fc': row.get('hydro_fc_avg', 0) if pd.notna(row.get('hydro_fc_avg', None)) else 0,
            'grid_da': row.get('grid_da_avg', 0) if pd.notna(row.get('grid_da_avg', None)) else 0,
        })

# Print table
print()
print("=" * 95)
print("P0 v3 Detailed Results: March 19-22, 2026 (Hourly)")
print("=" * 95)
print(f"{'Date':>10s}  {'Hour':>5s}  {'Actual':>7s}  {'Pred':>7s}  {'Error':>7s}  {'RenewFC':>8s}  {'LoadFC':>7s}  {'HydroFC':>8s}  {'GridDA':>7s}")
print("-" * 95)

prev_date = ''
for r in all_rows:
    d = r['date']
    ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if d != prev_date and prev_date != '':
        day_rows = [x for x in all_rows if x['date'] == prev_date]
        day_mae = np.mean([abs(x['error']) for x in day_rows])
        day_r2 = 1 - np.sum([(x['error'])**2 for x in day_rows]) / np.sum([(x['actual'] - np.mean([y['actual'] for y in day_rows]))**2 for x in day_rows])
        pds = f"{prev_date[:4]}-{prev_date[4:6]}-{prev_date[6:8]}"
        print(f"  >>> {pds}  MAE={day_mae:.1f}  R2={day_r2:.3f}")
        print("-" * 95)
    prev_date = d
    print(f"{ds}  {r['hour']:02d}:00  {r['actual']:7.1f}  {r['predicted']:7.1f}  {r['error']:+7.1f}  {r['renew_fc']:8.0f}  {r['load_fc']:7.0f}  {r['hydro_fc']:8.0f}  {r['grid_da']:7.1f}")

# Last day
day_rows = [x for x in all_rows if x['date'] == prev_date]
day_mae = np.mean([abs(x['error']) for x in day_rows])
day_r2 = 1 - np.sum([(x['error'])**2 for x in day_rows]) / np.sum([(x['actual'] - np.mean([y['actual'] for y in day_rows]))**2 for x in day_rows])
pds = f"{prev_date[:4]}-{prev_date[4:6]}-{prev_date[6:8]}"
print(f"  >>> {pds}  MAE={day_mae:.1f}  R2={day_r2:.3f}")
print("=" * 95)

total_mae = np.mean([abs(x['error']) for x in all_rows])
print(f"Overall Avg MAE = {total_mae:.1f}")
print()

# Summary comparison table
print("Version Comparison:")
print(f"  {'Version':>20s}  {'3-19':>6s}  {'3-20':>6s}  {'3-21':>6s}  {'3-22':>6s}  {'Avg':>6s}")
print(f"  {'v2.2 (no forecast)':>20s}  {'102.9':>6s}  {'56.3':>6s}  {'57.1':>6s}  {'224.3':>6s}  {'110.2':>6s}")
print(f"  {'v3 (mixed region)':>20s}  {'87.3':>6s}  {'65.4':>6s}  {'59.1':>6s}  {'229.4':>6s}  {'110.3':>6s}")

v3_maes = {}
for td in test_dates:
    day_rows = [x for x in all_rows if x['date'] == td]
    v3_maes[td] = np.mean([abs(x['error']) for x in day_rows])
v3_avg = np.mean(list(v3_maes.values()))
print(f"  {'v3 (Yunnan only)':>20s}  {v3_maes['20260319']:>6.1f}  {v3_maes['20260320']:>6.1f}  {v3_maes['20260321']:>6.1f}  {v3_maes['20260322']:>6.1f}  {v3_avg:>6.1f}")
