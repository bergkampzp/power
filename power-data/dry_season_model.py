#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
枯水期 DA 电价模型 + asinh VST 验证 (地基#2)
=============================================
项目数据以枯水期为主, 故先做枯季专用模型。本脚本在 DM 检验框架下回答:
  1. asinh 方差稳定变换(VST) 是否真的帮到 LEAR / GBDT ?
  2. 枯季专用训练 是否优于 全季混训 ?

数据/目标/特征复用 lear_baseline (DA[D+1], 闸口对齐, leakage-safe)。
枯季月份: 11,12,1,2,3,4。
用法: python dry_season_model.py
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
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from config import DB
from lear_baseline import build_frame, FEATURES
from eval_framework import rmae, diebold_mariano, asinh_params, asinh_fwd, asinh_inv

DRY_MONTHS = [11, 12, 1, 2, 3, 4]
# 完整枯季测试窗口 (最近一整个枯季)
TEST_START = "20251201"
TEST_END = "20260323"
LEAR_CV = 3   # LEAR 仅作参考基准, cv=3 以控制长窗口运行时长


def fit_lear(Xtr, ytr, Xte, use_vst):
    sc = StandardScaler().fit(Xtr)
    if use_vst:
        a, b = asinh_params(ytr)
        m = LassoCV(cv=LEAR_CV, max_iter=5000, n_jobs=-1, random_state=42)
        m.fit(sc.transform(Xtr), asinh_fwd(ytr, a, b))
        return asinh_inv(m.predict(sc.transform(Xte)), a, b)
    m = LassoCV(cv=LEAR_CV, max_iter=5000, n_jobs=-1, random_state=42)
    m.fit(sc.transform(Xtr), ytr)
    return m.predict(sc.transform(Xte))


def fit_gbdt(Xtr, ytr, Xte, use_vst):
    m = HistGradientBoostingRegressor(max_iter=300, max_depth=5,
                                      learning_rate=0.05, random_state=42)
    if use_vst:
        a, b = asinh_params(ytr)
        m.fit(Xtr, asinh_fwd(ytr, a, b))
        return asinh_inv(m.predict(Xte), a, b)
    m.fit(Xtr, ytr)
    return m.predict(Xte)


def run(df, feat, dry_train_only, test_dates):
    """walk-forward, 返回逐观测预测 dict。dry_train_only=True 时训练集只取枯季。"""
    cols = {k: [] for k in ['actual', 'persist', 'lear', 'lear_vst', 'gbdt', 'gbdt_vst']}
    for td in test_dates:
        tr = df[df['date_key'] < td]
        if dry_train_only:
            tr = tr[tr['month'].isin(DRY_MONTHS)]
        te = df[df['date_key'] == td]
        Xtr = tr[feat].fillna(0).values
        ytr = tr['da_target'].values
        ok = np.isfinite(ytr)
        Xtr, ytr = Xtr[ok], ytr[ok]
        if len(Xtr) < 48 or len(te) == 0:
            continue
        Xte = te[feat].fillna(0).values
        yte = te['da_target'].values
        persist = te['da_price'].values
        preds = {
            'lear': fit_lear(Xtr, ytr, Xte, False),
            'lear_vst': fit_lear(Xtr, ytr, Xte, True),
            'gbdt': fit_gbdt(Xtr, ytr, Xte, False),
            'gbdt_vst': fit_gbdt(Xtr, ytr, Xte, True),
        }
        m = np.isfinite(yte)
        cols['actual'].append(yte[m]); cols['persist'].append(persist[m])
        for k, v in preds.items():
            cols[k].append(np.asarray(v)[m])
    return {k: np.concatenate(v) for k, v in cols.items()}


def main():
    print("=" * 70)
    print("枯水期 DA 电价模型 + asinh VST 验证 (DA[D+1])")
    print("=" * 70)
    conn = sqlite3.connect(DB)
    df = build_frame(conn)
    conn.close()
    feat = [f for f in FEATURES if f in df.columns]

    # 训练数据规模 (枯季 vs 全季)
    n_all = df.dropna(subset=['da_target']).shape[0]
    n_dry = df.dropna(subset=['da_target'])
    n_dry = n_dry[n_dry['month'].isin(DRY_MONTHS)].shape[0]
    print(f"特征数: {len(feat)} | 全季样本: {n_all} | 枯季样本: {n_dry} "
          f"({100*n_dry/n_all:.0f}%)")

    # 测试集 = 完整枯季窗口内、属于枯季月份、且有有效目标的日期
    vd = df.dropna(subset=['da_target'])
    test_dates = sorted(vd[(vd['date_key'] >= TEST_START) & (vd['date_key'] <= TEST_END)
                           & (vd['month'].isin(DRY_MONTHS))]['date_key'].unique())
    print(f"测试窗口: {TEST_START}~{TEST_END} (枯季), 共 {len(test_dates)} 天, 逐日 walk-forward...\n")

    res = run(df, feat, dry_train_only=True, test_dates=test_dates)

    a = res['actual']; persist = res['persist']
    print(f"观测点: {len(a)}  [枯季专用训练]")
    mae_p = mean_absolute_error(a, persist)
    print(f"{'模型':<16}{'MAE':>8}{'rMAE':>8}   解读")
    print("-" * 58)
    print(f"{'Persistence':<16}{mae_p:>8.1f}{1.00:>8.2f}   朴素基准")
    order = [('LEAR', 'lear'), ('LEAR + asinh VST', 'lear_vst'),
             ('GBDT', 'gbdt'), ('GBDT + asinh VST', 'gbdt_vst')]
    for name, key in order:
        mae = mean_absolute_error(a, res[key])
        r = rmae(a, res[key], persist)
        flag = '✅赢基准' if r < 1 else '❌不如基准'
        print(f"{name:<16}{mae:>8.1f}{r:>8.2f}   {flag}")

    print("\nDM 检验 (loss=abs, stat>0 => 后者更优):")
    def dm(name_a, ka, name_b, kb):
        ea = a - res[ka]; eb = a - res[kb]
        stat, p = diebold_mariano(eb, ea)   # stat>0 => ka 模型更优
        win = name_a if stat > 0 else name_b
        sig = '显著' if p < 0.05 else '不显著'
        print(f"  {name_a:<18} vs {name_b:<14}: DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")
    dm('LEAR+VST', 'lear_vst', 'LEAR(raw)', 'lear')
    dm('GBDT+VST', 'gbdt_vst', 'GBDT(raw)', 'gbdt')

    # 枯季专用 vs 全季混训 (取各自最优 GBDT+VST)
    res_all = run(df, feat, dry_train_only=False, test_dates=test_dates)
    mae_dry = mean_absolute_error(a, res['gbdt_vst'])
    mae_allt = mean_absolute_error(res_all['actual'], res_all['gbdt_vst'])
    e_dry = a - res['gbdt_vst']
    e_all = res_all['actual'] - res_all['gbdt_vst']
    stat, p = diebold_mariano(e_all, e_dry)   # stat>0 => 枯季训练更优
    win = '枯季专用训练' if stat > 0 else '全季混训'
    sig = '显著' if p < 0.05 else '不显著'
    print("\n枯季专用训练 vs 全季混训 (均为 GBDT+VST):")
    print(f"  枯季训练 MAE={mae_dry:.1f} | 全季训练 MAE={mae_allt:.1f}")
    print(f"  DM={stat:+.2f} p={p:.3f} -> {win} 更优, {sig}")

    # GBDT 2x2 全景: {训练范围} x {是否VST}
    print("\nGBDT 配置 2x2 (MAE, 越低越好):")
    print(f"  {'':<12}{'raw':>10}{'+VST':>10}")
    print(f"  {'枯季训练':<12}{mean_absolute_error(a, res['gbdt']):>10.1f}"
          f"{mean_absolute_error(a, res['gbdt_vst']):>10.1f}")
    print(f"  {'全季训练':<12}{mean_absolute_error(res_all['actual'], res_all['gbdt']):>10.1f}"
          f"{mean_absolute_error(res_all['actual'], res_all['gbdt_vst']):>10.1f}")

    print("\n结论: rMAE<1 且 DM 显著, 才算真正改进。")


if __name__ == "__main__":
    main()
