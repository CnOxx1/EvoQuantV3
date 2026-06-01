# gas_network_data — Gas/网络数据模块

## 简介

采集以太坊 Gas 价格和网络拥堵状态数据，为 AI 提供链上活跃度、网络压力和 Gas 尖刺检测等结构化视角。Gas 价格的急剧飙升通常伴随链上恐慌性操作（清算、抢跑、大规模转账），是市场剧烈波动的同步/领先指标。

## 数据来源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Etherscan Gas Oracle | base fee、priority fee、Gas 估算 | 5 分钟 |
| Blocknative Gas API | pending 交易数、区块利用率、Gas 分布 | 5 分钟 |

## 数据库表

### gas_prices

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| base_fee_gwei | REAL | 当前 base fee（Gwei） |
| priority_fee_gwei | REAL | 推荐 priority fee（Gwei） |
| gas_price_fast | REAL | 快速确认 Gas 价格 |
| gas_price_standard | REAL | 标准确认 Gas 价格 |
| gas_price_slow | REAL | 慢速确认 Gas 价格 |

### network_congestion

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| pending_tx_count | INTEGER | 待处理交易数 |
| block_utilization | REAL | 区块利用率（0-1） |
| congestion_level | TEXT | 拥堵等级（low/medium/high/extreme） |
| avg_wait_seconds | REAL | 平均确认等待时间（秒） |

### gas_spikes

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 尖刺发生时间 |
| spike_magnitude | REAL | 尖刺幅度（相对均值倍数） |
| base_fee_peak | REAL | 峰值 base fee（Gwei） |
| duration_seconds | INTEGER | 尖刺持续时间（秒） |
| likely_cause | TEXT | 可能原因（liquidation/mint/airdrop/unknown） |

## 运行方式

```bash
# 首次回填
python -m data_layer.gas_network_data.runner --mode bootstrap

# 单次采集
python -m data_layer.gas_network_data.runner --mode once

# 定时采集
python -m data_layer.gas_network_data.runner --mode scheduler

# 输出 AI 上下文
python -m data_layer.gas_network_data.runner --print-context
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| ETHERSCAN_API_KEY | Etherscan API 密钥 | （空） |
| BLOCKNATIVE_API_KEY | Blocknative API 密钥 | （空） |

## 调度频率

每 5 分钟采集一次，由 `GAS_NETWORK_INTERVAL_SECONDS=300` 控制。

## 文件结构

```
gas_network_data/
├── __init__.py          # 包入口
├── client.py            # Etherscan / Blocknative API 请求封装
├── models.py            # Gas 和网络数据模型定义
├── runner.py            # CLI 运行入口
├── service.py           # 模块编排、调度与 context bundle
└── README.md
```
