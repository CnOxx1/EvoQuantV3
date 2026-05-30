# 资产级证据可用性模块 `asset_readiness`

## 模块定位

`asset_readiness` 不采集任何外部数据。

它只读取当前数据库里已经真实存在的：

- `exchange_data`
- `news_data`
- `event_calendar_data`
- `onchain_data`
- `tokenomics_data`
- `options_data`
- `alternative_data`
- `data_quality`

然后回答一个比“整体世界模型是否 ready”更细的问题：

- 当前具体哪些资产已经具备足够宽、足够稳、足够诚实的证据链
- 哪些资产只是有局部新闻或局部行情，但跨证据带仍然断裂
- 某个 band 的空白到底是 `untracked`，还是已经纳入默认宇宙但当前没有可用样本

## 快速导航

- [模块速览](#模块速览)
- [设计原则](#设计原则)
- [当前输出](#当前输出)
- [状态语义](#状态语义)
- [当前运行方式](#当前运行方式)
- [当前存储](#当前存储)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 目标 | 判断哪些资产已经具备足够宽、足够稳的真实证据链 |
| 主要依赖 | `exchange / news / event_calendar / onchain / tokenomics / options / alternative / data_quality` |
| 核心输出 | `market_world_status / band_coverage_summary / assets / readiness_score` |
| 状态层级 | `ready / partial / thin / blocked`，band 级还区分 `limited / missing / untracked` |
| 特别约束 | `exchange` band 只按 AI-visible section 计分 |
| 质量原则 | 不把 raw 旧快照、局部样本或未纳入默认宇宙的资产误报成 ready |

## 设计原则

- 不接任何新外部 API
- 不制造任何假数据、假价格、假事件、假链上指标
- 严格复用上游模块已经定义好的 `is_ready_for_ai` 语义
- 保守优先，不把链、协议、主题词硬洗成同等强度的“可交易资产证据”

也就是说：

- 如果 `macro / event_calendar / onchain / tokenomics / options` 这些证据带本身还没过 AI-ready 门槛，这里只会诚实地标成缺口
- 如果某个资产根本没被纳入默认跟踪宇宙，这里会标成 `untracked`
- 如果某个资产只是局部有新闻、有行情，但其他关键 band 仍然缺失，这里只会给 `partial / thin / blocked`
- 对 `exchange` band 来说，只有真正进入主视图的 AI-ready section 才会计入 readiness
- 如果只是 raw 表里还有真实旧快照、但这些 section 已因 stale / 质量问题被上游剥离，这里不会继续给分

## 当前输出

`build_latest_context_bundle()` 现在会输出：

- `market_world_status`
  - 当前全局市场世界模型状态，直接继承 `data_quality` 审计
- `global_band_statuses`
  - 每条全局证据带当前的 `band_status / is_band_ready_for_ai / blocking_reasons`
- `asset_count / ready_asset_count / partial_asset_count / thin_asset_count / blocked_asset_count`
  - 当前资产级 readiness 分布
- `average_readiness_score`
  - 基于真实 band 命中情况计算的平均 readiness 分数
- `band_coverage_summary`
  - 每条 band 在资产维度上的 `ready / limited / missing / untracked / shared_missing`
- `assets`
  - 每个资产当前的真实证据矩阵

每个资产会带出：

- `asset_status`
  - `ready / partial / thin / blocked`
- `readiness_score`
  - 基于 `exchange / news / event_calendar / onchain / tokenomics / options / alternative / macro`
    的确定性加权分数
- `missing_band_names`
  - 当前还缺哪些证据带
- `limited_band_names`
  - 当前有哪些证据带只有弱覆盖
- `bands`
  - 每条 band 的状态、权重、证据数、结构化细节和备注

其中 `exchange` band 的细节现在会额外带出：

- `visible_sections`
  - 当前真正还在 AI 主视图里的交易所 section
- `raw_row_count`
  - raw 层仍然存在多少真实交易所快照

这样可以明确区分“当前可用的交易所证据”和“数据库里还躺着但已经不该直接给 AI 用的旧结构”。

## 状态语义

- `ready`
  - 当前 band 或资产已经具备可直接给 AI 使用的真实证据
- `limited`
  - 已有真实样本，但覆盖仍偏薄或质量比例不够高
- `missing`
  - 理论上已纳入默认跟踪宇宙，但当前没有可用样本
- `untracked`
  - 当前默认跟踪宇宙根本没有覆盖该资产
- `shared_ready / shared_missing`
  - 对所有资产共享的全局证据带状态，例如宏观、事件日历

## 当前运行方式

输出当前资产级 readiness：

```bash
python -m logic_layer.asset_readiness.runner --print-context
```

只看指定资产：

```bash
python -m logic_layer.asset_readiness.runner --print-context --assets BTC,ETH,SOL
```

输出并保存快照：

```bash
python -m logic_layer.asset_readiness.runner --save-snapshot
```

## 当前存储

快照会落到数据库表：

- `asset_readiness_snapshots`

当前表保存：

- 快照时间
- 当前全局 `market_world_status`
- 资产级状态分布
- 平均 readiness 分数
- 完整 bundle JSON

## 维护约束

- 如果修改 `readiness_score` 权重或 `asset_status` 判定规则，必须同步更新测试和本 README
- 如果上游某个 bundle 改了字段名或 `is_ready_for_ai` 语义，必须同步校正这里的 band 映射
- 这个模块只做数据可用性判断，不做交易信号、不做收益预测、不做仓位建议
