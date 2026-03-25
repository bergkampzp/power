import sqlite3

conn = sqlite3.connect('../power-data/power_market_v2.db')
cur = conn.cursor()

# 列出所有表
cur.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = [r[0] for r in cur.fetchall()]
print("=== 数据库表 ===")
print(tables)

# 检查每个表的记录数
print("\n=== 表记录数 ===")
for table in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0]
        print(f"{table}: {count} 条")
    except Exception as e:
        print(f"{table}: 错误 - {e}")

# 检查分时电价数据
print("\n=== 分时电价测试 ===")
cur.execute("SELECT COUNT(*) FROM day_ahead_demand WHERE trade_date = '2026-03-10'")
print(f"day_ahead_demand 2026-03-10: {cur.fetchone()[0]} 条")

# 检查实时电价分时数据
print("\n=== 实时电价测试 ===")
cur.execute("SELECT COUNT(*) FROM realtime_hourly_price")
print(f"realtime_hourly_price: {cur.fetchone()[0]} 条")

conn.close()
