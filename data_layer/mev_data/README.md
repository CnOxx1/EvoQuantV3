# mev_data — MEV 智能数据模块

## 定位

采集以太坊 MEV（最大可提取价值）数据，为 AI 提供链上价值提取行为的量化视角。MEV 活动是链上流动性压力与市场微观结构的重要观测指标，与短期波动性存在因果关系。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Flashbots API | MEV 区块奖励、Builder 数据 | 30 分钟 |
| EigenPhi | 三明治攻击、套利、清算 | 30 分钟 |

## 代码结构

```
mev_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（Flashbots / EigenPhi）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层（采集 + 聚合 + AI bundle）
└── README.md
```

## 数据表

### mev_blocks
| 字段 | 类型 | 说明 |
|---|---|---|
| block_number | INTEGER | 区块高度 |
| timestamp | TEXT | 时间戳 |
| mev_reward_eth | REAL | MEV 奖励（ETH） |
| mev_reward_usd | REAL | MEV 奖励（美元） |
| sandwich_count | INTEGER | 三明治攻击次数 |
| arb_count | INTEGER | 套利次数 |
| liquidation_count | INTEGER | 清算次数 |
| builder | TEXT | 区块构建者 |

### mev_agg
| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 时间戳 |
| interval | TEXT | 聚合窗口 |
| total_mev_usd | REAL | MEV 总提取量（美元） |
| sandwich_volume_usd | REAL | 三明治攻击量（美元） |
| arb_volume_usd | REAL | 套利量（美元） |
| liquidation_mev_usd | REAL | 清算 MEV（美元） |
| avg_mev_per_block | REAL | 每区块平均 MEV |
| builder_hhi | REAL | Builder 集中度（HHI） |

## 运行方式

```bash
# 首次回填
python -m data_layer.mev_data.runner --mode bootstrap

# 单次采集
python -m data_layer.mev_data.runner --mode once

# 定时采集
python -m data_layer.mev_data.runner --mode scheduler --async-scheduler

# 输出 AI 上下文
python -m data_layer.mev_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "24h",
  "coverage": {"blocks_analyzed": 7200, "data_sources": 2},
  "summaries": {
    "ethereum": {
      "total_mev_24h_usd": 2850000,
      "sandwich_frequency_1h": 12.5,
      "liquidation_mev_ratio": 0.18,
      "builder_hhi": 0.35,
      "mev_trend": "increasing",
      "data_points": 48
    }
  }
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| FLASHBOTS_API_KEY | Flashbots API 密钥 | （空） |
| EIGENPHI_API_KEY | EigenPhi API 密钥 | （空） |
