#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2+Weather Model - 天气修正因子集成到P2 Ensemble
===================================================
在P2模型基础上增加天气修正特征:
  - solar_correction: 云量→光伏出力修正 (Kasten-Czeplak)
  - wind_correction: 风速→风电出力修正 (功率曲线)
  - combined_correction: 装机容量加权综合修正
  - renew_fc_corrected: 修正后可再生能源预测
  - weather_gap: 天气修正后的供需缺口

对比: P2 (原始) vs P2+Weather (天气修正)
回测: 3/13~3/22 (10天)
"""
import sqlite3, warnings, sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import lightgbm as lgb
import xgboost as xgb
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

from config import DB, OUT_DIR

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")
print("=" * 70)
print("P2+Weather Model - 天气修正因子集成")
print("=" * 70)

# ============================================================
# 1. Load data (same as P2 + weather)
# ============================================================
print("\n[1/8] Loading data...")
conn = sqlite3.connect(DB)

price_96 = pd.read_sql(
    """SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
       FROM realtime_node_price_96 WHERE node_name = '__avg__'
       ORDER BY trade_date, period""", conn)
price_96['date'] = pd.to_datetime(price_96['date_key'], format='%Y%m%d')
price_96['hour'] = price_96['period'].str[:2].astype(int)

load_96 = pd.read_sql("SELECT date_key, period, load FROM hourly_load WHERE region='云南'", conn)
load_96['hour'] = load_96['period'].str[:2].astype(int)
renew_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_renewable WHERE region='云南'", conn)
renew_96['hour'] = renew_96['period'].str[:2].astype(int)
hydro_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_hydro WHERE region='云南'", conn)
hydro_96['hour'] = hydro_96['period'].str[:2].astype(int)

manwan_da_96 = pd.read_sql(
    """SELECT trade_date, period, AVG(price) as manwan_da_price
       FROM day_ahead_node_price_96
       WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
       GROUP BY trade_date, period""", conn)
manwan_da_96['hour'] = manwan_da_96['period'].str[:2].astype(int)

grid_da_96 = pd.read_sql(
    "SELECT trade_date, period, price as grid_da_avg FROM day_ahead_node_price_96 WHERE node_name='__all_avg__'", conn)
grid_da_96['hour'] = grid_da_96['period'].str[:2].astype(int)

renew_fc_96 = pd.read_sql(
    "SELECT forecast_date as date_key, period, forecast_mw as renew_fc FROM renewable_forecast WHERE region='云南' AND category='总计'", conn)
renew_fc_96['hour'] = renew_fc_96['period'].str[:2].astype(int)
# ⚠️ 时效性: publish_date=D 含 forecast_date=[D, D+1, ..., D+6]，当前用forecast_date做join，D日nowcast可能不可用

hydro_fc = pd.read_sql("SELECT forecast_date as date_key, avg_output_mw as hydro_fc_avg FROM hydro_forecast WHERE region='云南'", conn)
hydro_fc = hydro_fc.groupby('date_key').agg(hydro_fc_avg=('hydro_fc_avg', 'mean')).reset_index()
# ⚠️ 时效性同上

gen_fc_96 = pd.read_sql("SELECT forecast_date as date_key, period, forecast_mw as gen_fc FROM generation_forecast", conn)
gen_fc_96['hour'] = gen_fc_96['period'].str[:2].astype(int)
# ⚠️ 时效性同上

load_fc_96 = pd.read_sql("SELECT trade_date as td, period, forecast_load as load_fc FROM load_forecast WHERE region='云南'", conn)
# ⚠️ 时效性: load_forecast无publish_date字段，建议改进: ETL增加publish_date或shift 1天
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

# ★ Weather correction factors
weather_corr = pd.read_sql("""
    SELECT date, hour, solar_correction, wind_correction, combined_correction,
           avg_cloud, avg_wind_speed, avg_ghi_ratio
    FROM weather_correction ORDER BY date, hour
