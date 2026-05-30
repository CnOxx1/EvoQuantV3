# 市场结构上下文模块 `market_structure`

## 模块定位

`market_structure` 不接任何新外部数据源。

它只重组当前已经真实落库的 `exchange_data`，把现货/合约横截面、资金费率、basis、持仓量、清算和主动买卖流整理成更适合 AI 消费的“市场结构证据”。

这个模块只做：

- 读取真实 `exchange_data` latest bundle
- 聚合成资产级市场结构上下文
- 明确暴露当前结构证据是否完整、是否偏薄
- 持久化上下文快照

这个模块不做：

- 外部采集
- 信号打分
- 交易决策
- 伪造缺失数据

## 快速导航

- [模块速览](#模块速览)
- [为什么需要它](#为什么需要它)
- [当前输入](#当前输入)
- [当前输出](#当前输出)
- [当前运行方式](#当前运行方式)
- [当前存储](#当前存储)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 核心任务 | 把 `exchange_data` 的分段证据重组为资产级市场结构上下文 |
| 主要 section | `trade_flow / funding / basis / open_interest / liquidation / positioning / cross_exchange` |
| 核心输出 | `assets / structure_completeness_score / data_quality_flags / ai_visible_coverage_summary` |
| 运行模式 | `--print-context` 或 `--save-snapshot` |
| 存储 | `market_structure_snapshots` |
| 质量原则 | raw 覆盖与 AI-visible 覆盖分离，stale 或 not-ready 结构不会继续给 AI 计分 |

## 为什么需要它

当前项目里最成熟的真实证据带是 `exchange_data`，但原始 bundle 仍然偏“按 source 分段”。

AI 真正更需要的是按市场结构问题来读：

- 当前各交易所资金费率方向是否分裂
- basis 是整体正 carry、负 carry，还是跨交易所严重分化
- 持仓量是否在扩张还是收缩
- 清算是偏多头还是偏空头
- 主动买卖流是现货主导还是合约主导
- 当前横截面对比是否足够厚，还是仍然只有单交易所/单 section 视角

`market_structure` 就是把这些真实证据重组为一层更稳定的解释结构。

## 当前输入

- `data_layer.exchange_data.load_latest_market_context_bundle()`

当前不会直接读原始 `latest_*` 表，而是复用上游已经完成的：

- `is_ready_for_ai` 过滤
- `coverage_summary`
- `cross_exchange_diagnostics`
- `source_health_summary`
- `ai_excluded_source_names`

这样可以避免在这一层重新把 not-ready 的真实数据洗白回主视图。

## 当前输出

`build_latest_context_bundle()` 当前输出：

- `configured_universe_summary`
- `source_health_summary`
- `coverage_summary`
- `ai_visible_coverage_summary`
- `quality_distribution`
- `assets`

每个资产会输出：

- `trade_flow_context`
- `funding_context`
- `basis_context`
- `open_interest_context`
- `liquidation_context`
- `positioning_context`
- `cross_exchange_context`
- `structure_completeness_score`
- `data_quality_flag`
- `data_quality_flags`
- `quality_notes`

其中最关键的是：

- `structure_completeness_score`
  - 当前市场结构核心 section 的 `AI-visible` 完整度
  - 只按真正进入主视图、可直接给 AI 使用的 section 计分
  - 不会因为 raw 表里仍有 stale 快照，就把完整度虚高抬上去
- `coverage_summary`
  - 保留上游 `exchange_data` 的 raw 覆盖诊断
- `ai_visible_coverage_summary`
  - 单独告诉你当前真正进入 AI 主视图的 section 有哪些
  - 以及哪些 section 虽然 raw 里有真实快照，但因为 stale / 质量不达标已被剥离
- `data_quality_flag`
  - `ok / partial / thin`
- `data_quality_flags`
  - 会明确标出 `market_structure_core_section_missing`、`market_structure_cross_exchange_thin`、`market_structure_trade_flow_derivatives_missing` 等问题

当前质量语义还要注意：

- `ok`
  - 不只要求 `spot / orderbook / funding / trade_flow / open_interest / basis` 这些核心结构齐全
  - 还要求 `liquidations` 和 `positioning` 这两类杠杆拥挤证据已真实可见
- `partial`
  - 代表核心结构大体可读，但像 `liquidations`、`positioning` 这类补充杠杆证据仍有缺口
- `thin`
  - 代表当前横截面交易所数量或核心 section 本身就过薄

这里要特别区分两层语义：

- `coverage_summary` 回答的是 raw 层“真实采到过什么”
- `structure_completeness_score` 和 `data_quality_flag` 回答的是“当前到底还有多少结构真的可以直接给 AI 用”

也就是说，真实但已经 stale、已被上游判定为 not-ready 的结构，不会在这里继续给 AI“冒充可用证据”。

## 当前运行方式

输出当前市场结构 bundle：

```bash
python -m logic_layer.market_structure.runner --print-context
```

只看指定资产：

```bash
python -m logic_layer.market_structure.runner --print-context --assets BTC,ETH
```

输出并保存快照：

```bash
python -m logic_layer.market_structure.runner --save-snapshot
```

## 当前存储

快照会落到数据库表：

- `market_structure_snapshots`

当前保存：

- `snapshot_time`
- `scope_kind`
- `asset_count`
- `data_quality_flag`
- `bundle_json`

## 维护约束

- 这里只能复用真实 `exchange_data` 已落库结果，不能补任何假 basis、假 funding、假 OI。
- 如果 raw 覆盖诊断和 AI-visible 主视图的语义发生变化，必须同时更新 `structure_completeness_score`、当前 README 和测试。
- 如果修改输出结构、质量标记或快照表语义，必须同步更新本 README、`logic_layer/README.md` 和相关测试。
- 如果上游 `exchange_data` bundle 字段变化，必须同步校正这里的聚合映射。
