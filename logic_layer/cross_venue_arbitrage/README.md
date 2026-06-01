# cross_venue_arbitrage — 跨交易所套利检测模块

## 简介

基于多交易所价格数据，实时检测跨交易所价差、分析套利机会持续性并计算市场效率评分。跨交易所价差的持续存在反映了市场分割和流动性碎片化程度，是衡量市场微观结构健康度的关键指标。

## 输入数据

| 来源模块 | 数据 |
|---|---|
| exchange_data | 多交易所实时价格（Binance/OKX/Bybit） |

## 计算内容

- 价差检测：计算所有交易所配对的实时价差（bps）
- 持续性分析：套利机会存续时间统计与衰减曲线
- 交易所相关性：各交易所间价格的滚动相关系数
- 利润估算：扣除手续费和滑点后的净套利空间
- 市场效率评分：0-100 综合评分（100 = 完全有效）

## 数据库表

### arb_opportunities

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 检测时间戳 |
| symbol | TEXT | 交易对 |
| venue_a | TEXT | 交易所 A |
| venue_b | TEXT | 交易所 B |
| spread_bps | REAL | 价差（基点） |
| direction | TEXT | 套利方向（A→B / B→A） |
| net_profit_bps | REAL | 扣费后净利润（基点） |
| is_actionable | INTEGER | 是否可执行 |

### arb_persistence

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 统计时间戳 |
| symbol | TEXT | 交易对 |
| venue_pair | TEXT | 交易所配对 |
| avg_duration_seconds | REAL | 平均持续时间（秒） |
| occurrence_count | INTEGER | 出现次数 |
| max_spread_bps | REAL | 最大价差（基点） |
| decay_half_life_s | REAL | 价差半衰期（秒） |

### venue_spreads

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| symbol | TEXT | 交易对 |
| venue_pair | TEXT | 交易所配对 |
| mean_spread_bps | REAL | 平均价差（基点） |
| correlation | REAL | 价格相关系数 |
| efficiency_score | INTEGER | 市场效率评分（0-100） |

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
