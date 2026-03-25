import sqlite3

conn = sqlite3.connect('../power-data/power_market_v2.db')
cur = conn.cursor()

# 检查 day_ahead_demand 表结构
print("=== day_ahead_demand 表结构 ===")
cur.execute("PRAGMA table_info(day_ahead_demand)")
for row in cur.fetchall():
    print(row)

# 检查 day_ahead_demand 数据样本
print("\n=== day_ahead_demand 数据样本 ===")
cur.execute("SELECT * FROM day_ahead_demand WHERE trade_date = '2026-03-10' LIMIT 5")
for row in cur.fetchall():
    print(row)

# 检查 realtime_hourly_price 表结构
print("\n=== realtime_hourly_price 表结构 ===")
cur.execute("PRAGMA table_info(realtime_hourly_price)")
for row in cur.fetchall():
    print(row)

# 检查 realtime_hourly_price 数据样本
print("\n=== realtime_hourly_price 数据样本 ===")
cur.execute("SELECT * FROM realtime_hourly_price LIMIT 5")
for row in cur.fetchall():
    print(row)

conn.close()
