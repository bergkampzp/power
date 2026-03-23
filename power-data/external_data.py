#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外部数据接入模块
- 负荷预测数据
- 新能源出力(光伏/风电)
- 水电站出力
- 系统备用信息
"""

import sqlite3
import pandas as pd
import os

DB_PATH = '/home/zp/clawd/projects/power-supply/electrate-clone/power-data/power_market.db'

def create_external_tables():
    """创建外部数据表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 负荷预测数据
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS load_forecast (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            period TEXT,
            forecast_load REAL,
            actual_load REAL,
            unit TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. 新能源出力数据
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS renewable_output (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            period TEXT,
            solar_output REAL,    -- 光伏出力
            wind_output REAL,    -- 风电出力
            total_renewable REAL, -- 新能源总出力
            unit TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 3. 水电站出力数据
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hydro_output (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            period TEXT,
            plant_name TEXT,
            output REAL,
            capacity REAL,
            utilization_rate REAL,
            unit TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 4. 系统备用信息
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_reserve (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            period TEXT,
            positive_reserve REAL,  -- 正备用
            negative_reserve REAL,  -- 负备用
            reserve_type TEXT,
            unit TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 5. 电网运行数据汇总
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grid_operation (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            period TEXT,
            total_load REAL,
            thermal_load REAL,     -- 火电出力
            hydro_load REAL,      -- 水电出力
            solar_load REAL,      -- 光伏出力
            wind_load REAL,       -- 风电出力
            nuclear_load REAL,    -- 核电出力
            import_power REAL,    -- 外送电力
            unit TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("外部数据表创建完成!")

def import_from_oneclick_export():
    """从一键导出数据导入外部数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    import glob
    import re
    
    export_dir = '/home/zp/clawd/projects/power-supply/electrate-clone/power-data/一键导出-2月/extracted/output'
    
    if not os.path.exists(export_dir):
        print(f"目录不存在: {export_dir}")
        conn.close()
        return
    
    files = os.listdir(export_dir)
    print(f"找到 {len(files)} 个文件")
    
    # 按文件类型分类处理
    for f in files:
        try:
            # 从文件名提取日期
            match = re.search(r'(\d{8})', f)
            if match:
                trade_date = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:8]}"
            else:
                continue
            
            file_path = os.path.join(export_dir, f)
            
            # 尝试读取Excel文件
            try:
                df = pd.read_excel(file_path)
                
                # 根据sheet名或列名判断数据类型
                sheet_name = f.lower()
                
                # 负荷相关
                if '负荷' in f:
                    print(f"  处理负荷数据: {f[:30]}")
                    for _, row in df.iterrows():
                        try:
                            # 根据实际列名调整
                            cursor.execute('''
                                INSERT INTO load_forecast (trade_date, period, forecast_load)
                                VALUES (?, ?, ?)
                            ''', [trade_date, str(row.iloc[0]) if len(row) > 0 else None, 
                                  row.iloc[1] if len(row) > 1 else None])
                        except:
                            pass
                
                # 新能源相关
                elif '新能源' in f or '光伏' in f or '风电' in f:
                    print(f"  处理新能源数据: {f[:30]}")
                
                # 水电相关
                elif '水电' in f or '水电机组' in f:
                    print(f"  处理水电数据: {f[:30]}")
                
                # 备用相关
                elif '备用' in f:
                    print(f"  处理备用数据: {f[:30]}")
                    for _, row in df.iterrows():
                        try:
                            if len(row) >= 2:
                                cursor.execute('''
                                    INSERT INTO system_reserve (trade_date, period, positive_reserve)
                                    VALUES (?, ?, ?)
                                ''', [trade_date, str(row.iloc[0]) if pd.notna(row.iloc[0]) else None,
                                      row.iloc[1] if len(row) > 1 and pd.notna(row.iloc[1]) else None])
                        except:
                            pass
                
            except Exception as e:
                pass
        
        except Exception as e:
            continue
    
    conn.commit()
    conn.close()
    print("一键导出数据导入完成!")

def get_statistics():
    """获取数据统计"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n=== 数据库统计 ===")
    
    tables = ['day_ahead_node_price', 'realtime_node_price', 
             'day_ahead_demand', 'realtime_demand',
             'load_forecast', 'renewable_output', 
             'hydro_output', 'system_reserve', 'grid_operation']
    
    for table in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"{table}: {count} 条")
        except:
            pass
    
    conn.close()

if __name__ == '__main__':
    print("=" * 50)
    print("外部数据接入模块")
    print("=" * 50)
    
    # 创建外部数据表
    create_external_tables()
    
    # 尝试从一键导出导入
    import_from_oneclick_export()
    
    # 显示统计
    get_statistics()
    
    print("\n完成!")
