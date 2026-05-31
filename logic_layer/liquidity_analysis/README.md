# liquidity_analysis — 流动性分析模块

## 定位

基于订单簿数据分析市场流动性状况，为 AI 提供执行决策依据。流动性是交易成本的核心决定因素。

## 核心指标

| 指标 | 说明 |
|---|---|
| spread_bps | Bid-Ask 价差（基点） |
| slippage_Xk_bps | 不同规模订单的预估滑点 |
| liquidity_score | 综合流动性评分（0~100） |
| bid/ask_depth_usd | 2% 范围内的买卖盘深度 |

## 预警类型

| 类型 | 触发条件 |
|---|---|
| spread_blow | Spread > 20bps (warning) / > 50bps (critical) |
| depth_drop | 深度下降 > 50% |
| imbalance | 买卖比 > 3:1 |
| thin_book | 总深度 < $100K |

## 代码结构

```
liquidity_analysis/
├── __init__.py          # 包入口
├── calculator.py        # 流动性计算器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
python -m logic_layer.liquidity_analysis.runner --mode analyze
python -m logic_layer.liquidity_analysis.runner --mode analyze --symbols BTC,ETH
python -m logic_layer.liquidity_analysis.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "market_liquidity_state": "healthy",
  "avg_liquidity_score": 72.5,
  "profiles": {
    "BTC": {
      "spread_bps": 1.2,
      "slippage_100k_bps": 3.5,
      "liquidity_score": 92.3
    }
  },
  "active_alerts": []
}
```

## 输入依赖

- `latest_orderbook_snapshot` 表（来自 exchange_data）
