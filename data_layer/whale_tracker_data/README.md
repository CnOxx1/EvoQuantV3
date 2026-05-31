# whale_tracker_data — 巨鲸追踪数据采集模块

## 定位

追踪加密货币大户（巨鲸）的链上行为，包括大额转账、交易所充提、标记地址活动。巨鲸行为对市场价格有直接冲击力，是重要的领先指标。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Whale Alert | 全链大额转账实时追踪（>$500K） | 15 分钟 |
| Arkham Intelligence | 标记地址行为分析 | 15 分钟 |
| Nansen | Smart Money 资金流向 | 15 分钟 |

## 代码结构

```
whale_tracker_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 数据表

### whale_transactions
| 字段 | 类型 | 说明 |
|---|---|---|
| tx_hash | TEXT | 交易哈希 |
| chain | TEXT | 链标识 |
| entity_key | TEXT | 标的符号 |
| from_label | TEXT | 发送方标签 |
| to_label | TEXT | 接收方标签 |
| amount_usd | REAL | USD 金额 |
| tx_type | TEXT | deposit/withdrawal/transfer |

### whale_flow_agg
| 字段 | 类型 | 说明 |
|---|---|---|
| entity_key | TEXT | 标的符号 |
| net_flow_usd | REAL | 净流入（正=抛压） |
| flow_direction | TEXT | accumulation/distribution/neutral |
| unique_whales | INTEGER | 独立大户数 |
| largest_tx_usd | REAL | 最大单笔 |

## 运行方式

```bash
python -m data_layer.whale_tracker_data.runner --mode bootstrap
python -m data_layer.whale_tracker_data.runner --mode once
python -m data_layer.whale_tracker_data.runner --mode scheduler --async-scheduler
python -m data_layer.whale_tracker_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "24h",
  "market_signal": {
    "total_net_flow_usd": -15000000,
    "distribution_assets": 3,
    "accumulation_assets": 8,
    "bias": "accumulation"
  },
  "entities": {
    "BTC": {
      "total_volume_usd": 250000000,
      "net_flow_usd": -8000000,
      "flow_direction": "accumulation",
      "unique_whales": 12
    }
  }
}
```

## 环境变量

| 变量 | 说明 |
|---|---|
| WHALE_ALERT_API_KEY | Whale Alert API 密钥 |
| ARKHAM_API_KEY | Arkham Intelligence API 密钥 |
| NANSEN_API_KEY | Nansen API 密钥 |
