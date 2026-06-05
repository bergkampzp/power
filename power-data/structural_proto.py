#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最简结构模型原型: 净负荷供给曲线 (merit-order proxy)
=====================================================
没有真实聚合供给曲线数据时, 用"净负荷 = 负荷 − 新能源"作为结构变量, 拟合一条
单调递增的经验供给曲线 (保序回归), 编码 merit-order 经济先验。自由度极低, 半年够用。

口径一致性: 训练与预测都用"闸口可得的净负荷预测"(load_fc − renew_fc), 避免实际/预测偏差。
两个变体, 用 rMAE + DM 对比 persistence:
  S1 纯结构      : price = iso(net_load_fc)
  S2 结构形状+持久水平: 日级水平取前一日均值(水价代理), 日内形状取结构曲线
对照: persistence, 以及(参考)我们已知 GBDT rMAE≈0.93。
用法: python structural_proto.py
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
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import mean_absolute_error

from config import DB
from lear_baseline import load_da_hourly, load_forecast_gateclosure
from eval_framework import rmae, diebold_mariano

DRY_MONTHS = [11, 12, 1, 2, 3, 4]
TEST_START = "20251201"
TEST_END = "20260323"


def build():
    c = sqlite3.connect(DB)
    da = load_da_hourly(c)                                      # date_key,hour,da_price
    lf = load_forecast_gateclosure(c, 'load_forecast', 'forecast_load', 'trade_date')
    rf = load_forecast_gateclosure(c, 'renewable_forecast', 'forecast_mw', 'forecast_date')
    c.close()
    df = da.merge(lf, on=['date_key', 'hour'], how='left').merge(rf, on=['date_key', 'hour'], how='left')
    df['net_load_fc'] = df['forecast_load'] - df['forecast_mw']  # 闸口可得净负荷预测
    df = df.sort_values(['hour', 'date_key']).reset_index(drop=True)
    df['persist'] = df.groupby('hour')['da_price'].shift(1)     # DA[前一日, h]
    df['month'] = pd.to_datetime(df['date_key'], format='%Y%m%d', errors='coerce').dt.month
    # 前一日日级均值 (S2 的水平代理)
    daily = df.groupby('date_key')['da_price'].mean()
    dates = sorted(df['date_key'].unique())
    prevmap = {d: dates[i - 1] for i, d in enumerate(dates) if i > 0}
    df['prev_daily_level'] = df['date_key'].map(prevmap).map(daily)
    return df


def main():
    print("=" * 66)
    print("最简结构模型原型: 净负荷供给曲线 (完整枯季, DM检验)")
    print("=" * 66)
    df = build()
    vd = df.dropna(subset=['da_target'] if 'da_target' in df else ['da_price'])
    test_dates = sorted(df[(df['date_key'] >= TEST_START) & (df['date_key'] <= TEST_END)
                           & (df['month'].isin(DRY_MONTHS))]['date_key'].unique())
    print(f"测试窗口: {TEST_START}~{TEST_END} ({len(test_dates)}天)\n")

    cols = {k: [] for k in ['actual', 'persist', 's1', 's2']}
    skipped = 0
    for td in test_dates:
        tr = df[df['date_key'] < td].dropna(subset=['net_load_fc', 'da_price'])
        te = df[df['date_key'] == td]
        if len(tr) < 200 or len(te) == 0:
            skipped += 1
            continue
        iso = IsotonicRegression(out_of_bounds='clip').fit(tr['net_load_fc'].values, tr['da_price'].values)
        nlf = te['net_load_fc'].values
        actual = te['da_price'].values
        persist = te['persist'].values
        level = te['prev_daily_level'].values
        # 仅保留净负荷预测、实际、persistence、水平都可用的小时
        m = np.isfinite(nlf) & np.isfinite(actual) & np.isfinite(persist) & np.isfinite(level)
        if m.sum() == 0:
            skipped += 1
            continue
        s1 = iso.predict(nlf[m])                               # 纯结构
        shape = s1 - s1.mean()                                 # 日内形状(去日均)
        s2 = level[m] + shape                                  # 形状 + 前一日水平
        cols['actual'].append(actual[m]); cols['persist'].append(persist[m])
        cols['s1'].append(s1); cols['s2'].append(s2)
    R = {k: np.concatenate(v) for k, v in cols.items()}
    a, persist = R['actual'], R['persist']
    print(f"有效观测点: {len(a)} (跳过 {skipped} 天)\n")

    print(f"{'模型':<26}{'MAE':>8}{'rMAE':>8}")
    print("-" * 44)
    print(f"{'Persistence':<26}{mean_absolute_error(a, persist):>8.1f}{1.00:>8.2f}")
    for name, k in [('S1 纯结构(净负荷曲线)', 's1'), ('S2 结构形状+持久水平', 's2')]:
        print(f"{name:<26}{mean_absolute_error(a, R[k]):>8.1f}{rmae(a, R[k], persist):>8.2f}")

    print("\nDM 检验 (vs Persistence, stat>0 => 结构更优):")
    for name, k in [('S1 纯结构', 's1'), ('S2 形状+水平', 's2')]:
        stat, p = diebold_mariano(a - persist, a - R[k])
        win = name if stat > 0 else 'Persistence'
        sig = '显著' if p < 0.05 else '不显著'
        print(f"  {name:<12} vs Persistence: DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")

    # 诊断: 净负荷与电价的相关性 (结构信号强弱)
    diag = df.dropna(subset=['net_load_fc', 'da_price'])
    corr = np.corrcoef(diag['net_load_fc'], diag['da_price'])[0, 1]
    print(f"\n诊断: 净负荷 vs DA价 相关系数 = {corr:+.3f} "
          f"({'结构信号较强' if abs(corr) > 0.4 else '结构信号弱→水价/自回归主导'})")
    print("参考: GBDT 全特征 rMAE≈0.92-0.93")


if __name__ == "__main__":
    main()
