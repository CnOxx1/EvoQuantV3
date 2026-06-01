# governance_data — 治理投票数据模块

## 简介

采集 DAO 治理投票数据，为 AI 提供提案状态、参与率趋势和巨鲸投票集中度等结构化视角。重大治理提案（如协议参数变更、资金分配）的通过或否决往往直接影响相关 Token 的价格走势。

## 数据来源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Snapshot GraphQL | Off-chain 投票（提案、选票、投票力） | 30 分钟 |
| Tally GraphQL | On-chain 投票（Governor 合约提案） | 30 分钟 |

## 跟踪空间

当前追踪 5 个重点治理空间：Aave、Uniswap、Compound、Arbitrum、Optimism。

## 数据库表

### governance_proposals

| 字段 | 类型 | 说明 |
|---|---|---|
| proposal_id | TEXT | 提案 ID |
| space | TEXT | 治理空间名称 |
| title | TEXT | 提案标题 |
| status | TEXT | 状态（active/closed/pending/defeated） |
| source | TEXT | 来源（snapshot/tally） |
| start_time | TEXT | 投票开始时间 |
| end_time | TEXT | 投票结束时间 |
| votes_for | REAL | 赞成票数 |
| votes_against | REAL | 反对票数 |
| quorum_reached | INTEGER | 是否达到法定人数 |

### governance_votes

| 字段 | 类型 | 说明 |
|---|---|---|
| vote_id | TEXT | 投票记录 ID |
| proposal_id | TEXT | 关联提案 ID |
| voter | TEXT | 投票者地址 |
| choice | TEXT | 投票选择 |
| voting_power | REAL | 投票力 |
| is_whale | INTEGER | 是否巨鲸（投票力 top 10） |
| ts | TEXT | 投票时间 |

### governance_activity

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 统计时间戳 |
| space | TEXT | 治理空间名称 |
| active_proposals | INTEGER | 活跃提案数 |
| participation_rate | REAL | 参与率 |
| whale_concentration | REAL | 巨鲸投票集中度（0-1） |
| avg_voting_power | REAL | 平均投票力 |

## 运行方式

```bash
# 首次回填
python -m data_layer.governance_data.runner --mode bootstrap

# 单次采集
python -m data_layer.governance_data.runner --mode once

# 定时采集
python -m data_layer.governance_data.runner --mode scheduler

# 输出 AI 上下文
python -m data_layer.governance_data.runner --print-context
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| TALLY_API_KEY | Tally GraphQL API 密钥 | （空） |

## 调度频率

每 30 分钟采集一次，由 `GOVERNANCE_INTERVAL_SECONDS=1800` 控制。

## 文件结构

```
governance_data/
├── __init__.py          # 包入口
├── client.py            # Snapshot / Tally GraphQL 请求封装
├── models.py            # 治理投票数据模型定义
├── runner.py            # CLI 运行入口
├── service.py           # 模块编排、调度与 context bundle
└── README.md
```
