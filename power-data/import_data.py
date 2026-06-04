#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力市场数据库 - 数据导入脚本
SQLite 版本
"""

import sqlite3
import pandas as pd
import re
import glob
import os

# 数据库路径
from config import DB_PATH, OUTPUT_DIR
DATA_DIR = OUTPUT_DIR

def create_connection():
    return sqlite3.connect(DB_PATH)

def create_tables():
    """创建所有表"""
    conn = create_connection()
    cursor = conn.cursor()
    
    # 日前节点电价
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS day_ahead_node_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            region TEXT NOT NULL,
            node_name TEXT NOT NULL,
            period_00_00 REAL, period_00_15 REAL, period_00_30 REAL, period_00_45 REAL,
            period_01_00 REAL, period_01_15 REAL, period_01_30 REAL, period_01_45 REAL,
            period_02_00 REAL, period_02_15 REAL, period_02_30 REAL, period_02_45 REAL,
            period_03_00 REAL, period_03_15 REAL, period_03_30 REAL, period_03_45 REAL,
            period_04_00 REAL, period_04_15 REAL, period_04_30 REAL, period_04_45 REAL,
            period_05_00 REAL, period_05_15 REAL, period_05_30 REAL, period_05_45 REAL,
            period_06_00 REAL, period_06_15 REAL, period_06_30 REAL, period_06_45 REAL,
            period_07_00 REAL, period_07_15 REAL, period_07_30 REAL, period_07_45 REAL,
            period_08_00 REAL, period_08_15 REAL, period_08_30 REAL, period_08_45 REAL,
            period_09_00 REAL, period_09_15 REAL, period_09_30 REAL, period_09_45 REAL,
            period_10_00 REAL, period_10_15 REAL, period_10_30 REAL, period_10_45 REAL,
            period_11_00 REAL, period_11_15 REAL, period_11_30 REAL, period_11_45 REAL,
            period_12_00 REAL, period_12_15 REAL, period_12_30 REAL, period_12_45 REAL,
            period_13_00 REAL, period_13_15 REAL, period_13_30 REAL, period_13_45 REAL,
            period_14_00 REAL, period_14_15 REAL, period_14_30 REAL, period_14_45 REAL,
            period_15_00 REAL, period_15_15 REAL, period_15_30 REAL, period_15_45 REAL,
            period_16_00 REAL, period_16_15 REAL, period_16_30 REAL, period_16_45 REAL,
            period_17_00 REAL, period_17_15 REAL, period_17_30 REAL, period_17_45 REAL,
            period_18_00 REAL, period_18_15 REAL, period_18_30 REAL, period_18_45 REAL,
            period_19_00 REAL, period_19_15 REAL, period_19_30 REAL, period_19_45 REAL,
            period_20_00 REAL, period_20_15 REAL, period_20_30 REAL, period_20_45 REAL,
            period_21_00 REAL, period_21_15 REAL, period_21_30 REAL, period_21_45 REAL,
            period_22_00 REAL, period_22_15 REAL, period_22_30 REAL, period_22_45 REAL,
            period_23_00 REAL, period_23_15 REAL, period_23_30 REAL, period_23_45 REAL,
            UNIQUE(trade_date, node_name)
        )
    ''')
    
    # 实时节点电价
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS realtime_node_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            region TEXT NOT NULL,
            node_name TEXT NOT NULL,
            period_00_00 REAL, period_00_15 REAL, period_00_30 REAL, period_00_45 REAL,
            period_01_00 REAL, period_01_15 REAL, period_01_30 REAL, period_01_45 REAL,
            period_02_00 REAL, period_02_15 REAL, period_02_30 REAL, period_02_45 REAL,
            period_03_00 REAL, period_03_15 REAL, period_03_30 REAL, period_03_45 REAL,
            period_04_00 REAL, period_04_15 REAL, period_04_30 REAL, period_04_45 REAL,
            period_05_00 REAL, period_05_15 REAL, period_05_30 REAL, period_05_45 REAL,
            period_06_00 REAL, period_06_15 REAL, period_06_30 REAL, period_06_45 REAL,
            period_07_00 REAL, period_07_15 REAL, period_07_30 REAL, period_07_45 REAL,
            period_08_00 REAL, period_08_15 REAL, period_08_30 REAL, period_08_45 REAL,
            period_09_00 REAL, period_09_15 REAL, period_09_30 REAL, period_09_45 REAL,
            period_10_00 REAL, period_10_15 REAL, period_10_30 REAL, period_10_45 REAL,
            period_11_00 REAL, period_11_15 REAL, period_11_30 REAL, period_11_45 REAL,
            period_12_00 REAL, period_12_15 REAL, period_12_30 REAL, period_12_45 REAL,
            period_13_00 REAL, period_13_15 REAL, period_13_30 REAL, period_13_45 REAL,
            period_14_00 REAL, period_14_15 REAL, period_14_30 REAL, period_14_45 REAL,
            period_15_00 REAL, period_15_15 REAL, period_15_30 REAL, period_15_45 REAL,
            period_16_00 REAL, period_16_15 REAL, period_16_30 REAL, period_16_45 REAL,
            period_17_00 REAL, period_17_15 REAL, period_17_30 REAL, period_17_45 REAL,
            period_18_00 REAL, period_18_15 REAL, period_18_30 REAL, period_18_45 REAL,
            period_19_00 REAL, period_19_15 REAL, period_19_30 REAL, period_19_45 REAL,
            period_20_00 REAL, period_20_15 REAL, period_20_30 REAL, period_20_45 REAL,
            period_21_00 REAL, period_21_15 REAL, period_21_30 REAL, period_21_45 REAL,
            period_22_00 REAL, period_22_15 REAL, period_22_30 REAL, period_22_45 REAL,
            period_23_00 REAL, period_23_15 REAL, period_23_30 REAL, period_23_45 REAL,
            UNIQUE(trade_date, node_name)
        )
    ''')
    
    # 日前用电侧
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS day_ahead_demand_result (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            period TEXT,
            demand REAL,
            price REAL
        )
    ''')
    
    # 实时用电侧
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS realtime_demand_result (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            period TEXT,
            demand REAL,
            price REAL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("表创建完成!")

def import_day_ahead_node_price():
    """导入日前节点电价"""
    conn = create_connection()
    cursor = conn.cursor()
    
    dir_path = os.path.join(DATA_DIR, '日前节点电价2-3月')
    files = glob.glob(os.path.join(dir_path, '*.xlsx'))
    print(f"\n=== 导入日前节点电价: {len(files)} 个文件 ===")
    
    total_records = 0
    
    for i, file in enumerate(files):
        try:
            # 从文件名提取日期
            filename = os.path.basename(file)
            match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if not match:
                continue
            trade_date = match.group(1)
            
            # 读取Excel - 跳过第一行表头
            df = pd.read_excel(file, header=1)
            
            # 重命名列
            df.columns = ['region', 'node_name'] + [f'period_{c}' for c in df.columns[2:]]
            
            # 插入数据
            for _, row in df.iterrows():
                try:
                    region = row['region']
                    node_name = row['node_name']
                    if pd.isna(region) or pd.isna(node_name):
                        continue
                    
                    values = [trade_date, str(region), str(node_name)]
                    cols = ['trade_date', 'region', 'node_name']
                    
                    for col in df.columns[2:]:
                        val = row[col]
                        if pd.notna(val):
                            try:
                                values.append(float(val))
                                cols.append(col)
                            except:
                                pass
                    
                    placeholders = ','.join(['?' for _ in values])
                    col_names = ','.join(cols)
                    sql = f'INSERT OR REPLACE INTO day_ahead_node_price ({col_names}) VALUES ({placeholders})'
                    cursor.execute(sql, values)
                    total_records += 1
                except:
                    continue
            
            if (i + 1) % 5 == 0:
                conn.commit()
                print(f"  已处理 {i+1}/{len(files)} 文件, {total_records} 条记录...")
                
        except Exception as e:
            print(f"  错误: {file} - {e}")
            continue
    
    conn.commit()
    print(f"  总记录数: {total_records}")
    conn.close()

def import_realtime_node_price():
    """导入实时节点电价"""
    conn = create_connection()
    cursor = conn.cursor()
    
    dir_path = os.path.join(DATA_DIR, '实时节点电价')
    files = glob.glob(os.path.join(dir_path, '*实时节点电价*.xlsx'))
    print(f"\n=== 导入实时节点电价: {len(files)} 个文件 ===")
    
    total_records = 0
    
    for i, file in enumerate(files):
        try:
            filename = os.path.basename(file)
            match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if not match:
                continue
            trade_date = match.group(1)
            
            df = pd.read_excel(file, header=1)
            df.columns = ['region', 'node_name'] + [f'period_{c}' for c in df.columns[2:]]
            
            for _, row in df.iterrows():
                try:
                    region = row['region']
                    node_name = row['node_name']
                    if pd.isna(region) or pd.isna(node_name):
                        continue
                    
                    values = [trade_date, str(region), str(node_name)]
                    cols = ['trade_date', 'region', 'node_name']
                    
                    for col in df.columns[2:]:
                        val = row[col]
                        if pd.notna(val):
                            try:
                                values.append(float(val))
                                cols.append(col)
                            except:
                                pass
                    
                    placeholders = ','.join(['?' for _ in values])
                    col_names = ','.join(cols)
                    sql = f'INSERT OR REPLACE INTO realtime_node_price ({col_names}) VALUES ({placeholders})'
                    cursor.execute(sql, values)
                    total_records += 1
                except:
                    continue
            
            if (i + 1) % 5 == 0:
                conn.commit()
                print(f"  已处理 {i+1}/{len(files)} 文件, {total_records} 条记录...")
                
        except Exception as e:
            continue
    
    conn.commit()
    print(f"  总记录数: {total_records}")
    conn.close()

def import_demand_data():
    """导入用电侧数据"""
    conn = create_connection()
    cursor = conn.cursor()
    
    # 日前用电侧
    dir_path = os.path.join(DATA_DIR, '日前用电侧数据2-3月')
    if os.path.exists(dir_path):
        files = glob.glob(os.path.join(dir_path, '*.xls*'))
        print(f"\n=== 导入日前用电侧: {len(files)} 个文件 ===")
        
        total = 0
        for file in files:
            try:
                filename = os.path.basename(file)
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    trade_date = match.group(1)
                else:
                    continue
                
                df = pd.read_excel(file)
                for _, row in df.iterrows():
                    try:
                        if len(row) >= 3 and pd.notna(row.iloc[0]):
                            cursor.execute(
                                "INSERT INTO day_ahead_demand_result (trade_date, period, demand, price) VALUES (?, ?, ?, ?)",
                                [trade_date, str(row.iloc[0]), row.iloc[1] if pd.notna(row.iloc[1]) else None, row.iloc[2] if pd.notna(row.iloc[2]) else None]
                            )
                            total += 1
                    except:
                        continue
            except:
                continue
        
        conn.commit()
        print(f"  日前用电侧: {total} 条")
    
    # 实时用电侧
    dir_path = os.path.join(DATA_DIR, '实时节点电价')
    if os.path.exists(dir_path):
        files = glob.glob(os.path.join(dir_path, '*用电侧*.xls'))
        print(f"\n=== 导入实时用电侧: {len(files)} 个文件 ===")
        
        total = 0
        for file in files:
            try:
                filename = os.path.basename(file)
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    trade_date = match.group(1)
                else:
                    continue
                
                df = pd.read_excel(file)
                for _, row in df.iterrows():
                    try:
                        if len(row) >= 3 and pd.notna(row.iloc[0]):
                            cursor.execute(
                                "INSERT INTO realtime_demand_result (trade_date, period, demand, price) VALUES (?, ?, ?, ?)",
                                [trade_date, str(row.iloc[0]), row.iloc[1] if pd.notna(row.iloc[1]) else None, row.iloc[2] if pd.notna(row.iloc[2]) else None]
                            )
                            total += 1
                    except:
                        continue
            except:
                continue
        
        conn.commit()
        print(f"  实时用电侧: {total} 条")
    
    conn.close()

if __name__ == '__main__':
    print("=" * 50)
    print("电力市场数据库 - 数据导入")
    print("=" * 50)
    
    create_tables()
    import_day_ahead_node_price()
    import_realtime_node_price()
    import_demand_data()
    
    # 显示统计
    conn = create_connection()
    cursor = conn.cursor()
    print("\n=== 最终统计 ===")
    for table in ['day_ahead_node_price', 'realtime_node_price', 'day_ahead_demand_result', 'realtime_demand_result']:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        print(f"{table}: {cursor.fetchone()[0]} 条")
    conn.close()
    
    print(f"\n数据库: {DB_PATH}")
