#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for holiday_calendar. Run: python test_holiday_calendar.py"""
import numpy as np
from holiday_calendar import holiday_features


def _row(df, dk):
    return df[df['date_key'] == dk].iloc[0]


def test_official_holiday_flagged():
    df = holiday_features(['20260217'])           # 2026 春节
    r = _row(df, '20260217')
    assert r['is_holiday'] == 1
    assert r['is_workday'] == 0
    assert r['is_offday'] == 1


def test_plain_weekday_is_workday():
    df = holiday_features(['20260304'])           # 周三, 非节假日
    r = _row(df, '20260304')
    assert r['is_workday'] == 1
    assert r['is_holiday'] == 0
    assert r['is_offday'] == 0
    assert r['is_adjusted_workday'] == 0


def test_plain_weekend_is_offday():
    df = holiday_features(['20250713'])           # 周日, 7月无节假日/调休, 确定为休息日
    r = _row(df, '20250713')
    assert r['is_workday'] == 0
    assert r['is_offday'] == 1
    assert r['is_holiday'] == 0


def test_adjusted_workdays_exist_in_2025():
    # 调休补班: 周末但需上班 (节假日前后), 2025 必然存在若干天
    dks = [d.strftime('%Y%m%d') for d in
           np.arange('2025-01-01', '2026-01-01', dtype='datetime64[D]').astype('datetime64[D]').tolist()]
    df = holiday_features(dks)
    assert df['is_adjusted_workday'].sum() > 0


def test_one_row_per_unique_date_and_sorted():
    df = holiday_features(['20260304', '20260217', '20260304'])
    assert len(df) == 2
    assert list(df['date_key']) == sorted(df['date_key'])


def test_proximity_to_holiday_is_zero_on_holiday():
    df = holiday_features(['20260216', '20260217', '20260218'])
    assert _row(df, '20260217')['days_to_holiday'] == 0


def test_uncovered_future_year_falls_back_without_crashing():
    # 超出库覆盖年份应退回"周末判定", 不抛异常
    df = holiday_features(['20351003'])   # 远期
    r = _row(df, '20351003')
    assert r['is_workday'] in (0, 1)


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
