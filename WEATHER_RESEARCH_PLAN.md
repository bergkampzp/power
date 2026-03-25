# 天气影响算法研讨方案 (Weather Impact Research Plan)

**创建日期**: 2026-03-25
**当前阶段**: P2 → P2+ (Weather-Corrected)
**核心目标**: 将天气因素集成到可再生能源预测，改进电价预测精度

---

## 一、问题诊断

### 3-22 异常事件根本原因

| 指标 | 数值 | 说明 |
|------|------|------|
| 可再生能源预报 | 15,844 MW | 国家电网公布的次日风光预报 |
| 实际可再生出力 | 10,637 MW | 实际96period平均值 |
| **预测误差** | **-32.9%** | ⚠️ 严重低估 |
| 日前电价预测 | 0-206 元/MWh | 基于预报（假设供给充足） |
| 实时电价峰值 | 700-822 元/MWh | 供不应求导致 |

### 误差来源分解

1. **天气原因 (~70-80%)**
   - 09:00 尖峰（822元）: 早晨云覆盖，光伏爬升缓慢
   - 16:00 尖峰（733元）: 午后云系+沙尘导致直射辐照急剧下降
   - 21:00 尖峰（721元）: 光伏结束 + 风力同步下降

2. **预报固有误差 (~20-30%)**
   - 国家电网的风光预报是初级的多日预报（D+1）
   - 缺少天气驱动的动态修正
   - 无法捕捉局地对流或沙尘事件

3. **模型上界**
   - **P2当前MAE = 82.4** (基于国家电网预报)
   - 如果预报本身错32%，模型无法超越这个上界
   - **需要用更精准的天气数据来修正预报**

---

## 二、天气数据集成框架

### 数据源选择

使用 **和风天气API** (QWeather)：
- 支持实时/预报天气数据
- 提供云覆盖率、风速、温度、相对湿度、能见度
- 小时级分辨率（与电力市场96period对齐）
- 凭据信息:
  - **API Key**: `7f8ffcbf0a8a49af809be219ca37ae4d`
  - **Credential ID**: `C7H25HGQCC`
  - **Host**: ⚠️ **需要从控制台-设置查看** (当前测试失败)

### 云南地区覆盖

优先级排序（按可再生能源集中度）：

| 城市 | Location ID | 优先级 | 理由 |
|------|------------|--------|------|
| 怒江 | 101291901 | ⭐⭐⭐ | 大型水电/风电项目区 |
| 迪庆 | 101292201 | ⭐⭐⭐ | 高海拔风力资源 |
| 曲靖 | 101290401 | ⭐⭐⭐ | 光伏集中区（60%容量） |
| 昆明 | 101290101 | ⭐⭐ | 省会，中等负荷中心 |
| 普洱 | 101291501 | ⭐⭐ | 生物质资源 |

### 关键天气参数

| 参数 | 用途 | 预期范围 | 优先级 |
|------|------|--------|--------|
| **Cloud Cover (%)** | 光伏修正基础 | 0~100 | ⭐⭐⭐ |
| **Wind Speed (m/s)** | 风电修正 | 0~30 | ⭐⭐⭐ |
| **Temperature (°C)** | 光伏效率系数 | -10~45 | ⭐⭐ |
| **Relative Humidity (%)** | 能见度推断 | 0~100 | ⭐⭐ |
| **Visibility (km)** | 气溶胶/沙尘指示 | 0~100 | ⭐⭐ |
| **Pressure (hPa)** | 天气系统指示 | 900~1050 | ⭐ |

---

## 三、修正因子模型

### 设计原则

```
renewable_forecast_corrected = renewable_forecast × correction_factor

correction_factor = f(cloud, wind_speed, temp, humidity, visibility)
```

### 分项修正

#### 1. 光伏修正因子 (Solar Correction)

```python
def solar_correction(cloud_cover, temperature, humidity):
    # 云覆盖对光伏的直接影响（非线性）
    cloud_factor = 1.0 - (cloud_cover / 100.0) * 0.9

    # 温度系数（硅面板效率 -0.4%/°C）
    temp_factor = 1.0 - (temp - 25) * 0.004

    # 湿度影响（高湿→高云？）
    humidity_factor = 1.0 - (humidity - 50) / 100 * 0.1

    return cloud_factor × temp_factor × humidity_factor
```

**期望效果**：
- 完全晴朗 (cloud=0%, T=25°C): factor ≈ 1.0 (无修正)
- 完全阴云 (cloud=100%, T=25°C): factor ≈ 0.1 (减少90%)
- 高温 (cloud=0%, T=40°C): factor ≈ 0.94 (减少6%)

#### 2. 风电修正因子 (Wind Correction)

```python
def wind_correction(wind_speed):
    # 风能与风速³次方成正比
    if wind_speed < 3:     return 0.0   # 启动风速
    if wind_speed > 25:    return 0.0   # 切出风速

    ratio = (wind_speed / 10.0) ** 3
    return ratio  # 可自动缩放
```

