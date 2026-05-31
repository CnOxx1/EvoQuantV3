# regime_detection — 市场状态识别模块

## 定位

基于多因子分析识别当前市场所处的状态（趋势/震荡/危机），为 AI 提供自适应策略分配的基础判断。状态识别是所有后续决策的前置条件。

## 分类维度

| 维度 | 状态 | 判定依据 |
|---|---|---|
| 价格状态 | trending_up, trending_down, ranging, crisis | ADX + 收益率 + 最大回撤 |
| 波动率状态 | low, normal, high, extreme | 年化波动率阈值 |
| 相关性状态 | high_corr, moderate_corr, decorrelated | 与 BTC 皮尔逊相关系数 |
| 动量状态 | strong_up, weak_up, neutral, weak_down, strong_down | RSI |

## 市场整体状态

| 状态 | 触发条件 |
|---|---|
| crisis | 30%+ 标的处于 crisis |
| bull_trend | 50%+ 标的 trending_up |
| bear_trend | 50%+ 标的 trending_down |
| mixed_ranging | 其他 |

## 代码结构

```
regime_detection/
├── __init__.py          # 包入口
├── classifier.py        # 多因子状态分类器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
# 执行状态识别
python -m logic_layer.regime_detection.runner --mode detect

# 指定标的
python -m logic_layer.regime_detection.runner --mode detect --symbols BTC,ETH,SOL

# 输出 AI 上下文
python -m logic_layer.regime_detection.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "market_phase": "bull_trend",
  "market_summary": {
    "crisis_assets": 0,
    "trending_up_assets": 8,
    "trending_down_assets": 2,
    "ranging_assets": 2
  },
  "entities": {
    "BTC": {
      "regime": "trending_up",
      "confidence": 0.82,
      "volatility_regime": "normal",
      "momentum_regime": "strong_up"
    }
  }
}
```

## 输入依赖

- `merged_klines` 表（来自 exchange_data）
- 需要至少 20 条历史 kline 才能进行分类
