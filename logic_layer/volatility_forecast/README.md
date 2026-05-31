# volatility_forecast — 波动率预测模块

## 定位

基于历史收益率计算已实现波动率、EWMA 预测、波动率锥，并与隐含波动率对比。为 AI 提供波动率维度的市场状态判断。

## 核心指标

| 指标 | 说明 |
|---|---|
| realized_vol_Xd | X 天已实现波动率（年化） |
| implied_vol | 隐含波动率（来自期权 ATM IV） |
| rv_iv_spread | RV - IV 差值（正=波动率被低估） |
| forecast_Xd | EWMA 模型 X 天波动率预测 |
| vol_percentile | 当前波动率在历史中的百分位 |
| volatility_cone | 多窗口历史分位数 |

## 波动率状态分类

| 状态 | 年化波动率范围 |
|---|---|
| low | < 30% |
| normal | 30% ~ 60% |
| high | 60% ~ 100% |
| extreme | > 100% |

## 代码结构

```
volatility_forecast/
├── __init__.py          # 包入口
├── calculator.py        # 波动率计算器（RV、EWMA、Cone）
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
python -m logic_layer.volatility_forecast.runner --mode forecast
python -m logic_layer.volatility_forecast.runner --mode forecast --symbols BTC,ETH
python -m logic_layer.volatility_forecast.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "market_volatility_state": "normal",
  "summary": {
    "extreme_vol_assets": 0,
    "high_vol_assets": 3,
    "avg_rv_30d": 0.52
  },
  "entities": {
    "BTC": {
      "realized_vol_30d": 0.45,
      "forecast_7d": 0.48,
      "vol_regime": "normal",
      "vol_percentile": 62.5
    }
  },
  "btc_volatility_cone": [...]
}
```

## 输入依赖

- `merged_klines` 表（收盘价序列）
- `options_vol_surface` 表（隐含波动率，可选）