**期望效果**：
- 3-5 m/s: factor ≈ 0.01~0.13 (低功率)
- 10 m/s: factor ≈ 1.0 (额定功率)
- 15 m/s: factor ≈ 3.4 (超额定，受限)
- >25 m/s: 切出 (0.0)

#### 3. 能见度修正 (Visibility Correction)

```python
def visibility_correction(visibility_km):
    # 能见度指示气溶胶/沙尘
    # 高能见度 → 清洁大气 → 高太阳辐照
    if visibility > 10:     return 1.0
    if visibility < 5:      return 0.5
    return 0.5 + (visibility - 5) / 5 * 0.5
```

#### 4. 综合可再生能源修正

```python
renewable_correction = (
    solar_correction × 0.60 +    # 光伏权重60%
    wind_correction × 0.30 +     # 风电权重30%
    visibility_correction × 0.10 # 能见度10%
)
```

---

## 四、核心算法设计

### 步骤1: 数据采集与特征工程

**输入**:
- 和风天气API (hourly forecast)
- 国家电网可再生预报 (renewable_forecast)
- 实际SCADA数据 (renewable_actual)

**输出**:
```python
df_weather = pd.DataFrame({
    'timestamp': [...],
    'city': [...],
    'temperature': [...],
    'wind_speed': [...],
    'cloud_cover': [...],
    'humidity': [...],
    'visibility': [...],
    'solar_correction': [...],
    'wind_correction': [...],
    'renewable_correction': [...]
})
```

### 步骤2: 相关性分析

分析修正因子与可再生能源误差的相关性：

```python
correlation = corr(
    renewable_actual / renewable_forecast,
    renewable_correction
)
```

期望结果：
- 如果 corr > 0.6，说明天气是主要驱动因素
- 如果 corr < 0.3，说明还有其他原因（规划调度、限电等）

### 步骤3: 修正模型训练

用过去数据训练一个映射：

```python
# 简单版本（直接乘法）
renewable_corrected = renewable_forecast × renewable_correction

# 高级版本（学习非线性映射）
renewable_corrected = GBR.predict(
    [weather_features_now, renewable_forecast]
)
```

### 步骤4: 集成到P2模型

在P2中替换原始预报特征：

```python
# 旧的P2特征
features_p2 = [
    renewable_forecast,      # ← 原始预报（有32%误差）
    load_forecast,
    hydro_forecast,
    # ...其他特征
]

# 新的P2+ 特征
features_p2_plus = [
    renewable_forecast * renewable_correction,  # ← 修正后预报
    load_forecast,
    hydro_forecast,
    # 可选: 增加天气特征
    cloud_cover,
    wind_speed,
    temperature,
    # ...其他特征
]
```

---

## 五、期望效果评估

### 性能指标

| 场景 | 方法 | MAE | 改进 |
|------|------|-----|------|
| Normal days (非异常) | P2 | ~45 | baseline |
| Normal days | P2+Weather | ~38 | -15% ✓ |
| **Anomaly days (3-22)** | **P2** | **~150** | **baseline** |
| **Anomaly days** | **P2+Weather** | **~80-100** | **-35% ✓** |
| **Overall 10-day** | **P2** | **82.4** | **baseline** |
| **Overall 10-day** | **P2+Weather** | **~65-75** | **-15-20% ✓** |

### 目标设定

- **短期目标** (2周): 完成API集成 + 修正因子验证
  - 验证 corr(actual/forecast, correction) > 0.5
  - 确认3-22日的修正方向正确

- **中期目标** (1个月): 集成到P2，完整回测
  - P2+ 10日测试 MAE < 75
  - 异常日性能提升 > 30%

- **长期目标** (1-2个月): 生产部署
  - 实时预报系统
  - 监控面板（天气影响指数）

---

## 六、实施计划

### Phase 1: API 配置 (Day 1-2)

**需要用户操作**:
1. 登录和风天气控制台
2. 进入 Settings/设置
3. 查看 "API Host" 地址
4. 检查 API Key 是否有 IP 白名单限制 (如有，添加当前IP)
5. 修改 `weather_data_pipeline.py` 中的 `QWEATHER_CONFIG['api_host']`

**可选**: 如果有专业版API，也可考虑其他来源 (MERRA-2, ERA5等)

### Phase 2: 数据集成 (Day 3-5)

文件清单:
```
power-data/
├── weather_api_explorer.py          ✓ 已创建
├── find_api_host.py                 ✓ 已创建
├── weather_data_pipeline.py          ✓ 已创建 (需API配置)
├── weather_correction_analysis.py    📝 TODO: 相关性分析
└── weather_feature_engineer.py       📝 TODO: 特征工程
```

### Phase 3: 模型集成 (Day 6-10)

