#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电价预测模型统一配置
=====================
集中管理所有数据库路径、输出目录和模型参数。
"""
import os

# 项目根目录 (based on this file's location)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POWER_DATA = os.path.join(PROJECT_ROOT, 'power-data')

# 数据库路径
DB_PATH = os.path.join(POWER_DATA, 'power_market_v2.db')
DB = DB_PATH  # 兼容短变量名

# 输出目录
OUTPUT_DIR = POWER_DATA
OUT_DIR = POWER_DATA  # 兼容短变量名

# 参考数据库（旧版 power_market.db，已不再使用）
# REF_DB_PATH = os.path.join(PROJECT_ROOT, 'reference-data', 'power_market.db')

# 原始数据目录
POWPER_BASE = os.path.join(POWER_DATA, 'powper-data-3-26')

# 回测窗口（默认）
BACKTEST_START = "20260301"
BACKTEST_END = "20260322"

# 模型参数
N_ESTIMATORS = 300
MAX_DEPTH = 5
LEARNING_RATE = 0.05

# PostgreSQL (da_price_model 专用)
PG_CONFIG = dict(
    host="localhost",
    port=5433,
    user="postgres",
    password="postgres",
    dbname="warehouse"
)
