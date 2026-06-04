#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电价预测模型 V2.0 - 整合供需两端特征
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

from config import DB_PATH, OUTPUT_DIR

def load_all_data():
    """加载所有数据"""
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 实时电价
    df_price = pd.read_sql_query('''
        SELECT trade_date, AVG(avg_price) as avg_price
        FROM realtime_node_price
        GROUP BY trade_date
    ''', conn)
    df_price['trade_date'] = df_price['trade_date'].str.replace('-', '')
    df_price = df_price.rename(columns={'avg_price': 'price'})
    
    # 2. 统调负荷
    df_load = pd.read_sql_query('''
        SELECT trade_date, AVG(total_load) as total_load
        FROM grid_load_overview
        GROUP BY trade_date
    ''', conn)
    
    # 3. 发电总出力
    df_gen = pd.read_sql_query('''
        SELECT trade_date, output_type, AVG(value) as value
        FROM output_summary
        GROUP BY trade_date, output_type
    ''', conn)
    
    df_gen_total = df_gen[df_gen['output_type'] == '发电总出力'][['trade_date', 'value']]
    df_gen_total.columns = ['trade_date', 'total_output']
    
    df_gen_nonmarket = df_gen[df_gen['output_type'] == '非市场化机组'][['trade_date', 'value']]
    df_gen_nonmarket.columns = ['trade_date', 'nonmarket_output']
    
    # 4. 新能源出力
    df_renewable = pd.read_sql_query('''
        SELECT trade_date, AVG(solar_output) as solar_output, 
               AVG(total_renewable) as total_renewable
        FROM renewable_output
        GROUP BY trade_date
    ''', conn)
    
    # 5. 水电出力
    df_hydro = pd.read_sql_query('''
        SELECT trade_date, AVG(output) as hydro_output
        FROM hydro_output
        GROUP BY trade_date
    ''', conn)
    
    conn.close()
    
    return {
        'price': df_price,
        'load': df_load,
        'gen_total': df_gen_total,
        'gen_nonmarket': df_gen_nonmarket,
        'renewable': df_renewable,
        'hydro': df_hydro
    }

def build_features(data):
    """构建综合特征"""
    print("\n=== 构建综合特征 ===")
    
    merged = data['price'].copy()
    merged = merged.merge(data['load'], on='trade_date', how='left')
    merged = merged.merge(data['gen_total'], on='trade_date', how='left')
    merged = merged.merge(data['gen_nonmarket'], on='trade_date', how='left')
    merged = merged.merge(data['renewable'], on='trade_date', how='left')
    merged = merged.merge(data['hydro'], on='trade_date', how='left')
    
    # 转换日期
    merged['date'] = pd.to_datetime(merged['trade_date'], format='%Y%m%d')
    
    # 时间特征
    merged['dayofweek'] = merged['date'].dt.dayofweek
    merged['day'] = merged['date'].dt.day
    merged['month'] = merged['date'].dt.month
    merged['is_weekend'] = merged['dayofweek'].isin([5, 6]).astype(int)
    
    # 计算火电出力 = 非市场化 - 新能源
    merged['thermal_output'] = merged['nonmarket_output'] - merged['total_renewable']
    merged['thermal_output'] = merged['thermal_output'].clip(lower=0)
    
    # 供需比
    merged['supply_demand_ratio'] = merged['total_output'] / merged['total_load']
    
    # 排序
    merged = merged.sort_values('date')
    
    # 滞后特征
    for lag in [1, 2, 3, 7]:
        merged[f'price_lag_{lag}'] = merged['price'].shift(lag)
    
    # 移动平均
    for w in [3, 7]:
        merged[f'price_ma_{w}'] = merged['price'].rolling(w, min_periods=1).mean()
        merged[f'price_std_{w}'] = merged['price'].rolling(w, min_periods=1).std()
    
    # 价格变化
    merged['price_change'] = merged['price'].diff()
    merged['price_change_pct'] = merged['price'].pct_change()
    
    # 去除缺失（保留至少7天数据）
    merged = merged.dropna()
    
    print(f"特征数据: {len(merged)} 条")
    print(f"日期范围: {merged['date'].min()} ~ {merged['date'].max()}")
    
    return merged

def train_and_evaluate(merged):
    """训练模型并评估"""
    print("\n=== 训练模型 ===")
    
    feature_cols = [
        'dayofweek', 'day', 'month', 'is_weekend',
        'total_load', 'total_output', 'nonmarket_output',
        'solar_output', 'total_renewable', 'hydro_output', 'thermal_output',
        'supply_demand_ratio',
        'price_lag_1', 'price_lag_2', 'price_lag_3', 'price_lag_7',
        'price_ma_3', 'price_ma_7', 'price_std_3', 'price_std_7',
        'price_change', 'price_change_pct'
    ]
    
    feature_cols = [c for c in feature_cols if c in merged.columns]
    
    X = merged[feature_cols]
    y = merged['price']
    
    train_size = int(len(X) * 0.8)
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]
    
    print(f"训练集: {len(X_train)} 条, 测试集: {len(X_test)} 条")
    
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    
    models = {}
    results = {}
    
    for name, model in [
        ('Ridge', Ridge(alpha=1.0)),
        ('RandomForest', RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)),
        ('GradientBoosting', GradientBoostingRegressor(n_estimators=100, random_state=42))
    ]:
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        models[name] = model
        results[name] = {
            'MAE': mean_absolute_error(y_test, pred),
            'RMSE': np.sqrt(mean_squared_error(y_test, pred)),
            'R2': r2_score(y_test, pred)
        }
    
    print("\n【模型评估结果 V2.0】")
    for name, metrics in results.items():
        print(f"{name}: MAE={metrics['MAE']:.2f}, RMSE={metrics['RMSE']:.2f}, R²={metrics['R2']:.4f}")
    
    # 特征重要性
    print("\n【特征重要性 (RandomForest)】")
    imp = pd.DataFrame({
        'feature': feature_cols,
        'importance': models['RandomForest'].feature_importances_
    }).sort_values('importance', ascending=False)
    print(imp.head(10).to_string(index=False))
    
    return models, results, feature_cols

