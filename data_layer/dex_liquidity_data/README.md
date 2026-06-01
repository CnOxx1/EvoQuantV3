# dex_liquidity_data — DEX 流动性模块

## 简介

采集去中心化交易所池的流动性分布数据，为 AI 提供 TVL 集中度、tick 级流动性深度和大额 mint/burn 事件等结构化视角。DEX 流动性的突然撤出或集中是价格剧烈波动的前兆信号。

## 数据来源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Uniswap V3 Subgraph (The Graph) | Top 池 TVL、tick 分布、mint/burn | 20 分钟 |
| Curve Subgraph (The Graph) | Curve 池 TVL、流动性事件 | 20 分钟 |

## 数据库表

### dex_pools

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| protocol | TEXT | 协议名称（uniswap_v3/curve） |
| pool_address | TEXT | 池合约地址 |
| token0 | TEXT | Token0 名称 |
| token1 | TEXT | Token1 名称 |
| tvl_usd | REAL | 池 TVL（美元） |
| fee_tier | INTEGER | 手续费等级（bps） |
| volume_24h_usd | REAL | 24h 成交量（美元） |

### dex_tick_liquidity

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| pool_address | TEXT | 池合约地址 |
| tick_lower | INTEGER | tick 下界 |
| tick_upper | INTEGER | tick 上界 |
| liquidity | REAL | 该 tick 范围流动性 |
| amount0 | REAL | Token0 数量 |
| amount1 | REAL | Token1 数量 |

### dex_liquidity_events

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 事件时间戳 |
| pool_address | TEXT | 池合约地址 |
| event_type | TEXT | 事件类型（mint/burn） |
| amount_usd | REAL | 事件金额（美元） |
| sender | TEXT | 发起地址 |
| tx_hash | TEXT | 交易哈希 |

## 运行方式

```bash
# 首次回填
python -m data_layer.dex_liquidity_data.runner --mode bootstrap

# 单次采集
python -m data_layer.dex_liquidity_data.runner --mode once

# 定时采集
python -m data_layer.dex_liquidity_data.runner --mode scheduler

# 输出 AI 上下文
python -m data_layer.dex_liquidity_data.runner --print-context
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| GRAPH_API_KEY | The Graph API 密钥 | （空） |

## 调度频率

每 20 分钟采集一次，由 `DEX_LIQUIDITY_INTERVAL_SECONDS=1200` 控制。

## 文件结构

```
dex_liquidity_data/
├── __init__.py          # 包入口
├── client.py            # Uniswap V3 / Curve The Graph 子图请求封装
├── models.py            # DEX 流动性数据模型定义
├── runner.py            # CLI 运行入口
├── service.py           # 模块编排、调度与 context bundle
└── README.md
```
