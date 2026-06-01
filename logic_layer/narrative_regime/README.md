# narrative_regime — 叙事状态机模块

## 定位

追踪加密市场中的叙事主题演变，识别叙事生命周期阶段并映射到资金流向。为 AI 提供市场注意力分布和叙事驱动的交易机会判断。

## 计算逻辑

| 类型 | 计算方法 | 说明 |
|---|---|---|
| narrative_clustering | 高频主题词聚类 | 叙事主题识别 |
| lifecycle_phase | emerging/growing/peak/decaying | 叙事生命周期阶段 |
| capital_flow_mapping | attention 与 token 价格相关性 | 资金流映射 |
| narrative_contagion | 叙事跨社区传播速度 | 叙事传染效应 |

## 代码结构

```
narrative_regime/
├── __init__.py          # 包入口
├── analyzer.py          # 叙事分析器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── service.py           # 服务层
├── runner.py            # CLI 入口
└── README.md
```

## 数据表

### market_narratives

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| narrative_id | TEXT | 叙事 ID |
| narrative_name | TEXT | 叙事名称 |
| lifecycle_phase | TEXT | 生命周期阶段 |
| attention_score | REAL | 注意力评分 |
| capital_flow_correlation | REAL | 资金流相关性 |
| related_tokens | TEXT | 关联代币 |

### narrative_transitions

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 转换时间戳 |
| narrative_id | TEXT | 叙事 ID |
| from_phase | TEXT | 原阶段 |
| to_phase | TEXT | 新阶段 |
| trigger_event | TEXT | 触发事件 |

## 运行方式

```bash
# 执行叙事分析
python -m logic_layer.narrative_regime.runner --mode analyze

# 指定时间窗口
python -m logic_layer.narrative_regime.runner --mode analyze --hours 48

# 输出 AI 上下文
python -m logic_layer.narrative_regime.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "active_narratives": [
    {"name": "AI_tokens", "phase": "growing", "attention_score": 0.85, "related_tokens": ["FET", "RNDR", "TAO"]},
    {"name": "L2_scaling", "phase": "peak", "attention_score": 0.72, "related_tokens": ["ARB", "OP", "STRK"]}
  ],
  "approaching_peak": ["L2_scaling", "RWA_tokenization"],
  "emerging_narratives": [
    {"name": "DePIN", "phase": "emerging", "attention_score": 0.3, "growth_rate": 0.15}
  ],
  "narrative_token_mapping": {
    "AI_tokens": {"tokens": ["FET", "RNDR"], "correlation": 0.78}
  }
}
```

## 输入依赖

- `news` 表（新闻数据）
- `social_sentiment` 表（社交媒体情绪数据）
- `alternative` 表（另类数据）
