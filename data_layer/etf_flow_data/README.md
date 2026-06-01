# etf_flow_data — ETF 资金流追踪模块

## 定位

采集加密货币现货 ETF 资金流向数据，为 AI 提供机构资金动向的量化视角。ETF 资金流是机构配置行为的直接观测指标，与中期价格趋势高度相关。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| SoSoValue API | BTC/ETH 现货 ETF 全产品线 | 每日（按交易日更新） |

## 代码结构

```
etf_flow_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（SoSoValue）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层（采集 + 聚合 + AI bundle）
└── README.md
```

## 数据表

### etf_daily_flows
| 字段 | 类型 | 说明 |
|---|---|---|
| date | TEXT | 交易日期 |
| etf_name | TEXT | ETF 产品名称 |
| asset | TEXT | 标的资产（BTC/ETH） |
| issuer | TEXT | 发行商 |
| net_flow_usd | REAL | 当日净流入（美元） |
| total_aum_usd | REAL | 总管理规模（美元） |
| shares_outstanding | REAL | 流通份额 |
| price | REAL | ETF 价格 |
| premium_discount_pct | REAL | 溢价/折价百分比 |

### etf_flow_summary
| 字段 | 类型 | 说明 |
|---|---|---|
| date | TEXT | 交易日期 |
| asset | TEXT | 标的资产 |
| total_net_flow_usd | REAL | 全市场净流入（美元） |
| cumulative_net_flow_usd | REAL | 累计净流入（美元） |
| top_inflow_issuer | TEXT | 最大流入发行商 |
| top_outflow_issuer | TEXT | 最大流出发行商 |

## 运行方式

```bash
# 首次回填
python -m data_layer.etf_flow_data.runner --mode bootstrap

# 单次采集
python -m data_layer.etf_flow_data.runner --mode once

# 定时采集
python -m data_layer.etf_flow_data.runner --mode scheduler --async-scheduler

# 输出 AI 上下文
python -m data_layer.etf_flow_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T20:00:00",
  "window": "7d",
  "coverage": {"etfs_tracked": 11, "assets": ["BTC", "ETH"]},
  "summaries": {
    "BTC": {
      "net_flow_7d_usd": 1250000000,
      "trend": "consecutive_inflow",
      "consecutive_days": 5,
      "cumulative_aum_change_pct": 2.3,
      "single_day_anomaly_zscore": 1.8,
      "top_inflow_issuer": "BlackRock",
      "data_points": 7
    }
  }
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| SOSOVALUE_API_KEY | SoSoValue API 密钥 | （空） |