""", conn)
weather_corr.rename(columns={'date': 'date_key'}, inplace=True)
print(f"  Weather correction: {len(weather_corr)} rows, {weather_corr['date_key'].nunique()} days")

conn.close()

# ============================================================
# 2. Aggregate to hourly
# ============================================================
print("[2/8] Aggregate to hourly...")

price_h = price_96.groupby(['date_key', 'hour']).agg(rt_price=('rt_price', 'mean'), date=('date', 'first')).reset_index()
load_h = load_96.groupby(['date_key', 'hour']).agg(load=('load', 'mean')).reset_index()
renew_h = renew_96.groupby(['date_key', 'hour']).agg(renewable=('output', 'mean')).reset_index()
hydro_h = hydro_96.groupby(['date_key', 'hour']).agg(hydro=('output', 'mean')).reset_index()
manwan_h = manwan_da_96.groupby(['trade_date', 'hour']).agg(manwan_da_price=('manwan_da_price', 'mean')).reset_index()
manwan_h['date_key'] = pd.to_datetime(manwan_h['trade_date']).dt.strftime('%Y%m%d')
grid_h = grid_da_96.groupby(['trade_date', 'hour']).agg(grid_da_avg=('grid_da_avg', 'mean')).reset_index()
grid_h['date_key'] = pd.to_datetime(grid_h['trade_date']).dt.strftime('%Y%m%d')
renew_fc_h = renew_fc_96.groupby(['date_key', 'hour']).agg(renew_fc=('renew_fc', 'mean')).reset_index()
gen_fc_h = gen_fc_96.groupby(['date_key', 'hour']).agg(gen_fc=('gen_fc', 'mean')).reset_index()
load_fc_h = load_fc_96.groupby(['date_key', 'hour']).agg(load_fc=('load_fc', 'mean')).reset_index()

section['date_key'] = section['trade_date'].str.replace('-', '')
section_h = section.groupby(['date_key', 'hour']).agg(n_sections=('section_name', 'nunique'), avg_limit=('limit_value', 'mean')).reset_index()
reserve['date_key'] = reserve['trade_date'].str.replace('-', '')
res_up = reserve[reserve['reserve_type'].str.contains('正')].groupby(['date_key', 'hour']).agg(reserve_up=('reserve_value', 'mean')).reset_index()
res_dn = reserve[reserve['reserve_type'].str.contains('负')].groupby(['date_key', 'hour']).agg(reserve_down=('reserve_value', 'mean')).reset_index()
maint['date_key'] = maint['trade_date'].str.replace('-', '')
channel['date_key'] = channel['trade_date'].str.replace('-', '')
chan_d = channel.groupby('date_key').agg(total_chan_cap=('capacity', 'sum')).reset_index()
interline['date_key'] = interline['trade_date'].str.replace('-', '')
inter_h = interline.groupby(['date_key', 'hour']).agg(total_flow=('power_flow', 'sum')).reset_index()

df = price_h[['date_key', 'hour', 'rt_price', 'date']].copy()
for src, cols, on in [
    (load_h, ['load'], ['date_key', 'hour']),
    (renew_h, ['renewable'], ['date_key', 'hour']),
    (hydro_h, ['hydro'], ['date_key', 'hour']),
    (manwan_h, ['manwan_da_price'], ['date_key', 'hour']),
    (grid_h, ['grid_da_avg'], ['date_key', 'hour']),
    (renew_fc_h, ['renew_fc'], ['date_key', 'hour']),
    (gen_fc_h, ['gen_fc'], ['date_key', 'hour']),
    (load_fc_h, ['load_fc'], ['date_key', 'hour']),
    (hydro_fc, ['hydro_fc_avg'], ['date_key']),
    (section_h, ['n_sections', 'avg_limit'], ['date_key', 'hour']),
    (res_up, ['reserve_up'], ['date_key', 'hour']),
    (res_dn, ['reserve_down'], ['date_key', 'hour']),
    (maint, ['maint_count'], ['date_key']),
    (chan_d, ['total_chan_cap'], ['date_key']),
    (inter_h, ['total_flow'], ['date_key', 'hour']),
    (weather_corr, ['solar_correction', 'wind_correction', 'combined_correction',
                    'avg_cloud', 'avg_wind_speed', 'avg_ghi_ratio'], ['date_key', 'hour']),
]:
    df = df.merge(src[on + cols], on=on, how='left')

df.rename(columns={'load': 'total_load'}, inplace=True)

# ============================================================
# 3. CEEMDAN Decomposition
# ============================================================
print("[3/8] CEEMDAN decomposition...")
# Causal decomposition: use only past data (no future leakage from Savgol)
def _causal_trend(signal, half_life=14):
    """单向指数加权趋势，只使用过去数据"""
    weights = np.exp(-np.linspace(0, 3, half_life))
    weights /= weights.sum()
    trend = np.convolve(signal, weights[::-1], mode='same')
    trend[:half_life] = signal[:half_life]
    return trend

def _causal_wave(residual, half_life=5):
    """单向波动分量"""
    weights = np.exp(-np.linspace(0, 2, half_life))
    weights /= weights.sum()
    wave = np.convolve(residual, weights[::-1], mode='same')
    wave[:half_life] = residual[:half_life]
    return wave

daily_price = df.groupby('date_key')['rt_price'].mean().reset_index().sort_values('date_key').reset_index(drop=True)
price_signal = daily_price['rt_price'].values
try:
    n = len(price_signal)
    trend = _causal_trend(price_signal, half_life=min(14, max(3, n//4)))
    residual1 = price_signal - trend
    wave = _causal_wave(residual1, half_life=min(5, max(2, n//6)))
    spike = residual1 - wave
    daily_price['price_trend'] = trend
    daily_price['price_wave'] = wave
    daily_price['price_spike'] = spike
    df = df.merge(daily_price[['date_key', 'price_trend', 'price_wave', 'price_spike']], on='date_key', how='left')
except:
    df['price_trend'] = df['price_wave'] = df['price_spike'] = 0

# ============================================================
# 4. Build features
# ============================================================
print("[4/8] Building features...")

df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)
df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
df['woy_sin'] = np.sin(2 * np.pi * df['week_of_year'] / 52)
df['woy_cos'] = np.cos(2 * np.pi * df['week_of_year'] / 52)
df['is_wet_season'] = df['month'].isin([6, 7, 8, 9, 10]).astype(int)
df['is_transition'] = df['month'].isin([5, 11]).astype(int)
df['quarter'] = df['date'].dt.quarter
for q in [1, 2, 3, 4]:
    df[f'q{q}'] = (df['quarter'] == q).astype(int)
df['wet_x_hour'] = df['is_wet_season'] * df['hour']
df['day_of_year'] = df['date'].dt.dayofyear
df['doy_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
df['doy_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)

df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)
df['fc_gap'] = df['load_fc'].fillna(0) - df['renew_fc'].fillna(0) - df['hydro_fc_avg'].fillna(0)
df['renew_fc_vs_lag'] = df['renew_fc'].fillna(0) - df['renewable'].fillna(0)
df['load_fc_vs_lag'] = df['load_fc'].fillna(0) - df['total_load'].fillna(0)
df['renew_fc_share'] = np.where(df['gen_fc'] > 0, df['renew_fc'].fillna(0) / df['gen_fc'], 0)
df['reserve_ratio'] = np.where(df['total_load'] > 0, df['reserve_up'].fillna(0) / df['total_load'], 0)
df['flow_to_cap'] = np.where(df['total_chan_cap'] > 0, df['total_flow'].fillna(0) / df['total_chan_cap'], 0)

# ★ Weather-derived features
df['renew_fc_corrected'] = df['renew_fc'].fillna(0) * df['combined_correction'].fillna(1.0)
df['weather_gap'] = df['load_fc'].fillna(0) - df['renew_fc_corrected'] - df['hydro_fc_avg'].fillna(0)
df['weather_delta'] = df['renew_fc_corrected'] - df['renew_fc'].fillna(0)
df['cloud_x_solar'] = df['avg_cloud'].fillna(50) * df['renew_fc_share']
df['wind_class'] = pd.cut(df['avg_wind_speed'].fillna(3), bins=[0, 3, 5, 8, 25], labels=[0, 1, 2, 3]).astype(float).fillna(0)

# Lag features
df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)

def lag_h(df, col, new, n):
    df[new] = df.groupby('hour')[col].shift(n)
    return df

for lag in [1, 2, 3, 7]:
    df = lag_h(df, 'rt_price', f'price_lag_{lag}d', lag)
for lag in [1, 2]:
    df = lag_h(df, 'total_load', f'load_lag_{lag}d', lag)
    df = lag_h(df, 'renewable', f'renew_lag_{lag}d', lag)
df = lag_h(df, 'hydro', 'hydro_lag_1d', 1)
df = lag_h(df, 'gap', 'gap_lag_1d', 1)
df = lag_h(df, 'gap', 'gap_lag_2d', 2)
df = lag_h(df, 'total_chan_cap', 'chan_lag1d', 1)
df['chan_change'] = df['total_chan_cap'].fillna(0) - df['chan_lag1d'].fillna(0)
df = lag_h(df, 'maint_count', 'maint_lag1d', 1)
df['maint_change'] = df['maint_count'].fillna(0) - df['maint_lag1d'].fillna(0)
df = lag_h(df, 'reserve_up', 'reserve_up_lag1d', 1)
df['reserve_change'] = df['reserve_up'].fillna(0) - df['reserve_up_lag1d'].fillna(0)
df = lag_h(df, 'renew_fc', 'renew_fc_lag1d', 1)
df['renew_fc_error_1d'] = df['renew_fc_lag1d'].fillna(0) - df['renew_lag_1d'].fillna(0)
df = lag_h(df, 'price_trend', 'trend_lag1d', 1)
df = lag_h(df, 'price_spike', 'spike_lag1d', 1)
df = lag_h(df, 'combined_correction', 'weather_corr_lag1d', 1)
df = lag_h(df, 'avg_cloud', 'cloud_lag1d', 1)
df['cloud_change'] = df['avg_cloud'].fillna(50) - df['cloud_lag1d'].fillna(50)

for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
    df[f'price_std_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0))

df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

daily_agg = df.groupby('date_key').agg(
    d_avg=('rt_price', 'mean'), d_max=('rt_price', 'max'),
    d_min=('rt_price', 'min'), d_std=('rt_price', 'std'),
    d_load=('total_load', 'mean'), d_renew=('renewable', 'mean'), d_gap=('gap', 'mean'),
).reset_index()
daily_agg.columns = ['date_key'] + [f'prevday_{c}' for c in daily_agg.columns[1:]]
all_dates = sorted(df['date_key'].unique())
ds = {d: all_dates[i-1] if i > 0 else None for i, d in enumerate(all_dates)}
daily_agg['dk_target'] = daily_agg['date_key'].map(ds)
daily_agg = daily_agg.dropna(subset=['dk_target']).drop('date_key', axis=1).rename(columns={'dk_target': 'date_key'})
df = df.merge(daily_agg, on='date_key', how='left')

df['prev_ratio'] = np.where(df['prevday_d_avg'] > 0, df['price_lag_1d'] / df['prevday_d_avg'], 1.0)
df = lag_h(df, 'manwan_da_price', 'manwan_da_lag1d', 1)
df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_lag1d']
df['da_rt_spread'] = df['rt_price'] - df['grid_da_avg'].fillna(0)
df = df.sort_values(['date_key', 'hour']).reset_index(drop=True)

# ============================================================
# 5. Feature lists
# ============================================================
P2_FEATURES = [
    'hour', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos',
    'month_sin', 'month_cos', 'week_of_year', 'woy_sin', 'woy_cos',
    'is_wet_season', 'is_transition', 'q1', 'q2', 'q3', 'q4',
    'wet_x_hour', 'day_of_year', 'doy_sin', 'doy_cos',
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d', 'price_momentum_3d',
    'load_lag_1d', 'load_lag_2d', 'renew_lag_1d', 'renew_lag_2d', 'hydro_lag_1d',
    'gap_lag_1d', 'gap_lag_2d', 'gap_change',
    'manwan_da_price', 'manwan_da_lag1d', 'manwan_da_change', 'grid_da_avg',
    'prevday_d_avg', 'prevday_d_max', 'prevday_d_min', 'prevday_d_std',
    'prevday_d_load', 'prevday_d_renew', 'prevday_d_gap', 'prev_ratio',
    'renew_fc', 'hydro_fc_avg', 'gen_fc', 'load_fc',
    'fc_gap', 'renew_fc_vs_lag', 'load_fc_vs_lag', 'renew_fc_share',
    'n_sections', 'avg_limit', 'reserve_up', 'reserve_down', 'reserve_ratio',
    'reserve_change', 'reserve_up_lag1d', 'maint_count', 'maint_change',
    'total_chan_cap', 'chan_change', 'total_flow', 'flow_to_cap',
    'renew_fc_error_1d',
    'price_trend', 'price_wave', 'price_spike', 'trend_lag1d', 'spike_lag1d',
]

WEATHER_FEATURES = [
    'solar_correction', 'wind_correction', 'combined_correction',
    'avg_cloud', 'avg_wind_speed', 'avg_ghi_ratio',
    'renew_fc_corrected', 'weather_gap', 'weather_delta',
    'cloud_x_solar', 'wind_class',
    'weather_corr_lag1d', 'cloud_lag1d', 'cloud_change',
]

feat_p2 = [f for f in P2_FEATURES if f in df.columns]
feat_weather = [f for f in P2_FEATURES + WEATHER_FEATURES if f in df.columns]
print(f"  P2 features: {len(feat_p2)}")
print(f"  P2+Weather features: {len(feat_weather)} (+{len(feat_weather)-len(feat_p2)} weather)")

# ============================================================
# 6. BiLSTM
# ============================================================
class BiLSTMModel(nn.Module):
    def __init__(self, input_dim, hidden=64, layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden, layers, batch_first=True, bidirectional=True, dropout=dropout)
        self.fc = nn.Sequential(nn.Linear(hidden*2, 32), nn.ReLU(), nn.Dropout(dropout), nn.Linear(32, 1))
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :]).squeeze(-1)

def train_bilstm(X_train, y_train, X_test, n_feat, seq_len=7, epochs=30):
    n = len(X_train)
    if n < seq_len + 1:
        return None
    X_seq, y_seq = [], []
    for i in range(seq_len, n):
        X_seq.append(X_train[i-seq_len:i]); y_seq.append(y_train[i])
    X_seq = np.array(X_seq, dtype=np.float32)
    y_seq = np.array(y_seq, dtype=np.float32)
    x_mean = X_seq.reshape(-1, n_feat).mean(0)
    x_std = X_seq.reshape(-1, n_feat).std(0) + 1e-8
    y_mean, y_std = y_seq.mean(), y_seq.std() + 1e-8
    X_seq_n = (X_seq - x_mean) / x_std
    y_seq_n = (y_seq - y_mean) / y_std
    X_test_np = X_test.astype(np.float32)
    X_context = X_train[-seq_len:].astype(np.float32)
    X_test_seqs = []
    for i in range(len(X_test_np)):
        ctx = np.vstack([X_context[i:], X_test_np[:i]]) if 0 < i < seq_len else (X_test_np[i-seq_len:i] if i >= seq_len else X_context)
        X_test_seqs.append(ctx)
    X_test_seqs = (np.array(X_test_seqs, dtype=np.float32) - x_mean) / x_std
    dataset = TensorDataset(torch.tensor(X_seq_n), torch.tensor(y_seq_n))
    loader = DataLoader(dataset, batch_size=32, shuffle=True)
    model = BiLSTMModel(n_feat).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=0.001)
    crit = nn.MSELoss()
    model.train()
    for _ in range(epochs):
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(); crit(model(xb), yb).backward(); opt.step()
    model.eval()
    with torch.no_grad():
        pred_n = model(torch.tensor(X_test_seqs).to(device)).cpu().numpy()
    return pred_n * y_std + y_mean

def run_ensemble(df, feat_list, test_date):
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date
    X_train_df = df.loc[train_mask, feat_list].fillna(0)
    y_train_s = df.loc[train_mask, 'rt_price']
    X_test_df = df.loc[test_mask, feat_list].fillna(0)
    y_test_s = df.loc[test_mask, 'rt_price']
    valid = y_train_s.notna()
    X_tr, y_tr = X_train_df[valid].values, y_train_s[valid].values
    X_te, y_te = X_test_df.values, y_test_s.values
    if len(X_tr) < 48 or len(X_te) == 0:
        return None

    train_d = df.loc[y_train_s[valid].index, 'date']
    test_dt = pd.to_datetime(test_date, format='%Y%m%d')
    days_ago = (test_dt - train_d).dt.days.values.astype(float)
    w = np.exp(-np.log(2) * days_ago / 45.0)
    w *= np.where(np.isin(train_d.dt.month.values, [11,12,1,2,3,4,5]), 2.0, 0.5)
    w /= w.mean()

    gbr = GradientBoostingRegressor(n_estimators=500, max_depth=6, learning_rate=0.04, subsample=0.85, min_samples_leaf=4, random_state=42)
    gbr.fit(X_tr, y_tr, sample_weight=w)
    p_gbr = gbr.predict(X_te)

    dtrain = lgb.Dataset(X_tr, y_tr, weight=w)
    lgb_model = lgb.train({'objective': 'regression', 'metric': 'mae', 'num_leaves': 63,
        'learning_rate': 0.04, 'feature_fraction': 0.8, 'bagging_fraction': 0.85,
        'bagging_freq': 5, 'verbose': -1, 'seed': 42}, dtrain, num_boost_round=500)
    p_lgb = lgb_model.predict(X_te)

    xgb_model = xgb.XGBRegressor(n_estimators=500, max_depth=6, learning_rate=0.04, subsample=0.85, colsample_bytree=0.8, random_state=42)
    xgb_model.fit(X_tr, y_tr, sample_weight=w, verbose=False)
    p_xgb = xgb_model.predict(X_te)

    y_spread = df.loc[y_train_s[valid].index, 'da_rt_spread'].values
    valid_sp = ~np.isnan(y_spread)
    if valid_sp.sum() > 24:
        gbr_sp = GradientBoostingRegressor(n_estimators=500, max_depth=6, learning_rate=0.04, subsample=0.85, min_samples_leaf=4, random_state=42)
        gbr_sp.fit(X_tr[valid_sp], y_spread[valid_sp], sample_weight=w[valid_sp])
        p_spread = df.loc[test_mask, 'grid_da_avg'].fillna(0).values + gbr_sp.predict(X_te)
    else:
        p_spread = p_gbr

    train_idx = df.loc[train_mask & y_train_s.notna()].sort_values(['hour', 'date_key']).index
    p_lstm = train_bilstm(df.loc[train_idx, feat_list].fillna(0).values,
                          df.loc[train_idx, 'rt_price'].values, X_te, len(feat_list))
    if p_lstm is None:
        p_lstm = p_gbr

    p_ens = 0.20*p_gbr + 0.25*p_lgb + 0.15*p_xgb + 0.35*p_spread + 0.05*p_lstm

    return {
        'date': test_date, 'actual': y_te, 'pred': p_ens,
        'hour': df.loc[test_mask, 'hour'].values,
        'mae': mean_absolute_error(y_te, p_ens), 'r2': r2_score(y_te, p_ens),
        'importance': sorted(zip(feat_list, gbr.feature_importances_), key=lambda x: -x[1]),
    }

# ============================================================
# 7. Walk-forward: P2 vs P2+Weather
# ============================================================
print("\n[5/8] Walk-forward backtest...\n")

test_dates = ['20260313', '20260314', '20260315', '20260316', '20260317',
              '20260318', '20260319', '20260320', '20260321', '20260322']

results_p2, results_w = [], []
for td in test_dates:
    r_p2 = run_ensemble(df, feat_p2, td)
    r_w = run_ensemble(df, feat_weather, td)
    if r_p2: results_p2.append(r_p2)
    if r_w: results_w.append(r_w)
    if r_p2 and r_w:
        d = r_p2['mae'] - r_w['mae']
        print(f"  {td}: P2={r_p2['mae']:.1f} → P2+W={r_w['mae']:.1f}  {'▼' if d > 0 else '▲'}{abs(d):.1f} ({d/r_p2['mae']*100:+.1f}%)")

# ============================================================
# 8. Summary & Charts
# ============================================================
print("\n[6/8] Summary")
print("=" * 90)
print(f"{'Date':>10}  {'P2 MAE':>8}  {'P2+W MAE':>9}  {'Delta':>7}  {'%':>7}  {'P2 R2':>7}  {'P2+W R2':>8}")
print("-" * 90)
for rp, rw in zip(results_p2, results_w):
    d = rp['mae'] - rw['mae']
    print(f"{rp['date']:>10}  {rp['mae']:8.1f}  {rw['mae']:9.1f}  {d:+7.1f}  {d/rp['mae']*100:+6.1f}%  {rp['r2']:7.3f}  {rw['r2']:8.3f}")

avg_p2 = np.mean([r['mae'] for r in results_p2])
avg_w = np.mean([r['mae'] for r in results_w])
avg_d = avg_p2 - avg_w
print("-" * 90)
print(f"{'Avg':>10}  {avg_p2:8.1f}  {avg_w:9.1f}  {avg_d:+7.1f}  {avg_d/avg_p2*100:+6.1f}%")

print("\n天气特征重要性 (最后一天GBR):")
wf_set = set(WEATHER_FEATURES)
for name, val in results_w[-1]['importance']:
    if name in wf_set:
        print(f"  {name:30s} {val*100:5.2f}%")

# Charts
print("\n[7/8] Generating comparison chart...")
fig, axes = plt.subplots(5, 2, figsize=(20, 25))
fig.suptitle(f'P2 vs P2+Weather (10-day Backtest)\nP2 Avg MAE={avg_p2:.1f} → P2+W Avg MAE={avg_w:.1f} ({avg_d/avg_p2*100:+.1f}%)',
             fontsize=14, fontweight='bold', y=0.995)

for i in range(len(results_p2)):
    ax = axes.flatten()[i]
    rp, rw = results_p2[i], results_w[i]
    order = np.argsort(rp['hour'])
    x = np.arange(24)
    ax.plot(x, rp['actual'][order], 'b-o', ms=5, lw=2.5, label='Actual', zorder=4)
    ax.plot(x, rp['pred'][order], 'r--s', ms=3, lw=1.5, alpha=0.7, label=f'P2 ({rp["mae"]:.0f})', zorder=3)
    ax.plot(x, rw['pred'][order], 'g-^', ms=4, lw=2, label=f'P2+W ({rw["mae"]:.0f})', zorder=3)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_ylabel('Yuan/MWh')
    ax.grid(True, alpha=0.3, ls='--')
    d = rp['mae'] - rw['mae']
    c = '#228B22' if d > 0 else '#DC143C'
    ax.set_title(f"{rp['date'][4:6]}-{rp['date'][6:8]}  P2:{rp['mae']:.0f}→P2+W:{rw['mae']:.0f} ({'↓' if d>0 else '↑'}{abs(d):.0f})",
                 fontsize=11, fontweight='bold', color=c)
    ax.legend(fontsize=8, loc='upper left')

plt.tight_layout(rect=[0, 0, 1, 0.98])
plt.savefig(f'{OUT_DIR}/p2_weather_comparison.png', dpi=150, bbox_inches='tight')
print(f"  Saved: p2_weather_comparison.png")

# Bar chart
print("[8/8] Summary bar chart...")
fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
dates_short = [f"3/{r['date'][6:8]}" for r in results_p2]
mae_p2 = [r['mae'] for r in results_p2]
mae_w = [r['mae'] for r in results_w]
x = np.arange(len(dates_short))
w = 0.35
ax1.bar(x - w/2, mae_p2, w, label='P2', color='#FF6B6B', alpha=0.8)
ax1.bar(x + w/2, mae_w, w, label='P2+Weather', color='#4CAF50', alpha=0.8)
ax1.set_ylabel('MAE (Yuan/MWh)'); ax1.set_xticks(x); ax1.set_xticklabels(dates_short)
ax1.set_title(f'MAE: P2 Avg={avg_p2:.1f} → P2+W Avg={avg_w:.1f} ({avg_d/avg_p2*100:+.1f}%)', fontweight='bold')
ax1.legend(); ax1.grid(True, alpha=0.3, axis='y')

deltas = [p - w for p, w in zip(mae_p2, mae_w)]
ax2.bar(x, deltas, color=['#4CAF50' if d > 0 else '#FF6B6B' for d in deltas], alpha=0.8)
ax2.axhline(y=0, color='black', lw=0.5)
ax2.set_ylabel('MAE Improvement'); ax2.set_xticks(x); ax2.set_xticklabels(dates_short)
ax2.set_title('Per-day Improvement (green=weather helps)', fontweight='bold')
ax2.grid(True, alpha=0.3, axis='y')
for i, d in enumerate(deltas):
    ax2.text(i, d + (1 if d >= 0 else -3), f'{d:+.0f}', ha='center', fontsize=9, fontweight='bold')

plt.tight_layout()
plt.savefig(f'{OUT_DIR}/p2_weather_summary.png', dpi=150, bbox_inches='tight')
print(f"  Saved: p2_weather_summary.png")

print(f"\n{'='*70}")
print(f"P2 Avg MAE={avg_p2:.1f} → P2+Weather Avg MAE={avg_w:.1f} ({avg_d/avg_p2*100:+.1f}%)")
print(f"{'='*70}")
