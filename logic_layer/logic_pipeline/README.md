# 逻辑层全链路编排模块 `logic_pipeline`

## 模块定位

`logic_pipeline` 是逻辑处理层的顶层编排器，负责按依赖顺序执行全部逻辑模块，生成 AI 可消费的完整市场上下文。

它不做任何计算，只负责调度和错误隔离。

## 模块代码树

```text
logic_layer/logic_pipeline/
  __init__.py       # 包入口
  service.py        # 全链路编排逻辑与定时调度
  runner.py         # CLI 运行入口
```

## 执行顺序

全链路按 5 个阶段顺序执行，阶段内模块互相独立可并行：

| 阶段 | 模块 | 依赖 |
| --- | --- | --- |
| Phase 1 | `technical_indicators` | 原始 klines |
| Phase 2 | `feature_standardization`, `cross_asset_analysis`, `exchange_comparison`, `macro_context`, `news_sentiment` | Phase 1 或原始数据 |
| Phase 3 | `portfolio_risk`, `market_breadth`, `asset_readiness` | Phase 2 |
| Phase 4 | `ai_market_context` | Phase 3（最终聚合） |
| Phase 5 | `pipeline_latency` | 只读监控 |

## 运行方式

```bash
# 单次执行全链路
python -m logic_layer.logic_pipeline.runner

# 定时执行（默认每 5 分钟）
python -m logic_layer.logic_pipeline.runner --schedule
```

定时间隔通过环境变量 `LOGIC_PIPELINE_INTERVAL_SECONDS` 配置，默认 300 秒。

## 错误隔离

- 单个模块失败不会阻断后续阶段执行
- 每个模块的执行结果（success / error）会被记录
- 全链路返回各阶段结果摘要供监控使用
