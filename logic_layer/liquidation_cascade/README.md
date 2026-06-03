# liquidation_cascade — 清算级联预测模块

## 简介

基于交易所 OI、价格和杠杆分布数据，按杠杆倍数模拟仓位分布，检测清算集群并建模级联概率。清算级联是加密市场闪崩的核心机制，提前识别高密度清算区间可为 AI 提供关键的风险预警。

## 输入数据

| 来源模块 | 数据表 | 用途 |
|---|---|---|
| exchange_data | open_interest_snapshots | OI 数据（open_interest_usd, open_interest_contracts） |
| exchange_data | klines | 最新价格、24h 成交量 |

## 计算内容

- 清算集群检测：按价格区间聚合各杠杆倍数（5x/10x/20x/50x/100x）的预估清算量
- 级联概率建模：基于 size/volume 比率 + 距离衰减计算触发概率
- 严重度分类：critical / high / medium / low
- 清算热力图：价格 × 杠杆倍数的二维清算密度分布
- 级联链模拟：一次清算触发后续清算的连锁反应路径

## 数据库表

### liquidation_clusters

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| symbol | TEXT | 交易对 |
| price_level | REAL | 清算价格区间中心 |
| leverage_bucket | TEXT | 杠杆倍数桶 |
| estimated_size_usd | REAL | 预估清算量（美元） |
| distance_pct | REAL | 距当前价格百分比 |

### cascade_risk

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| symbol | TEXT | 交易对 |
| cascade_probability | REAL | 级联触发概率（0-1） |
| severity | TEXT | 严重度（critical/high/medium/low） |
| total_at_risk_usd | REAL | 风险敞口总额（美元） |
| trigger_distance_pct | REAL | 最近触发距离（%） |

### liquidation_heatmap

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| symbol | TEXT | 交易对 |
| price_bin | REAL | 价格区间 |
| leverage_bin | TEXT | 杠杆区间 |
| density | REAL | 清算密度 |
| direction | TEXT | 方向（long/short） |

## 运行方式

```bash
# 执行清算级联分析
python -m logic_layer.liquidation_cascade.runner --mode once

# 指定标的
python -m logic_layer.liquidation_cascade.runner --mode once --symbols BTC,ETH,SOL

# 定时计算
python -m logic_layer.liquidation_cascade.runner --mode scheduler

# 输出 AI 上下文
python -m logic_layer.liquidation_cascade.runner --print-context
```

## 文件结构

```
liquidation_cascade/
├── __init__.py          # 包入口
├── calculator.py        # 集群检测、级联概率、热力图计算
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 运行入口
├── service.py           # 服务层（编排计算 + context bundle）
└── README.md
```
