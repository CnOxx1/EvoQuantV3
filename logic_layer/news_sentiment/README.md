# 新闻情感分类模块 `news_sentiment`

## 模块定位

`news_sentiment` 属于逻辑处理层，负责对 `news_data` 采集的新闻进行情感标注和事件分类。

当前实现完全基于规则和关键词匹配，不依赖任何外部 LLM API，可离线运行。

## 模块代码树

```text
logic_layer/news_sentiment/
  __init__.py       # 包入口
  models.py         # 数据模型定义（SentimentLabel）
  classifier.py     # 规则分类器（关键词 + 正则）
  repository.py     # 数据读取与结果落库
  service.py        # 编排入口
  runner.py         # CLI 运行入口
```

## 分类维度

| 维度 | 取值 | 说明 |
| --- | --- | --- |
| `sentiment` | bullish / bearish / neutral | 情感方向 |
| `confidence` | 0.0 ~ 1.0 | 分类置信度 |
| `event_type` | regulatory / hack / partnership / tokenomics / technical / macro / unknown | 事件类型 |
| `impact_scope` | market_wide / sector / asset_specific | 影响范围 |
| `impact_duration` | short / medium / long | 预估影响持续时间 |

## 分类方法

- 情感方向：中英文看涨/看跌关键词命中计数，取净方向
- 事件类型：正则模式匹配，按优先级取第一个命中
- 影响范围：根据文本中是否包含全市场/板块/具体资产关键词判断
- 影响持续时间：根据事件类型映射（如 hack → short，regulatory → long）

## 关键词覆盖

- 英文看涨词：surge, rally, breakout, approval, adoption, partnership...
- 英文看跌词：crash, plunge, hack, ban, lawsuit, liquidat...
- 中文看涨词：利好, 突破, 创新高, 通过, 合作...
- 中文看跌词：利空, 暴跌, 黑客, 禁止, 破产...

## 运行方式

```bash
python -m logic_layer.news_sentiment.runner
```
