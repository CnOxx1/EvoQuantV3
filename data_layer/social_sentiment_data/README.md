# social_sentiment_data — 社交情绪数据采集模块

## 定位

采集加密货币社交媒体情绪数据，为 AI 提供市场参与者情绪的量化视角。社交情绪是散户行为的领先指标，与价格走势存在因果关系。

## 数据源

| 来源 | 覆盖范围 | 采集频率 |
|---|---|---|
| LunarCrush | 全平台社交聚合（Twitter、Reddit、YouTube 等） | 30 分钟 |
| Santiment | 社交量 + 情绪加权指数 | 30 分钟 |
| Twitter API v2 | 原始推文搜索、KOL 追踪 | 30 分钟 |

## 代码结构

```
social_sentiment_data/
├── __init__.py          # 包入口
├── client.py            # HTTP 客户端（LunarCrush / Santiment / Twitter）
├── models.py            # 数据模型
├── runner.py            # CLI 入口
├── service.py           # 服务层（采集 + 聚合 + AI bundle）
└── README.md
```

## 数据表

### social_mentions
| 字段 | 类型 | 说明 |
|---|---|---|
| platform | TEXT | 平台标识 |
| entity_key | TEXT | 标的符号 |
| mention_time | TEXT | 提及时间 |
| author_tier | TEXT | 作者层级（kol/whale/retail） |
| sentiment_score | REAL | 情绪分数 -1~1 |
| engagement | INTEGER | 互动量 |
| reach | INTEGER | 触达人数 |

### social_sentiment_agg
| 字段 | 类型 | 说明 |
|---|---|---|
| entity_key | TEXT | 标的符号 |
| platform | TEXT | 数据源 |
| interval | TEXT | 聚合窗口 |
| mention_count | INTEGER | 提及次数 |
| avg_sentiment | REAL | 平均情绪 |
| weighted_sentiment | REAL | 加权情绪 |
| bullish_ratio | REAL | 看多比例 |
| bearish_ratio | REAL | 看空比例 |
| kol_sentiment | REAL | KOL 情绪 |
| volume_zscore | REAL | 提及量 z-score |

## 运行方式

```bash
# 首次回填
python -m data_layer.social_sentiment_data.runner --mode bootstrap

# 单次采集
python -m data_layer.social_sentiment_data.runner --mode once

# 定时采集
python -m data_layer.social_sentiment_data.runner --mode scheduler --async-scheduler

# 输出 AI 上下文
python -m data_layer.social_sentiment_data.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "window": "24h",
  "coverage": {"symbols_with_data": 15, "symbols_requested": 15},
  "summaries": {
    "BTC": {
      "mood": "bullish",
      "avg_sentiment_24h": 0.42,
      "total_mentions_24h": 12500,
      "volume_zscore_peak": 2.3,
      "data_points": 48
    }
  }
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| LUNARCRUSH_API_KEY | LunarCrush API 密钥 | （空） |
| SANTIMENT_API_KEY | Santiment API 密钥 | （空） |
| TWITTER_BEARER_TOKEN | Twitter Bearer Token | （空） |

## 局限性

- Twitter API v2 免费层级限额较低（每月 10,000 条推文）
- LunarCrush 免费 API 有速率限制
- 情绪分析依赖第三方模型，可能存在偏差
