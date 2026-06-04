#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for eval_framework: rMAE and Diebold-Mariano test.
Run:  python -m pytest test_eval_framework.py -q   (or: python test_eval_framework.py)
"""
import numpy as np
from eval_framework import (rmae, diebold_mariano, asinh_params, asinh_fwd, asinh_inv,
                            pick_blend_alpha)


def test_rmae_basic():
    actual = np.array([10.0, 20.0, 30.0, 40.0])
    naive = np.array([12.0, 18.0, 33.0, 36.0])   # abs err = [2,2,3,4] -> MAE 2.75
    model = np.array([11.0, 19.0, 31.0, 41.0])   # abs err = [1,1,1,1] -> MAE 1.0
    r = rmae(actual, model, naive)
    assert abs(r - (1.0 / 2.75)) < 1e-9
    assert r < 1.0  # model beats naive


def test_rmae_equal_to_naive_is_one():
    actual = np.array([1.0, 2.0, 3.0])
    naive = np.array([1.5, 2.5, 2.0])
    r = rmae(actual, naive, naive)
    assert abs(r - 1.0) < 1e-9


def test_dm_model_strictly_better_is_significant():
    # model2 error is uniformly half of model1 error -> model2 clearly better
    rng = np.random.default_rng(0)
    e1 = rng.normal(0, 10, 200)
    e2 = e1 * 0.5
    stat, p = diebold_mariano(e1, e2, loss="abs")
    # positive stat => loss1 > loss2 => second model better
    assert stat > 0
    assert p < 0.05


def test_dm_is_antisymmetric():
    rng = np.random.default_rng(1)
    e1 = rng.normal(0, 5, 150)
    e2 = rng.normal(0, 5, 150)
    s_ab, _ = diebold_mariano(e1, e2)
    s_ba, _ = diebold_mariano(e2, e1)
    assert abs(s_ab + s_ba) < 1e-9


def test_dm_identical_forecasts_not_significant():
    e = np.array([1.0, -2.0, 3.0, -1.0, 0.5])
    stat, p = diebold_mariano(e, e.copy())
    # zero loss differential -> no evidence of difference
    assert np.isnan(stat) or abs(stat) < 1e-9
    assert p == 1.0 or np.isnan(p)


def test_dm_handles_nan_pairwise():
    e1 = np.array([1.0, np.nan, 3.0, 4.0])
    e2 = np.array([0.5, 1.0, np.nan, 2.0])
    # only indices 0 and 3 are valid in both
    stat, p = diebold_mariano(e1, e2, loss="abs")
    assert np.isfinite(stat)


def test_asinh_round_trip_is_identity():
    y = np.array([0.0, 50.0, 200.0, -30.0, 1000.0, 12.5])
    a, b = asinh_params(y)
    z = asinh_fwd(y, a, b)
    back = asinh_inv(z, a, b)
    assert np.allclose(back, y, atol=1e-9)


def test_asinh_handles_negative_and_zero_prices():
    # 负价/零价是中国现货真实信号; asinh 对全体实数有定义 (log 不行)
    y = np.array([-100.0, -1.0, 0.0, 1.0, 100.0])
    a, b = asinh_params(y)
    z = asinh_fwd(y, a, b)
    assert np.all(np.isfinite(z))
    # 单调: 价格越高变换值越大
    assert np.all(np.diff(z) > 0)


def test_asinh_params_robust_to_outliers():
    # 中位数/MAD 不被尖峰拉偏
    y = np.array([100.0] * 50 + [9999.0])
    a, b = asinh_params(y)
    assert abs(a - 100.0) < 1e-9
    assert b >= 0


def test_asinh_params_constant_series_safe_scale():
    y = np.array([200.0] * 10)
    a, b = asinh_params(y)
    assert b > 0  # 不能除以 0


def test_pick_blend_alpha_prefers_model_when_model_perfect():
    actual = np.array([10.0, 20.0, 30.0, 40.0])
    model = actual.copy()
    persist = np.array([5.0, 25.0, 20.0, 50.0])
    assert pick_blend_alpha(actual, model, persist) == 1.0


def test_pick_blend_alpha_prefers_persist_when_persist_perfect():
    actual = np.array([10.0, 20.0, 30.0, 40.0])
    persist = actual.copy()
    model = np.array([5.0, 25.0, 20.0, 50.0])
    assert pick_blend_alpha(actual, model, persist) == 0.0


def test_pick_blend_alpha_in_range_and_reduces_error():
    rng = np.random.default_rng(3)
    actual = rng.normal(100, 20, 100)
    model = actual + rng.normal(0, 15, 100)     # noisy
    persist = actual + rng.normal(0, 15, 100)   # noisy, independent
    al = pick_blend_alpha(actual, model, persist)
    assert 0.0 <= al <= 1.0
    # blend should be no worse than the better single forecast
    from sklearn.metrics import mean_absolute_error
    blend_mae = mean_absolute_error(actual, al * model + (1 - al) * persist)
    assert blend_mae <= min(mean_absolute_error(actual, model),
                            mean_absolute_error(actual, persist)) + 1e-9


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
