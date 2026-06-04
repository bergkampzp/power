#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
枯季 DA 改进实验 #2: 标定窗口 (calibration window)
==================================================
EPF 最经典的超参数。检验"用全部历史(expanding) vs 仅最近N天 vs 仅同节点定义(__all_avg__)
回归口径"哪个更好。动机: 旧数据跨了不同节点定义(__avg__拼接)与更早市场, 可能拖累。

leakage-safe harness, 完整枯季 walk-forward, L2 GBDT 固定, 只变训练窗口。
rMAE + DM 检验各窗口 vs expanding 基线。
用法: python dry_window.py
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

DRY_MONTHS = [11, 12, 1, 2, 3, 4]
TEST_START = "20251201"
TEST_END = "20260323"
WINDOWS = [None, 180, 120, 90]   # None = expanding(全部)


def gbdt():
    return HistGradientBoostingRegressor(max_iter=400, max_depth=5,
                                         learning_rate=0.05, random_state=42)


def main():
    print("=" * 66)
    print("枯季 DA 改进实验 #2: 标定窗口 (完整枯季, DM检验)")
    print("=" * 66)
    conn = sqlite3.connect(DB)
    df = build_frame(conn)
    conn.close()
    feat = [f for f in FEATURES if f in df.columns]
    df['dt'] = pd.to_datetime(df['date_key'], format='%Y%m%d', errors='coerce')

    vd = df.dropna(subset=['da_target'])
    test_dates = sorted(vd[(vd['date_key'] >= TEST_START) & (vd['date_key'] <= TEST_END)
                           & (vd['month'].isin(DRY_MONTHS))]['date_key'].unique())
    print(f"特征数: {len(feat)} | 测试窗口: {TEST_START}~{TEST_END} ({len(test_dates)}天)\n")

    keys = [f"w{w}" if w else "expanding" for w in WINDOWS] + ["regime"]
    cols = {k: [] for k in ['actual', 'persist'] + keys}
    for td in test_dates:
        base = df[df['date_key'] < td]
        te = df[df['date_key'] == td]
        if len(te) == 0:
            continue
        Xte = te[feat].fillna(0).values
        yte = te['da_target'].values
        persist = te['da_price'].values
        td_dt = pd.to_datetime(td, format='%Y%m%d')

        def fit_predict(tr):
            ytr = tr['da_target'].values
            ok = np.isfinite(ytr)
            Xtr, ytr = tr[feat].fillna(0).values[ok], ytr[ok]
            if len(Xtr) < 48:
                return None
            m = gbdt(); m.fit(Xtr, ytr)
            return m.predict(Xte)

        preds = {}
        for w, k in zip(WINDOWS, keys[:len(WINDOWS)]):
            tr = base if w is None else base[base['dt'] >= td_dt - pd.Timedelta(days=w)]
            preds[k] = fit_predict(tr)
        preds['regime'] = fit_predict(base[base['is_all_avg'] == 1])

        if any(p is None for p in preds.values()):
            continue
        mask = np.isfinite(yte)
        cols['actual'].append(yte[mask]); cols['persist'].append(persist[mask])
        for k in keys:
            cols[k].append(preds[k][mask])
    R = {k: np.concatenate(v) for k, v in cols.items()}
    a, persist = R['actual'], R['persist']
    print(f"观测点: {len(a)}\n")

    print(f"{'训练窗口':<18}{'MAE':>8}{'rMAE':>8}")
    print("-" * 36)
    print(f"{'Persistence':<18}{mean_absolute_error(a, persist):>8.1f}{1.00:>8.2f}")
    labels = {'expanding': 'expanding(全部)', 'w180': '最近180天', 'w120': '最近120天',
              'w90': '最近90天', 'regime': '仅__all_avg__口径'}
    for k in keys:
        print(f"{labels[k]:<18}{mean_absolute_error(a, R[k]):>8.1f}{rmae(a, R[k], persist):>8.2f}")

    print("\nDM 检验 (各窗口 vs expanding基线, stat>0 => 该窗口更优):")
    for k in keys:
        if k == 'expanding':
            continue
        stat, p = diebold_mariano(a - R['expanding'], a - R[k])
        win = labels[k] if stat > 0 else 'expanding'
        sig = '显著' if p < 0.05 else '不显著'
        print(f"  {labels[k]:<16} vs expanding: DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")

    print("\n结论: rMAE 更低且 DM 显著者才算真改进, 回填 P5。")


if __name__ == "__main__":
    main()
