#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电力市场数据库建表脚本
PostgreSQL + TimescaleDB
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'zp',
    'password': 'zp',
    'database': 'power_market'
}

# 创建表的SQL语句
CREATE_TABLES_SQL = """
-- 1. 日前节点电价表
DROP TABLE IF EXISTS day_ahead_node_price CASCADE;
CREATE TABLE day_ahead_node_price (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    node_name VARCHAR(200) NOT NULL,
    period_00_15 DECIMAL(10,2),
    period_00_30 DECIMAL(10,2),
    period_00_45 DECIMAL(10,2),
    period_01_00 DECIMAL(10,2),
    period_01_15 DECIMAL(10,2),
    period_01_30 DECIMAL(10,2),
    period_01_45 DECIMAL(10,2),
    period_02_00 DECIMAL(10,2),
    period_02_15 DECIMAL(10,2),
    period_02_30 DECIMAL(10,2),
    period_02_45 DECIMAL(10,2),
    period_03_00 DECIMAL(10,2),
    period_03_15 DECIMAL(10,2),
    period_03_30 DECIMAL(10,2),
    period_03_45 DECIMAL(10,2),
    period_04_00 DECIMAL(10,2),
    period_04_15 DECIMAL(10,2),
    period_04_30 DECIMAL(10,2),
    period_04_45 DECIMAL(10,2),
    period_05_00 DECIMAL(10,2),
    period_05_15 DECIMAL(10,2),
    period_05_30 DECIMAL(10,2),
    period_05_45 DECIMAL(10,2),
    period_06_00 DECIMAL(10,2),
    period_06_15 DECIMAL(10,2),
    period_06_30 DECIMAL(10,2),
    period_06_45 DECIMAL(10,2),
    period_07_00 DECIMAL(10,2),
    period_07_15 DECIMAL(10,2),
    period_07_30 DECIMAL(10,2),
    period_07_45 DECIMAL(10,2),
    period_08_00 DECIMAL(10,2),
    period_08_15 DECIMAL(10,2),
    period_08_30 DECIMAL(10,2),
    period_08_45 DECIMAL(10,2),
    period_09_00 DECIMAL(10,2),
    period_09_15 DECIMAL(10,2),
    period_09_30 DECIMAL(10,2),
    period_09_45 DECIMAL(10,2),
    period_10_00 DECIMAL(10,2),
    period_10_15 DECIMAL(10,2),
    period_10_30 DECIMAL(10,2),
    period_10_45 DECIMAL(10,2),
    period_11_00 DECIMAL(10,2),
    period_11_15 DECIMAL(10,2),
    period_11_30 DECIMAL(10,2),
    period_11_45 DECIMAL(10,2),
    period_12_00 DECIMAL(10,2),
    period_12_15 DECIMAL(10,2),
    period_12_30 DECIMAL(10,2),
    period_12_45 DECIMAL(10,2),
    period_13_00 DECIMAL(10,2),
    period_13_15 DECIMAL(10,2),
    period_13_30 DECIMAL(10,2),
    period_13_45 DECIMAL(10,2),
    period_14_00 DECIMAL(10,2),
    period_14_15 DECIMAL(10,2),
    period_14_30 DECIMAL(10,2),
    period_14_45 DECIMAL(10,2),
    period_15_00 DECIMAL(10,2),
    period_15_15 DECIMAL(10,2),
    period_15_30 DECIMAL(10,2),
    period_15_45 DECIMAL(10,2),
    period_16_00 DECIMAL(10,2),
    period_16_15 DECIMAL(10,2),
    period_16_30 DECIMAL(10,2),
    period_16_45 DECIMAL(10,2),
    period_17_00 DECIMAL(10,2),
    period_17_15 DECIMAL(10,2),
    period_17_30 DECIMAL(10,2),
    period_17_45 DECIMAL(10,2),
    period_18_00 DECIMAL(10,2),
    period_18_15 DECIMAL(10,2),
    period_18_30 DECIMAL(10,2),
    period_18_45 DECIMAL(10,2),
    period_19_00 DECIMAL(10,2),
    period_19_15 DECIMAL(10,2),
    period_19_30 DECIMAL(10,2),
    period_19_45 DECIMAL(10,2),
    period_20_00 DECIMAL(10,2),
    period_20_15 DECIMAL(10,2),
    period_20_30 DECIMAL(10,2),
    period_20_45 DECIMAL(10,2),
    period_21_00 DECIMAL(10,2),
    period_21_15 DECIMAL(10,2),
    period_21_30 DECIMAL(10,2),
    period_21_45 DECIMAL(10,2),
    period_22_00 DECIMAL(10,2),
    period_22_15 DECIMAL(10,2),
    period_22_30 DECIMAL(10,2),
    period_22_45 DECIMAL(10,2),
    period_23_00 DECIMAL(10,2),
    period_23_15 DECIMAL(10,2),
    period_23_30 DECIMAL(10,2),
    period_23_45 DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_da_node_price ON day_ahead_node_price(trade_date, node_name);
CREATE INDEX idx_da_price_date ON day_ahead_node_price(trade_date);
CREATE INDEX idx_da_price_node ON day_ahead_node_price(node_name);

-- 2. 实时节点电价表
DROP TABLE IF EXISTS realtime_node_price CASCADE;
CREATE TABLE realtime_node_price (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    node_name VARCHAR(200) NOT NULL,
    period_00_15 DECIMAL(10,2),
    period_00_30 DECIMAL(10,2),
    period_00_45 DECIMAL(10,2),
    period_01_00 DECIMAL(10,2),
    period_01_15 DECIMAL(10,2),
    period_01_30 DECIMAL(10,2),
    period_01_45 DECIMAL(10,2),
    period_02_00 DECIMAL(10,2),
    period_02_15 DECIMAL(10,2),
    period_02_30 DECIMAL(10,2),
    period_02_45 DECIMAL(10,2),
    period_03_00 DECIMAL(10,2),
    period_03_15 DECIMAL(10,2),
    period_03_30 DECIMAL(10,2),
    period_03_45 DECIMAL(10,2),
    period_04_00 DECIMAL(10,2),
    period_04_15 DECIMAL(10,2),
    period_04_30 DECIMAL(10,2),
    period_04_45 DECIMAL(10,2),
    period_05_00 DECIMAL(10,2),
    period_05_15 DECIMAL(10,2),
    period_05_30 DECIMAL(10,2),
    period_05_45 DECIMAL(10,2),
    period_06_00 DECIMAL(10,2),
    period_06_15 DECIMAL(10,2),
    period_06_30 DECIMAL(10,2),
    period_06_45 DECIMAL(10,2),
    period_07_00 DECIMAL(10,2),
    period_07_15 DECIMAL(10,2),
    period_07_30 DECIMAL(10,2),
    period_07_45 DECIMAL(10,2),
    period_08_00 DECIMAL(10,2),
    period_08_15 DECIMAL(10,2),
    period_08_30 DECIMAL(10,2),
    period_08_45 DECIMAL(10,2),
    period_09_00 DECIMAL(10,2),
    period_09_15 DECIMAL(10,2),
    period_09_30 DECIMAL(10,2),
    period_09_45 DECIMAL(10,2),
    period_10_00 DECIMAL(10,2),
    period_10_15 DECIMAL(10,2),
    period_10_30 DECIMAL(10,2),
    period_10_45 DECIMAL(10,2),
    period_11_00 DECIMAL(10,2),
    period_11_15 DECIMAL(10,2),
    period_11_30 DECIMAL(10,2),
    period_11_45 DECIMAL(10,2),
    period_12_00 DECIMAL(10,2),
    period_12_15 DECIMAL(10,2),
    period_12_30 DECIMAL(10,2),
    period_12_45 DECIMAL(10,2),
    period_13_00 DECIMAL(10,2),
    period_13_15 DECIMAL(10,2),
    period_13_30 DECIMAL(10,2),
    period_13_45 DECIMAL(10,2),
    period_14_00 DECIMAL(10,2),
    period_14_15 DECIMAL(10,2),
    period_14_30 DECIMAL(10,2),
    period_14_45 DECIMAL(10,2),
    period_15_00 DECIMAL(10,2),
    period_15_15 DECIMAL(10,2),
    period_15_30 DECIMAL(10,2),
    period_15_45 DECIMAL(10,2),
    period_16_00 DECIMAL(10,2),
    period_16_15 DECIMAL(10,2),
    period_16_30 DECIMAL(10,2),
    period_16_45 DECIMAL(10,2),
    period_17_00 DECIMAL(10,2),
    period_17_15 DECIMAL(10,2),
    period_17_30 DECIMAL(10,2),
    period_17_45 DECIMAL(10,2),
    period_18_00 DECIMAL(10,2),
    period_18_15 DECIMAL(10,2),
    period_18_30 DECIMAL(10,2),
    period_18_45 DECIMAL(10,2),
    period_19_00 DECIMAL(10,2),
    period_19_15 DECIMAL(10,2),
    period_19_30 DECIMAL(10,2),
    period_19_45 DECIMAL(10,2),
    period_20_00 DECIMAL(10,2),
    period_20_15 DECIMAL(10,2),
    period_20_30 DECIMAL(10,2),
    period_20_45 DECIMAL(10,2),
    period_21_00 DECIMAL(10,2),
    period_21_15 DECIMAL(10,2),
    period_21_30 DECIMAL(10,2),
    period_21_45 DECIMAL(10,2),
    period_22_00 DECIMAL(10,2),
    period_22_15 DECIMAL(10,2),
    period_22_30 DECIMAL(10,2),
    period_22_45 DECIMAL(10,2),
    period_23_00 DECIMAL(10,2),
    period_23_15 DECIMAL(10,2),
    period_23_30 DECIMAL(10,2),
    period_23_45 DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_rt_node_price ON realtime_node_price(trade_date, node_name);
CREATE INDEX idx_rt_price_date ON realtime_node_price(trade_date);

-- 3. 日前用电侧交易结果
DROP TABLE IF EXISTS day_ahead_demand_result;
CREATE TABLE day_ahead_demand_result (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    period VARCHAR(10),
    demand DECIMAL(15,2),
    price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_da_demand_date ON day_ahead_demand_result(trade_date);

-- 4. 实时用电侧交易结果
DROP TABLE IF EXISTS realtime_demand_result;
CREATE TABLE realtime_demand_result (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    period VARCHAR(10),
    demand DECIMAL(15,2),
    price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_rt_demand_date ON realtime_demand_result(trade_date);

-- 5. 水电机组群电量上限
DROP TABLE IF EXISTS day_ahead_hydro_unit_limit;
CREATE TABLE day_ahead_hydro_unit_limit (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    seq_no INTEGER,
    region VARCHAR(50),
    unit_group_name VARCHAR(200),
    plant_name VARCHAR(200),
    unit_name VARCHAR(200),
    ratio DECIMAL(10,4),
    effect_time TIMESTAMP,
    expire_time TIMESTAMP,
    power_constraint DECIMAL(15,2),
    energy_constraint DECIMAL(15,2),
    max_mode_constraint VARCHAR(10),
    min_mode_constraint VARCHAR(10),
    max_energy DECIMAL(15,2),
    min_energy DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_hydro_limit_date ON day_ahead_hydro_unit_limit(trade_date);

-- 6. 高峰正备用信息
DROP TABLE IF EXISTS peak_reserve_info;
CREATE TABLE peak_reserve_info (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    period VARCHAR(10),
    reserve_type VARCHAR(50),
    reserve_value DECIMAL(15,2),
    unit VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_peak_reserve_date ON peak_reserve_info(trade_date);

-- 7. 稳定断面信息
DROP TABLE IF EXISTS stability_section_info;
CREATE TABLE stability_section_info (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    section_name VARCHAR(200),
    direction VARCHAR(50),
    stability_limit DECIMAL(15,2),
    unit VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_stability_date ON stability_section_info(trade_date);

-- 8. 断面约束及阻塞情况
DROP TABLE IF EXISTS section_constraint;
CREATE TABLE section_constraint (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    market_type VARCHAR(20),
    section_name VARCHAR(200),
    constraint_type VARCHAR(50),
    limit_value DECIMAL(15,2),
    actual_value DECIMAL(15,2),
    congestion_degree VARCHAR(20),
    period VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_section_constraint_date ON section_constraint(trade_date);

-- 9. 重要通道输电情况
DROP TABLE IF EXISTS transmission_channel;
CREATE TABLE transmission_channel (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    channel_name VARCHAR(200),
    power_flow DECIMAL(15,2),
    capacity DECIMAL(15,2),
    utilization_rate DECIMAL(10,4),
    period VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_transmission_date ON transmission_channel(trade_date);

-- 10. 电网负荷总体情况
DROP TABLE IF EXISTS grid_load_overview;
CREATE TABLE grid_load_overview (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    period VARCHAR(10),
    total_load DECIMAL(15,2),
    peak_load DECIMAL(15,2),
    valley_load DECIMAL(15,2),
    load_rate DECIMAL(10,4),
    unit VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_grid_load_date ON grid_load_overview(trade_date);

-- 11. 出力信息汇总表
DROP TABLE IF EXISTS output_summary;
CREATE TABLE output_summary (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    output_type VARCHAR(50) NOT NULL,
    period VARCHAR(10),
    value DECIMAL(15,2),
    unit VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_output_date ON output_summary(trade_date);
CREATE INDEX idx_output_type ON output_summary(output_type);

-- 12. 检修计划
DROP TABLE IF EXISTS maintenance_plan;
CREATE TABLE maintenance_plan (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    unit_name VARCHAR(200),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    description TEXT,
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_maintenance_date ON maintenance_plan(trade_date);

-- 13. 机组状态
DROP TABLE IF EXISTS unit_status;
CREATE TABLE unit_status (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    unit_name VARCHAR(200),
    unit_type VARCHAR(50),
    status VARCHAR(20),
    capacity DECIMAL(15,2),
    available_capacity DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_unit_status_date ON unit_status(trade_date);

-- 14. 系统备用信息
DROP TABLE IF EXISTS system_reserve;
CREATE TABLE system_reserve (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    reserve_type VARCHAR(50),
    period VARCHAR(10),
    reserve_value DECIMAL(15,2),
    unit VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_system_reserve_date ON system_reserve(trade_date);

-- 15. 省间联络线输电情况
DROP TABLE IF EXISTS inter_provincial_line;
CREATE TABLE inter_provincial_line (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    line_name VARCHAR(200),
    direction VARCHAR(50),
    power_flow DECIMAL(15,2),
    capacity DECIMAL(15,2),
    period VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_inter_provincial_date ON inter_provincial_line(trade_date);

-- 16. 实际输电断面约束情况
DROP TABLE IF EXISTS transmission_section;
CREATE TABLE transmission_section (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    section_name VARCHAR(200),
    direction VARCHAR(50),
    power_flow DECIMAL(15,2),
    limit_value DECIMAL(15,2),
    overload_ratio DECIMAL(10,4),
    period VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_transmission_section_date ON transmission_section(trade_date);

-- 17. 重要线路与变压器平均潮流
DROP TABLE IF EXISTS line_transformer_load;
CREATE TABLE line_transformer_load (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    equipment_name VARCHAR(200),
    equipment_type VARCHAR(50),
    avg_power DECIMAL(15,2),
    max_power DECIMAL(15,2),
    capacity DECIMAL(15,2),
    period VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_line_transformer_date ON line_transformer_load(trade_date);

-- 打印创建结果
SELECT 'Tables created successfully!' AS result;
"""


def create_database():
    """创建数据库"""
    try:
        # 连接到默认数据库
        conn = psycopg2.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # 检查数据库是否存在
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_CONFIG['database']}'")
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(f"CREATE DATABASE {DB_CONFIG['database']}")
            print(f"Database '{DB_CONFIG['database']}' created successfully!")
        else:
            print(f"Database '{DB_CONFIG['database']}' already exists.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error creating database: {e}")
        raise


def create_tables():
    """创建表"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 执行建表SQL
        cursor.execute(CREATE_TABLES_SQL)
        conn.commit()
        
        print("All tables created successfully!")
        
        # 列出所有表
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        
        tables = cursor.fetchall()
        print("\n=== Created Tables ===")
        for table in tables:
            print(f"  - {table[0]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error creating tables: {e}")
        raise


if __name__ == '__main__':
    print("=" * 50)
    print("电力市场数据库建表脚本")
    print("=" * 50)
    
    # 创建数据库
    create_database()
    
    # 创建表
    create_tables()
    
    print("\n完成!")
