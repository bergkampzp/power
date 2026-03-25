# 天气影响集成 - 完整实现路线图

**状态**: Phase 1 完成 ✅ → Phase 2 开始 🚀
**日期**: 2026-03-25
**目标**: 从 P2 (MAE=82.4) → P2+Weather (MAE<70)

---

## 📋 现状总结

### ✅ Phase 1 完成 (API集成)

| 任务 | 状态 | 输出物 |
|------|------|--------|
| API Host获取 | ✅ | `pe5pwdt2qy.re.qweatherapi.com` |
| API连接测试 | ✅ | 3个城市实时天气数据成功获取 |
| 修正因子算法设计 | ✅ | 物理模型 (光伏+风电+能见度) |
| 数据管道实现 | ✅ | `weather_data_pipeline.py` (248行) |
| 相关性分析框架 | ✅ | `weather_quick_analysis.py` |
| 研讨方案文档 | ✅ | `WEATHER_RESEARCH_PLAN.md` |

### 📊 实时数据样本

```
城市     温度  风速   云覆  光伏修正 风电修正 综合修正
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
昆明     22°C  28m/s  10%   0.915    0.000   0.649
曲靖     23°C  19m/s  10%   0.914    2.000   1.238
普洱     27°C   7m/s  10%   0.903    0.343   0.745
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**关键发现:**
- 曲靖风速19m/s → 修正因子2.0 (达到额定功率)
- 普洱风速低 → 修正因子0.745 (风力贡献小)
- 所有城市云覆盖低(10%) → 光伏贡献主要

---

## 🎯 Phase 2: P2+Weather 模型集成

### 2.1 数据融合架构

```
和风天气API
    ↓
[云覆, 风速, 温度, 湿度, 能见度]
    ↓
WeatherCorrectionFactor
    ↓
[光伏修正, 风电修正, 能见度修正]
    ↓
修正后的renewable_forecast
    ↓
P2 Model (5-ensemble)
    ↓
改进的电价预测
```

### 2.2 关键代码设计

#### 步骤1: 准备数据（30分钟）

```python
# 获取实时天气
weather_df = pipeline.fetch_all_cities()  # 3城市
weather_df = pipeline.calculate_correction_factors(weather_df)

# 获取当前的renewable_forecast
renewable_df = load_from_db(...)

# 融合
renewable_corrected = renewable_df['forecast'] * weather_df['renewable_correction'].mean()
```

#### 步骤2: 修改P2模型（1小时）

文件: `power-data/p2_with_weather.py`

```python
# 原始特征（P2）
features_p2 = [
    renewable_forecast,      # 原始预报
    load_forecast,
    hydro_forecast,
    # ... 其他62个特征
]

# 新特征（P2+Weather）
features_p2_weather = [
    renewable_forecast * weather_correction,  # ← 修正后预报
    load_forecast,
    hydro_forecast,
    cloud_cover,             # ← 新增：云覆盖
    wind_speed,              # ← 新增：风速
    # ... 其他特征
]

# 5-model ensemble (同P2)
p2_weather = (
    0.20 * GBR.predict(features_p2_weather) +
    0.25 * LGB.predict(features_p2_weather) +
    0.15 * XGB.predict(features_p2_weather) +
    0.30 * spread_model(...) +  # 可选: 增加spread权重
    0.10 * LSTM.predict(...)
)
```

#### 步骤3: 回测验证（2小时）

文件: `power-data/p2_weather_backtest.py`

```python
# 10日回测 (3/13-22)
test_dates = ['2026-03-13', ..., '2026-03-22']

for date in test_dates:
    # 获取该日的天气数据
    weather_data = fetch_qweather(date)

    # 计算修正因子
    correction = calculate_correction_factors(weather_data)

    # 修正预报
    renewable_corrected = load_forecast(date) * correction

    # P2+Weather预测
    pred = p2_weather_model.predict(
        features_with_weather_data
    )

    # 对比实际
    actual = load_actual_price(date)
    mae = np.mean(np.abs(pred - actual))

    results.append({
        'date': date,
        'mae': mae,
        'pred': pred,
        'actual': actual
    })

# 结果对比
print(f"P2 平均MAE:        {p2_results['mae'].mean():.2f}")
print(f"P2+Weather MAE:    {weather_results['mae'].mean():.2f}")
print(f"改进:             {improvement:.1f}%")
```

---

## 📈 预期成效

### 正常日 (70% 样本)

| 指标 | P2 | P2+Weather | 改进 |
|------|-----|-----------|------|
| MAE | 45 | **38** | -15% ↓ |
| RMSE | 62 | **52** | -16% ↓ |

### 异常日 (30% 样本，如3-22)

| 指标 | P2 | P2+Weather | 改进 |
|------|-----|-----------|------|
| MAE | 150 | **80-100** | -35~46% ↓ |
| 3-22时段 | 822 | **400-600** | -27~51% ↓ |

### 整体 10日

| 指标 | P2 | P2+Weather | 目标 |
|------|-----|-----------|------|
| **MAE** | **82.4** | **65-75** | **<70** ✓ |

---

## 🛠️ 实施步骤

### Week 1 (这周)

**Day 1-2: 数据准备** ✅ (已完成)
- [x] 获取API Host
- [x] 测试API连接
- [x] 设计修正因子算法
- [x] 创建数据管道

**Day 3-4: P2改造** (本周完成)
- [ ] 创建 `p2_with_weather.py`
- [ ] 集成weather_data_pipeline
- [ ] 训练P2+Weather模型
- [ ] 5个基础模型 (GBR/LGB/XGB/Spread/LSTM) 都加入weather特征

**Day 5: 回测验证**
- [ ] 10日回测脚本
- [ ] 绘制对比图 (P2 vs P2+Weather)
- [ ] 生成性能报告

### Week 2

**Day 6-8: 优化迭代**
- [ ] 调整修正因子权重 (光伏/风电/能见度比例)
- [ ] 异常日特殊处理
- [ ] 参数优化 (learning_rate等)

**Day 9-10: 最终验证 + 报告**
- [ ] 最终性能测试
- [ ] 与P2/P3/P4对比
- [ ] 完成研讨报告

---

## 📁 文件清单

### 已创建 ✅

```
power-data/
├── weather_api_explorer.py          (107行) ← API端点探索
├── find_api_host.py                 (83行)  ← Host诊断工具
├── weather_data_pipeline.py         (248行) ← 数据管道 (核心)
├── weather_analysis.py              (322行) ← 相关性分析
├── weather_quick_analysis.py        (150行) ← 快速POC
└── test_qweather_hosts.py          (108行) ← Host自动测试

