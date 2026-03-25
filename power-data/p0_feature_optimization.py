#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 特征工程优化 - 电价预测回归对比
基于 market_data.json 数据，输出3月7天实时电价 vs 预测电价对比图
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. 数据加载
# ============================================================
DATA_PATH = 'F:/work/power-supply-v2/power/electrate/src/data/market_data.json'
OUTPUT_DIR = 'F:/work/power-supply-v2/power/power-data/'

with open(DATA_PATH, 'r') as f:
    raw = json.load(f)

df = pd.DataFrame({
    'date': pd.to_datetime(raw['dates']),
    'price': raw['price'],           # 实时电价均价
    'min_price': raw['min_price'],   # 日最低价
    'max_price': raw['max_price'],   # 日最高价
    'solar': raw['solar'],           # 光伏出力
    'renewable': raw['renewable'],   # 新能源总出力
    'load': raw['load'],             # 统调负荷
    'demand': raw['demand'],         # 用电侧出清价
})

df = df.sort_values('date').reset_index(drop=True)
print(f"原始数据: {len(df)} 天, {df['date'].min().date()} ~ {df['date'].max().date()}")

# ============================================================
# 2. P0 特征工程优化
# ============================================================
print("\n=== P0 特征工程优化 ===")

# --- 2.1 基础时间特征 ---
df['dayofweek'] = df['date'].dt.dayofweek
df['day'] = df['date'].dt.day
df['month'] = df['date'].dt.month
df['is_weekend'] = df['dayofweek'].isin([5, 6]).astype(int)
# 周期性编码 (sin/cos)
df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7)
df['day_sin'] = np.sin(2 * np.pi * df['day'] / 31)
df['day_cos'] = np.cos(2 * np.pi * df['day'] / 31)

# --- 2.2 核心P0特征: 供需缺口 ---
# 供需缺口 = 负荷 - 新能源出力 (越大越紧张，价格越高)
df['supply_demand_gap'] = df['load'] - df['renewable']
# 新能源渗透率
df['renewable_ratio'] = df['renewable'] / df['load']
# 负荷-新能源比
df['load_renewable_diff_pct'] = (df['load'] - df['renewable']) / df['load']

# --- 2.3 价格波动特征 ---
df['price_range'] = df['max_price'] - df['min_price']   # 日内价差
df['price_volatility'] = df['price_range'] / (df['price'] + 1e-6)  # 波动率
df['price_skew'] = (df['price'] - df['min_price']) / (df['price_range'] + 1e-6)  # 偏度

# --- 2.4 滞后特征 ---
for lag in [1, 2, 3, 7]:
    df[f'price_lag_{lag}'] = df['price'].shift(lag)
    df[f'gap_lag_{lag}'] = df['supply_demand_gap'].shift(lag)

# 供需缺口变化率
df['gap_change'] = df['supply_demand_gap'].diff()
df['gap_change_pct'] = df['supply_demand_gap'].pct_change()

# --- 2.5 移动平均/统计 ---
for w in [3, 5, 7]:
    df[f'price_ma_{w}'] = df['price'].rolling(w, min_periods=1).mean()
    df[f'price_std_{w}'] = df['price'].rolling(w, min_periods=1).std().fillna(0)
    df[f'gap_ma_{w}'] = df['supply_demand_gap'].rolling(w, min_periods=1).mean()
    df[f'load_ma_{w}'] = df['load'].rolling(w, min_periods=1).mean()

# --- 2.6 价格动量 ---
df['price_change'] = df['price'].diff()
df['price_change_pct'] = df['price'].pct_change()
df['price_momentum_3'] = df['price'] - df['price_ma_3']

# --- 2.7 demand(用电侧出清价) 作为日前价格代理 ---
df['demand_price_ratio'] = df['demand'] / (df['price'] + 1e-6)
for lag in [1, 2]:
    df[f'demand_lag_{lag}'] = df['demand'].shift(lag)

print(f"特征总数: {len(df.columns)} 列")

# ============================================================
# 3. 准备训练/测试数据
# ============================================================
# 3月数据用于测试 (回测)
df_clean = df.dropna().copy()
march_mask = df_clean['date'].dt.month == 3
feb_mask = df_clean['date'].dt.month == 2

