# onchain_lead_lag — 链上领先/滞后分析模块

## 简介

基于链上信号和交易所价格序列，计算链上指标对价格变动的领先/滞后关系。通过交叉相关性、Granger 因果检验和预测力评估，量化哪些链上信号能有效预测价格走势，为 AI 提供信号优先级排序依据。

## 输入数据

| 来源模块 | 数据 |
|---|---|
| onchain_data | 链上信号时序（whale_net_flow、exchange_inflow 等） |
| exchange_data | BTC/ETH/SOL 价格序列 |

## 信号集

| 信号 | 说明 |
|---|---|
| whale_net_flow | 巨鲸地址净流入/流出 |
| exchange_inflow | 交易所净流入量 |
| gas_spike | Gas 价格尖刺事件 |
| funding_rate | 永续合约资金费率 |
| open_interest_change | 未平仓合约变化率 |

## 目标资产

BTC、ETH、SOL

## 计算内容

- 交叉相关性：信号与价格收益率在不同滞后期的相关系数
- 最优滞后期：相关性最大时对应的时间偏移（分钟/小时）
- Granger 因果检验：信号是否在统计意义上领先于价格变动
- 预测力评估：R² 衡量信号对未来收益率的解释力

## 数据库表

### lead_lag_signals

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| signal_name | TEXT | 信号名称 |
| target_symbol | TEXT | 目标资产 |
| optimal_lag_minutes | INTEGER | 最优滞后期（分钟） |
| max_correlation | REAL | 最大交叉相关系数 |
| granger_p_value | REAL | Granger 因果 p 值 |
| r_squared | REAL | 预测力 R² |
| direction | TEXT | 信号方向（leading/lagging/neutral） |

### onchain_price_relations

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 计算时间戳 |
| signal_name | TEXT | 信号名称 |
| target_symbol | TEXT | 目标资产 |
| lag_minutes | INTEGER | 滞后期 |
| correlation | REAL | 该滞后期相关系数 |
| sample_size | INTEGER | 样本量 |

### signal_alerts

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 触发时间 |
| signal_name | TEXT | 信号名称 |
| target_symbol | TEXT | 目标资产 |
| signal_value | REAL | 当前信号值 |
| expected_impact | TEXT | 预期影响方向（bullish/bearish） |
| confidence | REAL | 置信度（基于历史 R²） |

## 运行方式

```bash
# 执行领先/滞后分析
python -m logic_layer.onchain_lead_lag.runner --mode once

# 指定标的
python -m logic_layer.onchain_lead_lag.runner --mode once --symbols BTC,ETH,SOL

# 定时计算
python -m logic_layer.onchain_lead_lag.runner --mode scheduler

# 输出 AI 上下文
python -m logic_layer.onchain_lead_lag.runner --print-context
```

## 文件结构

```
onchain_lead_lag/
├── __init__.py          # 包入口
├── calculator.py        # 交叉相关、Granger 因果、R² 计算
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 运行入口
├── service.py           # 服务层（编排计算 + context bundle）
└── README.md
```
