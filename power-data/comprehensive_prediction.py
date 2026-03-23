#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合电价预测系统
整合所有可用数据进行电价预测
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

DB_PATH = '/home/zp/clawd/projects/power-supply/electrate-clone/power-data/power_market.db'

def load_all_data():
    """加载所有数据"""
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 电价数据
    df_price = pd.read_sql_query('''
        SELECT trade_date, node_name, avg_price, min_price, max_price 
        FROM realtime_node_price
    ''', conn)
    
    # 2. 日前电价
    df_da_price = pd.read_sql_query('''
        SELECT trade_date, node_name, avg_price 
        FROM day_ahead_node_price
    ''', conn)
    
    # 3. 用电侧数据
    df_demand = pd.read_sql_query('''
        SELECT trade_date, period, demand, price 
        FROM day_ahead_demand
    ''', conn)
    
    # 4. 机组状态
    df_unit = pd.read_sql_query('''
        SELECT * FROM unit_status
    ''', conn)
    
    # 5. 系统备用
    df_reserve = pd.read_sql_query('''
        SELECT * FROM system_reserve
    ''', conn)
    
    # 6. 负荷数据
    df_load = pd.read_sql_query('''
        SELECT * FROM grid_load_overview
    ''', conn)
    
    conn.close()
    
    return {
        'price': df_price,
        'da_price': df_da_price,
        'demand': df_demand,
        'unit': df_unit,
        'reserve': df_reserve,
        'load': df_load
    }

def build_features(data):
    """构建综合特征"""
    print("\n=== 构建综合特征 ===")
    
    df = data['price'].copy()
    
    # 日期处理
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values(['trade_date', 'node_name'])
    
    # 按日期聚合
    daily = df.groupby('trade_date').agg({
        'avg_price': ['mean', 'std', 'min', 'max'],
        'min_price': 'min',
        'max_price': 'max'
    }).reset_index()
    daily.columns = ['date', 'avg_price', 'price_std', 'price_min', 'price_max', 'daily_min', 'daily_max']
    
    # 时间特征
    daily['dayofweek'] = daily['date'].dt.dayofweek
    daily['day'] = daily['date'].dt.day
    daily['month'] = daily['date'].dt.month
    daily['is_weekend'] = daily['dayofweek'].isin([5, 6]).astype(int)
    
    # 滞后特征
    for lag in [1, 2, 3, 7]:
        daily[f'lag_{lag}'] = daily['avg_price'].shift(lag)
    
    # 移动平均
    for w in [3, 7, 14]:
        daily[f'ma_{w}'] = daily['avg_price'].rolling(w).mean()
        daily[f'std_{w}'] = daily['avg_price'].rolling(w).std()
    
    # 价格变化
    daily['price_change'] = daily['avg_price'].diff()
    daily['price_change_pct'] = daily['avg_price'].pct_change()
    
    # 合并日前电价
    da_daily = data['da_price'].groupby('trade_date')['avg_price'].mean().reset_index()
    da_daily.columns = ['date', 'da_price']
    da_daily['date'] = pd.to_datetime(da_daily['date'])
    
    daily = daily.merge(da_daily, on='date', how='left')
    
    # 清理数据
    daily = daily.dropna()
    
    print(f"特征数据: {len(daily)} 条")
    print(f"特征列: {list(daily.columns)}")
    
    return daily

