# anomaly_detection — 异常检测模块

## 定位

基于统计方法检测市场异常事件，为 AI 提供早期预警信号。异常事件往往预示着市场拐点或系统性风险。

## 检测维度

| 类型 | 检测方法 | 阈值 |
|---|---|---|
| price_spike | 收益率 z-score | warning: 2.5σ, critical: 3.5σ |
| volume_surge | 成交量/均值比 | warning: 3x, critical: 6x |
| funding_extreme | 资金费率绝对值 | warning: 0.1%, critical: 0.3% |
| correlation_break | 滚动相关性变化 | Δ > 0.4 |

## 风险等级

| 等级 | 触发条件 |
|---|---|
| high | 24h 内 ≥5 个 critical 异常 |
| elevated | 24h 内 ≥2 critical 或 ≥10 warning |
| normal | 其他 |

## 代码结构

```
anomaly_detection/
├── __init__.py          # 包入口
├── detector.py          # 统计异常检测器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
# 执行异常检测
python -m logic_layer.anomaly_detection.runner --mode detect

# 指定标的和时间窗口
python -m logic_layer.anomaly_detection.runner --mode detect --symbols BTC,ETH --hours 12

# 输出 AI 上下文
python -m logic_layer.anomaly_detection.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "market_risk_level": "elevated",
  "summary": {
    "total_anomalies": 12,
    "critical_count": 3,
    "affected_assets": 5
  },
  "entity_summaries": {
    "BTC": {"total_anomalies": 3, "critical": 1, "risk_level": "elevated"}
  },
  "recent_critical": [...]
}
```

## 输入依赖

- `merged_klines` 表（价格和成交量）
- `latest_funding_rates` 表（资金费率）
