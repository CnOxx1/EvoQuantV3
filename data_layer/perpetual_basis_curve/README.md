# perpetual_basis_curve — 期货期限结构模块

## 定位

采集加密货币季度合约期限结构数据，为 AI 提供市场远期定价与套利空间的量化视角。期限结构形态是市场预期与杠杆情绪的核心观测指标，与趋势延续性高度相关。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Binance 季度合约 | BTC/ETH 当季 + 次季 | 1 小时 |
| OKX 季度合约 | BTC/ETH 当季 + 次季 | 1 小时 |
| Bybit 季度合约 | BTC/ETH 当季 + 次季 | 1 小时 |

## 代码结构

```
perpetual_basis_curve/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（Binance / OKX / Bybit）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层（采集 + 聚合 + AI bundle）
└── README.md
```

## 数据表

### futures_term_structure
| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 时间戳 |
| symbol | TEXT | 交易对 |
| exchange | TEXT | 交易所 |
| contract_type | TEXT | 合约类型（当季/次季） |
| expiry_date | TEXT | 到期日 |
| price | REAL | 合约价格 |
| basis_pct | REAL | 基差百分比 |
| annualized_basis_pct | REAL | 年化基差百分比 |

### basis_curve_snapshot
| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 时间戳 |
| symbol | TEXT | 交易对 |
| curve_slope | REAL | 曲线斜率 |
| contango_backwardation | TEXT | 正向/反向结构 |
| roll_yield_7d | REAL | 7日滚动收益率 |
| term_premium | REAL | 期限溢价 |
| convexity | REAL | 曲线凸度 |

## 运行方式

```bash
# 首次回填
python -m data_layer.perpetual_basis_curve.runner --mode bootstrap

# 单次采集
python -m data_layer.perpetual_basis_curve.runner --mode once

# 定时采集
python -m data_layer.perpetual_basis_curve.runner --mode scheduler --async-scheduler

# 输出 AI 上下文
python -m data_layer.perpetual_basis_curve.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "24h",
  "coverage": {"symbols_tracked": 2, "exchanges": 3},
  "summaries": {
    "BTC": {
      "curve_shape": "contango",
      "curve_slope_24h_change": 0.15,
      "roll_yield_7d": 0.082,
      "term_premium": 0.045,
      "anomaly_detected": false,
      "data_points": 72
    }
  }
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| BINANCE_API_KEY | Binance API 密钥 | （空） |
| OKX_API_KEY | OKX API 密钥 | （空） |
| BYBIT_API_KEY | Bybit API 密钥 | （空） |