```
power-data/
├── p2_with_weather.py                📝 TODO: 修改P2模型
├── p2_weather_backtest.py            📝 TODO: 回测脚本
└── p2_weather_prediction_23_24.py    📝 TODO: 预报脚本
```

### Phase 4: 验证与优化 (Day 11-14)

- 10日回测对比
- 参数调优（权重分配）
- 异常日特殊处理
- 性能报告

---

## 七、关键文件与代码架构

### 已创建

1. **weather_api_explorer.py**
   - API连接测试
   - 端点探索
   - Location ID查询

2. **weather_data_pipeline.py** (核心)
   - QWeatherClient: API客户端
   - WeatherCorrectionFactor: 修正算法
   - WeatherDataPipeline: 完整管道

### 待创建

1. **weather_correction_analysis.py**
   ```python
   # 与renewable_forecast的相关性分析
   - 按城市分析
   - 按时间段分析
   - 相关性矩阵热力图
   - 修正因子有效性验证
   ```

2. **weather_feature_engineer.py**
   ```python
   # 从原始天气→特征
   - 聚合多个城市
   - 时间窗口移动平均
   - 与电力特征的交互项
   ```

3. **p2_with_weather.py**
   ```python
   # P2模型+天气特征
   - 替换renewable_forecast特征
   - 添加weather_correction
   - 可选: 添加天气特征直接输入
   - 5-model ensemble (同P2)
   ```

---

## 八、关键决策点

### Q1: 用哪种天气API?
- **A**: 和风天气 (QWeather) - 国内友好，覆盖好，有现成凭据
- 备选: MERRA-2再分析数据 (全球，但数据延迟1-2天)

### Q2: 修正因子如何验证?
- **A**: 用过去数据 (3/13-22) 验证
  - 若修正方向与实际相反，调整参数
  - 若修正不足30%，说明天气不是主因

### Q3: 是否需要训练修正模型?
- **A**: 先用物理模型 (简单乘法)，验证有效性
  - 若有效，可进阶为ML模型 (GBR学习非线性)
  - 若无效，需考虑其他因素 (电网限流、调度等)

### Q4: 何时集成到生产?
- **A**: 等待10日完整回测，性能稳定后
  - 不提前上线，避免regression
  - 保留P2作为备选方案

---

## 九、参考资源

### 和风天气API文档
- 开发者文档: https://dev.qweather.com/docs/api/
- API Key管理: 控制台 → 凭据 → 设置
- 常见问题:
  - Host错误 → 检查控制台-设置
  - 403错误 → 检查IP白名单/API权限

### 电力相关参考
- 可再生能源与天气的物理关系:
  - 光伏: GHI (Global Horizontal Irradiance) = f(cloud_cover, aerosol_optical_depth)
  - 风电: P = 0.5 × ρ × A × v³ (风能与风速³次方成正比)

### 模型融合
- P2当前权重: GBR(20%) + LGB(25%) + XGB(15%) + Spread(35%) + LSTM(5%)
- 考虑增加Weather权重: Spread(30%) + Weather(10%) + 其他(60%)

---

## 十、行动项 (Action Items)

**紧急 (今日)**:
- [ ] 从和风天气控制台获取正确的API Host
- [ ] 测试API连接 (`weather_api_explorer.py`)

**本周**:
- [ ] 完成相关性分析 (weather vs renewable_forecast误差)
- [ ] 验证修正因子有效性 (3/13-22 past data)
- [ ] 初步集成到P2

**2周内**:
- [ ] 10日完整回测
- [ ] 性能对比报告
- [ ] 参数优化

---

## 附录A: 天气修正因子示例

### 3-22日上午09:00的假设修正

```
预报数据:
  renewable_forecast = 12,000 MW (每小时平均)

实时天气:
  cloud_cover = 70%
  wind_speed = 5 m/s
  temperature = 18°C
  humidity = 80%
  visibility = 8 km

计算修正因子:
  solar_correction = (1 - 0.7×0.9) × (1 - (18-25)×0.004) × (1 - (80-50)/100×0.1)
                   = 0.37 × 1.028 × 0.97
                   ≈ 0.37 (光伏减少63%)

  wind_correction = (5/10)³ = 0.125 (风电减少87.5%)

  visibility_correction = 0.5 + (8-5)/5×0.5 = 0.8

  renewable_correction = 0.37×0.6 + 0.125×0.3 + 0.8×0.1
                       = 0.222 + 0.0375 + 0.08
                       ≈ 0.34

修正后预报:
  renewable_corrected = 12,000 × 0.34 = 4,080 MW

对比:
  原始预报: 12,000 MW (假设高估)
  修正后: 4,080 MW
  实际值: ? (需验证)
```

---

**版本**: v1.0
**上次更新**: 2026-03-25 15:30 UTC+8
**下次审视**: 完成Phase 1-2后
