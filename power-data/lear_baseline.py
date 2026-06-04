#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LEAR 强基准 + rMAE/DM 评估 (地基#1)
===================================
回答评审核心问题: 我们的 GBDT 模型, 究竟有没有"统计显著地"赢过
  (a) persistence 朴素基准, 以及
  (b) 一个简单的线性强基准 LEAR (LASSO-ARX) ?

数据/目标与 p5_da_predict.py 完全一致 (DA[D+1], __avg__+__all_avg__ 拼接),
但特征严格做到报价闸口可得 (leakage-safe): 预测特征按 publish_date < trade_date 对齐。

输出: 每个模型的 MAE / rMAE(相对persistence) / DM检验 p 值。
用法: python lear_baseline.py
"""
import warnings
warnings.filterwarnings("ignore")
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import sqlite3
import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import HistGradientBoostingRegressor

from config import DB
from eval_framework import rmae, diebold_mariano

N_TEST_DAYS = 10


def load_da_hourly(conn):
    """日前电价小时序列 (与 p5 相同: __avg__ + __all_avg__ 拼接)。"""
    da = pd.read_sql("""
        SELECT trade_date, period, price, node_name
        FROM day_ahead_node_price_96
        WHERE node_name IN ('__avg__', '__all_avg__')
    """, conn)
    da['date_key'] = da['trade_date'].str.replace('-', '')
    da['hour'] = da['period'].str[:2].astype(int)
    da['is_all_avg'] = (da['node_name'] == '__all_avg__').astype(int)
    return da.groupby(['date_key', 'hour']).agg(
        da_price=('price', 'mean'), is_all_avg=('is_all_avg', 'max')
    ).reset_index()


def load_rt_hourly(conn):
    rt = pd.read_sql("""
        SELECT REPLACE(trade_date,'-','') date_key, period, price rt_price
        FROM realtime_node_price_96 WHERE node_name='__avg__'
    """, conn)
    rt['hour'] = rt['period'].str[:2].astype(int)
    return rt.groupby(['date_key', 'hour']).agg(rt_price=('rt_price', 'mean')).reset_index()


def load_forecast_gateclosure(conn, table, value_col, trade_col):
    """读取预测并做闸口对齐: 对每个 (trade_date, hour) 取 publish_date 严格早于
    trade_date 的、最新一次发布 (= 报价时真实可得的日前预测)。返回 date_key/hour/<value>。"""
    df = pd.read_sql(f"""
        SELECT {trade_col} AS td, publish_date AS pub, period, {value_col} AS val
        FROM {table} WHERE region='云南'
    """, conn) if table == 'load_forecast' else pd.read_sql(f"""
        SELECT {trade_col} AS td, publish_date AS pub, period, {value_col} AS val
        FROM {table} WHERE region='云南' AND category='总计'
    """, conn)
    df['hour'] = df['period'].str[:2].astype(int)
    # 闸口约束: 发布日 < 交易日
    df = df[df['pub'].str.replace('-', '') < df['td'].str.replace('-', '')]
    if df.empty:
        return pd.DataFrame(columns=['date_key', 'hour', value_col])
    # 每个(交易日,小时)取最新发布
    df = df.sort_values('pub').groupby(['td', 'hour'], as_index=False).agg(
        val=('val', 'last'))
    df['date_key'] = df['td'].str.replace('-', '')
    return df.rename(columns={'val': value_col})[['date_key', 'hour', value_col]]


def build_frame(conn):
    da = load_da_hourly(conn)
    rt = load_rt_hourly(conn)
    df = da.merge(rt, on=['date_key', 'hour'], how='left')

    # 目标: DA[D+1] (与 p5 一致)
    df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)
    df['da_target'] = df.groupby('hour')['da_price'].shift(-1)
    # 目标交易日 (用于对齐"为次日发布"的预测)
    df['target_date'] = df.groupby('hour')['date_key'].shift(-1)

    # ── 价格 lag (闸口可得) ──
    # 预测 DA[D+1] 时, DA[D] 已于前一日出清, 故 da_price(=D) 可用; RT 保守用 D-1 及更早
    for n in [0, 1, 2, 6]:                       # 相对 D 的滞后 => 相对目标 D+1 的 lag1,2,3,7
        df[f'da_lag_{n+1}'] = df.groupby('hour')['da_price'].shift(n)
    for w in [3, 7]:
        df[f'da_ma_{w}'] = df.groupby('hour')['da_price'].transform(
            lambda x: x.rolling(w, min_periods=1).mean())
    for n in [1, 2]:                             # RT[D-1], RT[D-2]
        df[f'rt_lag_{n+1}'] = df.groupby('hour')['rt_price'].shift(n)

    # ── 日历 (目标日) ──
    tdate = pd.to_datetime(df['target_date'], format='%Y%m%d', errors='coerce')
    df['dow'] = tdate.dt.dayofweek
    for d in range(7):
        df[f'dow_{d}'] = (df['dow'] == d).astype(int)
    df['month'] = tdate.dt.month
    df['is_wet'] = df['month'].isin([6, 7, 8, 9, 10]).astype(int)

    # ── 预测特征 (闸口对齐, 按目标交易日 merge) ──
    load_fc = load_forecast_gateclosure(conn, 'load_forecast', 'forecast_load', 'trade_date')
    renew_fc = load_forecast_gateclosure(conn, 'renewable_forecast', 'forecast_mw', 'forecast_date')
    for fc, col in [(load_fc, 'forecast_load'), (renew_fc, 'forecast_mw')]:
        fc = fc.rename(columns={'date_key': 'target_date'})
        df = df.merge(fc, on=['target_date', 'hour'], how='left')

    return df


FEATURES = (['da_lag_1', 'da_lag_2', 'da_lag_3', 'da_lag_7', 'da_ma_3', 'da_ma_7',
             'rt_lag_2', 'rt_lag_3', 'is_all_avg', 'is_wet'] +
            [f'dow_{d}' for d in range(7)] + ['forecast_load', 'forecast_mw'])


def main():
    print("=" * 68)
    print("LEAR 强基准 + rMAE/DM 评估 — 与 p5 同数据同目标 (DA[D+1])")
    print("=" * 68)
    conn = sqlite3.connect(DB)
    df = build_frame(conn)
    conn.close()

    feat = [f for f in FEATURES if f in df.columns]
    print(f"特征数: {len(feat)} (leakage-safe, 闸口对齐)")

    valid_dates = sorted(df.dropna(subset=['da_target'])['date_key'].unique())
    test_dates = valid_dates[-N_TEST_DAYS:]
    print(f"测试期: {test_dates[0]} ~ {test_dates[-1]} ({len(test_dates)}天, walk-forward)\n")

    rows = []   # 逐观测: actual / persist / lear / lgbm
    for td in test_dates:
        tr = df[df['date_key'] < td]
        te = df[df['date_key'] == td]
        Xtr = tr[feat].fillna(0).values
        ytr = tr['da_target'].values
        ok = np.isfinite(ytr)
        Xtr, ytr = Xtr[ok], ytr[ok]
        if len(Xtr) < 48 or len(te) == 0:
            continue
        Xte = te[feat].fillna(0).values
        yte = te['da_target'].values
        persist = te['da_price'].values            # DA[D] -> DA[D+1]

        # LEAR: 标准化 + LASSO(CV alpha)
        sc = StandardScaler().fit(Xtr)
        lear = LassoCV(cv=5, max_iter=5000, n_jobs=-1, random_state=42)
        lear.fit(sc.transform(Xtr), ytr)
        p_lear = lear.predict(sc.transform(Xte))

        # GBDT: 同特征 (代表项目 GBDT 家族, 用 sklearn HistGBR)
        lgbm = HistGradientBoostingRegressor(max_iter=300, max_depth=5,
                                             learning_rate=0.05, random_state=42)
        lgbm.fit(Xtr, ytr)
        p_lgbm = lgbm.predict(Xte)

        for i in range(len(yte)):
            if np.isfinite(yte[i]):
                rows.append((yte[i], persist[i], p_lear[i], p_lgbm[i]))

    R = np.array(rows)
    actual, persist, lear_p, lgbm_p = R[:, 0], R[:, 1], R[:, 2], R[:, 3]
    print(f"有效观测点: {len(R)}\n")

    def report(name, pred):
        mae = mean_absolute_error(actual, pred)
        r = rmae(actual, pred, persist)
        return mae, r

    mae_p = mean_absolute_error(actual, persist)
    print(f"{'模型':<14}{'MAE':>9}{'rMAE':>9}   解读")
    print("-" * 60)
    print(f"{'Persistence':<14}{mae_p:>9.1f}{1.0:>9.2f}   朴素基准 (rMAE 定义为 1.0)")
    for name, pred in [('LEAR(LASSO)', lear_p), ('LightGBM', lgbm_p)]:
        mae, r = report(name, pred)
        flag = '✅赢基准' if r < 1 else '❌不如基准'
        print(f"{name:<14}{mae:>9.1f}{r:>9.2f}   {flag}")

    # DM 显著性
    e_p = actual - persist
    e_lear = actual - lear_p
    e_lgbm = actual - lgbm_p
    print("\nDiebold-Mariano 检验 (loss=abs, h=1):")
    for a_name, ea, b_name, eb in [
        ('LEAR', e_lear, 'Persistence', e_p),
        ('LightGBM', e_lgbm, 'Persistence', e_p),
        ('LightGBM', e_lgbm, 'LEAR', e_lear),
    ]:
        stat, p = diebold_mariano(eb, ea)   # stat>0 => 第二个(ea对应模型)更优
        better = a_name if stat > 0 else b_name
        sig = '显著' if p < 0.05 else '不显著(噪声内)'
        print(f"  {a_name:>9} vs {b_name:<11}: DM={stat:+.2f}  p={p:.3f}  "
              f"-> {better} 更优, {sig}")

    print("\n结论: rMAE<1 且 DM 显著, 才算真正赢过基准。")


if __name__ == "__main__":
    main()
