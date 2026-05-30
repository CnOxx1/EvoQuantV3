# 数据层设计

`data_layer` 用来存放所有“从外部系统获取数据”的模块。每个模块都应该满足下面几个约束：

- 模块目录独立，便于单独开发、测试、运行和扩展。
- 每个模块维护自己的 `README.md`，说明数据来源、字段定义、调度频率和后续扩展方向。
- 模块内部只负责采集、标准化、落库，不承担策略判断和前端展示职责。
- 数据库统一放在项目根目录下的 [`database`](../database)。

## AI 文档维护约束

这份 README 不是普通说明文档，而是给后续 AI 开发和维护 `data_layer` 时使用的入口文档。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块目录结构或新增/删除源码文件
- 数据来源、采集频率、运行模式或环境变量
- 字段定义、数据库落库语义或上下游依赖关系
- 当前支持的 AI 供数链路、模块边界或维护约束

## 快速导航

- [模块速览](#模块速览)
- [模块详述](#模块详述)
- [跨模块审计](#跨模块审计)
- [当前代码树](#当前代码树)

## 模块速览

| 模块 | 主要证据 | AI 主视图重点 |
| --- | --- | --- |
| `exchange_data` | 行情、盘口、K 线、资金费率、衍生品结构 | `latest_*` 市场快照与交易所诊断 |
| `news_data` | 新闻、标签、资产命中 | 新闻主视图、来源健康度、覆盖率 |
| `event_calendar_data` | 未来事件、催化剂 | `24h / 7d / 30d` 事件上下文 |
| `macro_data` | 美元、利率、股指、VIX、黄金、原油 | 宏观快照、变化率、coverage 诊断 |
| `onchain_data` | 资金流、储备、TVL、网络活跃度 | 链上实体 bundle 与质量摘要 |
| `tokenomics_data` | 供给、解锁、基金会钱包、质押 | 供给压力与未来解锁上下文 |
| `options_data` | IV 曲面、Gamma、墙位、成交意图、对冲压力 | 期权结构化因子与主 bundle |
| `alternative_data` | Trends、GitHub、稳定币供给 | 补充证据与广度诊断 |
| `data_quality` | 跨模块审计 | `world_model_status` 与 critical gaps |

## 模块详述

- `exchange_data`：接入 Binance、OKX、Bybit 等主流交易所，采集 18 个币种（BTC、ETH、SOL、SUI、DOGE、XRP、AVAX、LINK、ADA、DOT、MATIC、UNI、ARB、OP、NEAR、ATOM、APT、TIA）的市场基础数据、行情、K 线、盘口、资金费率，以及第二阶段的 `trades / taker_flow / open_interest / liquidations / long_short_ratio / basis` 衍生品结构数据，并支持 AI 面向的 `latest_*` 当前快照表。资产按三层分频管理：T1 核心（BTC/ETH，orderbook 3s）、T2 活跃（SOL/SUI/DOGE/XRP/AVAX/LINK，orderbook 10s）、T3 监控（其余 10 币种，orderbook 30s），Ticker 和 Kline 统一 batch 采集无限速压力。同时会在 latest bundle / coverage 输出交易所覆盖缺口、stale pair、cross-exchange dispersion 等质量诊断，且这些诊断只基于真实市场快照，不做伪造补值。`load_source_coverage()` 里的 `is_ready_for_ai` 现在也已收紧，不再把"最近运行成功但覆盖不完整"的 source 误判为可直接供 AI 做交易判断，并新增 `ready_for_ai_source_count / not_ready_for_ai_source_count` 方便快速看清当前市场数据到底有几路真的达标。`load_latest_market_context_bundle()` 现在还会额外输出 `configured_universe_summary`，直接提示当前默认 `TARGET_SYMBOLS / TARGET_EXCHANGES` 是否仍偏向核心执行市场视角，而不是更广的市场 breadth 视角；同时它已经把 AI 主载荷和原始真实诊断拆开，`spot / orderbook / funding / trade_flow / open_interest / liquidations / positioning / basis` 这些 section 只暴露 AI-ready 的真实数据，而未达门槛但真实已落库的市场快照会继续保留在 `raw_* / ai_excluded_sources / source_health` 里，symbol 级 `trade_flow_scope / coverage_summary / cross_exchange_diagnostics` 仍按原始真实快照计算，避免把“采到了但暂不达标”误判成完全缺失。`basis` 这一路现在不仅会对时间字段做逐列归一化和降级保护，坏掉的 `next_funding_time` 只会影响年化 basis 推导；如果 `funding_timestamp` 自身坏掉，该行 basis 会被直接丢弃，避免把坏时间戳伪装成最新快照。同时，即使 `basis` 这个 source 整体通过了 AI-ready 门槛，bundle 仍会继续做行级过滤，只把时间语义也可信的 basis 暴露在主视图里，其余真实 basis 会继续保留在 `raw_basis / basis_quality_summary` 诊断字段。除此之外，`ticker / orderbook / funding / open_interest / liquidations / long_short_ratio` 现在也不再把缺失或损坏的事件时间回退成“当前时间”伪装成最新快照；如果交易所仍给出可信的 `datetime` 事件时间，则会优先保留该真实时间。`open_interest / positioning / liquidations` 这三路即使 source 级通过 AI-ready，也会继续做行级值语义过滤，不完整的真实行只保留在 `raw_open_interest / raw_positioning / raw_liquidations` 与对应 `*_quality_summary` 里。`trade_flow` 也已经停止把 `side` 缺失成交默认归到 `sell`，并停止把缺失成交额的真实成交压成 `0`；现在只有方向和成交额都可证明的真实成交才会进入 bar 聚合。`klines` 也不再把缺失 `volume` 的真实行压成 `0`，任何缺少核心 OHLCV 字段的行都会被直接跳过。尤其 `liquidations` 现在已经明确区分“真实的零清算压力”和“清算字段未知”：缺失字段不会再被强制写成 `0`，只有总清算额明确存在，或多空两侧清算额都明确存在的真实行，才会进入 AI 主视图；如果数据库里还有旧版污染行，还可以通过 `python -m data_layer.exchange_data.runner --mode liquidations-repair` 基于已保存的 `raw_payload_json` 做可审计修复。symbol 级 bundle 还会新增 `derivatives_core_alignment`，专门告诉 AI `funding / open_interest / basis` 这三组核心合约证据能否被当成同一时间切片联合解释。
- `news_data`：从公开 RSS / Atom feed 采集加密货币新闻，标准化标题、摘要、正文、发布时间、标签和命中币种后落库；当前命中对象已经从 `BTC / ETH / SOL / SUI / USDT / USDC / DAI / FDUSD` 扩展到更大的主流资产与生态代币集合，并把资产别名表外置到 `news_data/registry/tracked_assets.json` 便于后续维护。模块同时在 coverage 中输出 `health_status / is_ready_for_ai / data_quality_flags / quality_notes`。其中 `core_media / market_intelligence` 现在不仅要求最近窗口里达到推荐文章阈值，还要求最近文章具备资产映射，且连续新闻流的正文覆盖率不能过薄，才会被标成 `is_ready_for_ai=true`。`load_latest_context_bundle()` 现在还会补充 `configured_universe_summary / coverage_summary.coverage_by_source / source_health_summary.ready_for_ai_source_count`，直接告诉 AI 当前新闻文本命中注册表到底是“广市场宇宙”还是“窄观察名单”；同时它会把非 AI-ready 来源从 `article_count / source_counts / latest_articles / dominant_symbols` 这些 AI 直接消费字段里剥离，只在 `raw_* / ai_excluded_sources / source_health` 等诊断字段里保留真实已落库新闻。如果默认跟踪资产仍过窄，bundle 会显式输出 `news_configured_market_breadth_limited`，而不是伪造未覆盖资产的新闻信号。
- `event_calendar_data`：采集未来已知事件，把宏观节点、ETF 审批节点、项目升级和解锁事件独立落到 `event_calendar_events`，避免未来事件和普通新闻流混杂；同时在 coverage 中输出 `configuration_ready / health_status / future-horizon` 相关质量语义，并新增 `load_upcoming_context_bundle()` 聚合未来 24h / 7d / 30d 事件、重点事件、symbol watchlist、事件类型缺口和 `configured_universe_summary`，帮助判断真实事件流是否足够支持 AI 的前瞻催化剂分析。`load_source_coverage()` 里的 `is_ready_for_ai` 现在也已继续收紧，不再把“最近运行成功但未来视野仍太短，或未来窗口里只有单条低信号事件”的 source 误判为可直接供 AI 使用，同时补充了 `coverage_summary.coverage_by_source` 和 `ready_for_ai_source_count / not_ready_for_ai_source_count`。`load_upcoming_context_bundle()` 现在还会把非 AI-ready 事件源从 AI 直接消费的 `upcoming_events / next_24h / high_importance_events` 视图里剥离，只在 `raw_* / ai_excluded_sources / source_health` 等诊断字段里保留真实已落库事件，避免把视野过短或配置不稳的事件源直接混进交易前瞻上下文。如果默认事件配置宇宙仍偏窄，bundle 会显式标记 `event_calendar_configured_market_breadth_limited`；如果只是按 `symbols` 做过滤查询，则不仅不会再把过滤结果误判成默认事件宇宙缺失，`missing_event_types` 也不会再输出误导性的缺口。事件日历模块的 `once` 与常驻 `scheduler` 现在也统一写入 `collection_runs`，而且未配置 endpoint 的来源会被诚实记录为 `unconfigured`，不再在运行台账里伪装成“空数据正常”。
- `macro_data`：采集跨市场宏观因子，当前已接入 `dxy`、`ust_3m_yield`、`ust_2y_yield`、`ust_10y_yield`、`ust_30y_yield`、`ust_10y_real_yield`、`us_10y_breakeven_inflation`、`us_bbb_oas`、`us_high_yield_oas`、`fed_funds_upper`、`nasdaq_100`、`sp500`、`vix`、`gold_spot`、`wti_crude`，并统一标准化到 `macro_timeseries` 和 `latest_macro_timeseries`。当前 latest bundle 还会额外输出 `configured_universe_summary / coverage_summary / source_health / source_health_summary / latest_quality_flag_breakdown / data_quality_flags / quality_notes`，明确告诉 AI 当前宏观证据是否真的覆盖了利率、通胀、信用和风险资产几个关键维度，以及宏观 source 是否已经达到可直接给 AI 使用的质量门槛。`load_source_coverage()` 现在也会直接输出 source 级 `data_quality_flags`，并把 `is_ready_for_ai` 继续收紧到“因子覆盖完整 + latest 样本质量干净”的标准，把“宏观源为什么暂时不能直接给 AI 用”结构化暴露出来。`load_latest_context_bundle()` 现在也会把非 AI-ready 宏观 source 从 `row_count / source_counts / leaders / factors / latest_quality_*` 这些 AI 直接消费字段里剥离，只在 `raw_as_of / raw_row_count / raw_source_counts / raw_latest_quality_* / ai_excluded_sources / source_health` 等诊断字段里保留真实已落库快照。`configured_universe_summary` 还会直接提示当前默认启用的宏观因子宇宙是否已经足够宽，还是只是裁剪后的宏观视角。启动回填现在默认采用 best-effort 容错，避免单个 FRED 超时直接打断整个宏观供数链。
- `onchain_data`：采集链上资金行为背景，当前已扩展到 `exchange_netflow`、`whale_transfer_count`、`stablecoin_exchange_inflow`、`bridge_netflow`、`exchange_reserve`、`protocol_tvl`、`network_usage`、`staking_flow`，并统一标准化到 `onchain_timeseries` 与 `latest_onchain_timeseries`。当前 latest bundle 会额外输出 `coverage_summary / configured_universe_summary / source_health / source_health_summary / data_quality_flags / quality_notes`，明确告诉 AI 当前链上证据是否足够直接参与市场判断。`load_source_coverage()` 里的 `is_ready_for_ai` 现在也已收紧，不再把“最近运行成功但 entity x factor 矩阵仍不完整、或 latest 混入 fallback/stale 样本”的 source 误判为可直接供 AI 使用，同时补充了 `coverage_summary.coverage_by_source` 和 `ready_for_ai_source_count / not_ready_for_ai_source_count`。`load_latest_context_bundle()` 现在也会把非 AI-ready 链上 source 从 `row_count / entity_count / entities / leaders / latest_quality_*` 这些 AI 直接消费字段里剥离，只在 `raw_as_of / raw_row_count / raw_entity_count / raw_source_counts / raw_latest_quality_* / ai_excluded_sources / source_health` 等诊断字段里保留真实已落库快照。链上覆盖统计现在按 `(entity_type, entity_key)` 计算，不再把同名但不同实体范围混成一个覆盖目标；同时 `configured_universe_summary` 会直接提示当前默认链上宇宙是否仍偏向核心执行资产，并且在 `factor_ids` 等过滤查询下会正确降为 `filtered`，不再把查询子集误报成默认宇宙缺口。
- `tokenomics_data`：采集供给压力背景，当前已实现 `circulating_supply`、`unlock_schedule`、`unlock_realization`、`treasury_wallet_flow`、`staking_ratio`，并统一标准化到 `tokenomics_timeseries`、`latest_tokenomics_timeseries` 与 `token_unlock_events`。当前 latest bundle 还会额外输出 `coverage_summary / configured_universe_summary / source_health / source_health_summary / data_quality_flags / quality_notes / upcoming_unlock_events / unlock_horizon_summary`，明确告诉 AI 当前供给证据是否足够直接参与市场判断，以及未来 `24h / 7d / 30d` 的真实解锁压力是否已经清晰可见。`load_source_coverage()` 里的 `is_ready_for_ai` 现在也已继续收紧，不再把“最近运行成功但实体/因子覆盖仍不完整，或 latest 混入 partial/fallback/stale/unknown 样本”的 source 误判为可直接供 AI 使用。现在 `load_latest_context_bundle()` 也已经统一按 `is_ready_for_ai` 过滤主视图，不再只排除 registry 未就绪的钱包流；所有非 AI-ready source 的真实 latest 点和未来解锁事件都会从 AI 主 bundle 中剥离，只保留在 `raw_* / ai_excluded_sources / source_health / raw_upcoming_unlock_event_count / raw_unlock_horizon_summary` 等诊断字段里。对于 `treasury_wallet_flow`，现在还额外要求 `treasury_wallet_groups.json` 的钱包组口径达到可核验门槛；如果 registry 仍是 placeholder、没有真实地址数量或缺少来源引用，这路数据仍可落库，但不会被标成可直接给 AI 使用。`configured_universe_summary` 还会直接提示当前默认 tokenomics 资产宇宙是否仍偏窄，更适合做核心执行资产供给跟踪，而不是更广的 cross-asset breadth 判断；在 `factor_ids` 等过滤查询下也会正确降为 `filtered`。
- `options_data`：采集期权侧的前瞻证据，当前已实现 `ATM IV 7d/30d`、`IV term structure`、`25d risk reversal / butterfly`、`realized vol 7d/30d`、`IV-RV spread`、`max pain / call wall / put wall distance`、`top strike / near expiry / ATM strike concentration`、`net gamma / gamma flip / gamma wall`、`top gamma / near expiry gamma concentration`、`call/put buyer premium share`、`net call / net put premium flow`、`opening / near expiry / block flow share`、`7d / 30d / 90d+` 到期桶 OI share、`7d / 30d` 到期桶 gamma share、`7d / 30d` 到期桶 premium flow share、`vanna / charm / volga / vomma / color exposure`、`vanna / charm flip distance`、`near expiry charm / color share`、`put/call OI ratio`、`near expiry / largest expiry OI concentration`，并统一标准化到 `options_timeseries` 与 `latest_options_timeseries`。当前默认资产宇宙已对齐 `BTC,ETH,SOL,SUI`，latest bundle 也会额外输出 `coverage_summary / configured_universe_summary / source_health / venue_coverage_summary / latest_quality_flag_breakdown / data_quality_flags / quality_notes`，明确告诉 AI 当前期权证据是否真的同时覆盖了目标资产集合和关键 venue。`load_source_coverage()` 里的 `is_ready_for_ai` 现在也已继续收紧，不再把“venue 看起来齐了，但 latest 混入 partial/fallback/stale/unknown，或实体/因子覆盖仍不完整”的 source 误判为可直接供 AI 使用。`load_latest_context_bundle()` 现在也会把非 AI-ready 期权 source 从 `row_count / entity_count / source_counts / leaders / sources / latest_quality_*` 这些 AI 直接消费字段里剥离，只在 `raw_as_of / raw_row_count / raw_entity_count / raw_source_counts / raw_latest_quality_* / ai_excluded_sources / source_health` 等诊断字段里保留真实已落库快照。`configured_universe_summary` 还会直接提示当前默认期权宇宙是否仍偏向核心风险代理，而不是更广的市场 breadth 视角；只有在 `factor_ids`、`entity_keys` 或真正把默认 source 宇宙缩成子集的 `source_names` 过滤查询下才会降为 `filtered`，不会再把“显式传完整默认 source 集合”的情况误报成默认宇宙缺口。
- `alternative_data`：补充特征模块，当前已实现 Google Trends 搜索热度、attention shock、cross-query 标准化、related query/topic 叙事特征、GitHub 活跃度，以及稳定币供给/链分布和 `mint / burn / bridge` 事件化历史采集，并统一标准化到 `alternative_timeseries` 与 `latest_alternative_timeseries`。当前 latest bundle 已对齐 `as_of=真实最新观测时间`，并额外输出 `coverage_summary / configured_universe_summary / source_health / source_health_summary / data_quality_flags / quality_notes`。`load_source_coverage()` 里的 `is_ready_for_ai` 现在也已收紧，不再把“最近运行成功但仍是 P1 experimental、实体覆盖不完整、或 latest 混入 partial/fallback/stale/unknown 样本”的 source 误判为可直接供 AI 使用，同时补充了 `ready_for_ai_source_count / not_ready_for_ai_source_count`。`load_latest_context_bundle()` 现在也会把非 AI-ready source 从 AI 直接消费的 `sources / row_count / source_counts / latest_quality_flag_breakdown` 里剥离，只在 `raw_* / ai_excluded_sources / source_health` 等诊断字段里保留真实已落库快照。其中 Google Trends 仍属于实验性 P1 source，而 `configured_universe_summary` 会直接提示当前默认补充特征宇宙是否仍偏向核心关注对象，尚不足以代表更广市场 breadth；只有在 `entity_keys`、`factor_ids` 或真正把默认 source 宇宙缩成子集的 `source_names` 过滤查询下才会降为 `filtered`，避免把局部查询误判成默认 registry 宇宙不足。
- `data_quality`：不采集外部市场数据，而是统一维护数据层健康语义、`quality_flag` 汇总、AI-ready 判定和跨模块市场世界模型审计。当前已经支持 `--mode once / --mode scheduler / --print-market-audit / --save-market-audit`，会基于各模块真实 `load_source_coverage()` 与数据库真实 `latest_* / history` 表，持续判断 `exchange / macro / news / event_calendar / onchain / tokenomics / options / alternative` 这些证据带到底是 `ready / stale / insufficient / unconfigured / missing`，并把审计结果同时落到 `data_quality_audit_snapshots` 与 `collection_runs`，明确告诉你“整套数据层是否真的足够给 AI 看市场”，而不是只看某个单点模块是否还活着。

## 跨模块审计

如果你要回答的不是“某个模块是否活着”，而是“整套数据层是否已经足够让 AI 看清市场”，当前统一入口是：

```bash
python -m data_layer.data_quality.runner --print-market-audit
```

如果希望把这份跨模块真实审计保存到数据库历史中：

```bash
python -m data_layer.data_quality.runner --save-market-audit
```

如果希望按标准模块入口执行一次审计并落库：

```bash
python -m data_layer.data_quality.runner --mode once
```

如果希望常驻巡检，让系统持续判断这套数据层是不是已经足够支撑 AI 看市场：

```bash
python -m data_layer.data_quality.runner --mode scheduler
```

这会基于各模块 `load_source_coverage()` 和数据库里的真实 `latest_* / history` 表，输出一份跨模块的市场世界模型健康摘要。
调度频率由 `DATA_QUALITY_AUDIT_INTERVAL_SECONDS` 控制，默认每 `300` 秒执行一次。

重点看：

- `summary.world_model_status`
  - `ready / partial / blocked`
- `summary.critical_gap_band_names`
  - 当前仍然缺失或不达标的 required 证据带
- `bands[].band_status`
  - 每条证据带当前是 `ready / stale / insufficient / unconfigured / missing`
- `bands[].latest_table_counts / history_table_counts`
  - 对应证据带是否真的有最新样本和历史样本
- `bands[].blocking_reasons`
  - 为什么这条证据带还不能视为 AI-ready

这层审计不会补假数据，也不会把“模块已建好但没有真实样本”伪装成已覆盖。
当前快照还会落库到 `data_quality_audit_snapshots`，并把巡检执行结果写入 `collection_runs`，方便长期追踪数据层是否真的在变好。

## 当前代码树

下面代码树省略 `__pycache__` 等缓存目录，保留后续维护最常用的源码入口：

```text
data_layer/
  README.md                      # 数据层总览、AI 供数结构与维护约束
  __init__.py                    # 数据层包入口
  exchange_data/
    README.md                    # 交易所采集模块说明与维护入口
    __init__.py                  # 交易所采集模块包入口
    client.py                    # 交易所客户端管理与连接封装
    funding.py                   # 资金费率采集与历史回填
    kline.py                     # K 线采集、增量更新与回填
    market_info.py               # 交易对静态信息采集
    models.py                    # 交易所数据模型定义
    normalized_derivatives.py    # 衍生品结构标准化辅助
    orderbook.py                 # 盘口快照采集与深度特征计算
    runner.py                    # CLI 运行入口
    service.py                   # 模块编排、调度与任务组织
    ticker.py                    # 实时行情快照采集
    trades/
      README.md                  # 成交流子模块维护入口
      __init__.py
      collector.py
    taker_flow/
      README.md                  # 主动买卖流子模块维护入口
      __init__.py
      collector.py
    open_interest/
      README.md                  # 持仓量子模块维护入口
      __init__.py
      collector.py
    liquidations/
      README.md                  # 清算子模块维护入口
      __init__.py
      collector.py
    long_short_ratio/
      README.md                  # 多空比子模块维护入口
      __init__.py
      collector.py
    basis/
      README.md                  # basis 子模块维护入口
      __init__.py
      collector.py
  event_calendar_data/
    README.md                    # 事件日历模块说明与维护入口
    __init__.py                  # 事件日历模块包入口
    client.py                    # JSON / ICS 事件源请求封装
    collector.py                 # 事件标准化、去重、状态更新与落库
    models.py                    # 事件源与日历事件模型
    runner.py                    # CLI 运行入口
    service.py                   # 模块编排、调度、upcoming 查询与 context bundle
    sources.py                   # 默认事件源配置
  alternative_data/
    README.md                    # 补充特征模块说明、运行方式与维护约束
    __init__.py                  # 模块包入口，导出 AlternativeDataService
    base.py                      # 公共落库与去重逻辑
    client.py                    # Google Trends / GitHub / Stablecoin 请求封装与解析
    google_trends.py             # Google Trends 搜索热度采集
    github_activity.py           # GitHub repo group 聚合采集
    models.py                    # 补充特征因子与时序模型定义
    registry/
      github_repo_groups.json    # GitHub repo group 外置注册表
      google_trends_query_groups.json
                                 # Google Trends query group 外置注册表
      stablecoin_assets.json     # 稳定币资产外置注册表
    runner.py                    # CLI 运行入口
    service.py                   # 模块编排、目录同步与调度
    sources.py                   # 因子目录与 registry 文件加载
    stablecoin_supply.py         # 稳定币供给与链分布采集
  macro_data/
    README.md                    # 宏观采集模块说明与维护入口
    __init__.py                  # 宏观采集模块包入口
    client.py                    # Yahoo Finance / FRED 请求封装
    market.py                    # 市场型宏观因子采集
    models.py                    # 宏观因子与时序模型定义
    rates.py                     # 利率型宏观因子采集
    runner.py                    # CLI 运行入口
    service.py                   # 模块编排、目录同步与调度
    sources.py                   # 宏观因子目录与来源配置
  news_data/
    README.md                    # 新闻采集模块说明与维护入口
    __init__.py                  # 新闻采集模块包入口
    client.py                    # RSS / Atom 下载与解析
    collector.py                 # 新闻筛选、去重与落库
    models.py                    # 新闻源与文章模型定义
    runner.py                    # CLI 运行入口
    service.py                   # 模块编排、覆盖检查与 context bundle
    sources.py                   # 默认新闻源配置
  onchain_data/
    README.md                    # 链上数据模块说明与维护入口
    __init__.py                  # 链上数据模块包入口
    client.py                    # 标准化 JSON 链上接口请求封装
    models.py                    # 链上 source / factor / 时序模型
    registry/
      chain_groups.json          # 链级实体注册表
      protocol_groups.json       # 协议级实体注册表
    runner.py                    # CLI 运行入口
    service.py                   # 因子目录同步、落库、调度与 context bundle
    sources.py                   # 默认链上 source / factor / entity 配置
    collectors/
      exchange_flow.py           # 交易所净流入流出采集器
      stablecoin_flow.py         # 稳定币流入交易所采集器
      whale_activity.py          # 鲸鱼异动采集器
    bridge_netflow/
      README.md                  # 跨链桥净流子模块维护入口
      __init__.py
      collector.py
    exchange_reserve/
      README.md                  # 交易所储备子模块维护入口
      __init__.py
      collector.py
    protocol_tvl/
      README.md                  # 协议 TVL 子模块维护入口
      __init__.py
      collector.py
    network_usage/
      README.md                  # 网络使用度子模块维护入口
      __init__.py
      collector.py
    staking_flow/
      README.md                  # 质押净流子模块维护入口
      __init__.py
      collector.py
  tokenomics_data/
    README.md                    # Tokenomics 数据模块说明与维护入口
    __init__.py                  # 模块包入口
    base.py                      # 公共落库与 latest/upsert 逻辑
    client.py                    # 标准化 JSON tokenomics 接口请求封装
    models.py                    # tokenomics source / factor / 时序 / 事件模型
    registry/
      token_profiles.json        # token profile 注册表
      treasury_wallet_groups.json
                                 # treasury wallet group 注册表
    runner.py                    # CLI 运行入口
    service.py                   # 因子目录同步、落库、调度与 context bundle
    sources.py                   # 默认 tokenomics source / factor / entity 配置
    circulating_supply/
      README.md                  # 流通盘子模块维护入口
      __init__.py
      collector.py
    unlock_schedule/
      README.md                  # 计划解锁子模块维护入口
      __init__.py
      collector.py
    unlock_realization/
      README.md                  # 已实现解锁子模块维护入口
      __init__.py
      collector.py
    treasury_wallet_flow/
      README.md                  # 基金会钱包流子模块维护入口
      __init__.py
      collector.py
    staking_ratio/
      README.md                  # 质押率子模块维护入口
      __init__.py
      collector.py
  options_data/
    README.md                    # 期权数据模块说明与维护入口
    __init__.py                  # 模块包入口
    base.py                      # 公共落库与 latest/upsert 逻辑
    client.py                    # 标准化 JSON options 接口请求封装
    deribit_client.py            # Deribit 公开 API 客户端（免费，无需认证）
    models.py                    # options source / factor / 时序模型
    runner.py                    # CLI 运行入口
    service.py                   # 因子目录同步、落库、调度与 context bundle
    sources.py                   # 默认 options source / factor / entity 配置
    vol_surface/
      README.md                  # 波动率曲面子模块维护入口
      __init__.py
      collector.py
    relative_value/
      README.md                  # IV 相对 realized vol 子模块维护入口
      __init__.py
      collector.py
    strike_concentration/
      README.md                  # 墙位、max pain 与 pinning 风险子模块维护入口
      __init__.py
      collector.py
    gamma_exposure/
      README.md                  # dealer gamma regime 子模块维护入口
      __init__.py
      collector.py
    flow_activity/
      README.md                  # 期权增量成交流子模块维护入口
      __init__.py
      collector.py
    expiry_structure/
      README.md                  # 到期桶期限结构子模块维护入口
      __init__.py
      collector.py
    hedge_pressure/
      README.md                  # 动态对冲压力子模块维护入口
      __init__.py
      collector.py
    positioning/
      README.md                  # 持仓结构子模块维护入口
      __init__.py
      collector.py
  data_quality/
    README.md                    # 共享质量语义、跨模块审计与巡检入口
    __init__.py                  # 模块包入口，导出共享健康与审计能力
    audit.py                     # 市场世界模型审计与快照落库
    health.py                    # 统一健康状态、quality flag 与 AI-ready 判定
    runner.py                    # CLI 与常驻巡检入口
```

## 当前对 AI 的供数结构

当前数据层已经形成八条原始输入链，目标不是在采集层直接做判断，而是先把原始背景抓全、抓稳、抓成统一结构，再交给 AI 使用：

- `exchange_data`
  - 提供价格、成交、盘口、资金费率等交易所市场原始输入
- `news_data`
  - 提供新闻、公告、治理、研究和监管等文本事件输入
  - 同时提供最近新闻窗口的 AI 上下文 bundle，显式暴露来源分布、资产提及和文本质量缺口
- `event_calendar_data`
  - 提供未来已知事件输入，避免 AI 把“还没发生的日程”误当成即时新闻
  - 同时提供未来事件上下文 bundle，显式暴露未来 24h / 7d / 30d 催化剂密度和缺失事件类型
- `macro_data`
  - 提供美元、利率曲线、政策利率、美股风险偏好、波动率、黄金和原油等跨市场宏观背景输入
- `onchain_data`
  - 提供交易所净流、鲸鱼异动、稳定币流入交易所、桥流、储备、协议 TVL、网络使用度和质押净流等链上背景输入
- `tokenomics_data`
  - 提供流通盘、解锁压力、基金会钱包流向、质押率等供给压力输入
- `options_data`
  - 提供期权市场对未来波动的定价、隐含波动相对真实波动的贵/便宜、墙位与 max pain、行权价拥挤度、dealer gamma regime、gamma flip / gamma wall、增量期权成交意图、按到期桶拆分的风险分布、dealer 动态对冲压力、波动率凸性冲击、gamma 时间衰减、上下行偏度、尾部溢价以及 OI 到期集中度输入
  - 同时提供期权上下文 bundle，显式暴露目标资产覆盖是否完整、latest 样本质量是否降级、哪些 source 仍未 ready，以及推荐 venue 是否被真实 latest 样本覆盖
- `alternative_data`
  - 当前已提供 Google Trends 搜索热度、7 日 attention shock、cross-query 标准化、related query/topic 叙事摘要、GitHub 开发者活跃度、稳定币供给与链分布，以及 `mint / burn / bridge` 事件化流量等补充背景输入
  - 同时已提供 `load_latest_context_bundle()`，可直接输出 AI 可消费的结构化上下文 bundle
  - 同时支持列出模块内部的 `source / factor / entity` 注册表，方便后续扩展与运维核对
  - 实体清单已外置为 JSON，后续维护不再需要直接改源码常量
  - registry 改动后可由长运行进程自动感知，也可以用 `--reload-registry` 强制刷新校验

当前 `main.py` 默认会自动拉起完整的数据层常驻模块集合：

- `exchange_data / macro_data / news_data / event_calendar_data / onchain_data / alternative_data / tokenomics_data / options_data / data_quality_audit`
- `technical_indicators / exchange_comparison / ai_market_context` 这类逻辑层任务仍保持手动启动，避免把“采集层”和“分析层”混成同一条默认运行链

当前总入口的常驻模块监管语义也已经收紧为“保住真实供数优先”：

- 某个常驻数据模块意外退出时，优先自动重启该模块，而不是立刻停掉整套数据层
- 如果某个模块在短窗口内连续崩溃超过上限，系统会隔离这个失败模块，但保留其他仍健康的真实数据链继续运行
- 失败模块是否已经影响 AI 可用性，不靠猜测，而是继续交给 `data_quality_audit` 用真实表计数和各模块 coverage 结果去判断

当前还新增了一层通用可观测性：

- `collection_runs`
  - 记录每个模块、每个 source 最近的采集状态、耗时和样本数
  - 现在 `macro_data / news_data / event_calendar_data / onchain_data / tokenomics_data / options_data / alternative_data / data_quality` 都已接入
  - 用来直接检查“数据是否抓全、某个源是否长期失效、某类数据是否变 stale”

这些原始链路向下游继续供给：

- `logic_layer.technical_indicators`
  - 生成趋势、波动、量价和微观结构时序特征
- `logic_layer.exchange_comparison`
  - 生成跨交易所横截面执行与价差特征
- `logic_layer.macro_context`
  - 生成 AI 可直接消费的宏观背景快照与变化特征
- `logic_layer.ai_market_context`
  - 聚合多模块 latest 快照，生成 AI 直接消费的最终市场上下文 bundle
  - 同时集成 `cross_asset_context` 和 `portfolio_risk_context`
- `logic_layer.cross_asset_analysis`
  - 基于 `merged_klines` 1h 收盘价计算 18 资产滚动相关性矩阵、相对强弱排名、板块轮动和聚合资金流向
- `logic_layer.portfolio_risk`
  - 基于相关性矩阵和各资产波动率计算组合波动率、VaR、集中度和分散化评分
- `logic_layer.market_breadth`
  - 基于库里已经存在的真实 `exchange_data / news_data / tokenomics_data` 结果，生成跨资产市场广度快照
  - 这层不采新数据，不做推断，只回答“当前 AI 真正看到多少资产、新闻 breadth 有多宽、解锁覆盖有多广”
  - 如果当前宇宙仍只是窄执行资产集合，它会显式输出 `breadth_status=narrow/thin`，而不是把窄宇宙伪装成广市场理解

## 当前数据层实践

围绕 `exchange_data`，当前数据层已经拆成三类采集任务：

- 低频静态任务：`market_info`
- 可历史回填任务：`klines`、`funding_rates`
- 只能从现在开始积累的高频任务：`tickers`、`orderbook_snapshots`

当前 `exchange_data` 的实现还有几项已经落地的运行优化：

- 资产按三层分频管理（T1 核心 3s / T2 活跃 10s / T3 监控 30s），在 18 币种 × 3 交易所下仍控制在 ~158 req/min，远低于交易所限速
- Ticker 使用 batch `fetch_tickers()` 一次请求覆盖全部 18 币种，不再逐币种轮询
- 调度模式下按线程隔离 SQLite 连接和交易所客户端，避免跨线程资源复用问题
- `market_info` 在进程内复用已加载的交易对元数据，减少重复全量 reload
- `ticker` 优先使用交易所批量接口，减少高频轮询的请求数
- `klines` 增量更新基于数据库最新游标继续追平，并按 `timeframe` 拆分调度
- `funding_rates` 历史回填按时间戳分页，不再只取第一页
- 高频上下文数据同时维护历史表和 `latest_*` 快照表，分别服务时序回看和 AI 当前市场分析
- `latest_*` 快照按事件时间戳保护，避免历史回填把旧样本覆盖成“当前状态”
- 数据库初始化会自动从历史快照表回灌 `latest_*`，便于平滑升级
- 高频快照表支持定时按保留期清理，控制 SQLite 膨胀速度

围绕 `news_data`，当前新增了一类文本与事件数据：

- 新闻与公告文本：`news_articles`

这类数据的特点是：

- 适合做 AI 的事件理解和文本分析输入
- 更强调去重、时效性和来源追踪
- 当前 coverage 会显式区分“连续新闻流是否够新”和“低频参考流是否只是暂时没有新公告”
- 当前 latest context bundle 会进一步聚合最近新闻窗口的来源结构、资产提及、正文覆盖率和来源集中度
- 不适合在数据层直接做情绪结论，应该把判断留给逻辑处理层

这意味着开发阶段不能只靠一次回填就构造完整特征。`ticker` 和 `orderbook` 必须通过持续运行或短时高频采样逐步积累样本。

围绕 `event_calendar_data`，当前新增了一类“未来已知事件”：

- 事件日历：`event_calendar_events`

这类数据的特点是：

- 强调未来时间点、状态更新和去重
- 适合给 AI 提供“还没发生但已知会发生”的事件背景
- 当前 coverage 会显式告诉你哪些源未配置、哪些未来窗口为空、哪些事件视野过短
- 当前 upcoming context bundle 会进一步聚合未来 24h / 7d / 30d 事件、重点事件、symbol watchlist 和缺失事件类型
- 不应该和即时新闻正文混在一起读取

围绕 `macro_data`，当前新增了一类“跨市场连续时序”：

- 宏观上下文因子：`macro_timeseries`

这类数据的特点是：

- 适合给 AI 补齐美元、前端利率、名义利率、真实利率、通胀预期、信用利差、纳指、黄金和原油等市场背景
- 同时维护历史表和 `latest_macro_timeseries` 快照表
- 更强调 `observation_time`、数据新鲜度和统一 `value` 语义
- 当前 latest bundle 会进一步聚合 factor 覆盖缺口、quality breakdown 和 source health，避免 AI 把“未采到”和“宏观没变化”混为一谈

围绕 `onchain_data`，当前新增了一类“链上资金行为时序”：

- 链上背景因子：`onchain_timeseries`

这类数据的目标是：

- 给 AI 补齐交易所净流、鲸鱼异动、稳定币交易所流入等背景
- 同时维护历史表和 `latest_onchain_timeseries` 快照表
- 保持和 `macro_data / alternative_data` 类似的统一读取语义
- 当前已扩到 `bridge_netflow / exchange_reserve / protocol_tvl / network_usage / staking_flow` 等第二阶段因子

围绕 `tokenomics_data`，当前新增了一类“供给压力背景时序”：

- Tokenomics 背景因子：`tokenomics_timeseries`

这类数据的目标是：

- 给 AI 补齐流通盘、解锁压力、基金会钱包流向和质押率变化
- 同时维护历史表和 `latest_tokenomics_timeseries` 快照表
- 将未来解锁事件单独落到 `token_unlock_events`
- 保持和 `macro_data / onchain_data / alternative_data` 类似的统一 bundle 读取语义

围绕 `alternative_data`，当前已经落地一类“补充背景因子时序”：

- 补充特征因子：`alternative_timeseries`

这类数据的目标是：

- 给 AI 补齐搜索注意力、开发者建设强度和稳定币流动性脉冲
- 同时维护历史表和 `latest_alternative_timeseries` 快照表
- 尽量沿用 `macro_data` 的统一因子表思路，降低后续维护复杂度
- 当前 Google Trends 以 `query_group` 形式提供实验性搜索热度、7 日 attention shock、cross-query 标准化、related query/topic 叙事摘要，以及分段拼接后的长历史 bootstrap 输入
- 当前 P0 已实现 GitHub repo group 滚动活跃度和稳定币供给/链分布，稳定币 bootstrap 也支持链级历史回填与 `mint / burn / bridge` 事件化历史
- 当前也已经有 AI 读取导向的上下文 bundle 入口，不再只停留在“采集完写表”
- 当前 `main.py` 已把 `alternative_data` 纳入默认自动启动的数据层常驻模块集合
- 当前完整供数链已经明确分成四层：
  - `registry/*.json` 维护实体范围
  - `alternative_factor_catalog` 维护因子目录元数据
  - `alternative_timeseries / latest_alternative_timeseries` 维护历史与当前快照
  - `AlternativeDataService.load_latest_context_bundle()` 负责把数据库快照重组为 AI 可直接消费的上下文 bundle

## 推荐运行模式

- `bootstrap`：先补市场基础信息和历史 K 线。
- `funding-backfill`：补最近一段时间资金费率。
- `context-burst`：短时间快速积累 `ticker / funding / orderbook` 样本。
- `scheduler`：长期稳定运行，持续沉淀数据库样本。
- `news-scheduler`：持续抓取新闻与公告，沉淀文本事件样本。
- `macro-bootstrap`：初始化宏观因子目录并回填市场因子、利率、真实利率、通胀预期和信用利差历史。
- `macro-scheduler`：持续更新宏观上下文，给 AI 提供最新跨市场背景。
- `event-calendar-scheduler`：持续更新未来事件日历和状态变更。
- `onchain-scheduler`：持续更新链上净流、鲸鱼异动和稳定币交易所流入。
- `tokenomics-scheduler`：持续更新流通盘、解锁压力、基金会钱包流和质押率。
- `alternative-bootstrap`：初始化补充特征目录，并补 Google Trends 分段长历史、稳定币资产/链级历史、事件化历史与当前 GitHub / Stablecoin 快照。
- `alternative-scheduler`：持续更新 Google Trends、GitHub 活跃度、稳定币供给快照与事件化流量。
- `coverage-check`：通过各模块的 `--print-coverage` 检查 source 覆盖、最近一次采集状态和新鲜度。

## 推荐的后续模块

- `source_registry_monitor`：监控各模块 source 覆盖率、失效率和最后成功时间。
- `raw_archive_export`：把原始 payload 和规范化结果定期导出归档，降低 SQLite 长期膨胀风险。
- `data_quality_monitor`：统一监控 freshness、缺口、重复率和 schema 漂移。

## 分层边界

- 数据层：外部拉取、清洗、标准化、落库。
- 逻辑处理层：特征工程、因子计算、策略信号、风险控制。
- Web/UI 层：监控面板、策略状态、任务调度、告警和手工操作入口。

## 数据质量约定

当前各数据子模块会通过各自的 `load_source_coverage()` 和 CLI `--print-coverage` 暴露统一的数据质量状态。

共享状态语义由 `data_layer/data_quality/` 维护：

- `ready`：最近一次采集成功，且当前快照足够新。
- `stale`：历史上采到过，但最近运行或最新观测已经过期。
- `error`：最近一次采集明确失败。
- `empty`：最近一次采集成功执行，但没有拿到任何点。
- `missing`：还没有形成可用快照。
- `unconfigured`：source 处于启用状态，但关键配置未完成，例如 URL / registry 缺失。
- `disabled`：source 明确关闭，不参与运行。
- `cooldown`：source 因连续失败被暂时熔断。

注意：

- `ready` 只表示 source 技术上可运行且最近快照可用，不等于“已经足够给 AI 直接使用”。
- 是否达到 AI 直接消费门槛，需要继续看各模块自己的 `is_ready_for_ai`、`ready_for_ai_source_count` 和相关 `data_quality_flags`。

共享 `quality_flag` 汇总语义也由 `data_layer/data_quality/` 维护，当前覆盖模块会统一输出：

- `latest_quality_flag_breakdown`
- `latest_ok_point_count / latest_partial_point_count / latest_fallback_point_count / latest_stale_point_count`
- `latest_non_ok_point_count`
- `latest_quality_ready_ratio`

其中“latest 快照质量是否已经干净到可直接给 AI 使用”现在也由 `data_layer.data_quality.is_quality_summary_ai_ready()` 统一维护：

- 默认要求 latest 快照至少存在 `ok` 样本
- 默认不允许 latest 混入 `partial / fallback / stale / unknown`
- 各业务模块只需要在这层共享质量门槛之上，继续追加自己的覆盖完整性约束，例如 entity / factor / point / venue 是否齐全

另外，`load_source_coverage()` 里的 `factor_ids / entity_keys / source_names` 过滤现在要求严格作用在 coverage 统计本身，而不只是作用在元数据描述上。

维护上要注意两件事：

- `unconfigured` 不能和 `empty` 混用。前者是配置问题，后者是数据结果为空。
- `quality_notes` 和 `semantic_scope` 用来显式标注“数据存在但语义不完整”的情况，避免下游 AI 误读。
