-- ==========================================
-- 水电站电价预测系统 - SQLite 数据库优化脚本
-- 数据库: power_market_v2.db
-- ==========================================

-- 启用性能优化PRAGMA
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -8000;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ===== 第1组: 日期时间索引 (P0 - 必需) =====
CREATE INDEX IF NOT EXISTS idx_day_ahead_node_price_date 
  ON day_ahead_node_price(trade_date);

CREATE INDEX IF NOT EXISTS idx_day_ahead_demand_date 
  ON day_ahead_demand(trade_date);

CREATE INDEX IF NOT EXISTS idx_renewable_output_date 
  ON renewable_output(trade_date);

CREATE INDEX IF NOT EXISTS idx_load_forecast_date 
  ON load_forecast(trade_date);

CREATE INDEX IF NOT EXISTS idx_hydro_output_date 
  ON hydro_output(trade_date);

CREATE INDEX IF NOT EXISTS idx_system_reserve_date 
  ON system_reserve(trade_date);

-- ===== 第2组: 日期+周期复合索引 (P0 - 必需) =====
CREATE INDEX IF NOT EXISTS idx_day_ahead_demand_date_period 
  ON day_ahead_demand(trade_date, period);

CREATE INDEX IF NOT EXISTS idx_renewable_output_date_period 
  ON renewable_output(trade_date, period);

CREATE INDEX IF NOT EXISTS idx_load_forecast_date_period 
  ON load_forecast(trade_date, period);

CREATE INDEX IF NOT EXISTS idx_hydro_output_date_period 
  ON hydro_output(trade_date, period);

CREATE INDEX IF NOT EXISTS idx_system_reserve_date_period 
  ON system_reserve(trade_date, period);

-- ===== 第3组: 节点/区域索引 (P1 - 推荐) =====
CREATE INDEX IF NOT EXISTS idx_day_ahead_node_price_node 
  ON day_ahead_node_price(node_name);

CREATE INDEX IF NOT EXISTS idx_day_ahead_node_price_region 
  ON day_ahead_node_price(region);

CREATE INDEX IF NOT EXISTS idx_day_ahead_node_price_region_date_node 
  ON day_ahead_node_price(region, trade_date, node_name);

-- ===== 第4组: 植物/站点索引 (P1 - 推荐) =====
CREATE INDEX IF NOT EXISTS idx_hydro_output_plant 
  ON hydro_output(plant_name);

CREATE INDEX IF NOT EXISTS idx_hydro_output_plant_date 
  ON hydro_output(plant_name, trade_date);

-- 统计信息分析
ANALYZE;

-- 数据库优化
VACUUM;

-- 验证索引创建
SELECT '索引创建完成' as status, 
       (SELECT COUNT(*) FROM sqlite_master WHERE type='index') as index_count;
