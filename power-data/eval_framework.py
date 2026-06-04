#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电价预测评估框架 (EPF evaluation foundation)
=============================================
业界标准评估工具, 替代裸 MAE 比较:

  1. rmae()            : 相对 MAE (相对朴素基准), 跨季节/节点可比
  2. diebold_mariano() : DM 检验, 判断两个模型的精度差异是否统计显著

参考: Lago, Marcjasz, De Schutter, Weron (2021), Applied Energy,
      "Forecasting day-ahead electricity prices: A review of state-of-the-art
       algorithms, best practices and an open-access benchmark" (epftoolbox)。
DM 检验采用 Harvey-Leybourne-Newbold (1997) 小样本修正 + t 分布。
"""
from __future__ import annotations
import numpy as np
from scipy import stats


def asinh_params(y_train):
    """估计 asinh 方差稳定变换(VST)的中心/尺度参数 (仅用训练数据, 防泄漏)。

    采用稳健统计: 中心=中位数, 尺度=1.4826*MAD (对尖峰/零负价稳健)。
    参考 Lago et al. (2021): asinh VST 是 EPF 处理尖峰价格的最佳实践,
    且对负价/零价有定义 (log 变换不行)。
    """
    y = np.asarray(y_train, dtype=float)
    y = y[np.isfinite(y)]
    a = float(np.median(y))
    mad = float(np.median(np.abs(y - a)))
    b = 1.4826 * mad
    if not np.isfinite(b) or b <= 0:
        b = float(np.std(y))
    if not np.isfinite(b) or b <= 0:
        b = 1.0
    return a, b


def asinh_fwd(y, a, b):
    """正变换: z = arcsinh((y - a) / b)。压缩尖峰, 全实数域有定义。"""
    return np.arcsinh((np.asarray(y, dtype=float) - a) / b)


def asinh_inv(z, a, b):
    """逆变换: y = sinh(z) * b + a。与 asinh_fwd 严格互逆。"""
    return np.sinh(np.asarray(z, dtype=float)) * b + a


def pick_blend_alpha(val_actual, val_model, val_persist, alphas=None):
    """在验证集上挑选预测组合权重 α, 最小化 MAE(α*model + (1-α)*persist)。

    用于"噪声模型与朴素基准组合"(forecast combination)。仅用验证数据(过去),
    不碰测试点, 故无泄漏。返回 [0,1] 内的 α。
    """
    a = np.asarray(val_actual, dtype=float)
    m = np.asarray(val_model, dtype=float)
    p = np.asarray(val_persist, dtype=float)
    if alphas is None:
        alphas = np.round(np.arange(0.0, 1.01, 0.1), 2)
    best_a, best_e = 1.0, np.inf
    for al in alphas:
        e = np.mean(np.abs(a - (al * m + (1 - al) * p)))
        if e < best_e:
            best_e, best_a = e, float(al)
    return best_a


def _losses(err: np.ndarray, loss: str) -> np.ndarray:
    if loss == "abs":
        return np.abs(err)
    if loss == "sq":
        return err ** 2
    raise ValueError(f"unknown loss '{loss}', use 'abs' or 'sq'")


def rmae(actual, model_pred, naive_pred) -> float:
    """相对 MAE = MAE(model) / MAE(naive).

    <1  : 模型优于朴素基准 (越小越好)
    =1  : 与朴素基准持平
    >1  : 比朴素基准还差 (不应上线)

    朴素基准通常是 persistence (前值) 或季节性朴素。NaN 成对剔除。
    """
    actual = np.asarray(actual, dtype=float)
    model_pred = np.asarray(model_pred, dtype=float)
    naive_pred = np.asarray(naive_pred, dtype=float)
    mask = np.isfinite(actual) & np.isfinite(model_pred) & np.isfinite(naive_pred)
    a, m, n = actual[mask], model_pred[mask], naive_pred[mask]
    mae_model = np.mean(np.abs(a - m))
    mae_naive = np.mean(np.abs(a - n))
    if mae_naive == 0:
        return np.nan
    return float(mae_model / mae_naive)


def diebold_mariano(err1, err2, loss: str = "abs", h: int = 1):
    """Diebold-Mariano 检验: 两组预测误差精度是否有显著差异。

    参数
    ----
    err1, err2 : 两个模型的预测误差序列 (actual - pred), 同长度, 同顺序。
    loss       : 'abs' (MAE 导向) 或 'sq' (RMSE 导向)。
    h          : 预测步长 (用于长程方差的滞后阶数; 日前预测 h=1)。

    返回
    ----
    (stat, p_value)
      stat > 0  => model1 损失更大 => model2 更优。
      stat < 0  => model1 更优。
      p_value   <0.05 即差异统计显著。
    损失差恒为 0 (两序列相同) 时返回 (nan, 1.0)。NaN 成对剔除。
    """
    e1 = np.asarray(err1, dtype=float)
    e2 = np.asarray(err2, dtype=float)
    if e1.shape != e2.shape:
        raise ValueError("err1 and err2 must have the same shape")
    mask = np.isfinite(e1) & np.isfinite(e2)
    e1, e2 = e1[mask], e2[mask]
    n = e1.size
    if n < 2:
        return np.nan, np.nan

    d = _losses(e1, loss) - _losses(e2, loss)   # 损失差: >0 表示 model2 更优
    d_mean = d.mean()
    if np.allclose(d, 0.0):
        return np.nan, 1.0

    # 长程方差 (Newey-West, 截断至 h-1 阶自协方差)
    gamma0 = np.sum((d - d_mean) ** 2) / n
    lrv = gamma0
    for lag in range(1, h):
        cov = np.sum((d[lag:] - d_mean) * (d[:-lag] - d_mean)) / n
        lrv += 2.0 * (1.0 - lag / h) * cov
    var_dbar = lrv / n
    if var_dbar <= 0:
        return np.nan, 1.0

    dm = d_mean / np.sqrt(var_dbar)

    # Harvey-Leybourne-Newbold 小样本修正
    hln = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    dm_corr = dm * hln
    p = 2.0 * stats.t.cdf(-np.abs(dm_corr), df=n - 1)
    return float(dm_corr), float(p)
