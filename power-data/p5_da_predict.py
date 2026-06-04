#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P5 次日前电价预测模型 (DA[D+1])
=================================
目标: 用过去数据预测次日的日前市场出清价
数据: __avg__(171d) + __all_avg__(134d) 拼接, is_all_avg 指示变量
特征: DA自回归 + RT滞后 + 负荷/新能源/水电 + 天气修正 + 电网约束
基线: 持久化 DA[D]→DA[D+1] (MAE≈56)
目标: MAE ≤45 ¥/MWh
"""
import sys, warnings, os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')   # Windows 控制台默认GBK, 无法打印 ¥ 等字符
except Exception:
    pass

from config import DB, OUT_DIR
import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import lightgbm as lgb
import xgboost as xgb
from eval_framework import rmae, diebold_mariano, pick_blend_alpha

print("=" * 70)
print("P5 次日前电价预测 (DA[D+1] - GBR+LGB+XGB Ensemble)", flush=True)
print("=" * 70)

# ============================================================
# 1. 数据加载
# ============================================================
print("\n[1/5] Loading data...", flush=True)
conn = sqlite3.connect(DB)

# ── 日前电价 (target: 拼接 __avg__ + __all_avg__) ──
da_96 = pd.read_sql("""
    SELECT trade_date, period, price, node_name
    FROM day_ahead_node_price_96
    WHERE node_name IN ('__avg__', '__all_avg__')
    ORDER BY trade_date, period, node_name
""", conn)
da_96['date_key'] = da_96['trade_date'].str.replace('-', '')
da_96['hour'] = da_96['period'].str[:2].astype(int)
da_96['is_all_avg'] = (da_96['node_name'] == '__all_avg__').astype(int)
# 去重: __avg__ 和 __all_avg__ 在同一天不会同时出现, 但安全起见取平均
da_h = da_96.groupby(['date_key', 'hour']).agg(
    da_price=('price', 'mean'),
    is_all_avg=('is_all_avg', 'max')
).reset_index()
print(f"  日前电价: {da_h['date_key'].nunique()}天, {len(da_h)}行, "
      f"均值={da_h['da_price'].mean():.1f} ¥/MWh", flush=True)

# ── 实时电价 (RT lag 特征) ──
rt_96 = pd.read_sql("""
    SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
    FROM realtime_node_price_96 WHERE node_name = '__avg__'
    ORDER BY trade_date, period
""", conn)
rt_96['hour'] = rt_96['period'].str[:2].astype(int)
rt_h = rt_96.groupby(['date_key', 'hour']).agg(rt_price=('rt_price', 'mean')).reset_index()
print(f"  实时电价: {rt_h['date_key'].nunique()}天, 均值={rt_h['rt_price'].mean():.1f}", flush=True)

# ── 负荷 ──
load_96 = pd.read_sql("SELECT date_key, period, load FROM hourly_load WHERE region='云南'", conn)
load_96['hour'] = load_96['period'].str[:2].astype(int)
load_h = load_96.groupby(['date_key','hour']).agg(total_load=('load','mean')).reset_index()

# ── 新能源出力 ──
renew_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_renewable WHERE region='云南'", conn)
renew_96['hour'] = renew_96['period'].str[:2].astype(int)
renew_h = renew_96.groupby(['date_key','hour']).agg(renewable=('output','mean')).reset_index()

# ── 水电 ──
hydro_96 = pd.read_sql("SELECT date_key, period, output FROM hourly_hydro WHERE region='云南'", conn)
hydro_96['hour'] = hydro_96['period'].str[:2].astype(int)
hydro_h = hydro_96.groupby(['date_key','hour']).agg(hydro=('output','mean')).reset_index()

# ── 日前电价(漫湾厂, 用于lag特征) ──
manwan_da = pd.read_sql("""
    SELECT trade_date, period, AVG(price) as manwan_da
    FROM day_ahead_node_price_96
    WHERE node_name IN ('漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母','漫湾厂.500kV#1M','漫湾厂.500kV#2M')
    GROUP BY trade_date, period
