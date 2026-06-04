#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
枯季 DA 模型改进实验 (方向: L1损失 / 价差建模)
================================================
在 leakage-safe harness (lear_baseline.build_frame) 上、完整枯季 walk-forward,
用 rMAE + Diebold-Mariano 判断以下改动是否"统计显著"地改进基线:

  B0  GBDT-L2 (squared_error, 现状默认)        — 基线
  V1  GBDT-L1 (absolute_error, 直接优化MAE)     — 主假设
  V2  GBDT-L1 + 价差目标 (预测 ΔDA=DA[D+1]-DA[D], 加回DA[D])

胜者(若 DM 显著)回填 p5_da_predict.py。
用法: python dry_improve.py
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from config import DB
from lear_baseline import build_frame, FEATURES
from eval_framework import rmae, diebold_mariano

DRY_MONTHS = [11, 12, 1, 2, 3, 4]
TEST_START = "20251201"
TEST_END = "20260323"


def gbdt(loss):
    return HistGradientBoostingRegressor(max_iter=400, max_depth=5,
                                         learning_rate=0.05, loss=loss, random_state=42)


def main():
    print("=" * 66)
    print("枯季 DA 改进实验: L1损失 / 价差建模 (完整枯季, DM检验)")
    print("=" * 66)
    conn = sqlite3.connect(DB)
    df = build_frame(conn)
    conn.close()
    feat = [f for f in FEATURES if f in df.columns]

    vd = df.dropna(subset=['da_target'])
    test_dates = sorted(vd[(vd['date_key'] >= TEST_START) & (vd['date_key'] <= TEST_END)
                           & (vd['month'].isin(DRY_MONTHS))]['date_key'].unique())
    print(f"特征数: {len(feat)} | 测试窗口: {TEST_START}~{TEST_END} ({len(test_dates)}天)\n")

    cols = {k: [] for k in ['actual', 'persist', 'l2', 'l1', 'l1_spread']}
    for td in test_dates:
        tr = df[df['date_key'] < td]
        te = df[df['date_key'] == td]
        ytr = tr['da_target'].values
        ok = np.isfinite(ytr)
        Xtr = tr[feat].fillna(0).values[ok]
        ytr = ytr[ok]
        da_now_tr = tr['da_price'].values[ok]          # DA[D] = 价差建模的锚
        if len(Xtr) < 48 or len(te) == 0:
            continue
        Xte = te[feat].fillna(0).values
        yte = te['da_target'].values
        persist = te['da_price'].values                # DA[D] -> DA[D+1]

        m = gbdt('squared_error'); m.fit(Xtr, ytr); p_l2 = m.predict(Xte)
        m = gbdt('absolute_error'); m.fit(Xtr, ytr); p_l1 = m.predict(Xte)
        m = gbdt('absolute_error'); m.fit(Xtr, ytr - da_now_tr)
        p_sp = persist + m.predict(Xte)

        mask = np.isfinite(yte)
        cols['actual'].append(yte[mask]); cols['persist'].append(persist[mask])
        cols['l2'].append(p_l2[mask]); cols['l1'].append(p_l1[mask])
        cols['l1_spread'].append(p_sp[mask])
    R = {k: np.concatenate(v) for k, v in cols.items()}
    a, persist = R['actual'], R['persist']
    print(f"观测点: {len(a)}\n")

    print(f"{'模型':<22}{'MAE':>8}{'rMAE':>8}")
    print("-" * 40)
    print(f"{'Persistence':<22}{mean_absolute_error(a, persist):>8.1f}{1.00:>8.2f}")
    for name, key in [('B0 GBDT-L2 (基线)', 'l2'), ('V1 GBDT-L1', 'l1'),
                      ('V2 GBDT-L1 + 价差', 'l1_spread')]:
        print(f"{name:<22}{mean_absolute_error(a, R[key]):>8.1f}{rmae(a, R[key], persist):>8.2f}")

    print("\nDM 检验 (stat>0 => 后者更优):")
    def dm(na, ka, nb, kb):
        stat, p = diebold_mariano(a - R[kb], a - R[ka])   # stat>0 => ka 更优
        win = na if stat > 0 else nb
        sig = '显著' if p < 0.05 else '不显著'
        print(f"  {na:<14} vs {nb:<14}: DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")
    dm('L1', 'l1', 'L2(基线)', 'l2')
    dm('L1+价差', 'l1_spread', 'L2(基线)', 'l2')
    dm('L1+价差', 'l1_spread', 'L1', 'l1')

    print("\n结论: 相对基线 L2, rMAE 更低且 DM 显著者才算真改进, 回填 P5。")


if __name__ == "__main__":
    main()
