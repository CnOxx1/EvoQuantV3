# defi_protocol_data — DeFi 协议数据采集模块

## 定位

采集 DeFi 协议核心指标（TVL、借贷利率、DEX 交易量），为 AI 提供链上真实资金活动的量化视角。DeFi 数据与 CEX 数据互补，反映链上资金的真实供需关系。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| DefiLlama | TVL、DEX 交易量、协议收入 | 1 小时 |
| DefiLlama Yields | 借贷池收益率 | 1 小时 |

## 追踪协议

Aave, Lido, MakerDAO, Uniswap, Curve, Compound, Rocket Pool, GMX, dYdX, Raydium, Jupiter, Morpho, EigenLayer, Pendle, Ethena

## 代码结构

```
defi_protocol_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（DefiLlama）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 数据表

### defi_tvl
协议 TVL 快照，含 1d/7d 变化率。

### defi_lending_rates
借贷协议利率快照（存款 APY、借款 APY、资金利用率）。

### defi_dex_volume
DEX 24h 交易量快照。

## 运行方式

```bash
python -m data_layer.defi_protocol_data.runner --mode bootstrap
python -m data_layer.defi_protocol_data.runner --mode once
python -m data_layer.defi_protocol_data.runner --mode scheduler --async-scheduler
python -m data_layer.defi_protocol_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "tvl": {
    "total_tracked_tvl_usd": 85000000000,
    "protocols": {
      "aave": {"tvl_usd": 12000000000, "change_1d_pct": 1.5}
    }
  },
  "lending": {
    "pools": {
      "aave-v3_USDC": {"supply_apy_pct": 4.2, "borrow_apy_pct": 5.8}
    }
  },
  "dex": {
    "total_volume_24h_usd": 3500000000
  }
}
```