def backtest(merged, model):
    """回测3月7天"""
    print("\n=== 回测3月7天 ===")
    
    march_data = merged[merged['date'].dt.month == 3].copy()
    
    if len(march_data) < 7:
        print(f"3月数据不足，使用最后7天")
        march_data = merged.tail(7)
    
    unique_dates = sorted(march_data['date'].unique())[-7:]
    print(f"回测日期: {[d.strftime('%Y-%m-%d') for d in unique_dates]}")
    
    backtest_data = march_data[march_data['date'].isin(unique_dates)].copy()
    
    feature_cols = [
        'dayofweek', 'day', 'month', 'is_weekend',
        'total_load', 'total_output', 'nonmarket_output',
        'solar_output', 'total_renewable', 'hydro_output', 'thermal_output',
        'supply_demand_ratio',
        'price_lag_1', 'price_lag_2', 'price_lag_3', 'price_lag_7',
        'price_ma_3', 'price_ma_7', 'price_std_3', 'price_std_7',
        'price_change', 'price_change_pct'
    ]
    feature_cols = [c for c in feature_cols if c in backtest_data.columns]
    
    y_pred = model.predict(backtest_data[feature_cols])
    backtest_data['predicted_price'] = y_pred
    
    daily_results = backtest_data.groupby('date').agg({
        'price': 'mean',
        'predicted_price': 'mean'
    }).reset_index()
    
    from sklearn.metrics import mean_absolute_error
    mae = mean_absolute_error(daily_results['price'], daily_results['predicted_price'])
    
    print(f"\n【日均对比】")
    for _, row in daily_results.iterrows():
        print(f"  {row['date'].strftime('%Y-%m-%d')}: 实际={row['price']:.2f}, 预测={row['predicted_price']:.2f}, 误差={abs(row['price']-row['predicted_price']):.2f}")
    print(f"\n日均MAE: {mae:.2f} 元/MWh")
    
    return backtest_data, daily_results

def plot_backtest(daily_results, output_path):
    """绘制回测对比图"""
    plt.figure(figsize=(12, 6))
    
    dates = daily_results['date']
    actual = daily_results['price']
    predicted = daily_results['predicted_price']
    
    x = range(len(dates))
    
    plt.plot(x, actual, 'b-o', label='实时节点电价 (实际)', linewidth=2, markersize=10)
    plt.plot(x, predicted, 'r--s', label='预测电价', linewidth=2, markersize=10)
    plt.fill_between(x, actual, predicted, alpha=0.3, color='gray')
    
    plt.xlabel('日期', fontsize=12)
    plt.ylabel('电价 (元/MWh)', fontsize=12)
    plt.title('电价预测回测对比 (V2.0 - 3月7天)\n含供需两端特征', fontsize=14)
    plt.xticks(x, [d.strftime('%m-%d') for d in dates], rotation=45)
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"回测图已保存: {output_path}")

def main():
    print("=" * 60)
    print("电价预测模型 V2.0 - 供需两端特征")
    print("=" * 60)
    
    data = load_all_data()
    print(f"数据: 电价{len(data['price'])}天, 负荷{len(data['load'])}天")
    
    merged = build_features(data)
    models, results, feature_cols = train_and_evaluate(merged)
    
    backtest_data, daily_results = backtest(merged, models['GradientBoosting'])
    plot_backtest(daily_results, OUTPUT_DIR + '回测对比_V2.0.png')
    
    # 保存结果
    with open(OUTPUT_DIR + '模型评估结果_V2.0.txt', 'w', encoding='utf-8') as f:
        f.write("电价预测模型 V2.0 评估结果\n")
        f.write("=" * 50 + "\n\n")
        f.write("新增特征:\n")
        f.write("  - 统调负荷 (total_load)\n")
        f.write("  - 发电总出力 (total_output)\n")
        f.write("  - 非市场化机组 (nonmarket_output)\n")
        f.write("  - 新能源出力 (solar_output, total_renewable)\n")
        f.write("  - 水电出力 (hydro_output)\n")
        f.write("  - 火电出力 (thermal_output)\n")
        f.write("  - 供需比 (supply_demand_ratio)\n")
        f.write("\n模型结果:\n")
        for name, metrics in results.items():
            f.write(f"\n{name}:\n")
            f.write(f"  MAE: {metrics['MAE']:.2f} 元/MWh\n")
            f.write(f"  RMSE: {metrics['RMSE']:.2f} 元/MWh\n")
            f.write(f"  R²: {metrics['R2']:.4f}\n")
    
    print("\n完成!")

if __name__ == '__main__':
    main()
