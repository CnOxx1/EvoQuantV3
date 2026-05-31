# orderflow_data — 订单流数据采集模块

## 定位

采集加密货币期货市场的微观订单流数据，包括逐笔成交、CVD（累积成交量差）、大单检测。订单流是价格发现的核心驱动力，为 AI 提供市场微观结构视角。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Binance Futures | aggTrades 聚合成交 | 5 分钟 |
| Bybit Linear | 近期成交 | 5 分钟 |
| OKX Swap | 近期成交 | 5 分钟 |

## 代码结构

```
orderflow_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（多交易所）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 核心指标

| 指标 | 说明 |
|---|---|
| CVD | 累积成交量差 = 主动买入量 - 主动卖出量 |
| aggression_ratio | 主动买/主动卖比率，>1 表示买方激进 |
| large_trade | 单笔 >$100K 的大单 |
| vwap | 成交量加权均价 |

## 数据表

### orderflow_trades
逐笔成交原始数据，按交易所+trade_id 去重。

### orderflow_agg
按 entity_key + exchange + interval 聚合的订单流指标。

## 运行方式

```bash
python -m data_layer.orderflow_data.runner --mode bootstrap
python -m data_layer.orderflow_data.runner --mode once
python -m data_layer.orderflow_data.runner --mode scheduler --async-scheduler
python -m data_layer.orderflow_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "1h",
  "summaries": {
    "BTC": {
      "buy_volume_usd": 85000000,
      "sell_volume_usd": 72000000,
      "cvd_usd": 13000000,
      "large_buy_count": 15,
      "large_sell_count": 8,
      "bias": "buy_dominant",
      "exchanges_covered": ["binance", "bybit", "okx"]
    }
  }
}
```