""", conn)
manwan_da['date_key'] = manwan_da['trade_date'].str.replace('-', '')
manwan_da['hour'] = manwan_da['period'].str[:2].astype(int)
manwan_h = manwan_da.groupby(['date_key','hour']).agg(manwan_da=('manwan_da','mean')).reset_index()

# ── 负荷预测 (使用 publish_date 对齐) ──
load_fc = pd.read_sql("""
    SELECT publish_date as pd, trade_date as td, period, forecast_load as load_fc
    FROM load_forecast WHERE region='云南'
""", conn)
load_fc['pub_key'] = load_fc['pd'].str.replace('-', '')
load_fc['hour'] = load_fc['period'].str[:2].astype(int)

# ── 新能源预测 ──
renew_fc = pd.read_sql("""
    SELECT publish_date as pd, forecast_date as fd, period, forecast_mw as renew_fc
    FROM renewable_forecast WHERE region='云南' AND category='总计'
""", conn)
renew_fc['pub_key'] = renew_fc['pd'].str.replace('-', '')
renew_fc['hour'] = renew_fc['period'].str[:2].astype(int)

# ── 发电预测 ──
gen_fc = pd.read_sql("""
    SELECT publish_date as pd, forecast_date as fd, period, forecast_mw as gen_fc
    FROM generation_forecast
""", conn)
gen_fc['pub_key'] = gen_fc['pd'].str.replace('-', '')
gen_fc['hour'] = gen_fc['period'].str[:2].astype(int)

# ── 水电预测 ──
hydro_fc = pd.read_sql("""
    SELECT publish_date as pd, forecast_date as fd, avg_output_mw as hydro_fc_avg
    FROM hydro_forecast WHERE region='云南'
""", conn)
hydro_fc['pub_key'] = hydro_fc['pd'].str.replace('-', '')

# ── 天气修正 (1179天, 覆盖全部) ──
weather = pd.read_sql("""
    SELECT date, hour, solar_correction, wind_correction, combined_correction
    FROM weather_correction
