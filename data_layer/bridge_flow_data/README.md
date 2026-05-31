# bridge_flow_data — 跨链桥资金流数据采集模块

## 定位

采集跨链桥资金流向数据，追踪资本在不同区块链之间的迁移。跨链资金流是判断生态热度和资金方向的重要信号。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| DefiLlama Bridges | 30+ 跨链桥交易量、10+ 链的净流向 | 1 小时 |

## 追踪链

Ethereum, Arbitrum, Optimism, Base, Polygon, BSC, Avalanche, Solana, Sui, Aptos

## 代码结构

```
bridge_flow_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（DefiLlama Bridges）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 核心指标

| 指标 | 说明 |
|---|---|
| net_flow_usd | 链净流入（正=资金流入该链） |
| capital_migration_bias | 资金迁移方向（l2_expansion/l1_consolidation） |
| bridge_volume_24h | 桥 24h 交易量 |

## 运行方式

```bash
python -m data_layer.bridge_flow_data.runner --mode bootstrap
python -m data_layer.bridge_flow_data.runner --mode once
python -m data_layer.bridge_flow_data.runner --mode scheduler --async-scheduler
python -m data_layer.bridge_flow_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "market_signal": {
    "capital_migration_bias": "l2_expansion",
    "net_inflow_chains": ["Arbitrum", "Base", "Optimism"],
    "net_outflow_chains": ["Ethereum"]
  },
  "chain_flows": {
    "Arbitrum": {"inflow_usd": 50000000, "net_flow_usd": 25000000, "direction": "net_inflow"}
  }
}
```
