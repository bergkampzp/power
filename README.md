# 电力交易电价预测系统

面向水电站的电力市场交易管理平台，核心解决"中长期锁价避险 + 现货分时套利 + 量化预测"三大痛点。

## 项目结构

```
power-trade-v2/
├── power-data/         # 电价预测算法
│   ├── *.py           # 预测脚本
│   ├── power_market.db # SQLite数据库
│   └── *.md           # 文档
│
└── electrate/         # 数据展示系统
    ├── src/          # React前端
    ├── pages/        # 页面组件
    └── *.md         # 产品/技术文档
```

## 快速启动

```bash
# 启动预测服务
cd power-data
python3 comprehensive_prediction.py

# 访问数据展示
# http://localhost:5175
```

## 核心功能

- [ ] 电价预测模型
- [ ] 数据可视化
- [ ] 交易策略建议

## 文档

- [产品设计文档](./electrate/产品设计文档.md)
- [技术架构文档](./electrate/技术架构文档.md)
- [数据清单](./electrate/数据清单.md)
- [模型版本记录](./electrate/模型版本记录.md)

---

*电力交易项目 V2.0*
