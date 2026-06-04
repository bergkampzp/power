#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
枯季 DA 改进实验 #3: 与 persistence 的自适应组合 (forecast combination)
=====================================================================
动机: 模型仅胜 persistence ~6%, 且在平稳日"过冲"(预测大波动而实际接近昨日)。
预测组合是这种"噪声模型勉强胜朴素"情形的教科书解法。

blended = α·GBDT + (1-α)·persistence。
α 自适应、无泄漏: 每个测试日用此前 V 天的滚动验证误差挑选 α* (只用过去)。
冷启动(<V 天历史)用 α=0.7 先验。对照: 纯模型(α=1) 与固定 α 仅作诊断。

leakage-safe harness, 完整枯季, rMAE + DM。
用法: python dry_blend.py
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
ALPHAS = np.round(np.arange(0.0, 1.01, 0.1), 2)
V = 20            # 滚动验证天数
COLD_ALPHA = 0.7  # 冷启动先验


def gbdt():
    return HistGradientBoostingRegressor(max_iter=400, max_depth=5,
                                         learning_rate=0.05, random_state=42)


def pick_alpha(hist):
    """在过去 V 天上挑选使 MAE 最小的 α (只用历史, 无泄漏)。"""
    if len(hist) < V:
        return COLD_ALPHA
    recent = hist[-V:]
    act = np.concatenate([h['a'] for h in recent])
    mdl = np.concatenate([h['m'] for h in recent])
    per = np.concatenate([h['p'] for h in recent])
    best_a, best_e = 1.0, np.inf
    for al in ALPHAS:
        e = mean_absolute_error(act, al * mdl + (1 - al) * per)
        if e < best_e:
            best_e, best_a = e, al
    return best_a


def main():
    print("=" * 66)
    print("枯季 DA 改进实验 #3: 自适应 persistence 组合 (完整枯季, DM)")
    print("=" * 66)
    conn = sqlite3.connect(DB)
    df = build_frame(conn)
    conn.close()
    feat = [f for f in FEATURES if f in df.columns]
    vd = df.dropna(subset=['da_target'])
    test_dates = sorted(vd[(vd['date_key'] >= TEST_START) & (vd['date_key'] <= TEST_END)
                           & (vd['month'].isin(DRY_MONTHS))]['date_key'].unique())
    print(f"特征数: {len(feat)} | 测试窗口: {len(test_dates)}天 | 验证窗 V={V}\n")

    hist = []
    cols = {k: [] for k in ['actual', 'persist', 'model', 'blend', 'fix05', 'fix07']}
    alphas_used = []
    for td in test_dates:
        tr = df[df['date_key'] < td]
        te = df[df['date_key'] == td]
        ytr = tr['da_target'].values
        ok = np.isfinite(ytr)
        Xtr, ytr = tr[feat].fillna(0).values[ok], ytr[ok]
        if len(Xtr) < 48 or len(te) == 0:
            continue
        Xte = te[feat].fillna(0).values
        yte = te['da_target'].values
        persist = te['da_price'].values
        m = gbdt(); m.fit(Xtr, ytr); model = m.predict(Xte)

        al = pick_alpha(hist)
        alphas_used.append(al)
        blend = al * model + (1 - al) * persist

        mask = np.isfinite(yte)
        # 存历史供后续日挑 α (只含已知的真实值)
        hist.append({'a': yte[mask], 'm': model[mask], 'p': persist[mask]})
        cols['actual'].append(yte[mask]); cols['persist'].append(persist[mask])
        cols['model'].append(model[mask]); cols['blend'].append(blend[mask])
        cols['fix05'].append((0.5 * model + 0.5 * persist)[mask])
        cols['fix07'].append((0.7 * model + 0.3 * persist)[mask])
    R = {k: np.concatenate(v) for k, v in cols.items()}
    a, persist = R['actual'], R['persist']
    print(f"观测点: {len(a)} | α 自适应均值={np.mean(alphas_used):.2f} "
          f"(范围 {min(alphas_used):.1f}~{max(alphas_used):.1f})\n")

    print(f"{'模型':<26}{'MAE':>8}{'rMAE':>8}")
    print("-" * 44)
    print(f"{'Persistence':<26}{mean_absolute_error(a, persist):>8.1f}{1.00:>8.2f}")
    for name, k in [('纯GBDT (α=1, 基线)', 'model'),
                    ('自适应组合 (候选)', 'blend'),
                    ('固定 α=0.7 (诊断)', 'fix07'),
                    ('固定 α=0.5 (诊断)', 'fix05')]:
        print(f"{name:<26}{mean_absolute_error(a, R[k]):>8.1f}{rmae(a, R[k], persist):>8.2f}")

    print("\nDM 检验 (stat>0 => 后者更优):")
    for na, k in [('自适应组合', 'blend'), ('固定α=0.7', 'fix07'), ('固定α=0.5', 'fix05')]:
        stat, p = diebold_mariano(a - R['model'], a - R[k])
        win = na if stat > 0 else '纯GBDT基线'
        sig = '显著' if p < 0.05 else '不显著'
        print(f"  {na:<12} vs 纯GBDT基线: DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")

    print("\n注: 仅'自适应组合'是无泄漏候选; 固定α在测试集上选, 仅作上限诊断。")


if __name__ == "__main__":
    main()