# 特征列 (排除目标和日期)
exclude_cols = ['date', 'price', 'min_price', 'max_price']
feature_cols = [c for c in df_clean.columns if c not in exclude_cols]

print(f"\n清洗后数据: {len(df_clean)} 天")
print(f"2月训练: {feb_mask.sum()} 天, 3月测试: {march_mask.sum()} 天")
print(f"特征数: {len(feature_cols)}")

# ============================================================
# 4. 两种方案对比: 基线 vs P0优化
# ============================================================

# --- 基线特征 (V1: 简单时间+价格滞后) ---
baseline_features = [
    'dayofweek', 'day', 'month', 'is_weekend',
    'price_lag_1', 'price_lag_2', 'price_lag_3',
    'price_ma_3', 'price_ma_7',
    'price_change', 'price_change_pct',
    'solar', 'load',
]
baseline_features = [c for c in baseline_features if c in df_clean.columns]

# --- P0优化特征 (V2: +供需缺口+波动+demand) ---
p0_features = [
    # 时间
    'dayofweek', 'day', 'month', 'is_weekend',
    'dow_sin', 'dow_cos', 'day_sin', 'day_cos',
    # 供给侧
    'solar', 'renewable', 'load',
    # P0核心: 供需缺口
    'supply_demand_gap', 'renewable_ratio', 'load_renewable_diff_pct',
    'gap_lag_1', 'gap_lag_2', 'gap_change', 'gap_change_pct',
    'gap_ma_3', 'gap_ma_5',
    # 价格历史
    'price_lag_1', 'price_lag_2', 'price_lag_3', 'price_lag_7',
    'price_ma_3', 'price_ma_5', 'price_ma_7',
    'price_std_3', 'price_std_7',
    'price_change', 'price_change_pct', 'price_momentum_3',
    # 波动特征
    'price_range', 'price_volatility', 'price_skew',
    # Demand代理
    'demand', 'demand_lag_1', 'demand_lag_2', 'demand_price_ratio',
    # 负荷趋势
    'load_ma_3', 'load_ma_5', 'load_ma_7',
]
p0_features = [c for c in p0_features if c in df_clean.columns]

print(f"\n基线特征数: {len(baseline_features)}")
print(f"P0优化特征数: {len(p0_features)}")

# ============================================================
# 5. 滚动预测 (Walk-Forward) 3月7天
# ============================================================
print("\n=== 滚动预测3月7天 ===")

march_data = df_clean[march_mask].copy()
march_dates = sorted(march_data['date'].unique())

# 取最后7天3月数据
test_dates = march_dates[-7:] if len(march_dates) >= 7 else march_dates
print(f"测试日期: {[d.strftime('%Y-%m-%d') for d in pd.to_datetime(test_dates)]}")

results = {}

for version_name, feat_cols in [('基线(V1)', baseline_features), ('P0优化(V2)', p0_features)]:
    predictions = []
    actuals = []
    test_date_list = []

    for test_date in test_dates:
        # 训练集: test_date之前的所有数据
        train_mask = df_clean['date'] < test_date
        test_mask = df_clean['date'] == test_date

        if train_mask.sum() < 5:
            continue

        X_train = df_clean.loc[train_mask, feat_cols].fillna(0)
        y_train = df_clean.loc[train_mask, 'price']
        X_test = df_clean.loc[test_mask, feat_cols].fillna(0)
        y_test = df_clean.loc[test_mask, 'price']

        if len(X_test) == 0:
            continue

        # GradientBoosting (当前最佳模型)
        model = GradientBoostingRegressor(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42
        )
        model.fit(X_train, y_train)
        pred = model.predict(X_test)

        predictions.append(pred[0])
        actuals.append(y_test.values[0])
        test_date_list.append(test_date)

    predictions = np.array(predictions)
    actuals = np.array(actuals)

    mae = mean_absolute_error(actuals, predictions)
    rmse = np.sqrt(mean_squared_error(actuals, predictions))
    r2 = r2_score(actuals, predictions) if len(actuals) > 1 else 0
    mape = np.mean(np.abs((actuals - predictions) / (actuals + 1e-6))) * 100

    results[version_name] = {
        'dates': test_date_list,
        'actual': actuals,
        'predicted': predictions,
        'MAE': mae,
        'RMSE': rmse,
        'R2': r2,
        'MAPE': mape
    }

    print(f"\n[{version_name}] MAE={mae:.2f}, RMSE={rmse:.2f}, R2={r2:.4f}, MAPE={mape:.1f}%")
    for i, d in enumerate(test_date_list):
        d_str = pd.to_datetime(d).strftime('%m-%d')
        err = abs(actuals[i] - predictions[i])
        pct = err / (actuals[i] + 1e-6) * 100
        print(f"  {d_str}: actual={actuals[i]:.1f}, pred={predictions[i]:.1f}, err={err:.1f} ({pct:.1f}%)")

