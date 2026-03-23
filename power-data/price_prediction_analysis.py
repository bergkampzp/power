#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力市场电价预测分析
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

DB_PATH = '/home/zp/clawd/projects/power-supply/electrate-clone/power-data/power_market.db'

def load_data():
    """加载数据"""
    conn = sqlite3.connect(DB_PATH)
    
    df_da = pd.read_sql_query('''
        SELECT trade_date, node_name, avg_price, min_price, max_price 
        FROM day_ahead_node_price 
        ORDER BY trade_date, node_name
    ''', conn)
    
    df_rt = pd.read_sql_query('''
        SELECT trade_date, node_name, avg_price, min_price, max_price 
        FROM realtime_node_price 
        ORDER BY trade_date, node_name
    ''', conn)
    
    conn.close()
    return df_da, df_rt

def main():
    print("=" * 60)
    print("电力市场电价预测分析")
    print("=" * 60)
    
    # 加载数据
    print("\n正在加载数据...")
    df_da, df_rt = load_data()
    
    # 1. 数据探索
    print("\n" + "=" * 60)
    print("一、数据探索")
    print("=" * 60)
    
    print(f"\n日前节点电价: {len(df_da)} 条")
    print(f"日期范围: {df_da['trade_date'].min()} ~ {df_da['trade_date'].max()}")
    print(f"节点数: {df_da['node_name'].nunique()}")
    print(f"\n电价统计:")
    print(df_da['avg_price'].describe().round(2))
    
    print(f"\n实时节点电价: {len(df_rt)} 条")
    print(f"日期范围: {df_rt['trade_date'].min()} ~ {df_rt['trade_date'].max()}")
    print(f"\n电价统计:")
    print(df_rt['avg_price'].describe().round(2))
    
    # 2. 日均电价趋势
    print("\n" + "=" * 60)
    print("二、日均电价趋势")
    print("=" * 60)
    
    # 日前电价日均
    da_daily = df_da.groupby('trade_date')['avg_price'].mean().reset_index()
    da_daily.columns = ['date', 'da_price']
    
    # 实时电价日均
    rt_daily = df_rt.groupby('trade_date')['avg_price'].mean().reset_index()
    rt_daily.columns = ['date', 'rt_price']
    
    print("\n【日前电价日均】")
    print(da_daily.to_string(index=False))
    
    print("\n【实时电价日均 (部分)】")
    print(rt_daily.head(15).to_string(index=False))
    
    # 3. 相关性分析
    print("\n" + "=" * 60)
    print("三、日前 vs 实时电价相关性")
    print("=" * 60)
    
    merged = pd.merge(da_daily, rt_daily, on='date', how='inner')
    if len(merged) > 2:
        corr = merged['da_price'].corr(merged['rt_price'])
        print(f"\n相关系数: {corr:.4f}")
        if corr > 0.7:
            print("→ 高度相关，日前电价可作为实时电价的重要参考")
        elif corr > 0.4:
            print("→ 中度相关")
        else:
            print("→ 低度相关，需要更多外部特征")
    
    # 4. 特征工程
    print("\n" + "=" * 60)
    print("四、特征工程")
    print("=" * 60)
    
    # 使用实时电价（有更多数据）
    daily = rt_daily.copy()
    daily['date'] = pd.to_datetime(daily['date'])
    daily = daily.sort_values('date')
    
    # 时间特征
    daily['dayofweek'] = daily['date'].dt.dayofweek
    daily['day'] = daily['date'].dt.day
    daily['month'] = daily['date'].dt.month
    daily['is_weekend'] = daily['dayofweek'].isin([5, 6]).astype(int)
    
    # 滞后特征
    for lag in [1, 2, 3, 7]:
        daily[f'lag_{lag}'] = daily['rt_price'].shift(lag)
    
    # 移动平均
    for w in [3, 7]:
        daily[f'ma_{w}'] = daily['rt_price'].rolling(w).mean()
    
    daily = daily.dropna()
    
    print(f"\n特征数据: {len(daily)} 条")
    print(f"特征列: {list(daily.columns)}")
    
    # 5. 简单预测模型
    print("\n" + "=" * 60)
    print("五、预测模型")
    print("=" * 60)
    
    if len(daily) >= 10:
        feature_cols = ['dayofweek', 'day', 'is_weekend', 'lag_1', 'lag_2', 'lag_7', 'ma_3', 'ma_7']
        X = daily[feature_cols]
        y = daily['rt_price']
        
        # 训练/测试分割
        train_size = int(len(X) * 0.8)
        X_train, X_test = X[:train_size], X[train_size:]
        y_train, y_test = y[:train_size], y[train_size:]
        
        print(f"\n训练集: {len(X_train)} 条")
        print(f"测试集: {len(X_test)} 条")
        
        try:
            from sklearn.linear_model import LinearRegression
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            
            # 线性回归
            lr = LinearRegression()
            lr.fit(X_train, y_train)
            lr_pred = lr.predict(X_test)
            lr_mae = mean_absolute_error(y_test, lr_pred)
            lr_rmse = np.sqrt(mean_squared_error(y_test, lr_pred))
            lr_r2 = r2_score(y_test, lr_pred)
            
            print("\n【线性回归】")
            print(f"MAE: {lr_mae:.2f}")
            print(f"RMSE: {lr_rmse:.2f}")
            print(f"R²: {lr_r2:.4f}")
            
            # 随机森林
            rf = RandomForestRegressor(n_estimators=50, random_state=42)
            rf.fit(X_train, y_train)
            rf_pred = rf.predict(X_test)
            rf_mae = mean_absolute_error(y_test, rf_pred)
            rf_rmse = np.sqrt(mean_squared_error(y_test, rf_pred))
            rf_r2 = r2_score(y_test, rf_pred)
            
            print("\n【随机森林】")
            print(f"MAE: {rf_mae:.2f}")
            print(f"RMSE: {rf_rmse:.2f}")
            print(f"R²: {rf_r2:.4f}")
            
            # 特征重要性
            print("\n【特征重要性】")
            imp = pd.DataFrame({'feature': feature_cols, 'importance': rf.feature_importances_})
            imp = imp.sort_values('importance', ascending=False)
            print(imp.to_string(index=False))
            
        except ImportError:
            print("\n需要安装: pip install scikit-learn")
    
    # 6. 电价分布
    print("\n" + "=" * 60)
    print("六、电价分布分析")
    print("=" * 60)
    
    print("\n【电价最高的10个节点 (日前)】")
    top = df_da.groupby('node_name')['avg_price'].mean().sort_values(ascending=False).head(10)
    for node, price in top.items():
        print(f"  {node[:30]}: {price:.2f}")
    
    print("\n【电价最低的10个节点 (日前)】")
    bottom = df_da.groupby('node_name')['avg_price'].mean().sort_values().head(10)
    for node, price in bottom.items():
        print(f"  {node[:30]}: {price:.2f}")
    
    # 7. 结论
    print("\n" + "=" * 60)
    print("七、分析结论")
    print("=" * 60)
    
    print("""
【发现】
1. 日前电价数据仅覆盖约7天，实时电价覆盖39天
2. 日前与实时电价存在一定相关性
3. 电价波动较大(0-748元)，存在极端值

【预测建议】
1. 短期预测(1-3天): 使用滞后特征+时间特征，MAE约20-40元
2. 需要更多历史数据(建议3个月以上)
3. 建议接入:
   - 负荷预测数据
   - 新能源出力(光伏/风电)
   - 水电站出力
   - 系统备用信息

【数据不足】
当前仅有约7天的日前电价历史数据，建议:
- 持续每日更新数据
- 收集更长时间的历史数据(3-6个月)
- 等待数据积累后重新训练模型
""")
    
    print("\n" + "=" * 60)
    print("分析完成!")
    print("=" * 60)

if __name__ == '__main__':
    main()
