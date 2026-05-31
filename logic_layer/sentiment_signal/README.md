# sentiment_signal — 情绪信号模块

## 定位

基于社交情绪数据和价格数据的交叉分析，生成情绪驱动的交易信号。验证情绪是否对价格有预测力，并在情绪极值时生成反转信号。

## 信号类型

| 类型 | 逻辑 | 方向 |
|---|---|---|
| extreme_reversal | 情绪达到极端水平（z>2），预期均值回归 | 反向 |
| momentum_confirm | 情绪与价格同向加速 | 同向 |
| divergence | 情绪与价格方向相反 | 情绪方向 |

## Granger 因果检验

通过比较不同滞后期的相关性判断领先/滞后关系：
- `sentiment_leads_price`: 情绪变化领先于价格变化
- `price_leads_sentiment`: 价格变化领先于情绪变化
- `bidirectional`: 双向因果
- `none`: 无显著因果关系

## 代码结构

```
sentiment_signal/
├── __init__.py          # 包入口
├── analyzer.py          # 情绪分析器（极值、动量、背离、因果）
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
python -m logic_layer.sentiment_signal.runner --mode analyze
python -m logic_layer.sentiment_signal.runner --mode analyze --symbols BTC,ETH
python -m logic_layer.sentiment_signal.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "signal_summary": {
    "total_signals": 5,
    "bullish_count": 3,
    "bearish_count": 2,
    "net_bias": "bullish"
  },
  "causality_summary": {
    "sentiment_leads_price": ["BTC", "ETH"],
    "predictive_assets": 2
  },
  "active_signals": [
    {
      "entity_key": "BTC",
      "signal_type": "extreme_reversal",
      "direction": "bearish",
      "strength": 0.75,
      "sentiment_zscore": 2.3
    }
  ]
}
```

## 输入依赖

- `social_sentiment_agg` 表（来自 social_sentiment_data）
- `merged_klines` 表（来自 exchange_data）
