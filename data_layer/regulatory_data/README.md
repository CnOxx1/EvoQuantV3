# regulatory_data — 监管动态数据采集模块

## 定位

采集全球加密货币监管动态，包括执法行动、立法进展、ETF 审批状态。监管事件是加密市场最大的外生冲击源之一，对价格有显著影响。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| CryptoCompare News | 监管类新闻过滤 | 2 小时 |
| SEC EDGAR | 美国 SEC 相关文件 | 2 小时 |

## 追踪维度

- **司法管辖区**: US, EU, CN, UK, JP, KR, global
- **事件类型**: enforcement, guidance, legislation, etf_decision, license
- **影响严重程度**: high, medium, low
- **ETF 状态**: filed, under_review, approved, rejected, withdrawn

## 代码结构

```
regulatory_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层
└── README.md
```

## 运行方式

```bash
python -m data_layer.regulatory_data.runner --mode bootstrap
python -m data_layer.regulatory_data.runner --mode once
python -m data_layer.regulatory_data.runner --mode scheduler --async-scheduler
python -m data_layer.regulatory_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "7d",
  "risk_signal": {
    "regulatory_risk_level": "moderate",
    "high_severity_events_7d": 1,
    "total_events_7d": 8
  },
  "recent_events": [...],
  "etf_tracker": [
    {"name": "iShares Bitcoin Trust", "asset": "BTC", "status": "approved"}
  ]
}
```

## 环境变量

| 变量 | 说明 |
|---|---|
| CRYPTOCOMPARE_API_KEY | CryptoCompare API 密钥（可选，提高限额） |
