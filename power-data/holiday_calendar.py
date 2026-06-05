#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国法定节假日日历工具 (含调休补班)
====================================
基于 chinesecalendar 库 (官方公布的法定节假日 + 调休), 为电价/负荷模型生成日历特征。
节假日/工作日是负荷的强驱动因子 — 节假日负荷骤降、调休补班日按工作日运行。

主函数 holiday_features(date_keys): 输入 'YYYYMMDD' 字符串序列, 返回每个唯一日期一行:
  date_key, is_workday, is_holiday, is_offday, is_adjusted_workday,
  holiday_name, days_to_holiday, days_since_holiday, day_type

覆盖范围之外的年份自动退回"周末判定"并告警 (不抛异常)。
依赖: pip install chinesecalendar
"""
import datetime as dt
import warnings
import numpy as np
import pandas as pd
import chinese_calendar as cc

_warned = set()


def _classify(d: dt.date):
    """返回 (is_workday, is_holiday, holiday_name, covered)。超范围退回周末判定。"""
    try:
        on_holiday, name = cc.get_holiday_detail(d)
        workday = cc.is_workday(d)
        # 注意: get_holiday_detail 对普通周末也返回 on_holiday=True, 但 name=None。
        # 法定节假日的判定应以 name 是否非空为准 (区分春节/国庆 与 普通周末)。
        is_statutory = name is not None
        return int(workday), int(is_statutory), name, True
    except NotImplementedError:
        if d.year not in _warned:
            warnings.warn(f"holiday_calendar: {d.year} beyond library coverage, "
                          f"falling back to weekend rule", stacklevel=2)
            _warned.add(d.year)
        is_wd = d.weekday() < 5
        return int(is_wd), 0, None, False


def holiday_features(date_keys) -> pd.DataFrame:
    """为 date_keys('YYYYMMDD') 生成日历特征 DataFrame (每唯一日期一行, 按日期升序)。"""
    uniq = sorted(set(str(k) for k in date_keys))
    recs = []
    for dk in uniq:
        d = dt.datetime.strptime(dk, '%Y%m%d').date()
        workday, is_holiday, name, _ = _classify(d)
        is_offday = int(workday == 0)
        # 调休补班: 是工作日但落在周末 (节假日前后补班), 对负荷是强信号
        is_adj_workday = int(workday == 1 and d.weekday() >= 5)
        recs.append({
            'date_key': dk,
            'is_workday': workday,
            'is_holiday': is_holiday,
            'is_offday': is_offday,
            'is_adjusted_workday': is_adj_workday,
            'holiday_name': name,
        })
    df = pd.DataFrame(recs)

    # 到最近节假日的天数 (前后), 捕捉节前/节后负荷模式
    hol_dates = [dt.datetime.strptime(r['date_key'], '%Y%m%d').date()
                 for r in recs if r['is_holiday'] == 1]
    if hol_dates:
        hol_ord = np.array(sorted(d.toordinal() for d in hol_dates))
        def _to(dk, after):
            o = dt.datetime.strptime(dk, '%Y%m%d').date().toordinal()
            if after:
                nxt = hol_ord[hol_ord >= o]
                return int(nxt[0] - o) if len(nxt) else -1
            prv = hol_ord[hol_ord <= o]
            return int(o - prv[-1]) if len(prv) else -1
        df['days_to_holiday'] = df['date_key'].map(lambda k: _to(k, True))
        df['days_since_holiday'] = df['date_key'].map(lambda k: _to(k, False))
    else:
        df['days_to_holiday'] = -1
        df['days_since_holiday'] = -1

    # 综合日类型: 0=工作日 1=普通周末 2=节假日 3=调休补班
    df['day_type'] = np.select(
        [df['is_holiday'] == 1, df['is_adjusted_workday'] == 1, df['is_offday'] == 1],
        [2, 3, 1], default=0)
    return df


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    # 演示: 覆盖项目数据区间
    rng = np.arange('2024-06-01', '2026-03-24', dtype='datetime64[D]')
    dks = [d.astype('datetime64[D]').item().strftime('%Y%m%d') for d in rng]
    f = holiday_features(dks)
    print(f"生成 {len(f)} 天日历特征 (2024-06-01 ~ 2026-03-23)")
    print(f"  工作日 {f['is_workday'].sum()} | 休息日 {f['is_offday'].sum()} | "
          f"法定节假日 {f['is_holiday'].sum()} | 调休补班 {f['is_adjusted_workday'].sum()}")
    print("  样例(2026春节周):")
    print(f[(f['date_key'] >= '20260214') & (f['date_key'] <= '20260224')].to_string(index=False))