def train_model(daily):
    """训练预测模型"""
    print("\n=== 训练预测模型 ===")
    
    if len(daily) < 10:
        print("数据不足，无法训练模型")
        return None
    
    # 特征列
    feature_cols = ['dayofweek', 'day', 'month', 'is_weekend',
                   'lag_1', 'lag_2', 'lag_3', 'lag_7',
                   'ma_3', 'ma_7', 'ma_14',
                   'std_3', 'std_7',
                   'price_change', 'price_change_pct',
                   'da_price']
    
    # 过滤存在的列
    feature_cols = [c for c in feature_cols if c in daily.columns]
    
    X = daily[feature_cols]
    y = daily['avg_price']
    
    # 分割
    train_size = max(1, int(len(X) * 0.8))
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]
    
    print(f"训练集: {len(X_train)} 条")
    print(f"测试集: {len(X_test)} 条")
    
    # 尝试训练模型
    try:
        from sklearn.linear_model import LinearRegression, Ridge
        from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        
        models = {}
        results = {}
        
        # 1. 线性回归
        lr = LinearRegression()
        lr.fit(X_train, y_train)
        lr_pred = lr.predict(X_test)
        models['LinearRegression'] = lr
        results['LinearRegression'] = {
            'MAE': mean_absolute_error(y_test, lr_pred),
            'RMSE': np.sqrt(mean_squared_error(y_test, lr_pred)),
            'R2': r2_score(y_test, lr_pred)
        }
        
        # 2. 随机森林
        rf = RandomForestRegressor(n_estimators=50, random_state=42)
        rf.fit(X_train, y_train)
        rf_pred = rf.predict(X_test)
        models['RandomForest'] = rf
        results['RandomForest'] = {
            'MAE': mean_absolute_error(y_test, rf_pred),
            'RMSE': np.sqrt(mean_squared_error(y_test, rf_pred)),
            'R2': r2_score(y_test, rf_pred)
        }
        
        # 3. 梯度提升
        gb = GradientBoostingRegressor(n_estimators=50, random_state=42)
        gb.fit(X_train, y_train)
        gb_pred = gb.predict(X_test)
        models['GradientBoosting'] = gb
        results['GradientBoosting'] = {
            'MAE': mean_absolute_error(y_test, gb_pred),
            'RMSE': np.sqrt(mean_squared_error(y_test, gb_pred)),
            'R2': r2_score(y_test, gb_pred)
        }
        
        print("\n【模型评估结果】")
        for name, metrics in results.items():
            print(f"\n{name}:")
            print(f"  MAE: {metrics['MAE']:.2f}")
            print(f"  RMSE: {metrics['RMSE']:.2f}")
            print(f"  R²: {metrics['R2']:.4f}")
        
        # 特征重要性
        if hasattr(rf, 'feature_importances_'):
            print("\n【特征重要性】")
            imp = pd.DataFrame({
                'feature': feature_cols,
                'importance': rf.feature_importances_
            }).sort_values('importance', ascending=False)
            print(imp.head(10).to_string(index=False))
        
        return models
    
    except ImportError:
        print("需要安装 scikit-learn: pip install scikit-learn")
        return None

def predict_next_days(daily, days=7):
    """预测未来N天电价"""
    print(f"\n=== 预测未来{days}天 ===")
    
    if len(daily) < 7:
        print("数据不足")
        return None
    
    # 获取最后一天的日期
    last_date = daily['date'].max()
    future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=days)
    
    # 创建预测数据框
    future = pd.DataFrame({'date': future_dates})
    future['dayofweek'] = future['date'].dt.dayofweek
    future['day'] = future['date'].dt.day
    future['month'] = future['date'].dt.month
    future['is_weekend'] = future['dayofweek'].isin([5, 6]).astype(int)
    
    # 使用最后已知值填充
    for lag in [1, 2, 3, 7]:
        if lag <= len(daily):
            future[f'lag_{lag}'] = daily['avg_price'].iloc[-lag]
        else:
            future[f'lag_{lag}'] = daily['avg_price'].mean()
    
    for w in [3, 7, 14]:
        if w <= len(daily):
            future[f'ma_{w}'] = daily['avg_price'].iloc[-w:].mean()
            future[f'std_{w}'] = daily['avg_price'].iloc[-w:].std()
        else:
            future[f'ma_{w}'] = daily['avg_price'].mean()
            future[f'std_{w}'] = daily['avg_price'].std()
    
    future['price_change'] = daily['avg_price'].diff().iloc[-1] if len(daily) > 1 else 0
    future['price_change_pct'] = daily['avg_price'].pct_change().iloc[-1] if len(daily) > 1 else 0
    future['da_price'] = daily['da_price'].iloc[-1] if 'da_price' in daily.columns else daily['avg_price'].iloc[-1]
    
    return future

def main():
    print("=" * 60)
    print("综合电价预测系统")
    print("=" * 60)
    
    # 加载数据
    print("\n加载数据...")
    data = load_all_data()
    
    print(f"电价数据: {len(data['price'])} 条")
    print(f"日前电价: {len(data['da_price'])} 条")
    print(f"用电侧: {len(data['demand'])} 条")
    
    # 构建特征
    daily = build_features(data)
    
    # 训练模型
    models = train_model(daily)
    
    # 预测未来
    future = predict_next_days(daily, 7)
    if future is not None:
        print("\n【未来7天预测】")
        print(future[['date', 'dayofweek', 'is_weekend']].to_string(index=False))
    
    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)

if __name__ == '__main__':
    main()
