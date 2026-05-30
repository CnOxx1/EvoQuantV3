# AI 市场上下文模块 `ai_market_context`

## 模块定位

`ai_market_context` 负责把多个数据层与逻辑层模块的 latest 快照，重组成一份 AI 可直接消费的最终市场上下文。

它不做：

- 做多做空判断
- 信号打分
- 结论归因

它只做：

- 聚合证据
- 统一结构
- 标记覆盖率和数据质量
- 显式告诉 AI 当前这份上下文到底值不值得信
- 持久化 AI 上下文快照

## 快速导航

- [模块速览](#模块速览)
- [当前输入](#当前输入)
- [当前设计要点](#当前设计要点)
- [当前输出结构](#当前输出结构)
- [当前代码树](#当前代码树)
- [当前落库](#当前落库)
- [运行方式](#运行方式)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 核心任务 | 聚合多个数据层与逻辑层 latest 快照，生成最终 AI 市场上下文 |
| 主要依赖 | `exchange / news / event_calendar / onchain / tokenomics / alternative / macro / market_structure / market_breadth / asset_readiness / exchange_comparison / data_quality` |
| 关键输出段 | `market_microstructure / derivatives_structure / macro_regime / news_and_events / data_readiness / evidence` |
| 关键分层 | `cross_exchange_execution` 与 `raw_cross_exchange_execution`、`macro_regime` 与 `raw_macro_regime` |
| 存储 | `ai_market_context_snapshots` |
| 质量原则 | 只复用上游 AI-ready 主视图，不把 not-ready 的真实快照重新洗白进最终 bundle |

## 当前输入

- `data_layer.exchange_data`
- `data_layer.news_data`
- `data_layer.event_calendar_data`
- `data_layer.onchain_data`
- `data_layer.tokenomics_data`
- `data_layer.alternative_data`
- `logic_layer.macro_context`
- `logic_layer.market_structure`
- `logic_layer.market_breadth`
- `logic_layer.asset_readiness`
- `data_layer.data_quality`
- `logic_layer.exchange_comparison`

## 当前设计要点

当前这层不再直接从 `news_articles / event_calendar_events` 原表拼一份“看起来有内容”的上下文。

它现在严格复用上游模块已经建立好的 AI-ready 主视图：

- 新闻只取 `news_data.load_latest_context_bundle()` 里已经通过 `is_ready_for_ai` 过滤的 `latest_articles`
- 市场广度只取 `market_breadth` 已经按 AI-ready `exchange / news / tokenomics` 主视图收紧后的结果
- 事件只取 `event_calendar_data.load_upcoming_context_bundle()` 里已经通过 `is_ready_for_ai` 过滤的 `upcoming_events`
- 资产是否真的具备足够证据，不再靠“字段有没有值”猜测，而是直接复用 `asset_readiness`
- 全局 required 证据带是否成型，不再靠局部 bundle 自说自话，而是直接复用 `data_quality` 的 `market_world_status`
- 跨交易所执行上下文也不再直接裸暴露 `exchange_comparison_snapshots` 原始结果，而是先剥离掉 `data_quality_warning`、ticker/orderbook 陈旧、盘口缺失、跨交易所时间错位等阻断性快照，只把 AI-visible 结果放进主视图

这意味着：

- `coverage_score` 现在本质上是资产级真实 `readiness_score`
- `data_quality_flag` 现在可能是 `ok / partial / thin / blocked`
- 即使某些原始快照存在，只要对应证据带还没达到 AI-ready，也不会被这里重新洗白成“可直接分析”
- `market_structure` 和 `asset_readiness.exchange` 现在也都只按 `AI-visible` section 计分
- `cross_exchange_execution` 现在也是 AI-visible 执行上下文，而不是“数据库里有横截面对比行就算可用”
- 所以你可能会看到“raw 诊断里仍有真实快照”，但 `coverage_score` 依然是 0 或很低，这正是为了避免高估数据质量

## 当前输出结构

当前 bundle 会按 AI 易消费的方式重组为几大段：

- `market_microstructure`
- `derivatives_structure`
- `cross_exchange_execution`
- `raw_cross_exchange_execution`
- `cross_exchange_execution_quality_summary`
- `market_structure`
- `onchain_capital_flow`
- `tokenomics_supply_pressure`
- `macro_regime`
- `raw_macro_regime`
- `news_and_events`
- `attention_and_builder_activity`
- `data_readiness`
- `risk_flags`
- `evidence`

同时输出：

- `coverage_score`
- `data_quality_flag`
- `data_quality_flags`
- `quality_notes`

### `data_readiness` 的作用

这是这次升级后最关键的新增段。

它会直接告诉 AI：

- 当前 `market_world_status`
- 当前市场 breadth 是 `sufficient / narrow / thin` 中的哪一种
- 当前资产自身是 `ready / partial / thin / blocked` 中的哪一种
- 当前资产缺了哪些 band
- 每个 band 当前是 `ready / limited / missing / shared_missing` 中的哪一种
- 当前 `cross_exchange_execution` 是 `ready / partial / raw_only / missing` 中的哪一种

也就是说，AI 不需要再从主 bundle 的“空不空”里猜数据质量，而是能直接拿到一层明确的真实性诊断。

### `cross_exchange_execution` 与 `raw_cross_exchange_execution`

这次升级后，跨交易所执行语境被明确拆成了两层：

- `cross_exchange_execution`
  - 只保留当前可以直接给 AI 用的横截面对比行
  - 如果行上已经带有 `data_quality_warning`
  - 或存在 `missing/stale ticker`
  - 或存在 `missing/stale orderbook`
  - 或存在 `missing bid/ask`
  - 或存在 `cross_exchange_ticker_gap / cross_exchange_orderbook_gap`
  - 则不会进入主视图
- `raw_cross_exchange_execution`
  - 保留真实原始对比快照，便于诊断为什么主视图为空
- `cross_exchange_execution_quality_summary`
  - 汇总 `raw_row_count / visible_row_count / excluded_row_count`
  - 明确标记当前状态是 `ready / partial / raw_only / missing`
  - 暴露被过滤掉的 `signal_label` 和 `data_quality_flag` 统计

这样做的目的是让 AI 看到的是“当前仍能成立的跨交易所执行证据”，而不是“数据库里残留过的所有横截面结果”。

### `macro_regime` 与 `raw_macro_regime`

`macro_context` 本身是逻辑层加工结果，但宏观证据带能不能直接给 AI 用，仍然要服从 `data_quality` 的世界模型审计。

因此现在：

- 如果宏观 band 已达到 AI-ready，结果会暴露在 `macro_regime`
- 如果宏观 band 还没有达到 AI-ready，`macro_regime` 会被剥离为空，只把原始上下文保留在 `raw_macro_regime`
- 即使宏观 band 已达到 AI-ready，`macro_regime.factors` 现在也只保留 `AI-visible` 宏观因子；stale 或 `raw_only` 的真实宏观点会继续保留在 `raw_macro_regime.raw_factors`

这样可以避免“上层特征比底层证据更乐观”的问题。

## 当前代码树

```text
ai_market_context/
  README.md
  __init__.py
  models.py
  repository.py
  service.py
  runner.py
```

## 当前落库

- `ai_market_context_snapshots`
  - 保存每个 `entity_key` 的最终上下文快照
  - `bundle_json` 保留完整证据结构，便于后续 AI 直接读取

## 运行方式

构建但不落库：

```bash
python -m logic_layer.ai_market_context.runner --entities BTC,ETH --no-save --print-bundle
```

构建并落库：

```bash
python -m logic_layer.ai_market_context.runner --entities BTC,ETH,SOL,SUI
```

## 维护约束

- 这里是 AI 供数聚合层，不是策略层。
- 如果新增新的数据子模块，优先扩 `data_readiness` 和 bundle 主结构，而不是回退到直接查原始表拼装。
- 如果修改 `coverage_score / data_quality_flag` 语义，必须同步更新当前 README 和测试。
- 如果修改 bundle 结构，必须同步更新当前 README 和下游 AI prompt / 解析逻辑。
