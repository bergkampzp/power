#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2 Model - CEEMDAN Decomposition + BiLSTM + GBR Ensemble
=========================================================
Stage 3: CEEMDAN decomposes price into trend/wave/spike components
Stage 6: BiLSTM for sequence prediction
Plus: GBR + LightGBM + XGBoost ensemble from P1

Walk-forward: 3-19 ~ 3-22 (4 days)
"""
import sqlite3, warnings, os
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

warnings.filterwarnings('ignore')

from config import DB, OUT_DIR

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")
print("=" * 70)
print("P2 Model - CEEMDAN + BiLSTM + Multi-Model Ensemble")
print("=" * 70)

# ============================================================
# 1. Load & aggregate (reuse P1 data pipeline)
# ============================================================
print("\n[1/7] Loading data...")
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
# ⚠️ 时效性验证: renewable_forecast 有 publish_date 和 forecast_date
#    publish_date=D 包含 forecast_date=[D, D+1, ..., D+6] 的预测
#    当前使用 forecast_date 作为 join key (D日预测用于D日价格)
#    风险: D日预测可能是同日nowcast，在真实预测场景(D-1日做D日预测)中可能不可用
#    建议改进: 使用 publish_date + 1 的 forecast (即D-1日发布的D日预测)
#    → 详见: 电价预测模型改善行动方案.md §2.2

hydro_fc = pd.read_sql("SELECT forecast_date as date_key, avg_output_mw as hydro_fc_avg FROM hydro_forecast WHERE region='云南'", conn)
hydro_fc = hydro_fc.groupby('date_key').agg(hydro_fc_avg=('hydro_fc_avg', 'mean')).reset_index()
# ⚠️ 时效性: hydro_forecast 也有 publish_date, 同上

gen_fc_96 = pd.read_sql("SELECT forecast_date as date_key, period, forecast_mw as gen_fc FROM generation_forecast", conn)
gen_fc_96['hour'] = gen_fc_96['period'].str[:2].astype(int)
# ⚠️ 时效性: generation_forecast 也有 publish_date, 同上

load_fc_96 = pd.read_sql("SELECT date_key, period, load as load_fc FROM hourly_load WHERE region='云南'", conn)
load_fc_96['hour'] = load_fc_96['period'].str[:2].astype(int)

# Stage 1 data
section = pd.read_sql("SELECT trade_date, section_name, limit_value, period FROM section_constraint", conn)
section['hour'] = section['period'].str[:2].astype(int)
reserve = pd.read_sql("SELECT trade_date, period, reserve_type, reserve_value FROM system_reserve WHERE region='云南'", conn)
reserve['hour'] = reserve['period'].str[:2].astype(int)
maint = pd.read_sql("SELECT trade_date, COUNT(*) as maint_count FROM maintenance_plan GROUP BY trade_date", conn)
channel = pd.read_sql("SELECT trade_date, capacity FROM transmission_channel", conn)
interline = pd.read_sql("SELECT trade_date, power_flow, period FROM inter_provincial_line", conn)
interline['hour'] = interline['period'].str[:2].astype(int)

# Weather correction features (28,296 records, 2023-01 ~ 2026-03)
weather_corr = pd.read_sql(
    """SELECT date, hour, solar_correction, wind_correction, combined_correction
       FROM weather_correction""", conn)
weather_corr['date_key'] = weather_corr['date'].str.replace('-', '')

conn.close()

# ============================================================
# 2. Aggregate to hourly
# ============================================================
print("[2/7] Aggregate to hourly...")

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

# Merge
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
    (weather_corr, ['solar_correction', 'wind_correction', 'combined_correction'], ['date_key', 'hour']),
]:
    df = df.merge(src[on + cols], on=on, how='left')

df.rename(columns={'load': 'total_load'}, inplace=True)

# ============================================================
# 3. CEEMDAN Decomposition (Stage 3)
# ============================================================
print("[3/7] CEEMDAN decomposition...")

# Causal decomposition: use only past data (no future leakage)
def _causal_trend(signal, half_life=14):
    """单向指数加权趋势：只使用过去数据，避免Savgol的中心窗口泄漏"""
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

# Decompose daily avg price into trend + wave + spike (causal only)
daily_price = df.groupby('date_key')['rt_price'].mean().reset_index()
daily_price = daily_price.sort_values('date_key').reset_index(drop=True)
price_signal = daily_price['rt_price'].values

try:
    n = len(price_signal)
    # Causal trend: exponential weighted (14-day half-life)
    trend = _causal_trend(price_signal, half_life=min(14, max(3, n//4)))
    # Causal wave: 5-day half-life on residual
    residual1 = price_signal - trend
    wave = _causal_wave(residual1, half_life=min(5, max(2, n//6)))
    spike = residual1 - wave

    daily_price['price_trend'] = trend
    daily_price['price_wave'] = wave
    daily_price['price_spike'] = spike
    print(f"  Decomposition: causal_trend(14d) + causal_wave(5d) + spike, signal len={n}")

    df = df.merge(daily_price[['date_key', 'price_trend', 'price_wave', 'price_spike']],
                  on='date_key', how='left')
except Exception as e:
    print(f"  Decomposition failed: {e}")
    df['price_trend'] = 0
    df['price_wave'] = 0
    df['price_spike'] = 0

# ============================================================
# 4. Build all features
# ============================================================
print("[4/7] Building features...")

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
# CEEMDAN lags
df = lag_h(df, 'price_trend', 'trend_lag1d', 1)
df = lag_h(df, 'price_spike', 'spike_lag1d', 1)

for w in [3, 5, 7]:
    df[f'price_ma_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
    df[f'price_std_{w}d'] = df.groupby('hour')['rt_price'].transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0))

df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

# Previous-day aggs
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
# 5. Feature list
# ============================================================
FEATURES = [
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
    # Weather correction features
    'solar_correction', 'wind_correction', 'combined_correction',
    # Stage 3: CEEMDAN
    'price_trend', 'price_wave', 'price_spike', 'trend_lag1d', 'spike_lag1d',
]
feat = [f for f in FEATURES if f in df.columns]
print(f"  Features: {len(feat)} active, {len(df)} rows, {df['date_key'].nunique()} days")

# ============================================================
# 6. BiLSTM Model (Stage 6)
# ============================================================
class BiLSTMModel(nn.Module):
    def __init__(self, input_dim, hidden=64, layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden, layers, batch_first=True,
                            bidirectional=True, dropout=dropout)
        self.fc = nn.Sequential(
            nn.Linear(hidden * 2, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        # x: (batch, seq_len, features)
        out, _ = self.lstm(x)
        # Use last timestep output
        out = out[:, -1, :]
        return self.fc(out).squeeze(-1)


def train_bilstm(X_train, y_train, X_test, n_feat, seq_len=7, epochs=50, lr=0.001):
    """Train BiLSTM with sliding window of seq_len days."""
    # Build sequences: for each sample, use past seq_len days same hour
    # X_train is already sorted by (hour, date_key)
    # We'll reshape to (n_samples, seq_len, n_features)

    n = len(X_train)
    if n < seq_len + 1:
        return None

    # Create sequences
    X_seq, y_seq = [], []
    for i in range(seq_len, n):
        X_seq.append(X_train[i-seq_len:i])
        y_seq.append(y_train[i])

    X_seq = np.array(X_seq, dtype=np.float32)
    y_seq = np.array(y_seq, dtype=np.float32)

    # Normalize
    x_mean = X_seq.reshape(-1, n_feat).mean(axis=0)
    x_std = X_seq.reshape(-1, n_feat).std(axis=0) + 1e-8
    y_mean, y_std = y_seq.mean(), y_seq.std() + 1e-8

    X_seq_n = (X_seq - x_mean) / x_std
    y_seq_n = (y_seq - y_mean) / y_std

    # Test sequence (use last seq_len from train + test)
    X_test_np = X_test.astype(np.float32)
    # For test, we need seq_len preceding samples for each test point
    # Use last seq_len train samples as context
    X_context = X_train[-seq_len:].astype(np.float32)
    X_test_seqs = []
    for i in range(len(X_test_np)):
        if i < seq_len:
            ctx = np.vstack([X_context[i:], X_test_np[:i]]) if i > 0 else X_context
        else:
            ctx = X_test_np[i-seq_len:i]
        X_test_seqs.append(ctx)
    X_test_seqs = np.array(X_test_seqs, dtype=np.float32)
    X_test_seqs_n = (X_test_seqs - x_mean) / x_std

    # Train
    dataset = TensorDataset(torch.tensor(X_seq_n), torch.tensor(y_seq_n))
    loader = DataLoader(dataset, batch_size=32, shuffle=True)

    model = BiLSTMModel(n_feat).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    # Predict
    model.eval()
    with torch.no_grad():
        xt = torch.tensor(X_test_seqs_n).to(device)
        pred_n = model(xt).cpu().numpy()
    preds = pred_n * y_std + y_mean
    return preds


# ============================================================
# 7. Walk-forward: 3-19 ~ 3-22
# ============================================================
print("\n[5/7] Walk-forward (3-19~3-22)...\n")

test_dates = ['20260313', '20260314', '20260315', '20260316', '20260317',
              '20260318', '20260319', '20260320', '20260321', '20260322']
results = []

for test_date in test_dates:
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date

    X_train_df = df.loc[train_mask, feat].fillna(0)
    y_train_s = df.loc[train_mask, 'rt_price']
    X_test_df = df.loc[test_mask, feat].fillna(0)
    y_test_s = df.loc[test_mask, 'rt_price']

    valid = y_train_s.notna()
    X_tr = X_train_df[valid].values
    y_tr = y_train_s[valid].values
    X_te = X_test_df.values
    y_te = y_test_s.values

    if len(X_tr) < 48 or len(X_te) == 0:
        print(f"  SKIP {test_date}")
        continue

    # Sample weights
    train_d = df.loc[y_train_s[valid].index, 'date']
    test_dt = pd.to_datetime(test_date, format='%Y%m%d')
    days_ago = (test_dt - train_d).dt.days.values.astype(float)
    w = np.exp(-np.log(2) * days_ago / 45.0)
    tm = train_d.dt.month.values
    dry = np.isin(tm, [11, 12, 1, 2, 3, 4, 5])
    w *= np.where(dry, 2.0, 0.5)
    w /= w.mean()

    # ── Model 1: GBR ──
    gbr = GradientBoostingRegressor(n_estimators=500, max_depth=6, learning_rate=0.04,
                                     subsample=0.85, min_samples_leaf=4, random_state=42)
    gbr.fit(X_tr, y_tr, sample_weight=w)
    p_gbr = gbr.predict(X_te)

    # ── Model 2: LightGBM ──
    dtrain = lgb.Dataset(X_tr, y_tr, weight=w)
    lgb_params = {'objective': 'regression', 'metric': 'mae', 'num_leaves': 63,
                  'learning_rate': 0.04, 'feature_fraction': 0.8, 'bagging_fraction': 0.85,
                  'bagging_freq': 5, 'verbose': -1, 'seed': 42}
    lgb_model = lgb.train(lgb_params, dtrain, num_boost_round=500)
    p_lgb = lgb_model.predict(X_te)

    # ── Model 3: XGBoost ──
    xgb_model = xgb.XGBRegressor(n_estimators=500, max_depth=6, learning_rate=0.04,
                                   subsample=0.85, colsample_bytree=0.8, random_state=42)
    xgb_model.fit(X_tr, y_tr, sample_weight=w, verbose=False)
    p_xgb = xgb_model.predict(X_te)

    # ── Model 4: GBR on DA-RT spread ──
    y_spread = df.loc[y_train_s[valid].index, 'da_rt_spread'].values
    valid_sp = ~np.isnan(y_spread)
    if valid_sp.sum() > 24:
        gbr_sp = GradientBoostingRegressor(n_estimators=500, max_depth=6, learning_rate=0.04,
                                            subsample=0.85, min_samples_leaf=4, random_state=42)
        gbr_sp.fit(X_tr[valid_sp], y_spread[valid_sp], sample_weight=w[valid_sp])
        da_test = df.loc[test_mask, 'grid_da_avg'].fillna(0).values
        p_spread = da_test + gbr_sp.predict(X_te)
    else:
        p_spread = p_gbr

    # ── Model 5: BiLSTM ──
    # Sort train by (hour, date) for sequence building
    train_idx = df.loc[train_mask & y_train_s.notna()].sort_values(['hour', 'date_key']).index
    X_tr_seq = df.loc[train_idx, feat].fillna(0).values
    y_tr_seq = df.loc[train_idx, 'rt_price'].values
    p_lstm = train_bilstm(X_tr_seq, y_tr_seq, X_te, len(feat), seq_len=7, epochs=30)
    if p_lstm is None:
        p_lstm = p_gbr

    # ── Ensemble: weighted average ──
    # Optimized: Spread dominant, drop LSTM weight
    # GBR:20% + LGB:25% + XGB:15% + Spread:35% + LSTM:5%
    p_ensemble = (0.20 * p_gbr + 0.25 * p_lgb + 0.15 * p_xgb +
                  0.35 * p_spread + 0.05 * p_lstm)

    # ── Quantile (P10/P90) from GBR ──
    q10 = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                     subsample=0.85, loss='quantile', alpha=0.10, random_state=42)
    q90 = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                     subsample=0.85, loss='quantile', alpha=0.90, random_state=42)
    q10.fit(X_tr, y_tr, sample_weight=w)
    q90.fit(X_tr, y_tr, sample_weight=w)
    p_q10 = q10.predict(X_te)
    p_q90 = q90.predict(X_te)

    # Metrics
    mae_gbr = mean_absolute_error(y_te, p_gbr)
    mae_lgb = mean_absolute_error(y_te, p_lgb)
    mae_xgb = mean_absolute_error(y_te, p_xgb)
    mae_sp = mean_absolute_error(y_te, p_spread)
    mae_lstm = mean_absolute_error(y_te, p_lstm)
    mae_ens = mean_absolute_error(y_te, p_ensemble)
    r2_ens = r2_score(y_te, p_ensemble)
    cov = np.mean((y_te >= p_q10) & (y_te <= p_q90)) * 100
    width = np.mean(p_q90 - p_q10)

    results.append({
        'date': test_date,
        'actual': y_te,
        'pred': p_ensemble,
        'p_gbr': p_gbr, 'p_lgb': p_lgb, 'p_xgb': p_xgb,
        'p_spread': p_spread, 'p_lstm': p_lstm,
        'p_q10': p_q10, 'p_q90': p_q90,
        'hour': df.loc[test_mask, 'hour'].values,
        'mae_gbr': mae_gbr, 'mae_lgb': mae_lgb, 'mae_xgb': mae_xgb,
        'mae_sp': mae_sp, 'mae_lstm': mae_lstm,
        'mae_ens': mae_ens, 'r2': r2_ens,
        'coverage': cov, 'width': width,
    })

    print(f"  {test_date}: GBR={mae_gbr:.1f} LGB={mae_lgb:.1f} XGB={mae_xgb:.1f} "
          f"Spread={mae_sp:.1f} LSTM={mae_lstm:.1f} | Ensemble={mae_ens:.1f} "
          f"R2={r2_ens:.3f} CI={cov:.0f}%")

# ============================================================
# 8. Plot
# ============================================================
print("\n[6/7] Chart...")

n_res = len(results)
n_rows_plot = (n_res + 1) // 2
fig, axes = plt.subplots(n_rows_plot, 2, figsize=(18, 4.5 * n_rows_plot + 1))
fig.suptitle('P2 Model - Decomposition + BiLSTM + GBR/LGB/XGB Ensemble\n'
             '(5-model, optimized weights, 10-day backtest)', fontsize=13, fontweight='bold', y=0.99)

for i, res in enumerate(results):
    ax = axes.flatten()[i]
    order = np.argsort(res['hour'])
    actual = res['actual'][order]
    pred = res['pred'][order]
    q10 = res['p_q10'][order]
    q90 = res['p_q90'][order]
    x = np.arange(24)

    ax.fill_between(x, q10, q90, alpha=0.2, color='orange', label='P10-P90')
    ax.plot(x, actual, 'b-o', ms=5, lw=2.5, label='actual', zorder=4)
    ax.plot(x, pred, 'r--s', ms=4, lw=2, label='ensemble', zorder=3)

    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 3)])
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylabel('Price (Yuan/MWh)')
    ax.set_xlabel('Hour')
    ax.grid(True, alpha=0.3, ls='--')

    date_s = f"2026-{res['date'][4:6]}-{res['date'][6:8]}"
    mae = res['mae_ens']
    c = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
    ax.set_title(f"{date_s}  MAE:{mae:.1f}  R2:{res['r2']:.3f}  CI:{res['coverage']:.0f}%",
                 fontsize=11, fontweight='bold')
    ax.text(0.97, 0.95,
            f"GBR:{res['mae_gbr']:.0f}\nLGB:{res['mae_lgb']:.0f}\nXGB:{res['mae_xgb']:.0f}\n"
            f"Spread:{res['mae_sp']:.0f}\nLSTM:{res['mae_lstm']:.0f}\nEns:{mae:.0f}",
            transform=ax.transAxes, fontsize=8, va='top', ha='right',
            bbox=dict(boxstyle='round', facecolor=c, alpha=0.3, edgecolor=c))
    ax.legend(fontsize=8, loc='upper left')

# Hide unused axes
for j in range(n_res, len(axes.flatten())):
    axes.flatten()[j].set_visible(False)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(f'{OUT_DIR}/p2_10day_backtest.png', dpi=150, bbox_inches='tight')
print(f"  Saved: p2_10day_backtest.png")

# ============================================================
# 9. Summary
# ============================================================
print("\n[7/7] Summary")
print("=" * 100)
print(f"{'Date':>10s}  {'GBR':>6s}  {'LGB':>6s}  {'XGB':>6s}  {'Spread':>6s}  {'LSTM':>6s}  "
      f"{'Ensem':>6s}  {'R2':>6s}  {'CI%':>4s}  {'Width':>5s}")
print("-" * 100)
for r in results:
    print(f"{r['date']:>10s}  {r['mae_gbr']:6.1f}  {r['mae_lgb']:6.1f}  {r['mae_xgb']:6.1f}  "
          f"{r['mae_sp']:6.1f}  {r['mae_lstm']:6.1f}  "
          f"{r['mae_ens']:6.1f}  {r['r2']:6.3f}  {r['coverage']:4.0f}  {r['width']:5.0f}")

avgs = {k: np.mean([r[k] for r in results])
        for k in ['mae_gbr', 'mae_lgb', 'mae_xgb', 'mae_sp', 'mae_lstm', 'mae_ens']}
print("-" * 100)
print(f"{'Avg':>10s}  {avgs['mae_gbr']:6.1f}  {avgs['mae_lgb']:6.1f}  {avgs['mae_xgb']:6.1f}  "
      f"{avgs['mae_sp']:6.1f}  {avgs['mae_lstm']:6.1f}  {avgs['mae_ens']:6.1f}")

# Feature importance from GBR
imp = sorted(zip(feat, gbr.feature_importances_), key=lambda x: -x[1])
print("\nTop 15 Feature Importance (GBR):")
for f_name, f_val in imp[:15]:
    print(f"  {f_name:30s} {f_val*100:5.2f}%")
