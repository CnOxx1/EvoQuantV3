# 补充特征采集模块 `alternative_data`

## 当前状态

`alternative_data` 现在已经从“设计态”进入“可运行实现态”。

当前版本边界：

- `P0` 已实现
  - GitHub 开发者活跃度
  - 稳定币供给与链分布
- `P1` 已实现首版
  - Google Trends 搜索热度
  - Google Trends 7 日 attention shock
  - Google Trends `related_queries / related_topics`
  - Google Trends cross-query 横截面标准化
  - Google Trends related term/topic 的叙事级聚合特征
  - Google Trends 长历史分段拼接与重标化 bootstrap
  - 稳定币链级历史回填
  - 稳定币 `mint / burn / bridge` 事件化历史

当前模块已经具备下面几项能力：

- 有独立的 `client / collector / service / runner`
- 已接入 `main.py` 模块注册表
- 已新增独立的 `alternative_*` 数据表
- 已有测试覆盖表结构、聚合逻辑、调度包装和入口注册
- 已实现 `google_trends / github / stablecoin` 三类 source
- 已支持从 CLI 列出当前 `source / factor / entity` 注册表
- 已将实体注册表外置到模块内 `registry/*.json`
- 已支持 registry 内容指纹版本、运行中自动热刷新和强制 reload
- 已将 Google Trends 的 AI 可读证据同时保留为数值因子与 `raw_payload_json` 明细
- 已提供面向 AI 读取的 `load_latest_context_bundle()` 聚合入口

需要特别说明：

- `main.py` 已能一键拉起 `alternative_data`
- 它现在默认 `autostart=True`
- 原因不是把它当成绝对主信号，而是因为稳定币流动性、开发者活跃度和注意力变化已经属于 AI 做市场分析时的重要补充证据
- 其中 `google_trends` 仍然保留 `P1/experimental` 标记，AI 应把它视为补充证据而不是唯一依据

当前 `load_source_coverage()` 里的 `is_ready_for_ai` 采用两层门槛：

- 先使用共享 `data_layer/data_quality` 语义，要求 latest 真实样本质量干净，不混入 `partial / fallback / stale / unknown`
- 再叠加 `alternative_data` 自身约束，例如 source 不能仍是 `P1/experimental`，实体覆盖不能残缺

当前 `load_latest_context_bundle()` 的 AI-facing 视图也已经和这套门槛对齐：

- 只有 `is_ready_for_ai=true` 的 source 会进入 AI 直接消费的 `sources / row_count / source_counts / latest_quality_flag_breakdown`
- 像 `google_trends` 这类仍是 `P1/experimental` 或 latest 质量未达标的真实快照不会被伪造补齐，也不会直接混进 AI section
- 这类真实已落库数据会保留在 `raw_row_count / raw_source_counts / raw_latest_quality_flag_breakdown / ai_excluded_sources / source_health`

当前 `load_latest_context_bundle()` 还会显式输出 `configured_universe_summary`：

- 这不是伪造补值，而是把当前默认 registry 宇宙的宽度结构化暴露出来
- 如果默认 query group / repo group / stablecoin asset 范围仍偏窄，bundle 会追加 `alternative_configured_market_breadth_limited`
- 这样 AI 可以区分“当前补充特征足够看核心执行资产”与“当前补充特征已经足够代表更广市场 breadth”
- 如果调用时通过 `entity_keys / factor_ids`，或通过 `source_names` 把默认 source 宇宙真实缩小成子集，`scope_kind` 会变成 `filtered`，避免把局部查询误判成默认 registry 覆盖不足
- 如果显式传入的 `source_names` 实际上等于完整默认 source 集合，`scope_kind` 仍保持 `default`

## 快速导航

