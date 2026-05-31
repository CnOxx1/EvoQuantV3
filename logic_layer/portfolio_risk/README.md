# 组合风险计算模块 `portfolio_risk`

## 模块定位

`portfolio_risk` 属于逻辑处理层，负责计算组合级别的波动率、VaR、集中度和分散化指标。

它是纯计算模块，不采集外部数据，基于 `cross_asset_analysis` 提供的协方差矩阵和假设权重进行风险分解。

## 模块代码树

```text
logic_layer/portfolio_risk/
  __init__.py       # 包入口
  models.py         # 数据模型定义
  calculator.py     # 纯计算引擎（不依赖数据库）
  repository.py     # 数据读取与结果落库
  service.py        # 编排入口
  runner.py         # CLI 运行入口
```

## 核心计算

| 指标 | 方法 | 说明 |
| --- | --- | --- |
| 组合波动率 | `w^T * Cov * w` | 日度波动率 |
| 年化波动率 | `daily_vol * sqrt(365)` | 加密市场全年无休 |
| VaR 95% | 参数法（正态） | `vol * 1.645` |
| VaR 99% | 参数法（正态） | `vol * 2.326` |
| 风险贡献 | 边际贡献分解 | 每个资产对组合风险的贡献比例 |
| 集中度 | HHI 指数 | 权重集中度 |
| 分散化比率 | 加权平均个体波动 / 组合波动 | >1 表示分散化有效 |

## 设计原则

- `calculator.py` 是纯函数，只接收权重和协方差矩阵
- 不做任何交易建议或仓位推荐
- 只输出风险度量，供 AI 和策略层自行决策

## 运行方式

```bash
python -m logic_layer.portfolio_risk.runner
```
