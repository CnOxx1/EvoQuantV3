# 事件日历采集模块 `event_calendar_data`

`event_calendar_data` 用来把“未来已知事件”从普通新闻流里拆出来，单独形成可调度、可去重、可回查的数据表。

当前版本目标只有一个：

- 把 `macro / etf / unlock / upgrade` 这类事件稳定落到 `event_calendar_events`

当前模块边界：

- 负责采集、标准化、去重、状态更新、落库
- 负责判断当前事件数据是否足够给 AI 当作“未来催化剂证据”
- 不负责市场影响判断
- 不负责给事件打交易信号

## 快速导航

- [模块速览](#模块速览)
- [当前代码树](#当前代码树)
- [当前实现](#当前实现)
- [上游约定](#上游约定)
- [运行方式](#运行方式)
- [AI 数据质量语义](#ai-数据质量语义)
- [环境变量](#环境变量)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 目标 | 把未来已知催化剂从普通新闻流里单独结构化出来 |
| 当前事件语义 | `macro / etf / unlock / upgrade` |
| 核心输出表 | `event_calendar_events` |
| 主 bundle | `load_upcoming_context_bundle()` |
| 上游适配 | `normalized_json` 与 `ics` |
| 质量原则 | 只有 future horizon 与事件密度都达标的真实 source 才会进入 AI 主视图 |

## 当前代码树

```text
event_calendar_data/
  README.md
  __init__.py
  client.py
  collector.py
  models.py
  runner.py
  service.py
  sources.py
```

## 当前实现

- 已有独立的 `client / collector / service / runner`
- 已新增 `event_calendar_events` 表
- 已支持 `scheduled / updated / canceled / completed` 状态
- 已支持 `--list-sources` 和 `--print-upcoming`
- 已支持 `--print-coverage`
- 已支持 `--print-context`
- 已支持两种上游适配方式
  - `normalized_json`
  - `ics`
- 已将每个事件源的采集结果写入 `collection_runs`
- `once` 和 `scheduler` 两条运行路径现在都会写入 `collection_runs`，不再出现“首轮启动有 run 台账，后续常驻调度却没有真实运行记录”的断层
- 已将每个事件源的覆盖状态标准化为 `configuration_ready / health_status / is_ready_for_ai / data_quality_flags / quality_notes`
- 已新增未来事件上下文 bundle，可直接输出未来 24h / 7d / 30d 事件、重点事件、symbol watchlist，以及默认事件宇宙 breadth 诊断

## 上游约定

当前默认最稳的接入方式是让上游输出规范化 JSON：

```json
{
  "events": [
    {
      "external_id": "fomc-2026-06",
      "event_type": "macro",
      "title": "FOMC Rate Decision",
      "description": "Federal Reserve interest rate decision",
      "symbol": "MARKET",
      "scheduled_at": "2026-06-17T18:00:00+00:00",
      "timezone": "UTC",
      "importance_score": 0.98,
      "status": "scheduled",
      "tags": ["fomc", "rates"],
      "source_url": "https://example.com/fomc-2026-06"
    }
  ]
}
```

如果来源本身提供 `.ics`，模块也可以直接解析基础 `VEVENT`。

## 运行方式

一次采集：

```bash
python -m data_layer.event_calendar_data.runner --mode once
```

按事件类型过滤：

```bash
python -m data_layer.event_calendar_data.runner --mode once --event-types macro,etf
```

查看已落库的未来事件：

```bash
python -m data_layer.event_calendar_data.runner --print-upcoming --limit 30
```

查看事件源覆盖和最近采集情况：

```bash
python -m data_layer.event_calendar_data.runner --print-coverage
```

查看给 AI 直接消费的未来事件上下文：

```bash
python -m data_layer.event_calendar_data.runner --print-context --lookahead-days 30
```

## AI 数据质量语义

`event_calendar_data` 的目标不是“只要有事件表就算完成”，而是要明确告诉后续 AI：

- 哪些事件源已经配置了真实上游
- 哪些事件源最近还在正常更新
- 哪些事件源未来视野太短，不足以支持交易前瞻判断
- 哪些事件类型当前根本没有未来事件可用

因此 `load_source_coverage()` 现在会补齐这些字段：

- `configuration_ready`
  - 是否已配置真实 `endpoint`
- `health_status`
  - `ready / stale / error / empty / missing / unconfigured / disabled`
- `is_ready_for_ai`
  - 当前这一路事件数据能否直接给 AI 当作前瞻催化剂输入
  - `health_status=ready` 只表示最近任务成功且 source 没有整体过期；如果未来视野没有达到该事件类型的 `minimum_horizon_days`，或者未来窗口里只有单条低重要度事件，仍不会被标成 `is_ready_for_ai=true`
- `data_quality_flags`
  - 例如 `unconfigured_source / no_historical_events / no_upcoming_events / thin_upcoming_horizon / stale_source`
- `quality_notes`
  - 对上面标记的解释说明
- `minimum_horizon_days`
  - 该类事件建议至少覆盖到多远的未来
- `farthest_event_horizon_days`
  - 当前数据库里这一路事件最远只覆盖到多少天后
- `upcoming_event_density`
  - 当前 horizon 内平均每天能看到多少条未来事件
- `upcoming_high_importance_events`
  - 当前 horizon 内高重要度未来事件数量

当前模块的质量判断原则：

- 不生成任何伪造事件或占位数据
- 如果 `endpoint` 没配，coverage 会明确标成 `unconfigured`，而不是伪装成“空数据正常”
- 如果 `endpoint` 没配，`collection_runs.status` 现在也会直接写成 `unconfigured`，而不是再被误记成 `empty`
- 如果未来窗口里没有可用事件，coverage 会明确标成 `no_upcoming_events`
- 如果事件只覆盖到很近的几天，coverage 会标记 `thin_upcoming_horizon`，提示 AI 的前瞻视野不足
- 如果未来窗口里只有单条低重要度事件，coverage 会标记 `single_low_signal_upcoming_event`
- source 只有在 `farthest_event_horizon_days >= minimum_horizon_days`，且未来窗口不是“单条低信号事件”时，才会被视为 `is_ready_for_ai=true`

在 source coverage 之上，`load_upcoming_context_bundle()` 还会额外构建 AI 可直接消费的未来催化剂上下文：

- `configured_universe_summary`
  - 显式输出当前默认事件宇宙的 `source_count / event_type_count / covered_semantic_groups / missing_semantic_groups / breadth_status`
  - 这层回答的是“默认事件配置本身够不够宽”，不会伪造任何未来事件
- `coverage_summary`
  - 当前 horizon 内 ready/problem source 数量、`ready_for_ai_source_count / not_ready_for_ai_source_count`、已观测事件类型、按 AI-ready 口径计算的缺失事件类型、未来 24h / 7d / 30d 事件数、最远覆盖天数，以及 `coverage_by_source`
- `source_health`
  - 每个事件源的 `health_status / upcoming_events / minimum_horizon_days / farthest_event_horizon_days`
- `upcoming_events`
  - 时间排序后的未来事件列表
  - 这里只保留来自 `is_ready_for_ai=true` 事件源的未来事件，避免把未来视野太短、未配置或 stale 的 source 直接混进 AI 前瞻视图
- `next_24h / next_7d / next_30d`
  - 分时间窗口的未来催化剂切片
- `high_importance_events`
  - 高重要度事件清单
- `by_event_type`
  - 各事件类型当前覆盖数量、重点事件数和最近事件时间
- `symbol_watchlist`
  - 各 symbol 对应的未来事件数、重点事件数、事件类型和标题摘要
- `raw_event_count / raw_source_counts / ai_excluded_source_names / ai_excluded_sources`
  - 保留所有真实已落库事件的原始诊断
  - 如果某个 source 还没达到 `is_ready_for_ai=true`，它的真实事件不会被伪装删除，而是从 AI 直接消费视图剥离，并在这里解释剥离原因
- `data_quality_flags / quality_notes`
  - 是否存在未来事件过 sparse、缺关键事件类型、没有高重要度事件、只剩单一事件类型、或默认事件宇宙本身仍偏窄等问题

这层 bundle 只整理真实 future events，不会制造假的“预测事件”或虚构时间表。
同时它现在会明确区分：

- AI 直接消费视图
  - 只包含来自 `is_ready_for_ai=true` 的事件源
- 原始真实落库视图
  - 通过 `raw_*` 和 `ai_excluded_sources` 暴露全部已落库事件与排除原因

- `coverage_summary.missing_event_types`
  - 现在按 `is_ready_for_ai` 计算，而不是按技术上的 `ready` 计算，避免把“源还活着但未来视野太短”的事件类型误判成已经覆盖
- 如果调用 `load_upcoming_context_bundle(symbols=[...])` 做单资产过滤，bundle 不会再把“过滤后只剩少数事件类型”误判成默认事件宇宙缺失
  - `coverage_summary.missing_event_types` 在这种 symbol-filtered 场景下也会直接返回空列表，避免继续误导 AI

四类默认事件源的维护重点：

- `macro`
  - 用于识别 CPI、非农、FOMC 等风险窗口
- `etf`
  - 用于识别审批、延期和审议节点
- `unlock`
  - 用于识别潜在供给冲击
- `upgrade`
  - 用于识别协议升级、治理执行和主网节点

`load_upcoming_context_bundle()` 现在还会在默认配置宇宙过窄时显式追加 `event_calendar_configured_market_breadth_limited`。例如当前只启用 `macro + unlock` 两类事件，即使这两路数据本身都新鲜完整，AI 看到的仍然只是局部催化剂视角，而不是完整的前瞻事件世界观。

## 环境变量

- `EVENT_CALENDAR_MACRO_SOURCE_URL`
- `EVENT_CALENDAR_ETF_SOURCE_URL`
- `EVENT_CALENDAR_UNLOCK_SOURCE_URL`
- `EVENT_CALENDAR_UPGRADE_SOURCE_URL`
- `EVENT_CALENDAR_EXTRA_SOURCES_JSON`
- `EVENT_CALENDAR_LOOKAHEAD_DAYS`
- `EVENT_CALENDAR_INTERVAL_SECONDS`

## 维护约束

- 这层只做事件获取和结构化，不做市场判断。
- 这层只接真实上游，不允许为了“让 coverage 好看”而填充伪造未来事件。
- 如果后续要扩源，优先新增 source 配置或上游规范化代理，不要把复杂判断写死在 collector 里。
