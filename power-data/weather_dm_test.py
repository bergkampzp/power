#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天气预报特征增量 DM 检验
=========================
把 leakage-safe 次日天气预报(全省装机加权 GHI / wind100 / 温度 / 云)按"目标交易日"接进
harness, 用 rMAE + Diebold-Mariano 判断"加天气特征"相对基线 GBDT 是否统计显著改进。
gate-legal: weather_forecast.publish_date < forecast_date(=目标日)。
用法: python weather_dm_test.py
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from config import DB
from lear_baseline import build_frame, FEATURES
from eval_framework import rmae, diebold_mariano
from weather_forecast_fetch import CITIES

DRY_MONTHS = [11, 12, 1, 2, 3, 4]
TEST_START = "20251201"
TEST_END = "20260323"
WX = ['ghi_prov', 'wind100_prov', 'temp_prov', 'cloud_prov']


def province_weather(conn):
    df = pd.read_sql("SELECT * FROM weather_forecast", conn)
    if df.empty:
        return pd.DataFrame(columns=['target_date', 'hour'] + WX)
    sw = {c: v[2] for c, v in CITIES.items()}
    ww = {c: v[3] for c, v in CITIES.items()}
    df['sw'] = df['city'].map(sw).fillna(0.0)
    df['ww'] = df['city'].map(ww).fillna(0.0)

    def wavg(x, val, wt):
        s = x[wt].sum()
        return (x[val] * x[wt]).sum() / s if s else x[val].mean()
    out = df.groupby(['forecast_date', 'hour']).apply(lambda x: pd.Series({
        'ghi_prov': wavg(x, 'ghi', 'sw'),
        'wind100_prov': wavg(x, 'wind100', 'ww'),
        'temp_prov': x['temp'].mean(),
        'cloud_prov': x['cloud'].mean(),
    })).reset_index().rename(columns={'forecast_date': 'target_date'})
    out['target_date'] = out['target_date'].astype(str)
    return out


def gbdt():
    return HistGradientBoostingRegressor(max_iter=400, max_depth=5,
                                         learning_rate=0.05, random_state=42)


def main():
    print("=" * 64)
    print("天气预报特征增量 DM 检验 (完整枯季)")
    print("=" * 64)
    conn = sqlite3.connect(DB)
    df = build_frame(conn)
    wx = province_weather(conn)
    conn.close()
    df = df.merge(wx, on=['target_date', 'hour'], how='left')

    base = [f for f in FEATURES if f in df.columns]
    wxf = [f for f in WX if f in df.columns]

    test_dates = sorted(df.dropna(subset=['da_target'])
                        .query("date_key>=@TEST_START and date_key<=@TEST_END")
                        .loc[lambda d: d['month'].isin(DRY_MONTHS), 'date_key'].unique())
    # 覆盖率只在"实际测试行"上算 (按目标交易日), 不掺入范围外历史
    cov = (df[df['date_key'].isin(test_dates)]['ghi_prov'].notna().mean() * 100
           if 'ghi_prov' in df.columns else 0)
    print(f"基线特征 {len(base)} | 天气特征 {len(wxf)}: {wxf}")
    print(f"测试窗口: {len(test_dates)}天 | 测试行天气覆盖率 {cov:.0f}%\n")

    cols = {k: [] for k in ['actual', 'persist', 'm_base', 'm_wx']}
    for td in test_dates:
        tr = df[df['date_key'] < td]
        te = df[df['date_key'] == td]
        ytr = tr['da_target'].values
        ok = np.isfinite(ytr)
        if ok.sum() < 200 or len(te) == 0:
            continue
        yte = te['da_target'].values
        m = np.isfinite(yte)
        persist = te['da_price'].values
        for name, feats in [('m_base', base), ('m_wx', base + wxf)]:
            g = gbdt(); g.fit(tr[feats].fillna(0).values[ok], ytr[ok])
            cols[name].append(g.predict(te[feats].fillna(0).values)[m])
        cols['actual'].append(yte[m]); cols['persist'].append(persist[m])
    R = {k: np.concatenate(v) for k, v in cols.items()}
    a, persist = R['actual'], R['persist']
    print(f"观测点: {len(a)}\n")

    print(f"{'模型':<22}{'MAE':>8}{'rMAE':>8}")
    print("-" * 40)
    print(f"{'Persistence':<22}{mean_absolute_error(a, persist):>8.1f}{1.00:>8.2f}")
    for name, k in [('GBDT 基线', 'm_base'), ('GBDT + 天气预报', 'm_wx')]:
        print(f"{name:<22}{mean_absolute_error(a, R[k]):>8.1f}{rmae(a, R[k], persist):>8.2f}")

    stat, p = diebold_mariano(a - R['m_base'], a - R['m_wx'])  # stat>0 => 加天气更优
    win = '加天气' if stat > 0 else '基线'
    sig = '显著' if p < 0.05 else '不显著(噪声内)'
    print(f"\nDM: 加天气 vs 基线: DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")
    print("结论: rMAE 更低且 DM 显著, 天气特征才算真增量。")


if __name__ == "__main__":
    main()
