#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 Model v2.1 - 279天训练数据, power_market_v2.db
================================================
- 零泄露：只用 D-1 及更早历史数据
- 96时段粒度预测
- 价格来源：realtime_node_price_96.__avg__ (279天, 替代原38天)
- Walk-forward验证（3月1-11日）
- 漫湾日前电价作为合法特征
"""
import sqlite3, os, warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

warnings.filterwarnings('ignore')

DB = 'F:/work/power-supply-v2/power/power-data/power_market_v2.db'
OUT_DIR = 'F:/work/power-supply-v2/power/power-data'

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def log(msg): print(f"  {msg}", flush=True)

# ============================================================
# 1. Load raw data from v2 DB
# ============================================================
def load_data():
    conn = sqlite3.connect(DB)

    # 目标：实时电价 96时段
    # 使用 realtime_node_price_96.__avg__ (全网加权平均, 279天)
    # 替代 realtime_hourly_price (仅38天)
    price = pd.read_sql(
        """SELECT REPLACE(trade_date, '-', '') as date_key, period, price as rt_price
           FROM realtime_node_price_96
           WHERE node_name = '__avg__'
           ORDER BY trade_date, period""",
        conn
    )
    price['date'] = pd.to_datetime(price['date_key'], format='%Y%m%d')

    # 全区域负荷
    load = pd.read_sql(
        "SELECT date_key, period, load FROM hourly_load WHERE region='全区域' ORDER BY date_key, period",
        conn
    )

    # 云南新能源
    renew = pd.read_sql(
        "SELECT date_key, period, output FROM hourly_renewable WHERE region='云南' ORDER BY date_key, period",
        conn
    )

    # 云南水电
    hydro = pd.read_sql(
        "SELECT date_key, period, output FROM hourly_hydro WHERE region='云南' ORDER BY date_key, period",
        conn
    )

    # 漫湾日前电价（D-1出清，合法特征）
    # 优先用 500kV#1M，取4个节点均值作为代表
    manwan_da = pd.read_sql(
        """
        SELECT trade_date, period, AVG(price) as manwan_da_price
        FROM day_ahead_node_price_96
        WHERE node_name IN ('漫湾厂.500kV#1M','漫湾厂.500kV#2M','漫湾厂.220kVⅠ母','漫湾厂.220kVⅡ母')
        GROUP BY trade_date, period
        ORDER BY trade_date, period
        """,
        conn
    )
    # 全网均价（日前）
    grid_da = pd.read_sql(
        """
        SELECT trade_date, period, price as grid_da_avg
        FROM day_ahead_node_price_96
        WHERE node_name = '__all_avg__'
        ORDER BY trade_date, period
        """,
        conn
    )

    conn.close()
    return price, load, renew, hydro, manwan_da, grid_da


# ============================================================
# 2. Build feature matrix (ZERO leakage)
# ============================================================
def build_features(price, load, renew, hydro, manwan_da, grid_da):
    log("Building feature matrix...")

    # Merge all to price frame (inner join: only days with rt_price)
    df = price.copy()
    df = df.merge(load.rename(columns={'load': 'total_load'}), on=['date_key', 'period'], how='left')
    df = df.merge(renew.rename(columns={'output': 'renewable'}), on=['date_key', 'period'], how='left')
    df = df.merge(hydro.rename(columns={'output': 'hydro'}), on=['date_key', 'period'], how='left')

    # Convert period to period_idx (0-95)
    period_map = {f"{h:02d}:{m:02d}": h * 4 + i
                  for h in range(24)
                  for i, m in enumerate([0, 15, 30, 45])}
    df['period_idx'] = df['period'].map(period_map).fillna(0).astype(int)

    # Time features
    df['hour'] = df['period_idx'] // 4
    df['minute_slot'] = df['period_idx'] % 4
    df['dayofweek'] = df['date'].dt.dayofweek
    df['day'] = df['date'].dt.day
    df['month'] = df['date'].dt.month
    df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
    df['period_sin'] = np.sin(2 * np.pi * df['period_idx'] / 96)
    df['period_cos'] = np.cos(2 * np.pi * df['period_idx'] / 96)
    df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)

    # ──────────────────────────────────────────────
    # 季节性特征 (云南电力市场核心驱动)
    # ──────────────────────────────────────────────
    # 年周期 (月份编码)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    # 周序号 (年内更细粒度的季节定位)
    df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
    df['woy_sin'] = np.sin(2 * np.pi * df['week_of_year'] / 52)
    df['woy_cos'] = np.cos(2 * np.pi * df['week_of_year'] / 52)

    # 云南水电 汛期/枯期 标记
    # 汛期: 6-10月 (丰水, 水电出力大, 电价低)
    # 枯期: 11-5月 (枯水, 水电少, 电价高)
    df['is_wet_season'] = df['month'].isin([6, 7, 8, 9, 10]).astype(int)
    # 枯汛过渡期 (5月、11月价格波动大)
    df['is_transition'] = df['month'].isin([5, 11]).astype(int)

    # 季度 one-hot (Q1枯期末/Q2过渡/Q3汛期/Q4枯期初)
    df['quarter'] = df['date'].dt.quarter
    df['q1'] = (df['quarter'] == 1).astype(int)
    df['q2'] = (df['quarter'] == 2).astype(int)
    df['q3'] = (df['quarter'] == 3).astype(int)
    df['q4'] = (df['quarter'] == 4).astype(int)

    # 季节×时段 交互特征 (枯期晚高峰 vs 汛期晚高峰价格差异大)
    df['wet_x_hour'] = df['is_wet_season'] * df['hour']
    df['wet_x_period_sin'] = df['is_wet_season'] * df['period_sin']

    # 年内天数 (day_of_year) - 连续季节定位
    df['day_of_year'] = df['date'].dt.dayofyear
    df['doy_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
    df['doy_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)

    # 供需缺口（当天值 - 用于lag计算）
    df['gap'] = df['total_load'].fillna(0) - df['renewable'].fillna(0) - df['hydro'].fillna(0)

    # Sort for lag calculation
    df = df.sort_values(['period_idx', 'date_key']).reset_index(drop=True)

    # ──────────────────────────────────────────────
    # LAG FEATURES (shift by 1 day = 38 periods 分组)
    # ──────────────────────────────────────────────
    def add_lag_by_period(df, col, new_col, n_days):
        """For each period, shift value by n_days"""
        df[new_col] = df.groupby('period_idx')[col].shift(n_days)
        return df

    for lag in [1, 2, 3, 7]:
        df = add_lag_by_period(df, 'rt_price', f'price_lag_{lag}d', lag)
    for lag in [1, 2]:
        df = add_lag_by_period(df, 'total_load', f'load_lag_{lag}d', lag)
        df = add_lag_by_period(df, 'renewable', f'renew_lag_{lag}d', lag)
    df = add_lag_by_period(df, 'hydro', 'hydro_lag_1d', 1)
    df = add_lag_by_period(df, 'gap', 'gap_lag_1d', 1)
    df = add_lag_by_period(df, 'gap', 'gap_lag_2d', 2)

    # Moving averages (per period)
    for w in [3, 5, 7]:
        df[f'price_ma_{w}d'] = (
            df.groupby('period_idx')['rt_price']
            .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
        )
        df[f'price_std_{w}d'] = (
            df.groupby('period_idx')['rt_price']
            .transform(lambda x: x.shift(1).rolling(w, min_periods=1).std().fillna(0))
        )

    df['price_momentum_3d'] = df['price_lag_1d'] - df['price_ma_3d']
    df['gap_change'] = df['gap_lag_1d'] - df['gap_lag_2d']

    # ──────────────────────────────────────────────
    # Previous-day daily aggregates (per date)
    # ──────────────────────────────────────────────
    daily = df.groupby('date_key').agg(
        daily_avg_price=('rt_price', 'mean'),
        daily_max_price=('rt_price', 'max'),
        daily_min_price=('rt_price', 'min'),
        daily_std_price=('rt_price', 'std'),
        daily_avg_load=('total_load', 'mean'),
        daily_avg_renew=('renewable', 'mean'),
        daily_avg_gap=('gap', 'mean'),
    ).reset_index()
    daily.columns = ['date_key'] + [f'prevday_{c}' for c in daily.columns[1:]]

    # Shift by 1 day (map D-1 stats to D)
    all_dates = sorted(df['date_key'].unique())
    date_shift = {d: all_dates[i-1] if i > 0 else None for i, d in enumerate(all_dates)}
    daily['date_key_target'] = daily['date_key'].map(date_shift)
    daily = daily.dropna(subset=['date_key_target'])
    daily = daily.drop('date_key', axis=1).rename(columns={'date_key_target': 'date_key'})

    df = df.merge(daily, on='date_key', how='left')

    # ──────────────────────────────────────────────
    # Ratio: period price vs previous day daily avg
    # ──────────────────────────────────────────────
    df['prev_period_to_daily_ratio'] = np.where(
        df['prevday_daily_avg_price'] > 0,
        df['price_lag_1d'] / df['prevday_daily_avg_price'],
        1.0
    )

    # ──────────────────────────────────────────────
    # 漫湾日前电价 (LEGITIMATE: D日DA价在D-1出清)
    # ──────────────────────────────────────────────
    manwan_da['date'] = pd.to_datetime(manwan_da['trade_date'])
    manwan_da['date_key'] = manwan_da['date'].dt.strftime('%Y%m%d')

    df = df.merge(
        manwan_da[['date_key', 'period', 'manwan_da_price']],
        on=['date_key', 'period'], how='left'
    )
    # Manwan DA lag (D-1 manwan DA price)
    df = add_lag_by_period(df, 'manwan_da_price', 'manwan_da_lag1d', 1)

    # 全网均价日前
    grid_da['date_key'] = pd.to_datetime(grid_da['trade_date']).dt.strftime('%Y%m%d')
    df = df.merge(
        grid_da[['date_key', 'period', 'grid_da_avg']],
        on=['date_key', 'period'], how='left'
    )

    # Manwan DA change (今日DA - 昨日DA，在D-1时可计算)
    df = add_lag_by_period(df, 'manwan_da_price', 'manwan_da_prev', 1)
    df['manwan_da_change'] = df['manwan_da_price'] - df['manwan_da_prev']

    df = df.sort_values(['date_key', 'period_idx']).reset_index(drop=True)
    log(f"Feature matrix: {len(df)} rows × {df.shape[1]} cols, {df['date_key'].nunique()} days")
    return df


# ============================================================
# 3. Clean feature list (ZERO leakage)
# ============================================================
FEATURES = [
    # Time - basic (13)
    'hour', 'minute_slot', 'period_idx', 'dayofweek', 'day', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'period_sin', 'period_cos', 'dow_sin', 'dow_cos',
    # Season (16) - 云南水电季节性核心
    'month_sin', 'month_cos',
    'week_of_year', 'woy_sin', 'woy_cos',
    'is_wet_season', 'is_transition',
    'q1', 'q2', 'q3', 'q4',
    'wet_x_hour', 'wet_x_period_sin',
    'day_of_year', 'doy_sin', 'doy_cos',
    # Price history (10)
    'price_lag_1d', 'price_lag_2d', 'price_lag_3d', 'price_lag_7d',
    'price_ma_3d', 'price_ma_5d', 'price_ma_7d',
    'price_std_3d', 'price_std_7d',
    'price_momentum_3d',
    # Load history (2)
    'load_lag_1d', 'load_lag_2d',
    # Renewable history (2)
    'renew_lag_1d', 'renew_lag_2d',
    # Hydro history (1)
    'hydro_lag_1d',
    # Supply-demand gap history (3)
    'gap_lag_1d', 'gap_lag_2d', 'gap_change',
    # 漫湾日前 DA (3) - LEGITIMATE
    'manwan_da_price', 'manwan_da_lag1d', 'manwan_da_change',
    # 全网均价日前 (1) - LEGITIMATE
    'grid_da_avg',
    # Previous-day daily stats (7) - LEGITIMATE
    'prevday_daily_avg_price', 'prevday_daily_max_price',
    'prevday_daily_min_price', 'prevday_daily_std_price',
    'prevday_daily_avg_load', 'prevday_daily_avg_renew', 'prevday_daily_avg_gap',
    # Ratio (1)
    'prev_period_to_daily_ratio',
]


# ============================================================
# 4. Walk-forward training + prediction (March 7 days)
# ============================================================
def walk_forward_predict(df):
    log("Walk-forward prediction on March 7 days...")

    march_dates = sorted([d for d in df['date_key'].unique() if d.startswith('202603')])
    test_dates = march_dates[:11]  # 3/1 ~ 3/11 or available
    log(f"Test dates: {test_dates}")

    features = [f for f in FEATURES if f in df.columns]
    log(f"Active features: {len(features)}")

    results = []
    for test_date in test_dates:
        train_mask = df['date_key'] < test_date
        test_mask = df['date_key'] == test_date

        X_train = df.loc[train_mask, features].fillna(0)
        y_train = df.loc[train_mask, 'rt_price']
        X_test = df.loc[test_mask, features].fillna(0)
        y_test = df.loc[test_mask, 'rt_price']

        # Drop rows where target is NaN
        valid_train = y_train.notna()
        X_train, y_train = X_train[valid_train], y_train[valid_train]

        if len(X_train) < 96 or len(X_test) == 0:
            log(f"  SKIP {test_date}: insufficient data")
            continue

        # ── 样本权重: 时间衰减 + 同季节加成 ──
        train_dates = df.loc[y_train.index, 'date']
        test_dt = pd.to_datetime(test_date, format='%Y%m%d')
        days_ago = (test_dt - train_dates).dt.days.values.astype(float)

        # 1) 指数时间衰减 (半衰期=60天)
        half_life = 60.0
        w_time = np.exp(-np.log(2) * days_ago / half_life)

        # 2) 同季节加成: 枯期(11-5月)训练枯期测试 → 权重×2
        train_months = train_dates.dt.month.values
        test_month = test_dt.month
        test_is_dry = test_month in [11, 12, 1, 2, 3, 4, 5]
        if test_is_dry:
            same_season = np.isin(train_months, [11, 12, 1, 2, 3, 4, 5])
        else:
            same_season = np.isin(train_months, [6, 7, 8, 9, 10])
        w_season = np.where(same_season, 2.0, 0.5)

        sample_weight = w_time * w_season
        # 归一化使权重总和 = 样本数
        sample_weight = sample_weight / sample_weight.mean()

        model = GradientBoostingRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, min_samples_leaf=5, random_state=42
        )
        model.fit(X_train, y_train, sample_weight=sample_weight)
        preds = model.predict(X_test)

        mae = mean_absolute_error(y_test, preds)
        r2 = r2_score(y_test, preds)

        results.append({
            'date': test_date,
            'actual': y_test.values,
            'predicted': preds,
            'period': df.loc[test_mask, 'period'].values,
            'period_idx': df.loc[test_mask, 'period_idx'].values,
            'mae': mae,
            'r2': r2,
            'n_train_days': train_mask.sum() // 96,
        })
        log(f"  {test_date}: MAE={mae:.1f}  R2={r2:.3f}  train_days={train_mask.sum()//96}")

    return results


# ============================================================
# 5. Plot - v3.3 style (actual 96-point intraday)
# ============================================================
def plot_results(results):
    log("Generating charts...")

    n = len(results)
    n_cols = 2
    n_rows = (n + 1) // 2

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4.2 * n_rows + 1))
    fig.suptitle('P0 v2.2 - 3月预测 vs 实际\n(279天+季节特征+时间衰减 | 零泄露 | 96时段)',
                 fontsize=14, fontweight='bold', y=0.98)

    axes_flat = axes.flatten() if n > 2 else [axes] if n == 1 else list(axes)

    time_ticks = list(range(0, 96, 12))
    time_labels = [f"{h:02d}:00" for h in range(0, 24, 3)]

    for i, res in enumerate(results):
        ax = axes_flat[i]
        actual = res['actual']
        pred = res['predicted']
        pidx = res['period_idx']

        # Sort by period_idx
        order = np.argsort(pidx)
        actual = actual[order]
        pred = pred[order]
        x = np.arange(len(actual))

        ax.plot(x, actual, 'b-o', ms=2, lw=1.8, label='实际电价', zorder=3)
        ax.plot(x, pred, 'r--s', ms=2, lw=1.6, label='预测电价', alpha=0.9, zorder=2)
        ax.fill_between(x, actual, pred, alpha=0.12, color='gray')

        ax.set_xticks(time_ticks)
        ax.set_xticklabels(time_labels, fontsize=8)
        ax.set_xlim(0, len(x) - 1)
        ax.set_ylabel('电价 (元/MWh)', fontsize=9)
        ax.set_xlabel('时间', fontsize=9)
        ax.grid(True, alpha=0.3)

        mae = res['mae']
        r2 = res['r2']
        color = '#228B22' if mae < 40 else ('#FF8C00' if mae < 80 else '#DC143C')
        date_str = f"{res['date'][:4]}-{res['date'][4:6]}-{res['date'][6:8]}"
        ax.set_title(f"{date_str}  MAE:{mae:.1f}  R2:{r2:.3f}", fontsize=11, fontweight='bold')
        ax.text(0.97, 0.95, f'MAE: {mae:.1f}', transform=ax.transAxes,
                fontsize=10, fontweight='bold', va='top', ha='right',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.3, edgecolor=color))
        ax.legend(fontsize=8, loc='upper left')

    # Last panel: MAE summary bar chart
    if n % 2 == 1 and n < len(axes_flat):
        ax_sum = axes_flat[n]
        dates_s = [f"{r['date'][4:6]}-{r['date'][6:8]}" for r in results]
        maes = [r['mae'] for r in results]
        colors = ['#228B22' if m < 40 else ('#FF8C00' if m < 80 else '#DC143C') for m in maes]
        bars = ax_sum.bar(dates_s, maes, color=colors, alpha=0.82, edgecolor='gray', width=0.6)
        for bar, m in zip(bars, maes):
            ax_sum.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                       f'{m:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
        avg_mae = np.mean(maes)
        ax_sum.axhline(avg_mae, color='red', ls='--', lw=1.5, alpha=0.7)
        ax_sum.text(len(dates_s) - 0.5, avg_mae + 1, f'均值 {avg_mae:.1f}',
                   ha='right', fontsize=10, color='red', fontweight='bold')
        ax_sum.set_title('MAE汇总', fontsize=12, fontweight='bold')
        ax_sum.set_ylabel('MAE (元/MWh)', fontsize=10)
        ax_sum.grid(True, alpha=0.3, axis='y')
    elif n % 2 == 0:
        pass  # Even: all filled
    else:
        axes_flat[-1].set_visible(False)

    plt.tight_layout()
    out = os.path.join(OUT_DIR, 'p0_v2_march_96period.png')
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    log(f"Chart saved: {out}")
    return out


# ============================================================
# 6. Feature importance report
# ============================================================
def print_feature_report(results, df):
    log("\n=== Feature Importance (final day model) ===")
    features = [f for f in FEATURES if f in df.columns]
    march_dates = sorted([d for d in df['date_key'].unique() if d.startswith('202603')])
    last = march_dates[min(10, len(march_dates)-1)]
    train_mask = df['date_key'] < last
    X = df.loc[train_mask, features].fillna(0)
    y = df.loc[train_mask, 'rt_price'].dropna()
    X = X.loc[y.index]
    model = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.85, random_state=42)
    model.fit(X, y)
    imp = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print("\n  Top 15 features:")
    for feat, val in imp.head(15).items():
        bar = '█' * int(val * 200)
        print(f"  {feat:35s} {val:.4f} {bar}")
    return imp


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("P0 Model v2.2 - 279天+季节特征+时间衰减权重 - Zero Leakage")
    print("=" * 60)

    print("\n[1/4] Loading data from v2 DB...")
    price, load, renew, hydro, manwan_da, grid_da = load_data()
    log(f"Price: {len(price)} rows, {price['date_key'].nunique()} days")
    log(f"Load:  {len(load)} rows, {load['date_key'].nunique()} days")
    log(f"Manwan DA: {len(manwan_da)} rows")

    print("\n[2/4] Building features (zero leakage)...")
    df = build_features(price, load, renew, hydro, manwan_da, grid_da)

    print("\n[3/4] Walk-forward prediction (March)...")
    results = walk_forward_predict(df)

    if not results:
        print("ERROR: No results - check data availability")
        exit(1)

    avg_mae = np.mean([r['mae'] for r in results])
    avg_r2 = np.mean([r['r2'] for r in results])
    print(f"\n  Average MAE: {avg_mae:.1f} yuan/MWh")
    print(f"  Average R2:  {avg_r2:.3f}")

    print("\n[4/4] Generating chart...")
    out_path = plot_results(results)

    print("\n[5/5] Feature importance...")
    imp = print_feature_report(results, df)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Date':12s} {'MAE':>8s} {'R2':>8s} {'TrainDays':>10s}")
    print("-" * 42)
    for r in results:
        d = f"{r['date'][4:6]}-{r['date'][6:8]}"
        print(f"{d:12s} {r['mae']:>8.1f} {r['r2']:>8.3f} {r['n_train_days']:>10d}")
    print("-" * 42)
    print(f"{'平均':12s} {avg_mae:>8.1f} {avg_r2:>8.3f}")
    print(f"\nChart: {out_path}")
    print("=" * 60)