""", conn)
weather['date_key'] = weather['date'].str.replace('-', '')

# ── 电网数据 ──
section = pd.read_sql("SELECT trade_date, section_name, limit_value, period FROM section_constraint", conn)
section['hour'] = section['period'].str[:2].astype(int)
reserve = pd.read_sql("SELECT trade_date, period, reserve_type, reserve_value FROM system_reserve WHERE region='云南'", conn)
reserve['hour'] = reserve['period'].str[:2].astype(int)
maint = pd.read_sql("SELECT trade_date, COUNT(*) as maint_count FROM maintenance_plan GROUP BY trade_date", conn)
channel = pd.read_sql("SELECT trade_date, capacity FROM transmission_channel", conn)
interline = pd.read_sql("SELECT trade_date, power_flow, period FROM inter_provincial_line", conn)
interline['hour'] = interline['period'].str[:2].astype(int)

conn.close()

# ============================================================
# 2. 聚合到小时 + 特征构建
# ============================================================
print("[2/5] Building features...", flush=True)

# ── 基础特征 DataFrame ──
# 以日前电价为主表, 左连接所有特征
df = da_h[['date_key', 'hour', 'da_price', 'is_all_avg']].copy()

# 合并实时电价
df = df.merge(rt_h, on=['date_key', 'hour'], how='left')

# 合并负荷/新能源/水电
for src, cols in [(load_h, ['total_load']), (renew_h, ['renewable']), (hydro_h, ['hydro'])]:
    df = df.merge(src, on=['date_key', 'hour'], how='left')

# 合并漫湾日前价
df = df.merge(manwan_h, on=['date_key', 'hour'], how='left')

# ── 合并预测特征 (闸口对齐, leakage-safe) ──
# 修复: 原实现按 publish_date 合并, 把同一天发布的"多个预测期"混合平均, 且未对齐到
# 真正的目标交易日(D+1)。现改为: 按目标交易日对齐, 只取"发布日严格早于目标日"的最近一次
# 发布 (= DA[D+1] 报价闸口时真实可得的次日预测)。
_dates = sorted(df['date_key'].unique())
_next = {d: (_dates[i + 1] if i + 1 < len(_dates) else None) for i, d in enumerate(_dates)}
df['target_date'] = df['date_key'].map(_next)

def _gate_aligned(raw, tgt_col, val_col, out_name, with_hour=True):
    """按目标交易日对齐预测, 取闸口前(发布<目标日)最近一次发布。"""
    r = raw.copy()
    r['tkey'] = r[tgt_col].str.replace('-', '')
    r['pkey'] = r['pd'].str.replace('-', '')
    r = r[r['pkey'] < r['tkey']]
    keys = ['tkey', 'hour'] if with_hour else ['tkey']
    if r.empty:
        cols = ['target_date'] + (['hour'] if with_hour else []) + [out_name]
        return pd.DataFrame(columns=cols)
    r = r.sort_values('pkey').groupby(keys, as_index=False).agg(**{out_name: (val_col, 'last')})
    return r.rename(columns={'tkey': 'target_date'})

df = df.merge(_gate_aligned(load_fc, 'td', 'load_fc', 'load_fc'),
              on=['target_date', 'hour'], how='left')
df = df.merge(_gate_aligned(renew_fc, 'fd', 'renew_fc', 'renew_fc'),
              on=['target_date', 'hour'], how='left')
df = df.merge(_gate_aligned(gen_fc, 'fd', 'gen_fc', 'gen_fc'),
              on=['target_date', 'hour'], how='left')
df = df.merge(_gate_aligned(hydro_fc, 'fd', 'hydro_fc_avg', 'hydro_fc_avg', with_hour=False),
              on='target_date', how='left')

# 天气修正
df = df.merge(weather, on=['date_key', 'hour'], how='left')

# 电网数据
def _section(df):
    section['date_key'] = section['trade_date'].str.replace('-','')
    sh = section.groupby(['date_key','hour']).agg(n_sections=('section_name','nunique'),avg_limit=('limit_value','mean')).reset_index()
    return df.merge(sh, on=['date_key','hour'], how='left')
def _reserve(df):
    reserve['date_key'] = reserve['trade_date'].str.replace('-','')
    ru = reserve[reserve['reserve_type'].str.contains('正')].groupby(['date_key','hour']).agg(reserve_up=('reserve_value','mean')).reset_index()
    rd = reserve[reserve['reserve_type'].str.contains('负')].groupby(['date_key','hour']).agg(reserve_down=('reserve_value','mean')).reset_index()
    df = df.merge(ru, on=['date_key','hour'], how='left')
    df = df.merge(rd, on=['date_key','hour'], how='left')
    return df
def _maint(df):
    maint['date_key'] = maint['trade_date'].str.replace('-','')
    return df.merge(maint, on='date_key', how='left')
def _channel(df):
    channel['date_key'] = channel['trade_date'].str.replace('-','')
    ch = channel.groupby('date_key').agg(total_chan_cap=('capacity','sum')).reset_index()
    return df.merge(ch, on='date_key', how='left')
def _interline(df):
    interline['date_key'] = interline['trade_date'].str.replace('-','')
    ih = interline.groupby(['date_key','hour']).agg(total_flow=('power_flow','sum')).reset_index()
    return df.merge(ih, on=['date_key','hour'], how='left')

df = _section(df); df = _reserve(df); df = _maint(df)
df = _channel(df); df = _interline(df)

# ════════════════════════════════════════════════
# 目标构造: 预测次日前电价 DA[D+1]
# 将 da_price 按 hour group shift -1 天
# ════════════════════════════════════════════════
df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)
df['da_target'] = df.groupby('hour')['da_price'].shift(-1)
print(f"  DA[D+1] target 就绪, 有效样本={df['da_target'].notna().sum()}", flush=True)

# ════════════════════════════════════════════════
# 时间编码
# ════════════════════════════════════════════════
df['date'] = pd.to_datetime(df['date_key'], format='%Y%m%d', errors='coerce')
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
df['day_of_year'] = df['date'].dt.dayofyear
df['doy_sin'] = np.sin(2*np.pi*df['day_of_year']/365)
df['doy_cos'] = np.cos(2*np.pi*df['day_of_year']/365)

# ════════════════════════════════════════════════
# 供需特征
# ════════════════════════════════════════════════
df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)
df['fc_gap'] = df['load_fc'].fillna(0) - df['renew_fc'].fillna(0) - df['hydro_fc_avg'].fillna(0)
df['renew_fc_share'] = np.where(df['gen_fc']>0, df['renew_fc'].fillna(0)/df['gen_fc'], 0)
df['reserve_ratio'] = np.where(df['total_load']>0, df['reserve_up'].fillna(0)/df['total_load'], 0)
df['flow_to_cap'] = np.where(df['total_chan_cap']>0, df['total_flow'].fillna(0)/df['total_chan_cap'], 0)

# ════════════════════════════════════════════════
# Lag 特征 (用 shift, 按 hour group)
# ════════════════════════════════════════════════
def lag_h(d, col, new, n):
    d[new] = d.groupby('hour')[col].shift(n)
    return d

# DA 自回归 lag (替代 grid_da_avg 特征)
for lag in [1,2,3,7]:
    df = lag_h(df, 'da_price', f'da_lag_{lag}d', lag)

# RT lag (D-1实时价在预测DA[D+1]时已知)
for lag in [1,2,3,7]:
    df = lag_h(df, 'rt_price', f'rt_lag_{lag}d', lag)

# 曼湾厂 DA lag
df = lag_h(df, 'manwan_da', 'manwan_lag1d', 1)
df['manwan_change'] = df['manwan_da'].fillna(0) - df['manwan_lag1d'].fillna(0)

# 负荷/新能源 lag
for lag in [1,2]:
    df = lag_h(df, 'total_load', f'load_lag_{lag}d', lag)
    df = lag_h(df, 'renewable', f'renew_lag_{lag}d', lag)
df = lag_h(df, 'hydro', 'hydro_lag_1d', 1)
df = lag_h(df, 'gap', 'gap_lag_1d', 1)
df = lag_h(df, 'gap', 'gap_lag_2d', 2)
df['gap_change'] = df['gap_lag_1d'].fillna(0) - df['gap_lag_2d'].fillna(0)

# DA-RT 价差 lag
df['rt_da_spread_lag1'] = df['rt_lag_1d'].fillna(0) - df['da_lag_1d'].fillna(0)

# MA/STD
for w in [3,5,7]:
    df[f'da_ma_{w}d'] = df.groupby('hour')['da_price'].transform(lambda x: x.shift(1).rolling(w,min_periods=1).mean())
    df[f'da_std_{w}d'] = df.groupby('hour')['da_price'].transform(lambda x: x.shift(1).rolling(w,min_periods=1).std().fillna(0))
df['da_momentum_3d'] = df['da_lag_1d'] - df['da_ma_3d']

# 电网 lag
df = lag_h(df, 'total_chan_cap', 'chan_lag1d', 1)
df['chan_change'] = df['total_chan_cap'].fillna(0) - df['chan_lag1d'].fillna(0)
df = lag_h(df, 'maint_count', 'maint_lag1d', 1)
df['maint_change'] = df['maint_count'].fillna(0) - df['maint_lag1d'].fillna(0)
df = lag_h(df, 'reserve_up', 'reserve_up_lag1d', 1)
df['reserve_change'] = df['reserve_up'].fillna(0) - df['reserve_up_lag1d'].fillna(0)
df = lag_h(df, 'renew_fc', 'renew_fc_lag1d', 1)
df['renew_fc_error_1d'] = df['renew_fc_lag1d'].fillna(0) - df['renew_lag_1d'].fillna(0)

# 天气 lag
df = lag_h(df, 'combined_correction', 'weather_lag1d', 1)

# 前一日聚合统计
da_daily = df.groupby('date_key').agg(
    d_avg=('da_price','mean'), d_max=('da_price','max'),
    d_min=('da_price','min'), d_std=('da_price','std'),
).reset_index()
da_daily.columns=['date_key']+[f'prevday_{c}' for c in da_daily.columns[1:]]
all_dates = sorted(df['date_key'].unique())
# 修复时间反转泄漏: 原代码把"X日聚合"标到 X 的前一日, 导致预测 DA[D+1] 的 D 行
# 拿到了次日(D+1, 即目标日)的当日均值/极值, 严重泄漏。改为标到 X 的次日,
# 这样 D 行获得的是"前一日(D-1)"的真实历史统计。
nxt={d:(all_dates[i+1] if i+1<len(all_dates) else None) for i,d in enumerate(all_dates)}
da_daily['dk_target']=da_daily['date_key'].map(nxt)
da_daily=da_daily.dropna(subset=['dk_target']).drop('date_key',axis=1).rename(columns={'dk_target':'date_key'})
df=df.merge(da_daily,on='date_key',how='left')
df['prev_ratio'] = np.where(df['prevday_d_avg']>0, df['da_lag_1d']/df['prevday_d_avg'], 1.0)

df = df.sort_values(['date_key','hour']).reset_index(drop=True)

# ════════════════════════════════════════════════
# 特征列表 (移除原RT模型中的grid_da_avg, manwan_da_price)
# 新增: da_lag, rt_lag, rt_da_spread_lag1, is_all_avg
# ════════════════════════════════════════════════
FEATURES = [
    'hour', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos',
    'month_sin', 'month_cos', 'week_of_year', 'woy_sin', 'woy_cos',
    'is_wet_season', 'is_transition', 'day_of_year', 'doy_sin', 'doy_cos',
    'is_all_avg',
    # DA 自回归 (替代 grid_da_avg)
    'da_lag_1d', 'da_lag_2d', 'da_lag_3d', 'da_lag_7d',
    'da_ma_3d', 'da_ma_5d', 'da_ma_7d',
    'da_std_3d', 'da_std_7d', 'da_momentum_3d',
    # RT 滞后参考
    'rt_lag_1d', 'rt_lag_2d', 'rt_lag_3d', 'rt_lag_7d',
    'rt_da_spread_lag1',
    # 曼湾厂
    'manwan_da', 'manwan_lag1d', 'manwan_change',
    # 负荷/新能源/水电 lag
    'load_lag_1d', 'load_lag_2d', 'renew_lag_1d', 'renew_lag_2d', 'hydro_lag_1d',
    'gap_lag_1d', 'gap_lag_2d', 'gap_change',
    # 前日聚合
    'prevday_d_avg', 'prevday_d_max', 'prevday_d_min', 'prevday_d_std', 'prev_ratio',
    # 预测值
    'load_fc', 'renew_fc', 'hydro_fc_avg', 'gen_fc',
    'fc_gap', 'renew_fc_share',
    # 电网约束
    'n_sections', 'avg_limit', 'reserve_up', 'reserve_down', 'reserve_ratio',
    'reserve_change', 'reserve_up_lag1d',
    'total_chan_cap', 'chan_change', 'total_flow', 'flow_to_cap',
    'maint_count', 'maint_change',
    # 天气修正
    'solar_correction', 'wind_correction', 'combined_correction', 'weather_lag1d',
    # 预测误差
    'renew_fc_error_1d',
]

feat = [f for f in FEATURES if f in df.columns]
print(f"  特征: {len(feat)} active", flush=True)

# ============================================================
# 3. 持久化基线 (Persistence Baseline)
# ============================================================
print("\n[3/5] Persistence Baseline: DA[D]→DA[D+1]...", flush=True)

# 持久化预测: 直接用 DA[D] 作为 DA[D+1] 的预测
persist_valid = df[['date_key', 'hour', 'da_price', 'da_target']].dropna(subset=['da_target']).copy()
persist_valid['pred_persist'] = persist_valid['da_price']  # DA[D] → DA[D+1]
persist_mae = mean_absolute_error(persist_valid['da_target'], persist_valid['pred_persist'])
persist_r2 = r2_score(persist_valid['da_target'], persist_valid['pred_persist'])
print(f"  持久化基线 MAE={persist_mae:.1f} ¥/MWh, R²={persist_r2:.3f}", flush=True)

# ============================================================
# 4. Walk-forward 回测
# ============================================================
print("\n[4/5] Walk-forward backtest (last 10 days)...", flush=True)

# 最后10个有da_target的日期
valid_dates = sorted(df.dropna(subset=['da_target'])['date_key'].unique())
test_dates = valid_dates[-10:]
print(f"  测试日期: {test_dates[0]} ~ {test_dates[-1]} ({len(test_dates)}天)", flush=True)

results = []
# 预测组合(forecast combination): blend = α·Ensemble + (1-α)·Persistence。
# 完整枯季验证: 该组合显著优于纯Ensemble (rMAE 0.94->0.91, DM p<0.001)。
# α 自适应、无泄漏: 用过去 BLEND_V 天滚动验证误差挑选; 冷启动用先验 BLEND_COLD。
BLEND_V = 20
BLEND_COLD = 0.7
_blend_hist = []
print(f"\n{'Date':>10s}  {'GBR':>6s}  {'LGB':>6s}  {'XGB':>6s}  {'Ensemble':>8s}  {'R2':>6s}  {'Persist':>8s}")
print("-" * 75)

for test_date in test_dates:
    train_mask = df['date_key'] < test_date
    test_mask = df['date_key'] == test_date

    X_tr = df.loc[train_mask, feat].fillna(0).values
    y_tr = df.loc[train_mask, 'da_target'].values
    X_te = df.loc[test_mask, feat].fillna(0).values
    y_te = df.loc[test_mask, 'da_target'].values

    valid = ~np.isnan(y_tr)
    X_tr, y_tr = X_tr[valid], y_tr[valid]
    if len(X_tr) < 48 or len(X_te) == 0:
        print(f"  SKIP {test_date}")
        continue

    # 注: 原"枯季权重"是对全体样本统一乘 1.5, 对任何模型拟合都无效果(均匀缩放),
    # 已移除。完整枯季回测验证: 全季无权重训练与原方案无显著差异 (DM p=0.061)。

    # GBR
    gbr = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                     subsample=0.8, min_samples_leaf=5, random_state=42)
    gbr.fit(X_tr, y_tr)
    p_gbr = gbr.predict(X_te)

    # LightGBM
    dtrain = lgb.Dataset(X_tr, y_tr)
    lgbm = lgb.train({'objective':'regression','metric':'mae','num_leaves':63,
                       'learning_rate':0.04,'feature_fraction':0.8,'bagging_fraction':0.85,
                       'bagging_freq':5,'verbose':-1,'seed':42},
                      dtrain, num_boost_round=300)
    p_lgb = lgbm.predict(X_te)

    # XGBoost
    xgb_model = xgb.XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42)
    xgb_model.fit(X_tr, y_tr, verbose=False)
    p_xgb = xgb_model.predict(X_te)

    # Ensemble: LGB 占主导 (DA预测中LGB通常最好)
    p_ens = 0.25 * p_gbr + 0.45 * p_lgb + 0.30 * p_xgb

    # 持久化对比
    p_persist = df.loc[test_mask, 'da_price'].values  # DA[D]

    # 自适应预测组合 (无泄漏: α 只用历史验证日挑选)
    _vmask = np.isfinite(y_te)
    if len(_blend_hist) >= BLEND_V:
        _r = _blend_hist[-BLEND_V:]
        _alpha = pick_blend_alpha(np.concatenate([h[0] for h in _r]),
                                  np.concatenate([h[1] for h in _r]),
                                  np.concatenate([h[2] for h in _r]))
    else:
        _alpha = BLEND_COLD
    p_blend = _alpha * p_ens + (1 - _alpha) * p_persist
    _blend_hist.append((y_te[_vmask], p_ens[_vmask], p_persist[_vmask]))

    mae_gbr = mean_absolute_error(y_te, p_gbr)
    mae_lgb = mean_absolute_error(y_te, p_lgb)
    mae_xgb = mean_absolute_error(y_te, p_xgb)
    mae_ens = mean_absolute_error(y_te, p_ens)
    mae_blend = mean_absolute_error(y_te, p_blend)
    mae_persist = mean_absolute_error(y_te, p_persist)
    r2_ens = r2_score(y_te, p_ens)

    results.append({
        'date': test_date,
        'actual': y_te.copy(),
        'pred': p_ens.copy(),
        'blend': p_blend.copy(),
        'persist': p_persist.copy(),
        'alpha': _alpha,
        'hour': df.loc[test_mask, 'hour'].values.copy(),
        'mae_gbr': mae_gbr, 'mae_lgb': mae_lgb, 'mae_xgb': mae_xgb,
        'mae_ens': mae_ens, 'mae_blend': mae_blend, 'mae_persist': mae_persist, 'r2': r2_ens,
    })

    print(f"  {test_date}: {mae_gbr:6.1f} {mae_lgb:6.1f} {mae_xgb:6.1f} {mae_ens:8.1f} {r2_ens:6.3f} {mae_persist:8.1f}")

# ============================================================
# 5. 汇总和图表
# ============================================================
print(f"\n{'='*80}")
print("SUMMARY - 次日前电价预测 (P5)")
print(f"{'='*80}")
print(f"{'Date':>10s}  {'GBR':>6s}  {'LGB':>6s}  {'XGB':>6s}  {'Ensemble':>8s}  {'R2':>6s}  {'Persist':>8s}")
print("-" * 75)
for r in results:
    print(f"{r['date']:>10s}  {r['mae_gbr']:6.1f}  {r['mae_lgb']:6.1f}  {r['mae_xgb']:6.1f}  {r['mae_ens']:8.1f}  {r['r2']:6.3f}  {r['mae_persist']:8.1f}")

avgs = {k: np.mean([r[k] for r in results]) for k in ['mae_gbr','mae_lgb','mae_xgb','mae_ens','mae_persist']}
print("-" * 75)
print(f"{'Avg':>10s}  {avgs['mae_gbr']:6.1f}  {avgs['mae_lgb']:6.1f}  {avgs['mae_xgb']:6.1f}  {avgs['mae_ens']:8.1f}  {'':>6s}  {avgs['mae_persist']:8.1f}")

# 目标对比
target = avgs['mae_ens']
print(f"\n目标: MAE ≤45 ¥/MWh", flush=True)
if target <= 45:
    print(f"  ✅ 达成! Ensemble MAE={target:.1f} ≤ 45", flush=True)
else:
    print(f"  ❌ 未达标: Ensemble MAE={target:.1f} > 45, 差 {target-45:.1f}", flush=True)
print(f"  vs 持久化基线: {avgs['mae_persist']:.1f}", flush=True)

# ── 相对指标 + 显著性检验 (评估地基) ──
# 裸 MAE 不可跨季节/节点比较, 且"赢一点"可能在噪声内。用 rMAE(相对persistence) +
# Diebold-Mariano 检验, 判断 Ensemble 是否"统计显著地"赢过朴素基准。
_act = np.concatenate([r['actual'] for r in results])
_prd = np.concatenate([r['pred'] for r in results])
_bld = np.concatenate([r['blend'] for r in results])
_per = np.concatenate([r['persist'] for r in results])
_m = np.isfinite(_act) & np.isfinite(_prd) & np.isfinite(_per) & np.isfinite(_bld)
_act, _prd, _bld, _per = _act[_m], _prd[_m], _bld[_m], _per[_m]

def _report(name, pred, ref, ref_name):
    r = rmae(_act, pred, _per)
    stat, p = diebold_mariano(_act - ref, _act - pred)   # stat>0 => pred 更优
    sig = "显著" if p < 0.05 else "不显著(噪声内)"
    flag = '✅<1 胜基准' if r < 1 else '❌≥1 不如基准'
    print(f"  {name:<22} rMAE={r:.3f} ({flag}) | DM vs {ref_name}: {stat:+.2f}, p={p:.3f} {sig}", flush=True)

print(f"\n  组合权重 α 均值 = {np.mean([r['alpha'] for r in results]):.2f}  "
      f"(Blend = α·Ensemble + (1-α)·Persistence)", flush=True)
print(f"  Blend MAE={mean_absolute_error(_act, _bld):.1f} vs Ensemble MAE={mean_absolute_error(_act, _prd):.1f} "
      f"vs Persist MAE={mean_absolute_error(_act, _per):.1f}", flush=True)
_report("Ensemble", _prd, _per, "Persist")
_report("Blend(最终)", _bld, _per, "Persist")
_report("Blend vs Ensemble", _bld, _prd, "Ensemble")

# 图表
print("\n[5/5] Chart...", flush=True)
n_res = len(results)
n_rows = (n_res+1)//2
fig, axes = plt.subplots(n_rows, 2, figsize=(20, 4.5*n_rows+1))
fig.suptitle('P5 次日前电价预测 (DA[D+1]) - GBR+LGB+XGB Ensemble', fontsize=14, fontweight='bold')

for i, res in enumerate(results):
    ax = axes.flatten()[i]
    order = np.argsort(res['hour'])
    actual = res['actual'][order]
    pred = res['pred'][order]
    persist = res['persist'][order]
    x = np.arange(24)

    ax.plot(x, actual, 'b-o', ms=5, lw=2.5, label='Actual DA', zorder=4)
    ax.plot(x, pred, 'r--s', ms=4, lw=2, label='Predicted', zorder=3)
    ax.plot(x, persist, 'g:', lw=1.5, alpha=0.5, label='Persist(DA[D])', zorder=2)

    mae = res['mae_ens']
    ax.fill_between(x, np.minimum(actual,pred), np.maximum(actual,pred),
                    alpha=0.12, color='red')
    ax.set_xticks(range(0,24,3))
    ax.set_xticklabels([f'{h:02d}:00' for h in range(0,24,3)])
    ax.set_xlim(-0.5,23.5)
    ax.set_ylabel('Price (¥/MWh)')
    ax.grid(True, alpha=0.3, ls='--')
    c = '#228B22' if mae<30 else ('#FF8C00' if mae<50 else '#DC143C')
    ax.set_title(f"2026-{res['date'][4:6]}-{res['date'][6:8]}  MAE={mae:.1f}  R²={res['r2']:.3f}  "
                 f"Persist={res['mae_persist']:.1f}", fontsize=11, fontweight='bold', color=c)
    ax.legend(fontsize=7, loc='upper left')

for j in range(n_res, len(axes.flatten())):
    axes.flatten()[j].set_visible(False)
plt.tight_layout(rect=[0,0,1,0.96])
chart_path = f'{OUT_DIR}/p5_da_predict.png'
plt.savefig(chart_path, dpi=150, bbox_inches='tight')
print(f"  Chart saved: {chart_path}", flush=True)

# 特征重要性
imp = sorted(zip(feat, gbr.feature_importances_), key=lambda x:-x[1])
print("\nTop 15 Feature Importance (GBR):")
for f_name, f_val in imp[:15]:
    print(f"  {f_name:30s} {f_val*100:5.2f}%")

print(f"\n{'✅ P5 Done!' if target <= 45 else '❌ Need improvement'}", flush=True)
