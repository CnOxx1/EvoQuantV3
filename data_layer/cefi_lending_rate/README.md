# cefi_lending_rate — CeFi 借贷利率模块

## 定位

采集中心化交易所借贷利率数据，为 AI 提供 CeFi 资金成本与套利机会的量化视角。CeFi 借贷利率反映市场杠杆需求与资金供需平衡，与 DeFi 利率价差构成跨市场套利信号。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| Binance Earn | 活期/定期借贷产品 | 1 小时 |
| OKX Earn | 活期/定期借贷产品 | 1 小时 |
| Bybit Earn | 活期/定期借贷产品 | 1 小时 |

## 代码结构

```
cefi_lending_rate/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（Binance / OKX / Bybit）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层（采集 + 聚合 + AI bundle）
└── README.md
```

## 数据表

### cefi_lending_rates
| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 时间戳 |
| platform | TEXT | 平台（Binance/OKX/Bybit） |
| asset | TEXT | 资产符号 |
| product_type | TEXT | 产品类型（活期/定期） |
| supply_apy | REAL | 存款年化收益率 |
| borrow_apy | REAL | 借款年化利率 |
| utilization_pct | REAL | 资金利用率百分比 |
| min_amount | REAL | 最低金额 |

### lending_rate_spread
| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TEXT | 时间戳 |
| asset | TEXT | 资产符号 |
| cefi_avg_supply | REAL | CeFi 平均存款利率 |
| defi_avg_supply | REAL | DeFi 平均存款利率 |
| cefi_avg_borrow | REAL | CeFi 平均借款利率 |
| defi_avg_borrow | REAL | DeFi 平均借款利率 |
| supply_spread | REAL | 存款利率价差 |
| borrow_spread | REAL | 借款利率价差 |
| spread_signal | TEXT | 价差信号（normal/inverted/opportunity） |

## 运行方式

```bash
# 首次回填
python -m data_layer.cefi_lending_rate.runner --mode bootstrap

# 单次采集
python -m data_layer.cefi_lending_rate.runner --mode once

# 定时采集
python -m data_layer.cefi_lending_rate.runner --mode scheduler --async-scheduler

# 输出 AI 上下文
python -m data_layer.cefi_lending_rate.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "24h",
  "coverage": {"platforms": 3, "assets_tracked": 10},
  "summaries": {
    "USDT": {
      "cefi_avg_supply_apy": 0.058,
      "defi_avg_supply_apy": 0.072,
      "supply_spread": -0.014,
      "borrow_spread": 0.021,
      "spread_signal": "opportunity",
      "rate_inversion_detected": false,
      "platform_ranking": ["OKX", "Bybit", "Binance"],
      "rate_trend": "rising",
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