# ============================================================
# 6. 特征重要性分析 (P0模型)
# ============================================================
print("\n=== P0特征重要性 TOP 15 ===")
# 用全量数据训练一次看特征重要性
X_all = df_clean[p0_features].fillna(0)
y_all = df_clean['price']
full_model = GradientBoostingRegressor(n_estimators=150, max_depth=4, learning_rate=0.1, random_state=42)
full_model.fit(X_all, y_all)

imp_df = pd.DataFrame({
    'feature': p0_features,
    'importance': full_model.feature_importances_
}).sort_values('importance', ascending=False)

for _, row in imp_df.head(15).iterrows():
    bar = '█' * int(row['importance'] * 100)
    print(f"  {row['feature']:30s} {row['importance']:.4f} {bar}")

# ============================================================
# 7. 绘制对比图
# ============================================================
print("\n=== 生成对比图 ===")

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('P0 Feature Engineering Optimization\nMarch 7-Day Price Prediction Comparison',
             fontsize=16, fontweight='bold')

# --- 子图1: 基线 vs P0 对比 ---
ax1 = axes[0, 0]
dates_str = [pd.to_datetime(d).strftime('%m-%d') for d in results['P0优化(V2)']['dates']]
x = range(len(dates_str))

ax1.plot(x, results['基线(V1)']['actual'], 'ko-', label='Actual Price', linewidth=2.5, markersize=9, zorder=5)
ax1.plot(x, results['基线(V1)']['predicted'], 'b--^', label='Baseline(V1)', linewidth=1.8, markersize=8, alpha=0.8)
ax1.plot(x, results['P0优化(V2)']['predicted'], 'r-s', label='P0 Optimized(V2)', linewidth=2.2, markersize=8)

ax1.set_xticks(list(x))
ax1.set_xticklabels(dates_str, rotation=45)
ax1.set_ylabel('Price (yuan/MWh)', fontsize=11)
ax1.set_title('Actual vs Predicted Price', fontsize=13)
ax1.legend(fontsize=10)
ax1.grid(True, alpha=0.3)

# --- 子图2: 误差对比 ---
ax2 = axes[0, 1]
err_baseline = np.abs(results['基线(V1)']['actual'] - results['基线(V1)']['predicted'])
err_p0 = np.abs(results['P0优化(V2)']['actual'] - results['P0优化(V2)']['predicted'])

bar_width = 0.35
x_bar = np.arange(len(dates_str))
bars1 = ax2.bar(x_bar - bar_width/2, err_baseline, bar_width, label='Baseline Error', color='#5B9BD5', alpha=0.8)
bars2 = ax2.bar(x_bar + bar_width/2, err_p0, bar_width, label='P0 Error', color='#FF6B6B', alpha=0.8)

ax2.set_xticks(x_bar)
ax2.set_xticklabels(dates_str, rotation=45)
ax2.set_ylabel('Absolute Error (yuan/MWh)', fontsize=11)
ax2.set_title('Prediction Error Comparison', fontsize=13)
ax2.legend(fontsize=10)
ax2.grid(True, alpha=0.3, axis='y')

# 标注数值
for bar in bars1:
    h = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2., h + 1, f'{h:.0f}', ha='center', va='bottom', fontsize=8, color='#5B9BD5')
for bar in bars2:
    h = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2., h + 1, f'{h:.0f}', ha='center', va='bottom', fontsize=8, color='#FF6B6B')

# --- 子图3: 散点回归图 ---
ax3 = axes[1, 0]
actual_all = results['P0优化(V2)']['actual']
pred_all = results['P0优化(V2)']['predicted']

