#!/usr/bin/env python3
"""
数据库优化脚本 - 创建索引和优化配置
"""
import sqlite3
import os

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'power-data', 'power_market_v2.db')

def optimize_database():
    """执行数据库优化"""
    print(f"正在连接数据库: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 启用性能优化PRAGMA
        print("\n1. 配置数据库性能参数...")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA cache_size = -8000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        print("   ✓ PRAGMA配置完成")
        
        # 获取当前索引数量
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
        initial_index_count = cursor.fetchone()[0]
        print(f"\n2. 当前索引数量: {initial_index_count}")
        
        # 创建索引
        indexes = [
            # 第1组: 日期时间索引
            ("idx_day_ahead_node_price_date", "day_ahead_node_price", "trade_date"),
            ("idx_day_ahead_demand_date", "day_ahead_demand", "trade_date"),
            ("idx_renewable_output_date", "renewable_output", "trade_date"),
            ("idx_load_forecast_date", "load_forecast", "trade_date"),
            ("idx_hydro_output_date", "hydro_output", "trade_date"),
            ("idx_system_reserve_date", "system_reserve", "trade_date"),
            
            # 第2组: 日期+周期复合索引
            ("idx_day_ahead_demand_date_period", "day_ahead_demand", "trade_date, period"),
            ("idx_renewable_output_date_period", "renewable_output", "trade_date, period"),
            ("idx_load_forecast_date_period", "load_forecast", "trade_date, period"),
            ("idx_hydro_output_date_period", "hydro_output", "trade_date, period"),
            ("idx_system_reserve_date_period", "system_reserve", "trade_date, period"),
            
            # 第3组: 节点/区域索引
            ("idx_day_ahead_node_price_node", "day_ahead_node_price", "node_name"),
            ("idx_day_ahead_node_price_region", "day_ahead_node_price", "region"),
            ("idx_day_ahead_node_price_region_date_node", "day_ahead_node_price", "region, trade_date, node_name"),
            
            # 第4组: 植物/站点索引
            ("idx_hydro_output_plant", "hydro_output", "plant_name"),
            ("idx_hydro_output_plant_date", "hydro_output", "plant_name, trade_date"),
        ]
        
        print("\n3. 创建索引...")
        created_count = 0
        for idx_name, table, columns in indexes:
            try:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
                created_count += 1
                print(f"   ✓ {idx_name}")
            except Exception as e:
                print(f"   ✗ {idx_name}: {e}")
        
        print(f"\n   共创建/验证 {created_count} 个索引")
        
        # 统计信息分析
        print("\n4. 更新统计信息 (ANALYZE)...")
        cursor.execute("ANALYZE")
        print("   ✓ 统计信息更新完成")
        
        # 提交事务
        conn.commit()
        
        # 验证索引
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
        final_index_count = cursor.fetchone()[0]
        print(f"\n5. 优化完成!")
        print(f"   初始索引数: {initial_index_count}")
        print(f"   最终索引数: {final_index_count}")
        print(f"   新增索引: {final_index_count - initial_index_count}")
        
        # 显示所有索引
        print("\n6. 索引列表:")
        cursor.execute("""
            SELECT name, tbl_name 
            FROM sqlite_master 
            WHERE type='index' 
            ORDER BY tbl_name, name
        """)
        for row in cursor.fetchall():
            print(f"   - {row[0]} (表: {row[1]})")
        
        # 测试查询性能
        print("\n7. 测试查询性能...")
        import time
        
        # 测试1: 按日期范围查询
        start = time.time()
        cursor.execute("""
            SELECT trade_date, AVG(avg_price) 
            FROM day_ahead_node_price 
            WHERE trade_date >= '2026-02-01' AND trade_date <= '2026-03-24'
            GROUP BY trade_date
        """)
        cursor.fetchall()
        duration1 = (time.time() - start) * 1000
        print(f"   日期范围查询: {duration1:.2f}ms")
        
        # 测试2: 按节点查询
        start = time.time()
        cursor.execute("""
            SELECT * FROM day_ahead_node_price 
            WHERE node_name = '节点A' 
            AND trade_date >= '2026-02-01'
            LIMIT 100
        """)
        cursor.fetchall()
        duration2 = (time.time() - start) * 1000
        print(f"   节点查询: {duration2:.2f}ms")
        
        print("\n✅ 数据库优化全部完成!")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    optimize_database()
