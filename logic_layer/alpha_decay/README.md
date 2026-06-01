# alpha_decay — 信号衰减与拥挤度模块

## 定位

监控所有逻辑层信号的有效性衰减和市场拥挤度，识别信号过度一致带来的反转风险。为 AI 提供信号质量评估和逆向思维依据。

## 计算逻辑

| 类型 | 计算方法 | 说明 |
|---|---|---|
| half_life | 自相关衰减拟合 | 信号半衰期估算 |
| crowding | 多信号同向比例 | 市场拥挤度量化 |
| signal_surprise | 偏离近期分布程度 | 信号惊喜度 |
| cross_divergence | 跨信号方向背离 | 信号一致性/分歧度 |

## 代码结构

```
alpha_decay/
├── __init__.py          # 包入口
├── calculator.py        # 信号衰减计算器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── service.py           # 服务层
├── runner.py            # CLI 入口
└── README.md
```

## 数据表

### signal_decay

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| signal_name | TEXT | 信号名称 |
| module_source | TEXT | 来源模块 |
| half_life_hours | REAL | 半衰期(小时) |
| autocorrelation | REAL | 自相关系数 |
| current_strength | REAL | 当前信号强度 |
| decay_rate | REAL | 衰减速率 |

### crowding_index

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| crowding_score | REAL | 拥挤度评分 |
| agreeing_signals | INTEGER | 同向信号数 |
| disagreeing_signals | INTEGER | 反向信号数 |
| contrarian_signal | TEXT | 最强反向信号 |
| signal_surprise_index | REAL | 信号惊喜指数 |

## 运行方式

```bash
# 执行信号衰减分析
python -m logic_layer.alpha_decay.runner --mode calculate

# 指定信号源和时间窗口
python -m logic_layer.alpha_decay.runner --mode calculate --symbols BTC,ETH --hours 24

# 输出 AI 上下文
python -m logic_layer.alpha_decay.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "signal_effectiveness": {
    "momentum": {"half_life_hours": 4.2, "current_strength": 0.7, "validity": "active"},
    "mean_reversion": {"half_life_hours": 1.5, "current_strength": 0.3, "validity": "decaying"}
  },
  "market_crowding": {
    "score": 78,
    "level": "high",
    "agreeing_signals": 8,
    "disagreeing_signals": 2
  },
  "strongest_contrarian": "volatility_regime_shift",
  "signal_consistency": 0.8
}
```

## 输入依赖

- 所有逻辑层信号输出（跨模块聚合）
