# cross_venue_arbitrage — 跨交易所套利检测模块

## 简介

基于多交易所价格数据，实时检测跨交易所价差、分析套利机会持续性并计算市场效率评分。跨交易所价差的持续存在反映了市场分割和流动性碎片化程度，是衡量市场微观结构健康度的关键指标。

## 输入数据

| 来源模块 | 数据表 | 用途 |
|---|---|---|
| exchange_data | klines | 各交易所最新收盘价（通过 exchange 字段区分场所） |
| exchange_data | tickers | 备用价格源（last_price） |

## 计算内容

- 价差检测：计算所有交易所配对的实时价差（bps）
- 持续性分析：套利机会存续时间统计与频率
- 利润估算：基于 spread_bps 和假定交易规模估算套利利润
- 市场效率评分：0-100 综合评分（100 = 完全有效）

## 数据库表

### arb_opportunities

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 检测时间戳 |
| symbol | TEXT | 交易对 |
| venue_buy | TEXT | 买入交易所 |
| venue_sell | TEXT | 卖出交易所 |
| price_buy | REAL | 买入价格 |
| price_sell | REAL | 卖出价格 |
| spread_bps | REAL | 价差（基点） |
| estimated_profit_usd | REAL | 预估利润（美元） |
| latency_ms | INTEGER | 延迟（毫秒） |

### arb_persistence

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 统计时间戳 |
| symbol | TEXT | 交易对 |
| venue_pair | TEXT | 交易所配对 |
| avg_spread_bps | REAL | 平均价差（基点） |
| duration_seconds | INTEGER | 持续时间（秒） |
| frequency_per_hour | REAL | 每小时出现频率 |

### venue_spreads

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| symbol | TEXT | 交易对 |
| venue_a | TEXT | 交易所 A |
| venue_b | TEXT | 交易所 B |
| mid_spread_bps | REAL | 中间价差（基点） |
| bid_ask_cross | INTEGER | 是否存在买卖交叉（0/1） |

## 运行方式

```bash
# 执行套利检测
python -m logic_layer.cross_venue_arbitrage.runner --mode once

# 指定标的
python -m logic_layer.cross_venue_arbitrage.runner --mode once --symbols BTC,ETH,SOL

# 定时计算
python -m logic_layer.cross_venue_arbitrage.runner --mode scheduler

# 输出 AI 上下文
python -m logic_layer.cross_venue_arbitrage.runner --print-context
```

## 文件结构

```
cross_venue_arbitrage/
├── __init__.py          # 包入口
├── calculator.py        # 价差检测、持续性分析、效率评分计算
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 运行入口
├── service.py           # 服务层（编排计算 + context bundle）
└── README.md
```
