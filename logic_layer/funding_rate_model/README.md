# funding_rate_model — 资金费率模型模块

## 定位

基于历史 funding rate 和期现基差数据，预测未来 funding rate 走势并生成均值回归交易信号。为 AI 提供衍生品市场定价偏差的量化视角。

## 核心指标

### Funding Rate 维度
| 指标 | 说明 |
|---|---|
| predicted_next | 下一期 funding rate 预测 |
| rate_zscore | 当前 rate 相对历史的 z-score |
| cumulative_7d | 7 天累积 funding 成本 |
| direction_bias | 多空拥挤方向 |
| mean_reversion_signal | 均值回归信号 (-1~1) |

### Basis 维度
| 指标 | 说明 |
|---|---|
| basis_pct | 期现价差百分比 |
| annualized_basis | 年化基差收益 |
| basis_regime | contango/backwardation/flat |
| mean_reversion_signal | 基差均值回归信号 |

## 代码结构

```
funding_rate_model/
├── __init__.py          # 包入口
├── calculator.py        # 费率计算器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
python -m logic_layer.funding_rate_model.runner --mode model
python -m logic_layer.funding_rate_model.runner --mode model --symbols BTC,ETH
python -m logic_layer.funding_rate_model.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "market_positioning": {
    "long_crowded_assets": ["DOGE", "SOL"],
    "short_crowded_assets": [],
    "overall_bias": "long"
  },
  "funding": {
    "BTC": {
      "current_rate": 0.0003,
      "predicted_next": 0.00025,
      "direction_bias": "slight_long",
      "mean_reversion_signal": -0.35
    }
  },
  "basis": {
    "BTC": {
      "basis_pct": 0.15,
      "annualized_basis": 0.61,
      "basis_regime": "contango"
    }
  }
}
```

## 输入依赖

- `latest_funding_rates` 表（funding rate 历史）
- `latest_tickers` 表（现货/期货价格）
- `latest_basis` 表（基差历史）
