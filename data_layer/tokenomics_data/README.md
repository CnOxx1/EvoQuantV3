# Tokenomics 数据模块 `tokenomics_data`

## 模块定位

`tokenomics_data` 负责给 AI 提供“供给变化和潜在抛压”这条独立证据链，重点不是直接判断涨跌，而是把会影响市场解释的供给侧事实结构化。

这层只做：

- 采集
- 标准化
- 落库
- 输出 AI 可消费的 tokenomics bundle

这层不做：

- 交易信号判断
- 主观利好利空结论

## 快速导航

- [模块速览](#模块速览)
- [当前子模块](#当前子模块)
- [当前输出](#当前输出)
- [当前代码树](#当前代码树)
- [运行方式](#运行方式)
- [环境变量](#环境变量)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 目标证据 | 供给变化、潜在抛压、已实现解锁、国库钱包流与质押变化 |
| 当前子模块 | `circulating_supply / unlock_schedule / unlock_realization / treasury_wallet_flow / staking_ratio` |
| 核心表 | `tokenomics_factor_catalog / tokenomics_timeseries / latest_tokenomics_timeseries / token_unlock_events` |
| AI 主入口 | `TokenomicsDataService.load_latest_context_bundle()` |
| registry | `token_profiles.json` 与 `treasury_wallet_groups.json` |
| 质量原则 | AI 主 bundle 只保留达标 source，真实但未达标样本保留在 `raw_* / coverage_summary / source_health` |

## 当前子模块

当前每个子模块都使用独立目录加独立 `README.md`，后续可以单独替换数据源、补字段和扩实体范围：

- `circulating_supply/`
  - 采集流通盘、自由流通盘、年化通胀率
- `unlock_schedule/`
  - 采集未来 `7d / 30d` 计划解锁压力，并落 `token_unlock_events`
- `unlock_realization/`
  - 采集最近 `24h` 已实现解锁规模
- `treasury_wallet_flow/`
  - 采集基金会 / 国库钱包流入、流出和净流
- `staking_ratio/`
  - 采集质押率与 `7d` 变化

## 当前输出

当前模块维护四层结构，目的是让 AI 既能拿到最新快照，也能回看历史轨迹：

- `registry/*.json`
  - 维护 token profile 和 treasury wallet group
- `tokenomics_factor_catalog`
  - 维护因子目录、频率、来源和新鲜度约束
- `tokenomics_timeseries / latest_tokenomics_timeseries`
  - 维护历史时序和最新快照
- `token_unlock_events`
  - 维护未来解锁事件明细

同时提供：

- `TokenomicsDataService.load_latest_context_bundle()`
  - 输出 AI 可直接消费的供给压力上下文，并显式提示当前 tokenomics 证据是否完整、是否混入 partial/fallback、哪些资产仍缺关键供给字段
  - 现在只要某个 source 没达到 `is_ready_for_ai=true`，它的最新时序点就不会进入 AI 主 bundle
  - 如果某个 source 的原始数据虽然已落库，但覆盖不完整、latest 混入 partial/fallback/stale，或者它依赖的 registry 口径仍未达到可核验门槛，这类 source 都会被从 AI 直接消费视图里排除，同时保留 `raw_* / coverage_summary / ai_excluded_sources / source_health` 诊断

## 当前代码树

```text
tokenomics_data/
  README.md
  __init__.py
  base.py
  client.py
  models.py
  service.py
  runner.py
  sources.py
  registry/
    token_profiles.json
    treasury_wallet_groups.json
  circulating_supply/
    README.md
    __init__.py
    collector.py
  unlock_schedule/
    README.md
    __init__.py
    collector.py
  unlock_realization/
    README.md
    __init__.py
    collector.py
  treasury_wallet_flow/
    README.md
    __init__.py
    collector.py
  staking_ratio/
    README.md
    __init__.py
    collector.py
```

## 运行方式

一次采集：

```bash
python -m data_layer.tokenomics_data.runner --mode once
```

只采指定币种：

```bash
python -m data_layer.tokenomics_data.runner --mode once --entities BTC,ETH
```

查看注册表：

```bash
python -m data_layer.tokenomics_data.runner --list-sources
python -m data_layer.tokenomics_data.runner --list-factors
python -m data_layer.tokenomics_data.runner --list-entities
```

查看 AI 可读 bundle：

```bash
python -m data_layer.tokenomics_data.runner --print-context
```

`--print-context` 现在会同时回答：

- 当前 bundle 覆盖了多少目标资产、多少目标因子
- 哪些资产完全没进来，哪些资产虽然进来了但仍缺关键供给字段
- latest 快照里是否已经混入 `partial / fallback / stale / unknown`
- 哪些 source 虽然有数据，但健康状态其实还没到 `ready`
- 未来解锁事件是否已经同步落进 `token_unlock_events`
- 当前默认资产宇宙到底更像“核心执行资产视角”，还是已经足够支撑更广的供给 breadth 判断

bundle 里最值得 AI 先看的字段：

- `coverage_summary`
  - `expected_entity_count / observed_entity_count`
  - `expected_factor_count / observed_factor_count`
  - `missing_entity_keys / missing_factor_ids`
  - `coverage_by_source`
- `ai_ready_source_names`
- `ai_excluded_source_names / ai_excluded_sources`
- `configured_universe_summary`
- `latest_quality_flag_breakdown`
- `latest_quality_ready_ratio`
- `raw_latest_quality_flag_breakdown`
- `raw_latest_quality_ready_ratio`
- `data_quality_flags`
- `quality_notes`
- `source_health`
- `source_health_summary`
- `unlock_horizon_summary`
- `raw_unlock_horizon_summary`
- `upcoming_unlock_events`
- `raw_upcoming_unlock_event_count / raw_unlock_event_source_counts`

其中 `data_quality_flags` 会重点提示：

- `tokenomics_entity_coverage_incomplete`
- `tokenomics_factor_coverage_incomplete`
- `tokenomics_source_not_ready_for_ai_present`
- `tokenomics_configured_market_breadth_limited`
- `tokenomics_partial_present / tokenomics_fallback_present / tokenomics_stale_present`
- `circulating_supply_structure_missing_for_*_entities`
- `unlock_pressure_missing_for_*_entities`
- `realized_unlock_missing_for_*_entities`
- `treasury_flow_missing_for_*_entities`
- `treasury_wallet_registry_not_ai_ready`
- `staking_evidence_missing_for_*_entities`

查看 source 覆盖和最近采集情况：

```bash
python -m data_layer.tokenomics_data.runner --print-coverage
```

`--print-coverage` 主要用于回答三件事：

- 这个 source 是否已经配置好上游 endpoint
- 最近一次采集到底是 `success / empty / error / unconfigured`
- 当前 tokenomics 快照是否还足够新，能不能作为 AI 的供给侧输入

当前 coverage 还会额外回答：

- 在当前 `factor_ids / entity_keys / source_names` 过滤条件下，理论应覆盖多少 `entity / factor`
- 最新快照中 `ok / partial / fallback / stale / unknown` 各有多少点
- 当前 source 的 `latest_quality_ready_ratio` 是否足够高
- 当前到底有多少 source 真正 `ready_for_ai`
- 如果 source 依赖实体注册表口径，当前 registry 是否已经达到可直接给 AI 使用的门槛

其中 `configured_universe_summary` 会给出：

- `scope_kind`
  - 当前是默认全宇宙视角，还是用户传参后的过滤子集
  - 现在只要通过 `entity_keys`，或通过 `factor_ids` 间接把 bundle 观察宇宙缩小到局部 source 子集，就会标成 `filtered`，避免把查询子集误判成默认资产宇宙缺失
- `tracked_entity_keys`
  - 当前 tokenomics 模块设计内目标资产列表
- `asset_entity_count`
  - 默认资产宇宙实际包含多少资产
- `minimum_asset_entity_count_for_market_breadth`
  - 当前模块内部对“更广供给 breadth 判断”建议的最小资产数门槛
- `breadth_status`
  - `sufficient / limited / filtered`

需要特别注意 `treasury_wallet_flow`：

- 这一路数据现在不再只看“上游有值没有值”
- 还要求 `registry/treasury_wallet_groups.json` 里的钱包组定义本身可核验
- 当前实现至少要求：
  - `verification_status` 达到 `verified` 或 `maintained`
  - `address_count > 0`
  - `source_refs` 非空
- 如果 registry 仍是 placeholder，`health_status` 依然可能是 `ready`
- 但 `is_ready_for_ai` 会被明确降为 `False`
- 并且 `load_latest_context_bundle()` 会把这一路 source 从 AI 直接消费的 `entities / source_counts / latest_quality_*` 视图中排除
- 原始落库事实不会被删除，而是继续通过 `raw_row_count / raw_source_counts / raw_latest_quality_flag_breakdown / ai_excluded_sources` 暴露，方便维护者核对“上游有值但口径不可信”的状态
- 原因不是否认上游数值，而是避免把“钱包边界尚不稳定的流向数据”误当成强事实证据

需要补充一条新的统一规则：

- 现在不只是 `treasury_wallet_flow`
- 只要某个 source 的 `is_ready_for_ai=false`
- 它的 latest points 就不会进入 AI 主 bundle
- 它对应的未来解锁事件也不会进入 `upcoming_unlock_events / unlock_horizon_summary`
- 但真实原始事件仍会保留在 `raw_upcoming_unlock_event_count / raw_unlock_event_source_counts / raw_unlock_horizon_summary`

需要特别区分：

- `load_latest_context_bundle()`
  - 用来回答“AI 当前看到的 tokenomics 证据够不够完整，能不能直接参与交易分析”
- `load_source_coverage()`
  - 用来回答“问题具体出在什么 source、什么健康状态、什么覆盖缺口”

状态语义上要区分：

- `unconfigured`
  - source 开着，但 URL / 上游关键配置没完成
- `empty`
  - 任务跑了，但本轮没有拿到点或事件
- `ready`
  - 最新快照、新鲜度和最近运行状态都满足 AI 读取要求
- `is_ready_for_ai`
  - 比 `ready` 更严格
  - 不只要求任务最近成功、source 不 stale，还要求当前过滤条件下实体覆盖完整、因子覆盖完整，且 latest 快照满足共享 `data_quality` 的 AI-ready 质量门槛
  - 如果一个 source 只有 `partial / fallback` 样本，或者当前只覆盖了部分目标资产 / 因子，即使 `health_status=ready`，也不应直接当成完整供给证据

常看字段：

- `expected_entity_count / expected_factor_count`
- `latest_entity_count / latest_factor_count / latest_point_count`
- `raw_observed_entity_count / raw_observed_factor_count / raw_observed_point_count`
- `data_quality_flags`
- `latest_quality_flag_breakdown`
- `raw_latest_quality_flag_breakdown`
- `latest_ok_point_count / latest_partial_point_count / latest_fallback_point_count / latest_stale_point_count`
- `latest_non_ok_point_count`
- `latest_quality_ready_ratio`
- `raw_latest_quality_ready_ratio`
- `ready_for_ai_source_count / not_ready_for_ai_source_count`

`unlock_horizon_summary` 现在会额外把未来解锁事件聚合成三个真实时间窗：

- `next_24h`
- `next_7d`
- `next_30d`

每个时间窗都会给出：

- `event_count`
- `asset_count`
- `assets`
- `total_unlock_value_usd`
- `max_unlock_value_usd`

这样 AI 不需要自己重新扫事件表，就能先判断“供给风险是马上落地，还是堆在未来一周 / 一个月”。

如果需要核对“真实事件有没有落库，但为什么没进 AI 主视图”，要同时看：

- `upcoming_unlock_event_count / unlock_event_source_counts / unlock_horizon_summary`
  - 只统计 AI-ready source 的真实事件
- `raw_upcoming_unlock_event_count / raw_unlock_event_source_counts / raw_unlock_horizon_summary`
  - 统计全部真实已落库事件，包括当前被质量门槛排除的 source

## 环境变量

- `TOKENOMICS_CIRCULATING_SUPPLY_URL`
- `TOKENOMICS_UNLOCK_SCHEDULE_URL`
- `TOKENOMICS_UNLOCK_REALIZATION_URL`
- `TOKENOMICS_TREASURY_WALLET_FLOW_URL`
- `TOKENOMICS_STAKING_RATIO_URL`
- `TOKENOMICS_ASSET_ENTITY_KEYS`
- `TOKENOMICS_EXTRA_ENTITIES_JSON`
- `TOKENOMICS_DEFAULT_INTERVAL`
- `TOKENOMICS_DEFAULT_LOOKBACK_HOURS`

## 维护约束

- 上游如果切换供应商，优先保持标准化 JSON 输出不变。
- `unlock_schedule` 既写 timeseries，也写独立事件表，后续不要把这两类语义混在一起。
- 这个模块的目标是给 AI 提供供给证据，不在采集层直接输出方向判断。

### 2026-05-15 本地验证记录

本轮围绕 tokenomics AI 可用性语义完成了下面这些本地验证：

- `python -m py_compile data_layer/tokenomics_data/service.py tests/tokenomics_data/test_tokenomics_module.py`
  - 通过
- `pytest -q tests/tokenomics_data/test_tokenomics_module.py`
  - `4 passed`

这轮验证说明：

- `coverage_summary` 已新增 `coverage_by_source`
- `source_health_summary` 已新增 `ready_for_ai_source_count / not_ready_for_ai_source_count`
- `unlock_horizon_summary` 已能直接输出未来 `24h / 7d / 30d` 的真实解锁压力聚合
- `is_ready_for_ai` 已升级为更严格语义，不再把只有 `partial / fallback` 的 source，或当前实体 / 因子覆盖仍不完整的 source 误判为可直接给 AI 使用

### 2026-05-17 本地验证记录

本轮围绕 tokenomics bundle 的 AI-ready 过滤边界完成了下面这些本地验证：

- `python -m py_compile data_layer/tokenomics_data/service.py tests/tokenomics_data/test_tokenomics_module.py`
  - 通过
- `pytest -q tests/tokenomics_data/test_tokenomics_module.py`
  - `7 passed`

这轮验证说明：

- `load_latest_context_bundle()` 现在已经不再只屏蔽 registry 未就绪的钱包流 source
- 只要某个 source 的 `is_ready_for_ai=false`，它的 latest points 都会从 AI 主 bundle 中剥离
- `upcoming_unlock_events / unlock_horizon_summary` 也已经跟随同一 source 级质量门槛过滤，不再把来自非 AI-ready source 的真实事件直接混进 AI 主视图
- 同时新增 `ai_ready_source_names / raw_upcoming_unlock_event_count / raw_unlock_event_source_counts / raw_unlock_horizon_summary`，保留全部真实原始落库事实，方便维护者区分"AI 当前可直接消费的数据"和"真实存在但暂时被质量门槛挡住的数据"

### 2026-05-28 免费 API 直接采集接入

本轮为 2 个子模块接入了 CoinGecko 免费公开 API，不再依赖环境变量配置的外部 URL：

- `circulating_supply/collector.py` — 重写
  - 数据源：`https://api.coingecko.com/api/v3/coins/{coin_id}`
  - 实体覆盖：BTC / ETH / SOL / SUI / ARB / OP / AVAX / MATIC / LINK / UNI / AAVE / MKR / CRV / JUP 等 18 个
  - 输出：circulating_supply, float_supply
  - inflation_rate_annualized 当前标记 partial（需历史对比）
  - 频率限制：每请求间隔 2.5s（CoinGecko 免费 30 calls/min）
- `staking_ratio/collector.py` — 重写
  - 数据源：CoinGecko + 内置 KNOWN_STAKING_RATIOS 静态映射
  - 覆盖：ETH≈28%, SOL≈67%, SUI≈79%, AVAX≈56%, MATIC≈38%, ATOM≈63%, DOT≈53%
  - 输出：staking_ratio
  - quality_flag：CoinGecko 实时数据为 ok，静态映射为 fallback
