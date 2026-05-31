# 数据管道延迟追踪模块 `pipeline_latency`

## 模块定位

`pipeline_latency` 是一个纯只读监控模块，负责追踪各数据域的端到端新鲜度指标。

它不修改任何数据，只读取各域表的最新时间戳，计算延迟并分类为 `fresh / acceptable / stale`。

## 模块代码树

```text
logic_layer/pipeline_latency/
  __init__.py       # 包入口
  models.py         # 数据模型定义（DomainLatency, PipelineLatencyReport）
  repository.py     # 各域最新时间戳读取
  service.py        # 延迟计算与分类
  runner.py         # CLI 运行入口
```

## 新鲜度阈值

| 域 | Fresh（秒） | Acceptable（秒） |
| --- | --- | --- |
| `klines` | 3600 | 7200 |
| `technical_indicators` | 3600 | 7200 |
| `feature_standardization` | 7200 | 14400 |
| `cross_asset` | 7200 | 14400 |
| `portfolio_risk` | 7200 | 14400 |
| `macro_context` | 86400 | 172800 |
| `market_breadth` | 7200 | 14400 |
| `asset_readiness` | 7200 | 14400 |
| `ai_market_context` | 7200 | 14400 |
| `exchange_comparison` | 3600 | 7200 |
| `news` | 3600 | 7200 |

## 输出

- 每个域的最新数据时间戳
- 延迟秒数
- 新鲜度分类（`fresh / acceptable / stale`）
- 全局管道健康状态摘要

## 运行方式

```bash
python -m logic_layer.pipeline_latency.runner
```

在 `logic_pipeline` 全链路中作为 Phase 5 最后执行。
