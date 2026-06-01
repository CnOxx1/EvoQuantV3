# perpetual_dex_data — 永续 DEX 数据模块

## 简介

采集去中心化永续合约交易所的 funding rate、open interest 和成交量数据，为 AI 提供 CEX-DEX 套利价差、跨 DEX funding 对比和 OI 分布等结构化视角。永续 DEX 的 funding 偏离和 OI 集中度是链上杠杆情绪的重要领先指标。

## 数据来源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| dYdX v4 | Funding rate、OI、24h 成交量 | 15 分钟 |
| Hyperliquid | Funding rate、OI、交易笔数 | 15 分钟 |
| GMX v2 | Funding rate、OI、成交量 | 15 分钟 |

## 数据库表

### perp_dex_funding

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| dex | TEXT | DEX 名称 |
| symbol | TEXT | 交易对 |
| funding_rate | REAL | 当前 funding rate |
| next_funding_time | TEXT | 下次结算时间 |
| open_interest_usd | REAL | 未平仓合约（美元） |

### perp_dex_volume

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| dex | TEXT | DEX 名称 |
| symbol | TEXT | 交易对 |
| volume_24h_usd | REAL | 24h 成交量（美元） |
| trades_24h | INTEGER | 24h 交易笔数 |

## 运行方式

```bash
# 首次回填
python -m data_layer.perpetual_dex_data.runner --mode bootstrap

# 单次采集
python -m data_layer.perpetual_dex_data.runner --mode once

# 定时采集
python -m data_layer.perpetual_dex_data.runner --mode scheduler

# 输出 AI 上下文
python -m data_layer.perpetual_dex_data.runner --print-context
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| DYDX_API_URL | dYdX v4 API 地址 | （空） |
| HYPERLIQUID_API_URL | Hyperliquid API 地址 | （空） |
| GMX_API_URL | GMX v2 API 地址 | （空） |

## 调度频率

每 15 分钟采集一次，由 `PERPETUAL_DEX_INTERVAL_SECONDS=900` 控制。

## 文件结构

```
perpetual_dex_data/
├── __init__.py          # 包入口
├── client.py            # dYdX / Hyperliquid / GMX API 请求封装
├── models.py            # 永续 DEX 数据模型定义
├── runner.py            # CLI 运行入口
├── service.py           # 模块编排、调度与 context bundle
└── README.md
```