ax3.scatter(actual_all, pred_all, c='red', s=100, zorder=5, edgecolors='darkred', linewidths=1, label='P0(V2)')
ax3.scatter(results['基线(V1)']['actual'], results['基线(V1)']['predicted'], c='blue', s=80,
            marker='^', zorder=4, edgecolors='darkblue', linewidths=1, alpha=0.7, label='Baseline(V1)')

# 完美预测线
all_vals = np.concatenate([actual_all, pred_all, results['基线(V1)']['predicted']])
min_v, max_v = all_vals.min() * 0.8, all_vals.max() * 1.1
ax3.plot([min_v, max_v], [min_v, max_v], 'k--', alpha=0.5, label='Perfect Prediction')
ax3.set_xlim(min_v, max_v)
ax3.set_ylim(min_v, max_v)
ax3.set_xlabel('Actual Price (yuan/MWh)', fontsize=11)
ax3.set_ylabel('Predicted Price (yuan/MWh)', fontsize=11)
ax3.set_title('Regression Scatter Plot', fontsize=13)
ax3.legend(fontsize=10)
ax3.grid(True, alpha=0.3)
ax3.set_aspect('equal', adjustable='box')

# --- 子图4: 模型指标对比 ---
ax4 = axes[1, 1]
metrics_names = ['MAE', 'RMSE', 'MAPE(%)']
baseline_vals = [results['基线(V1)']['MAE'], results['基线(V1)']['RMSE'], results['基线(V1)']['MAPE']]
p0_vals = [results['P0优化(V2)']['MAE'], results['P0优化(V2)']['RMSE'], results['P0优化(V2)']['MAPE']]

x_m = np.arange(len(metrics_names))
bars_b = ax4.bar(x_m - 0.2, baseline_vals, 0.35, label='Baseline(V1)', color='#5B9BD5')
bars_p = ax4.bar(x_m + 0.2, p0_vals, 0.35, label='P0 Optimized(V2)', color='#FF6B6B')

for bar in bars_b:
    h = bar.get_height()
    ax4.text(bar.get_x() + bar.get_width()/2., h + 0.5, f'{h:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
for bar in bars_p:
    h = bar.get_height()
    ax4.text(bar.get_x() + bar.get_width()/2., h + 0.5, f'{h:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

ax4.set_xticks(x_m)
ax4.set_xticklabels(metrics_names, fontsize=12)
ax4.set_title('Model Metrics Comparison', fontsize=13)
ax4.legend(fontsize=11)
ax4.grid(True, alpha=0.3, axis='y')

# 添加R2和改进幅度
r2_baseline = results['基线(V1)']['R2']
r2_p0 = results['P0优化(V2)']['R2']
mae_improve = (results['基线(V1)']['MAE'] - results['P0优化(V2)']['MAE']) / results['基线(V1)']['MAE'] * 100

summary_text = (
    f"R2 Baseline: {r2_baseline:.4f}\n"
    f"R2 P0:       {r2_p0:.4f}\n"
    f"MAE Improvement: {mae_improve:+.1f}%"
)
ax4.text(0.98, 0.98, summary_text, transform=ax4.transAxes, fontsize=10,
         verticalalignment='top', horizontalalignment='right',
         bbox=dict(boxstyle='round,pad=0.5', facecolor='lightyellow', edgecolor='orange', alpha=0.9),
         fontfamily='monospace')

plt.tight_layout(rect=[0, 0, 1, 0.95])
output_path = OUTPUT_DIR + 'p0_march_7day_comparison.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"\n图表已保存: {output_path}")

# ============================================================
# 8. 总结
# ============================================================
print("\n" + "=" * 60)
print("P0 特征工程优化总结")
print("=" * 60)
print(f"基线(V1) MAE: {results['基线(V1)']['MAE']:.2f} yuan/MWh")
print(f"P0优化(V2) MAE: {results['P0优化(V2)']['MAE']:.2f} yuan/MWh")
print(f"MAE改进: {mae_improve:+.1f}%")
print(f"R2 基线: {r2_baseline:.4f} → P0优化: {r2_p0:.4f}")
print(f"\n核心新增特征:")
print(f"  - supply_demand_gap (供需缺口)")
print(f"  - renewable_ratio (新能源渗透率)")
print(f"  - price_volatility (价格波动率)")
print(f"  - gap_change/gap_ma (缺口动量)")
print(f"  - demand_lag (用电侧滞后)")
print("=" * 60)