- [模块速览](#模块速览)
- [AI 文档维护约束](#ai-文档维护约束)
- [模块定位](#模块定位)
- [当前代码树](#当前代码树)
- [当前实现范围](#当前实现范围)
- [数据表与落库语义](#数据表与落库语义)
- [统一键规则](#统一键规则)
- [数据流向](#数据流向)
- [运行方式](#运行方式)
- [AI 读取入口](#ai-读取入口)
- [环境变量](#环境变量)
- [测试覆盖](#测试覆盖)
- [当前限制与后续扩展](#当前限制与后续扩展)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 已实现 source | `google_trends / github / stablecoin` |
| 已实现阶段 | `P0` 已完整可用，`P1` 已落首版 |
| 目标证据 | 注意力变化、开发者建设强度、稳定币流动性脉冲 |
| registry 设计 | `registry/*.json` 外置，支持版本指纹、热刷新和强制 reload |
| AI 主输出 | `load_latest_context_bundle()` 与 `load_source_coverage()` |
| 质量原则 | AI 主视图与 `raw` 真实诊断分层，实验或未达标 source 不会被洗白进主视图 |

## AI 文档维护约束

这份 README 是后续 AI 继续维护 `alternative_data` 时的工作文档。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 已实现 / 未实现范围
- 数据源清单、环境变量、调度间隔或 bootstrap 语义
- 因子目录、表结构、实体键规则或落库语义
- repo group 映射、稳定币资产范围或测试覆盖边界
- registry 热加载、版本指纹规则或 CLI 注册表查看语义

## 模块定位

`alternative_data` 负责补齐价格、新闻、宏观之外的“外生背景输入”，目标是给 AI 增加三类信息：

- 注意力变化
- 开发者建设强度
- 稳定币流动性脉冲

这个模块不是为了“尽可能多抓原始数据”，而是为了给 AI 提供更稳定、更容易消费的决策输入。

当前设计原则：

- 优先产出可直接排序、比较、建模的数值因子
- 同时把上游证据明细保留在 `raw_payload_json`
- 尽量把“实体键稳定性”和“采样口径稳定性”前置到数据层
- 避免把过强业务解释写死在采集层，把最终判断留给 AI / logic_layer

当前仓库里已经有三条主要原始链路：

- `exchange_data`
- `news_data`
- `macro_data`

`alternative_data` 不是替代它们，而是补上下面这些目前对 AI 仍然重要但原先缺失的上下文：

- 某个生态最近是否仍在持续建设
- 稳定币供给是否在扩张或收缩
- 稳定币是否在不同链之间迁移

## 当前代码树

```text
alternative_data/
  README.md              # 模块说明、运行方式、边界与维护约束
  __init__.py            # 模块包入口，导出 AlternativeDataService
  base.py                # 公共落库与去重逻辑
  client.py              # Google Trends / GitHub / Stablecoin HTTP 客户端与通用解析
  google_trends.py       # Google Trends query group 搜索热度采集器
  github_activity.py     # GitHub repo group 聚合采集器
  models.py              # 因子目录模型、时序点模型与维度键序列化
  registry/
    github_repo_groups.json          # GitHub repo group 外置注册表
    google_trends_query_groups.json  # Google Trends query group 外置注册表
    stablecoin_assets.json           # 稳定币资产外置注册表
  runner.py              # CLI 运行入口
  service.py             # 模块编排、目录同步、调度与线程安全包装
  sources.py             # 因子定义与 registry 文件加载
  stablecoin_supply.py   # 稳定币供给、净变化与链分布采集器
```

## 当前实现范围

### P0：GitHub 活跃度

当前实现方式不是“全 GitHub 扫描”，而是固定的 `repo_group` 映射。

当前 repo group 清单已经从源码常量外置到：

- `data_layer/alternative_data/registry/github_repo_groups.json`

当前内置 repo group：

- `BTC`
- `ETH`
- `SOL`
- `SUI`

当前实现指标：

- `github_commit_count_1d`
- `github_commit_count_7d`
- `github_active_contributors_7d`
- `github_opened_pr_count_7d`
- `github_merged_pr_count_7d`
- `github_release_count_30d`

当前实现语义：

- `entity_type = repo_group`
- `entity_key` 使用资产级短键，例如 `BTC`
- 维度里强制携带 `repo_group_version`
- 原始聚合细节会写入 `raw_payload_json`

当前 GitHub 采集逻辑：

- `commits` 通过仓库 commits REST 接口统计
- `opened_pr_count_7d` / `merged_pr_count_7d` 通过 GitHub Search API 统计
- `release_count_30d` 通过 releases REST 接口过滤近 30 天记录
- 如果某个 repo group 只有部分仓库成功，会写 `quality_flag=partial`

### P0：稳定币供给变化

当前跟踪资产：

- `USDT`
- `USDC`
- `DAI`
- `FDUSD`

当前资产清单已经从源码常量外置到：

- `data_layer/alternative_data/registry/stablecoin_assets.json`

当前实现指标：

- `stablecoin_total_supply`
- `stablecoin_net_supply_change_24h`
- `stablecoin_net_supply_change_7d`
- `stablecoin_chain_supply`
- `stablecoin_chain_supply_share`
- `stablecoin_mint_volume`
- `stablecoin_burn_volume`
- `stablecoin_bridge_inflow`
- `stablecoin_bridge_outflow`

当前实现语义：

- 资产级指标使用 `entity_type = stablecoin_asset`
- 链级指标使用 `entity_type = stablecoin_chain`
- 链级 `entity_key` 采用 `ASSET:chain_key`，例如 `USDT:ethereum`
- `dimensions_json` 里显式保留 `aggregation_scope / asset / chain`

当前稳定币采集逻辑：

- 从稳定币列表接口拿当前资产快照
- 从资产详情接口拿历史供给序列
- `net_supply_change_*` 是基于历史库存差分计算出来的净供给变化
- bootstrap 会落资产级 `1d` 历史，同时补当前 `1h` 快照
- 如果上游可提供链级历史，会同时回填 `stablecoin_chain_supply` 和 `stablecoin_chain_supply_share` 的 `1d` 序列
- 当前 `mint / burn / bridge` 事件流第一版采用“快照差分事件化”
  - 资产总供给相邻快照差分推断 `mint / burn`
  - 链级供给相邻快照差分推断 `bridge inflow / outflow`
  - `bridge` 估算采用 `positive_delta / negative_delta` 的比例重分配
- 当前这批事件并不是逐笔链上原始日志，而是为 AI 提供更稳定可比的“事件化流量因子”

### P1：Google Trends

Google Trends 首版已经接入，但当前仍应视为“实验性 source”。

当前实现 query group：

- `bitcoin`
- `ethereum`
- `solana`
- `sui`
- `crypto`
- `stablecoin`
- `bitcoin_etf`
- `memecoin`

当前 query group 清单已经从源码常量外置到：

- `data_layer/alternative_data/registry/google_trends_query_groups.json`

当前实现指标：

- `google_trends_search_interest`
- `google_trends_attention_shock_7d`
- `google_trends_related_query_breakout_count`
- `google_trends_related_query_rising_max_score`
- `google_trends_related_topic_breakout_count`
- `google_trends_related_topic_rising_max_score`
- `google_trends_cross_query_zscore`
- `google_trends_cross_query_percentile`
- `google_trends_narrative_concentration`
- `google_trends_narrative_speculation_share`
- `google_trends_narrative_builder_share`
- `google_trends_narrative_institutional_share`
- `google_trends_narrative_risk_share`

当前实现语义：

- `entity_type = query_group`
- `entity_key` 使用稳定 query group 键，例如 `bitcoin`、`bitcoin_etf`
- `dimensions_json` 显式保留 `query / geo / gprop / category / window_days / query_group_type / query_version`
- 当前 source 名称固定为 `google_trends`

当前 Trends 采集逻辑：

- 通过 Google Trends 公开网页使用的 `explore` / `widgetdata/multiline` 接口拉取时序
- 当前会落原始 `search_interest`
- 当前会基于同一 query group 的滚动历史计算 `attention_shock_7d`
- `attention_shock_7d = (current - trailing_mean_7d) / max(abs(trailing_mean_7d), 1.0)`
- attention shock 至少要求过去 7 天窗口里已有 `2` 个基线观测点
- 当前会同步拉取 `related queries` 和 `related topics`
- 当前把 related ranked list 压缩成适合 AI 首轮筛选的数值因子
  - breakout 数量
  - rising 最大分值
- 当前会把同批 query group 的 `search_interest` 进一步做 cross-query 标准化
  - `zscore`
  - `percentile`
- 当前会把 related query/topic 明细进一步压缩成 narrative-level 聚合特征
  - narrative concentration
  - speculation share
  - builder share
  - institutional share
  - risk share
- narrative 聚合当前使用规则式分类 + `log1p(value)` 权重
- 相关 query/topic 的明细条目保留在 `raw_payload_json`
- 当前按稳定滚动窗口采集，默认窗口 `90` 天
- bootstrap 支持更长历史的分段回填
  - 通过重叠窗口拼接
  - 使用 overlap 区间比例中位数做重标化
  - 历史样本会在 `raw_payload_json` 中保留 `history_mode / history_depth_days / rescale_factor / overlap_observation_count`
- 当前 `dimensions_json` 仍保留最近滚动窗口语义，避免把最新快照污染成多套并存口径
- cross-query 因子当前只在“本次已加载 query group 批次”内部标准化

当前限制：

- Google Trends 本身是相对标准化分数，不是绝对搜索量
- 同一个 query 在不同窗口重新拉取时，历史值可能被 Google 重标化
- 当前实现已经支持长历史拼接，但它本质上仍是“相对可比的近似连续历史”，不是严格不可变的绝对搜索量基线

## 数据表与落库语义

当前模块新增三张表：

### `alternative_factor_catalog`

用途：

- 因子目录
- 保存默认频率、实体范围、来源与配置版本

当前关键字段：

- `factor_id`
- `category`
- `factor_type`
- `entity_scope`
- `entity_type`
- `source_name`
- `source_symbol`
- `config_version`
- `raw_meta_json`

约束：

- `factor_id` 唯一

### `alternative_timeseries`

用途：

- 历史时序主表

当前关键字段：

- `factor_id`
- `entity_type`
- `entity_key`
- `interval`
- `observation_time`
- `value`
- `quality_flag`
- `dimensions_key`
- `dimensions_json`
- `config_version`
- `source_name`
- `source_symbol`
- `raw_payload_json`
- `collected_at`
- `updated_at`

当前唯一键：

- `UNIQUE(factor_id, entity_type, entity_key, interval, observation_time, dimensions_key, source_name, config_version)`

### `latest_alternative_timeseries`

用途：

- 当前最新快照
- 给 AI 和逻辑层快速读取当前上下文

当前唯一键：

- `UNIQUE(factor_id, entity_type, entity_key, interval, dimensions_key, source_name, config_version)`

当前 upsert 规则：

- 只有当新样本 `observation_time` 不早于旧样本时，才允许覆盖 latest

## 统一键规则

这个模块后续继续扩展时，必须继续遵守下面三条规则。

### `entity_type`

当前已使用：

- `query_group`
- `repo_group`
- `stablecoin_asset`
- `stablecoin_chain`

### `entity_key`

当前规则：

- 必须稳定
- 必须适合 CLI 过滤
- 不把所有语义都硬塞进 `entity_key`

当前示例：

- `bitcoin`
- `bitcoin_etf`
- `BTC`
- `ETH`
- `USDT`
- `USDT:ethereum`

### `dimensions_key`

当前规则：

- 由 `dimensions_json` 排序后稳定序列化得到
- 用来参与唯一键，避免不同口径样本互相覆盖

当前已使用维度：

- Google Trends
  - `query`
  - `geo`
  - `gprop`
  - `category`
  - `window_days`
  - `query_group_type`
  - `query_version`
  - `related_limit`
  - `cross_query_peer_count`
  - `cross_query_peer_set`
- GitHub
  - `repo_group_version`
  - `repo_count`
- Stablecoin
  - `aggregation_scope`
  - `asset`
  - `chain`
  - `eventization_mode`

## 数据流向

当前模块的数据流不是“抓到什么就直接给 AI 什么”，而是先经过注册表约束、标准化落库，再由统一 bundle 入口输出。

```text
registry/*.json
  -> sources.py(load_alternative_sources / load_alternative_factors / load_alternative_entities)
  -> AlternativeDataService.sync_factor_catalog()
  -> alternative_factor_catalog

Google Trends / GitHub / Stablecoin 上游接口
  -> client.py
  -> google_trends.py / github_activity.py / stablecoin_supply.py
  -> AlternativeTimeSeriesPoint
  -> AlternativeCollectorBase.save_to_db()
  -> alternative_timeseries
  -> latest_alternative_timeseries
  -> AlternativeDataService.load_latest_context_bundle()
  -> AI / CLI / 后续 API
```

### 1. 注册表与因子目录流

- `registry/github_repo_groups.json`
- `registry/google_trends_query_groups.json`
- `registry/stablecoin_assets.json`

这三份 JSON 是模块内部实体范围的事实来源。

- `sources.py` 通过 `refresh_alternative_registries()` 和 `load_alternative_*()` 系列函数加载它们
- `describe_registry()` 和 CLI `--list-sources / --list-factors / --list-entities` 输出的也是这套注册表视图
- `sync_factor_catalog()` 会把当前因子定义写入 `alternative_factor_catalog`

这里要注意两点：

- `alternative_factor_catalog` 保存的是“因子目录元数据”，不是时序样本
- `--list-factors` 能成功输出，并不代表数据库里已经有历史点位，它读取的是当前代码定义和 registry 快照

### 2. 采集与标准化流

- `runner.py` 接收 `bootstrap / once / scheduler`
- `AlternativeDataService.bootstrap()` 会做首轮历史回填与目录同步
- `AlternativeDataService.collect_once()` 会执行一次增量采集
- `AlternativeDataService.build_scheduler()` 会把三类 source 包装成独立 job

当前三条采集支路分别是：

- `GoogleTrendsCollector`
- `GitHubActivityCollector`
- `StablecoinSupplyCollector`

它们都会先通过 `AlternativeDataClient` 拉取上游 payload，再统一转成 `AlternativeTimeSeriesPoint`。每个点位至少带有：

- `factor_id`
- `entity_type`
- `entity_key`
- `interval`
- `observation_time`
- `value`
- `dimensions_json`
- `raw_payload_json`

这一步的目标，是把“不同 source 的异构响应”压缩成统一时序语义，让 AI 后面面对的是稳定键空间，而不是三套不同的原始接口格式。

### 3. 历史表与最新快照流

- `AlternativeCollectorBase.save_to_db()` 先做 `_deduplicate_history_points()`
- 再做 `_deduplicate_latest_points()`
- 然后一次性 upsert 到 `alternative_timeseries`
- 同时 upsert 到 `latest_alternative_timeseries`

两张表分工明确：

- `alternative_timeseries`
  - 保存完整历史
  - 适合回看 attention shock、长历史拼接、稳定币链级迁移等时间序列分析
- `latest_alternative_timeseries`
  - 保存每个 `factor_id + entity_key + interval + dimensions_key + source_name + config_version` 的最新快照
  - 适合 AI 当前上下文和 CLI 快速读取

当前 latest 表还有一个关键保护规则：

- 只有新样本的 `observation_time` 不早于旧样本时，才允许覆盖现有 latest 记录

这能避免 bootstrap 或历史回填把旧数据误覆盖成“当前状态”。

### 4. 从数据库到 AI bundle 的读取流

- `AlternativeDataService.load_latest_context()` 直接读 `latest_alternative_timeseries`
- `_select_preferred_context_rows()` 按因子偏好挑选更适合当前语义的 interval
  - 例如稳定币库存类优先取 `1h`
  - 稳定币事件流优先取 `1d`
- `load_alternative_entities()` 再从 registry 补实体名称和说明
- `load_latest_context_bundle()` 最终只把 AI-ready 的 source 组装进 `google_trends / github / stablecoin` section
  - 未达到 AI-ready 门槛但真实已落库的 source 会转入 `raw_* / ai_excluded_sources / source_health`

当前 bundle 不是数据库行的直接透传，而是面向 AI 的二次组织结果，重点输出：

- Google Trends 的 `attention_leaders / risk_watchlist / entities`
- GitHub 的 `leaders_by_commit_7d / entities`
- Stablecoin 的 `summary / bridge_hotspots / assets`
- `raw_row_count / raw_source_counts / raw_latest_quality_flag_breakdown / ai_excluded_sources`
  - 这组字段专门保留“真实已落库但当前不应直接给 AI 使用”的诊断证据

CLI 验证入口：

- `python -m data_layer.alternative_data.runner --print-context`

如果当前 `latest_alternative_timeseries` 还是空表，`--print-context` 返回空 bundle 是正常行为，不是 bug。

## 运行方式

当前 runner：

- `python -m data_layer.alternative_data.runner --mode once`
- `python -m data_layer.alternative_data.runner --mode bootstrap`
- `python -m data_layer.alternative_data.runner --mode scheduler`
- `python -m data_layer.alternative_data.runner --mode scheduler --async-scheduler`
- `python -m data_layer.alternative_data.runner --reload-registry`

当前可选参数：

- `--sources`
  - 逗号分隔，可选 `google_trends,github,stablecoin`
- `--entities`
  - 逗号分隔，可按 `bitcoin,stablecoin,BTC,USDT` 这类实体键过滤
- `--skip-bootstrap`
  - 仅对 `scheduler` 模式生效
- `--list-sources`
  - 列出当前 source 注册表，并显示对应 registry 文件、指纹版本和记录数
- `--list-factors`
  - 列出当前 factor 注册表
- `--list-entities`
  - 列出当前 entity 注册表
- `--reload-registry`
  - 强制刷新进程内 registry 缓存
  - 如果单独使用，会默认输出当前 source 注册表
- `--print-context`
  - 输出当前 `latest_alternative_timeseries` 的 AI 上下文 bundle

总入口启动示例：

- `python main.py --modules alternative_data`

注册表查看示例：

- `python -m data_layer.alternative_data.runner --list-sources`
- `python -m data_layer.alternative_data.runner --reload-registry`
- `python -m data_layer.alternative_data.runner --list-factors --sources github`
- `python -m data_layer.alternative_data.runner --list-entities --sources google_trends --entities bitcoin`
- `python -m data_layer.alternative_data.runner --print-context --sources google_trends,stablecoin`

## AI 读取入口

当前已经提供面向 AI 的 bundle 读取接口：

- `AlternativeDataService.load_latest_context_bundle()`

当前语义：

- 不是直接把数据库行原样吐给上游
- 会按 AI 常见分析场景重组为 `google_trends / github / stablecoin` 三个 section
- 会自动优先选择更适合当前语义的 interval
  - 例如稳定币库存优先取 `1h`
  - 稳定币事件流优先取 `1d`
- 如果传入 `entity_keys=["USDT"]`，bundle 会自动把 `USDT:*` 链级行一并带出
- `as_of` 现在代表“bundle 内真实最新观测时间”，不再等于“当前生成 bundle 的墙钟时间”

当前输出重点：

- Google Trends
  - `attention_leaders`
  - `risk_watchlist`
  - 每个 query group 的 search / shock / cross-query / narrative 摘要
- GitHub
  - `leaders_by_commit_7d`
  - 每个 repo group 的开发活跃度摘要
- Stablecoin
  - 资产级供给与 `mint / burn`
  - 链级分布与 `bridge inflow / outflow`
  - `bridge_hotspots`

同时 bundle 还会额外暴露：

- `coverage_summary`
- `latest_quality_flag_breakdown / latest_quality_ready_ratio`
- `source_health_summary / source_health`
- `data_quality_flags / quality_notes`

这层语义的目标是明确告诉 AI：

- 当前补充特征是否真的足够新
- 哪些 section 缺失或仍不稳定
- latest 快照里是否已经混入 `partial / fallback / stale / unknown`
- 哪些 source 虽然有数据，但其实还不该被视为同等可靠

这里的“可直接给 AI 用”和“最近运行成功”已经明确分开：

- `health_status=ready`
  - 只表示 source 最近运行成功，且 latest 快照没有整体过期
- `is_ready_for_ai=true`
  - 还额外要求当前 source 不是 `P1/experimental`
  - 并且注册表实体覆盖完整
  - 并且 latest 快照里没有 `partial / fallback / stale / unknown`
  - 也就是说，像 `google_trends` 这种仍处于 `P1` 的 source，即使最近运行成功，也不会被标成 `is_ready_for_ai=true`

`coverage_summary` 现在需要按两层去理解：

- 顶层 `expected_entity_count / observed_entity_count`
  - 只是跨 source 的总量视图
- `coverage_by_source`
  - 每条 source 自己的覆盖情况，适合判断 GitHub、Google Trends、Stablecoin 分别缺不缺
- `coverage_by_entity_type`
  - 按 `query_group / repo_group / stablecoin_asset / stablecoin_chain` 这类实体语义分层看覆盖

这样做的原因是：

- `google_trends` 的 `query_group`
- `github` 的 `repo_group`
- `stablecoin` 的资产级/链级实体

本来就不是同一种市场对象，不能简单把它们加总后当成统一横截面去理解。

## 调度与线程安全

当前调度器有三个 job：

- `alternative_google_trends`
- `alternative_github`
- `alternative_stablecoin`

当前实现约束：

- APScheduler job 不复用主线程 SQLite 连接
- 每个 job 都会重新创建 `DBManager`
- 采集器在子线程内独立落库

这是为了与当前项目里的 `macro_data`、`news_data` 实现风格保持一致，避免 SQLite 跨线程连接问题。

## 环境变量

当前模块实际读取的环境变量：

- `ALTERNATIVE_ENABLE_GOOGLE_TRENDS`
- `ALTERNATIVE_GOOGLE_TRENDS_INTERVAL_SECONDS`
- `ALTERNATIVE_GOOGLE_TRENDS_TIMEOUT_SECONDS`
- `ALTERNATIVE_GOOGLE_TRENDS_BASE_URL`
- `ALTERNATIVE_GOOGLE_TRENDS_GEO`
- `ALTERNATIVE_GOOGLE_TRENDS_HL`
- `ALTERNATIVE_GOOGLE_TRENDS_TZ`
- `ALTERNATIVE_GOOGLE_TRENDS_CATEGORY`
- `ALTERNATIVE_GOOGLE_TRENDS_PROPERTY`
- `ALTERNATIVE_GOOGLE_TRENDS_WINDOW_DAYS`
- `ALTERNATIVE_GOOGLE_TRENDS_BOOTSTRAP_HISTORY_DAYS`
- `ALTERNATIVE_GOOGLE_TRENDS_HISTORY_SEGMENT_DAYS`
- `ALTERNATIVE_GOOGLE_TRENDS_HISTORY_OVERLAP_DAYS`
- `ALTERNATIVE_GOOGLE_TRENDS_RELATED_LIMIT`
- `ALTERNATIVE_GOOGLE_TRENDS_QUERY_VERSION`
- `ALTERNATIVE_ENABLE_GITHUB`
- `ALTERNATIVE_ENABLE_STABLECOIN`
- `ALTERNATIVE_GITHUB_INTERVAL_SECONDS`
- `ALTERNATIVE_GITHUB_TIMEOUT_SECONDS`
- `ALTERNATIVE_GITHUB_REST_BASE_URL`
- `ALTERNATIVE_GITHUB_REPO_GROUP_VERSION`
- `GITHUB_TOKEN`
- `ALTERNATIVE_STABLECOIN_INTERVAL_SECONDS`
- `ALTERNATIVE_STABLECOIN_TIMEOUT_SECONDS`
- `ALTERNATIVE_STABLECOIN_LOOKBACK_DAYS`
- `ALTERNATIVE_STABLECOIN_REST_BASE_URL`
- `ALTERNATIVE_USER_AGENT`

当前默认值：

- Google Trends 调度间隔 `43200` 秒
- Google Trends 窗口 `90` 天
- Google Trends bootstrap 历史深度 `1095` 天
- Google Trends 分段窗口 `90` 天
- Google Trends overlap `30` 天
- Google Trends related 榜单截断 `10`
- Google Trends 默认地域 `US`
- GitHub 调度间隔 `21600` 秒
- Stablecoin 调度间隔 `3600` 秒
- 稳定币历史 lookback `30` 天

## 测试覆盖

当前已有测试文件：

- `tests/alternative_data/test_alternative_module.py`

当前覆盖点：

- `AlternativeTimeSeriesPoint` 维度键与时间标准化
- `DBManager.init_tables()` 新表创建
- `registry/*.json` 外置配置加载
- registry 指纹版本与热刷新
- 因子目录同步
- `source / factor / entity` 注册表描述与过滤
- Google Trends query group 搜索热度采集
- Google Trends 7 日 attention shock 派生计算
- Google Trends related query/topic 因子落库
- Google Trends cross-query zscore / percentile
- Google Trends narrative aggregation 因子落库
- Google Trends 长历史分段拼接与重标化
- GitHub repo group 聚合结果
- 稳定币总供给 / 净变化 / 链分布计算
- 稳定币链级历史回填与链级历史解析兼容
- 稳定币 `mint / burn / bridge` 事件化推断
- AI bundle 读取入口与按 source 分组聚合
- 调度线程包装
- `main.py` 模块注册

### 2026-05-14 本地验证记录

本轮围绕 coverage 语义和默认启动行为完成了下面这些本地验证：

- `pytest tests/alternative_data/test_alternative_module.py -q`
  - `15 passed`
- `python main.py --list-modules`
  - 已确认总入口注册 `alternative_data [daemon] 默认启动`
  - 已确认 `event_calendar_data / onchain_data / alternative_data / tokenomics_data / options_data` 也都已并入默认数据层常驻模块集合
- `pytest -q`
  - `119 passed`

这轮验证说明：

- `alternative_data` 的 AI bundle 覆盖语义已经补充到 `coverage_by_source / coverage_by_entity_type`
- 总入口默认启动链已经对齐“完整数据层常驻模块”而不是只拉起早期三条采集链
- 当前改动没有破坏全仓测试

### 2026-05-08 历史验证记录

本轮已完成下面这些本地验证：

- `python -m py_compile data_layer/alternative_data/*.py tests/alternative_data/test_alternative_module.py config/settings.py`
  - 通过
- `pytest tests/alternative_data/test_alternative_module.py -q`
  - `14 passed`
- `pytest -q`
  - `64 passed`
- `python main.py --list-modules`
  - 当时已确认总入口注册 `alternative_data [daemon] 手动启动`
- `python main.py --modules alternative_data --dry-run`
  - 已确认总入口会拉起 `/usr/bin/python -m data_layer.alternative_data.runner --mode scheduler`
- `python -m data_layer.alternative_data.runner --list-factors --sources google_trends,github,stablecoin`
  - 已确认三类 source 的 factor 注册表都能正确输出
- `python -m data_layer.alternative_data.runner --print-context --sources google_trends,github,stablecoin`
  - 已确认 AI bundle 读取链路可执行
  - 当前输出 `row_count=0`
  - 这说明当前数据库里还没有 `latest_alternative_timeseries` 快照数据，而不是读取逻辑失败
- `sqlite3 database/crypto_data.db ...`
  - 已确认 `alternative_factor_catalog / alternative_timeseries / latest_alternative_timeseries` 三张表存在

当前没有在这轮测试里直接执行真实在线采集。

原因：

- 当前环境网络受限
- 本轮重点是验证模块代码、数据库表、CLI 与总入口集成是否完整打通

这意味着：

- 本地静态与集成链路已通过
- 上游在线接口字段稳定性、限流行为和真实 payload 兼容性，仍需要在可联网环境单独联调

## 当前限制与后续扩展

当前限制：

- Google Trends 目前仍依赖网页侧公开接口，稳定性弱于 GitHub / Stablecoin
- Google Trends cross-query 当前只在“当前加载批次”内部标准化，不是全市场统一横截面
- Google Trends related query/topic 目前只沉淀“最新榜单摘要 + 明细证据”，还没有 term/topic 级别的独立历史表
- Google Trends narrative 当前还是规则式聚合，还没有引入 embedding / topic model
- registry 热刷新已经支持，但当前时序语义版本仍主要依赖 `ALTERNATIVE_GITHUB_REPO_GROUP_VERSION` 和 `ALTERNATIVE_GOOGLE_TRENDS_QUERY_VERSION`
- 稳定币链级历史依赖上游字段质量，真实环境仍需要继续做 payload 验证
- 稳定币 `mint / burn / bridge` 当前还是快照差分事件化，不是逐笔链上原始日志
- 稳定币客户端对上游 payload 做了兼容解析，但仍需要后续在线上环境继续验证字段稳定性

## 现在还没做的事

当前模块已可运行，但下面这些事情仍然没有做：

- Google Trends 叙事级特征
  - 已有第一版 narrative share / concentration
  - 但还没有 narrative cluster 演化、主题迁移、embedding 相似度之类更高阶特征
- registry 语义升级自动化
  - 当前已经支持 JSON 内容指纹、变更校验和进程内热刷新
  - 但如果 repo group / query group 的业务语义发生变化，仍建议同步提升 `repo_group_version` 或 `query_version`
- GitHub 低频补充指标
  - 还没有 stars、forks、issue velocity、release notes 结构化提取
- 稳定币链上事件流
  - 已有第一版 `mint / burn / bridge` 事件化推断
  - 但还没有 redemption 明细、bridge route、tx hash 和地址级事件
- 在线联调验证
  - 当前测试主要是静态假数据，真实上游返回字段和限流行为还需要单独联调
- 下游消费接口
  - 已有 `load_latest_context_bundle()` 和 CLI `--print-context`
  - 但还没有专门给 API 层暴露的查询路由，也还没接到独立的 context 表

后续扩展建议：

- 如果后续要继续扩展 Google Trends，优先在现有 query_group 主键体系下增加新 factor，而不是另起一套表
- 如果后续要把 related queries / topics 提升到更强 AI 特征，建议保留“数值摘要 + 明细证据”双轨设计
- 如果 repo group 映射变更，必须同步提升 `ALTERNATIVE_GITHUB_REPO_GROUP_VERSION`
- 如果后续新增 `onchain_data`，应把地址级原始 mint / burn / redemption 事件放在那里，本模块继续保留 AI 友好的聚合因子
- 如果继续扩展 Google Trends，优先复用当前统一表结构，而不是另建 Trends 专用表

## 数据质量与覆盖检查

查看当前 source 覆盖率：

```bash
python -m data_layer.alternative_data.runner --print-coverage
```

当前 coverage 会统一暴露：

- `registry_version / registry_record_count / registry_modified_at`
- `configuration_ready`
- `expected_entity_count`
- `latest_entity_count / latest_factor_count / latest_point_count`
- `last_run_status / last_run_item_count / last_run_finished_at`
- `health_status / is_ready_for_ai / is_stale`
- `data_quality_flags / quality_notes`
- `latest_quality_flag_breakdown`
- `latest_quality_ready_ratio`
- `ready_for_ai_source_count / not_ready_for_ai_source_count`

另外 `source_health` 现在会显式带上：

- `phase`
- `entity_type`

这样 AI 在读取结构化健康信息时，就能直接区分：

- 哪些 source 是 `P0`
- 哪些 source 仍是 `P1/experimental`
- 当前覆盖的是 `query_group`、`repo_group` 还是稳定币相关实体

与 coverage 的分工：

- `load_latest_context_bundle()`
  - 更适合直接给 AI 读取当前补充特征上下文
- `load_source_coverage()`
  - 更适合排查到底是哪条 source、哪一类 registry 或哪一批 latest 快照出了问题

解释原则：

- `unconfigured`
  - 代表 source 虽然启用，但 registry 本身没有有效记录，不能简单理解为“今天没有数据”
- `empty`
  - 代表这轮采集执行了，但结果为空
- `ready`
  - 代表 registry、最近运行和最新快照三者都达标
- `is_ready_for_ai`
  - 代表这路 source 不只是“活着”，而是真的达到了可直接作为 AI 补充证据使用的门槛
  - 当前实现要求：不是 `P1/experimental`、实体覆盖完整、latest 里至少有 `ok` 样本，且没有 `partial / fallback / stale / unknown`

另外：

- 如果传入 `entity_keys`，coverage 统计会严格按该实体子集重算
- `quality_flag` 统计会显式区分 `ok / partial / fallback / stale / unknown`，避免“有数据”被误读成“数据完全可用”

模块内的特殊说明：

- `google_trends` 当前仍属于 `P1/experimental` source，coverage 会在 `quality_notes` 里显式提示，且不会被标成 `is_ready_for_ai=true`
- `stablecoin` 的 `expected_entity_count` 代表顶层资产数，而 `latest_entity_count` 可能更高，因为同一资产下还会展开链级实体，例如 `USDT:ethereum`
- `coverage_summary` 顶层数字不能直接当成统一特征宇宙大小理解，优先读取 `coverage_by_source / coverage_by_entity_type`
- scheduler wrapper 现在也会记录 `collection_runs`，因此 `--print-coverage` 能反映长期运行中的真实健康状态，而不只是手动 `--mode once`