文档/
├── WEATHER_RESEARCH_PLAN.md         (完整方案设计)
└── WEATHER_IMPLEMENTATION_ROADMAP.md (本文件)
```

### 待创建 📝

```
power-data/
├── p2_with_weather.py               ← 核心：P2+Weather模型
├── p2_weather_backtest.py           ← 回测脚本
├── p2_weather_prediction_23_24.py   ← 预报脚本
└── weather_feature_engineer.py      ← 特征工程（可选）

输出物/
├── p2_weather_10day_backtest.png    ← 10日对比图
├── weather_impact_analysis.png      ← 天气影响分析
└── p2_vs_weather_report.txt         ← 性能报告
```

---

## 🔑 关键决策

### Q1: 修正因子如何选择?

**A**: 使用物理模型 (非机器学习)

理由:
- 可解释性强
- 实施快速 (一周内)
- 与电力系统物理相符

```python
# 设计已验证:
光伏修正 = cloud_factor × temp_factor × humidity_factor
风电修正 = (wind_speed / base_speed)³  # 风能正比于风速³
综合修正 = 0.6×光伏 + 0.3×风电 + 0.1×能见度
```

### Q2: P2中哪些基础模型要改?

**A**: 全部5个都改

- GBR: 特征+weather_correction
- LGB: 特征+weather_correction
- XGB: 特征+weather_correction
- Spread: 特征+weather_correction
- LSTM: 考虑是否加入时序weather特征

### Q3: 权重需要重新调整吗?

**A**: 可能需要

当前P2权重 (针对无weather特征):
```
GBR: 20%, LGB: 25%, XGB: 15%, Spread: 35%, LSTM: 5%
```

改造后建议权重 (待验证):
```
GBR: 20%, LGB: 25%, XGB: 15%, Spread: 30%, LSTM: 10%
```

理由: 加入weather特征后，Spread相关性可能降低，LSTM可能能更好地学习时序

### Q4: 异常日如何处理?

**A**: 分层策略

- **正常日** (误差<20%): 用P2+Weather标准版
- **异常日** (误差>20%): 考虑增加weather特征权重
  ```python
  if error_pct > 20:
      weight_weather = 1.5 × 当前权重  # 加强weather影响
  ```

---

## 📊 性能监控

### 核心指标

| 指标 | P2基准 | P2+W 目标 | 检查点 |
|------|--------|----------|--------|
| **MAE** | 82.4 | <70 | 每日 |
| **RMSE** | ~ | <100 | 每日 |
| **MAPE** | ~ | <25% | 每周 |
| **异常日MAE** | 150 | <100 | 每周 |

### 监控仪表板

```
日期: 2026-03-25
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
指标           当前    目标    进度
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
整体 MAE      82.4    <70     ⏳ 未开始
正常日 MAE     45     <40     ⏳
异常日 MAE    150     <100    ⏳
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🚨 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 天气API中断 | 低 | 高 | 保存缓存数据，支持离线模式 |
| 修正因子权重不对 | 中 | 中 | 用小数据集快速验证，迭代调整 |
| 性能没改进 | 低 | 高 | 保留P2作备选，混合模型 (50% P2 + 50% P2+W) |
| 异常日特殊性 | 中 | 低 | 分别优化，参数分层 |

---

## ✨ 下一步行动

### 立即 (今日)

1. ✅ 获取API Host → **已完成**
2. ✅ 测试API连接 → **已完成**
3. ✅ 设计修正因子 → **已完成**

### 这周 (优先)

4. [ ] 创建 `p2_with_weather.py` - **关键路径**
   - 修改P2中的5个基础模型
   - 集成weather数据管道
   - 添加修正因子特征

5. [ ] 快速回测 (1-2天数据)
   - 验证方向是否正确
   - 调整参数

6. [ ] 完整10日回测
   - 生成对比图表
   - 性能分析

### 下周 (可选)

7. [ ] 优化与微调
8. [ ] 异常日特殊处理
9. [ ] 生产部署准备

---

## 📞 支持资源

- **和风天气文档**: https://dev.qweather.com/docs/api/
- **气象数据**: 控制台已配置，API已验证 ✅
- **P2模型代码**: `power-data/p2_decompose_lstm.py` (595行)
- **回测框架**: `power-data/p2_decompose_lstm.py` 中已有10日回测逻辑

---

**版本**: 1.0 | **状态**: 准备实施 | **预计完成**: 2026-04-05

> 💡 核心目标: 利用实时天气数据修正可再生能源预报，最终改进电价预测精度 15-20%
