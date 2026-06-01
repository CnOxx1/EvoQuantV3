# onchain_address_data — 链上地址画像模块

## 简介

采集链上地址的实体标签、资金流向和大额转账数据，为 AI 提供巨鲸行为追踪和交易所净流向等结构化视角。巨鲸地址的异常资金流动往往是价格变动的领先信号。

## 数据来源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Arkham Intelligence | 实体标签、地址关联、资金流向 | 10 分钟 |
| Etherscan | 地址余额、交易历史、Token 转账 | 10 分钟 |

## 数据库表

### address_labels

| 字段 | 类型 | 说明 |
|---|---|---|
| address | TEXT | 链上地址 |
| entity | TEXT | 实体名称 |
| label_type | TEXT | 标签类型（exchange/fund/whale/project） |
| chain | TEXT | 所属链 |
| confidence | REAL | 标签置信度 |
| updated_at | TEXT | 最后更新时间 |

### address_flows

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 采集时间戳 |
| address | TEXT | 链上地址 |
| direction | TEXT | 流向（in/out） |
| token | TEXT | Token 名称 |
| amount_usd | REAL | 金额（美元） |
| counterparty | TEXT | 对手方地址/实体 |

### whale_moves

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 发生时间 |
| from_address | TEXT | 发送方 |
| to_address | TEXT | 接收方 |
| token | TEXT | Token 名称 |
| amount_usd | REAL | 金额（美元） |
| from_label | TEXT | 发送方标签 |
| to_label | TEXT | 接收方标签 |

## 运行方式

```bash
# 首次回填
python -m data_layer.onchain_address_data.runner --mode bootstrap

# 单次采集
python -m data_layer.onchain_address_data.runner --mode once

# 定时采集
python -m data_layer.onchain_address_data.runner --mode scheduler

# 输出 AI 上下文
python -m data_layer.onchain_address_data.runner --print-context
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| ARKHAM_API_KEY | Arkham Intelligence API 密钥 | （空） |
| ETHERSCAN_API_KEY | Etherscan API 密钥 | （空） |

## 调度频率

每 10 分钟采集一次，由 `ONCHAIN_ADDRESS_INTERVAL_SECONDS=600` 控制。

## 文件结构

```
onchain_address_data/
├── __init__.py          # 包入口
├── client.py            # Arkham / Etherscan API 请求封装
├── models.py            # 链上地址画像数据模型定义
├── runner.py            # CLI 运行入口
├── service.py           # 模块编排、调度与 context bundle
└── README.md
```
