# 链上数据采集模块 `onchain_data`

## 模块定位

`onchain_data` 负责补齐交易所行情之外的链上资金、桥流、储备、协议活跃度和质押行为背景。这个模块的核心目标是给 AI 提供“链上资本流与网络状态证据”，不是直接给出市场结论。

## 快速导航

- [模块速览](#模块速览)
- [当前来源与子模块](#当前来源与子模块)
- [当前代码树](#当前代码树)
- [当前输出](#当前输出)
- [上游约定](#上游约定)
- [运行方式](#运行方式)
- [环境变量](#环境变量)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 核心目标 | 补齐交易所以外的链上资本流、网络使用和协议资金状态 |
| 当前来源链 | `exchange_flow / whale_activity / stablecoin_flow / bridge_netflow / exchange_reserve / protocol_tvl / network_usage / staking_flow / dex_volume / stablecoin_supply` |
| 主要输出 | `onchain_factor_catalog / onchain_timeseries / latest_onchain_timeseries` |
| AI 主入口 | `load_latest_context_bundle()` 与 `load_source_coverage()` |
| 默认链覆盖 | `BITCOIN / ETHEREUM / SOLANA / ARBITRUM / BASE / SUI` |
| 质量原则 | AI 主视图只保留 `is_ready_for_ai=True` 的真实 source，其他样本保留在 `raw_*` 与 `source_health` 诊断里 |

## 当前来源与子模块

当前模块已经从第一阶段的 3 类基础因子扩展到 10 条独立来源链，每条链都对应独立 collector 或独立子目录：

- `collectors/exchange_flow.py`
  - `exchange_netflow`
- `collectors/whale_activity.py`
  - `whale_transfer_count`
- `collectors/stablecoin_flow.py`
  - `stablecoin_exchange_inflow`
- `bridge_netflow/`
  - `bridge_inflow / bridge_outflow / bridge_netflow`
- `exchange_reserve/`
  - `exchange_reserve_balance / exchange_reserve_change_24h`
- `protocol_tvl/`
  - `protocol_tvl / protocol_tvl_change_24h / protocol_tvl_change_7d`
- `network_usage/`
  - `active_addresses / transaction_count / fees_paid`
- `staking_flow/`
  - `staking_netflow`
- `dex_volume/`
  - `dex_volume_24h / dex_volume_change_1d`（来源: DeFiLlama）
- `stablecoin_supply/`
  - `stablecoin_mcap / stablecoin_mcap_change_7d`（来源: DeFiLlama）

新加的第二阶段子模块都采用“独立文件夹 + 独立 `README.md`”方式组织，便于后续独立维护。

## 当前代码树

```text
onchain_data/
  README.md
  __init__.py
  client.py
  models.py
  runner.py
  service.py
  sources.py
  registry/
    chain_groups.json
    protocol_groups.json
  collectors/
    exchange_flow.py
    whale_activity.py
    stablecoin_flow.py
  bridge_netflow/
    README.md
    __init__.py
    collector.py
  exchange_reserve/
    README.md
    __init__.py
    collector.py
  protocol_tvl/
    README.md
    __init__.py
    collector.py
  network_usage/
    README.md
    __init__.py
    collector.py
  staking_flow/
    README.md
    __init__.py
    collector.py
  dex_volume/
    __init__.py
    collector.py
  stablecoin_supply/
    __init__.py
    collector.py
```

## 当前输出

- `onchain_factor_catalog`
- `onchain_timeseries`
- `latest_onchain_timeseries`
- `OnchainDataService.load_latest_context_bundle()`
- `OnchainDataService.load_source_coverage()`

这些输出的目的，是让 AI 能同时看到历史链上轨迹和当前 latest 快照，而不是只依赖单点数值。

其中 `load_latest_context_bundle()` 现在除了 `entities / leaders` 之外，还会显式返回：

- `source_counts`
- `raw_as_of / raw_row_count / raw_entity_count / raw_source_counts`
- `coverage_summary`
- `configured_universe_summary`
- `latest_quality_flag_breakdown / latest_quality_ready_ratio`
- `raw_latest_quality_flag_breakdown / raw_latest_quality_ready_ratio`
- `ai_ready_source_names / ai_excluded_source_names / ai_excluded_sources`
- `source_health_summary / source_health`
- `data_quality_flags / quality_notes`

当前 `load_source_coverage()` 里的 `is_ready_for_ai` 也已与共享 `data_layer/data_quality` 语义对齐：latest 快照默认必须存在 `ok` 样本，且不能混入 `partial / fallback / stale / unknown`，然后再叠加链上模块自己的 `entity x factor x point` 完整矩阵约束。

这层语义的目标不是替 AI 做结论，而是明确告诉 AI：“当前链上证据是否完整、哪些实体没覆盖、哪些字段虽然有值但并不应视为同等可靠”。

同时要注意，AI 主视图现在只会暴露 `is_ready_for_ai=True` 的 source。那些真实已落库、但覆盖不完整或暂时不适合直接给 AI 使用的链上快照，不会再继续混进 `row_count / entity_count / entities / leaders / latest_quality_*`，而是只在 `raw_* / ai_excluded_sources / source_health` 等诊断字段里保留。

`configured_universe_summary` 解决的是另一类问题：

- 当前链上模块默认到底覆盖了多少资产、链、稳定币、协议
- 这些配置更适合做“执行资产跟踪”
- 还是已经足够支撑更广的市场 breadth 判断

它不会制造任何新链或新协议的数据，只会诚实描述当前默认配置宇宙本身的宽度。

当前默认链级覆盖已经包含：

- `BITCOIN`
- `ETHEREUM`
- `SOLANA`
- `ARBITRUM`
- `BASE`
- `SUI`

这样做的原因很直接：

- 交易宇宙里已经包含 `BTC / ETH / SOL / SUI`
- 如果链级网络使用度不覆盖 `BITCOIN`，AI 在判断 BTC 交易时就会天然少一条高价值链上证据

## 上游约定

当前默认最稳的接入方式是使用“标准化 JSON 接口”，每个 source 输出：

```json
{
  "points": [
    {
      "entity_key": "BTC",
      "observation_time": "2026-05-08T10:00:00+00:00",
      "value": -1250000.0,
      "interval": "1h",
      "unit": "usd",
      "quality_flag": "ok",
      "dimensions_json": {
        "exchange_count": 4
      }
    }
  ]
}
```

含义示例：

- `exchange_netflow`
  - 正值代表净流入交易所，负值代表净流出交易所
- `bridge_netflow`
  - 用来判断资产是否在特定链上累积或流失
- `exchange_reserve_balance`
  - 用来判断交易所可售库存变化
- `protocol_tvl`
  - 用来判断协议吸引力和资金黏性
- `active_addresses`
  - 用来判断网络使用热度
- `fees_paid`
  - 用来判断链上手续费压力和真实使用强度，而不是只看交易笔数

## 运行方式

一次采集：

```bash
python -m data_layer.onchain_data.runner --mode once
```

只采指定来源：

```bash
python -m data_layer.onchain_data.runner --mode once --sources exchange_flow,bridge_netflow,protocol_tvl
```

只采指定实体：

```bash
python -m data_layer.onchain_data.runner --mode once --entities BTC,ETH,SOLANA,AAVE
```

常驻调度（BlockingScheduler，默认）：

```bash
python -m data_layer.onchain_data.runner --mode scheduler
```

常驻调度（AsyncIOScheduler，推荐与其他 async 组件共存时使用）：

```bash
python -m data_layer.onchain_data.runner --mode scheduler --async-scheduler
```

查看当前 latest bundle：

```bash
python -m data_layer.onchain_data.runner --print-context
```

`--print-context` 现在会同时回答：

- 当前 bundle 覆盖了多少目标实体、多少目标因子
- 哪些实体完全没进来，哪些实体还缺关键链上字段
- latest 快照里是否混入 `partial / fallback / stale / unknown`
- 哪些 source 还没有达到 `ready`

这里的“实体”现在严格按 `(entity_type, entity_key)` 计算，而不是只看 `entity_key`。

这很重要，因为：

- `asset:SUI` 和 `chain:SUI` 是两个不同观察对象
- `missing_entity_keys`
  - 只是给人快速扫一眼的扁平 key 列表
- `missing_entities`
  - 才是 AI 和运维应优先读取的精确缺口字段，能区分同名但不同实体类型的覆盖缺失

bundle 里最值得 AI 先看的字段：

- `coverage_summary`
- `configured_universe_summary`
- `latest_quality_flag_breakdown`
- `latest_quality_ready_ratio`
- `data_quality_flags`
- `quality_notes`
- `source_health`

`configured_universe_summary.scope_kind` 现在不再只看 `entity_keys`。如果调用 bundle 时通过 `factor_ids` 把链上观察宇宙缩小到了局部 source 子集，也会被标成 `filtered`，避免把查询范围误读成默认链上宇宙本身过窄。

其中 `data_quality_flags` 会重点提示：

- `onchain_entity_coverage_incomplete`
- `onchain_factor_coverage_incomplete`
- `onchain_partial_present / onchain_fallback_present / onchain_stale_present`
- `onchain_source_not_ready_for_ai_present`
- `onchain_configured_market_breadth_limited`
- `exchange_flow_missing_for_*_entities`
- `whale_activity_missing_for_*_entities`
- `stablecoin_flow_missing_for_*_entities`
- `bridge_flow_missing_for_*_entities`
- `exchange_reserve_missing_for_*_entities`
- `protocol_tvl_missing_for_*_entities`
- `network_usage_missing_for_*_entities`
- `staking_flow_missing_for_*_entities`

查看 source 覆盖和最近采集情况：

```bash
python -m data_layer.onchain_data.runner --print-coverage
```

`--print-coverage` 里的关键字段：

- `configuration_ready`
  - source 是否已经配置好上游 endpoint
- `expected_entity_count / expected_factor_count`
  - 当前过滤条件下理论上应覆盖多少链上实体身份和因子
- `expected_point_count`
  - 当前过滤条件下理论上应覆盖多少 `entity x factor` 最新点位
- `latest_entity_count / latest_factor_count / latest_point_count`
  - 当前过滤条件下实际拿到了多少最新快照
- `health_status`
  - `ready / stale / error / empty / missing / unconfigured / disabled`
- `is_ready_for_ai`
  - 当前是否适合作为 AI 的链上背景输入
  - `health_status=ready` 只表示最近任务成功且 source 没有整体过期，不代表链上矩阵已经足够完整
  - 当前实现要求 source 至少满足：目标实体、目标因子、目标点位矩阵没有缺口，且 latest 快照中不含 `partial / fallback / stale / unknown`
- `latest_quality_flag_breakdown`
  - 最新快照里的 `ok / partial / fallback / stale / unknown` 分布
- `latest_quality_ready_ratio`
  - 最新快照中 `ok` 样本占比
- `data_quality_flags`
  - source 级质量缺陷，例如 `entity_coverage_incomplete / factor_coverage_incomplete / point_coverage_incomplete / fallback_points_present`
- `ready_for_ai_source_count / not_ready_for_ai_source_count`
  - 当前 coverage 里有多少 source 已经达到 AI 可直接消费门槛，以及还有多少没有达到

需要特别注意：

- `unconfigured` 代表 source 已启用但还没有配置 URL，不应该误解为链上没有变化
- `empty` 才代表这轮执行成功但没有取到值
- 如果传了 `factor_ids / entity_keys`，coverage 统计会严格按这些过滤条件重算
- `expected_entity_count / latest_entity_count`
  - 也是按 `(entity_type, entity_key)` 统计，不会再把 `asset:SUI` 和 `chain:SUI` 混成同一个实体
- `load_latest_context_bundle().coverage_summary`
  - 现在也会补充 `ready_for_ai_source_count / not_ready_for_ai_source_count / coverage_by_source`
  - 让 AI 能直接看清是哪一路链上 source 还没达到可用门槛，而不是只知道总体 coverage 不完整
- 覆盖率检查优先用来判断“链上证据是否缺口过大”，而不是直接做交易方向判断
- `load_latest_context_bundle()`
  - 更适合直接给 AI 读取当前链上上下文
- `load_source_coverage()`
  - 更适合运维和排障，定位到底是哪条 source 还不健康

## 环境变量

- `ONCHAIN_EXCHANGE_FLOW_URL`
- `ONCHAIN_WHALE_ACTIVITY_URL`
- `ONCHAIN_STABLECOIN_FLOW_URL`
- `ONCHAIN_BRIDGE_NETFLOW_URL`
- `ONCHAIN_EXCHANGE_RESERVE_URL`
- `ONCHAIN_PROTOCOL_TVL_URL`
- `ONCHAIN_NETWORK_USAGE_URL`
- `ONCHAIN_STAKING_FLOW_URL`
- `ONCHAIN_ASSET_ENTITY_KEYS`
- `ONCHAIN_STABLECOIN_ENTITY_KEYS`
- `ONCHAIN_CHAIN_ENTITY_KEYS`
- `ONCHAIN_PROTOCOL_ENTITY_KEYS`
- `ONCHAIN_EXTRA_ENTITIES_JSON`
- `ONCHAIN_DEFAULT_INTERVAL`
- `ONCHAIN_DEFAULT_LOOKBACK_HOURS`

## 维护约束

- 采集层不做链上行为解释，只保存原始数值、维度、来源和质量标记。
- 后续切换供应商时，优先保持标准化 JSON 协议不变。
- `protocol`、`chain`、`asset` 是三种不同实体范围，后续扩展不要混用同一 factor 语义。
- bundle / coverage 里的实体覆盖统计必须继续按 `(entity_type, entity_key)` 维护，不能退回到只按 `entity_key` 去重。
- `network_usage` 当前真实因子名是 `active_addresses / transaction_count / fees_paid`，后续不要再写成旧文档里的 `fee_burned_usd`。

### 2026-05-28 免费 API 直接采集接入

本轮为 3 个子模块接入了 DeFiLlama 免费公开 API，不再依赖环境变量配置的外部 URL：

- `protocol_tvl/collector.py` — 重写
  - 数据源：`https://api.llama.fi/protocols`
  - 协议映射：aave / uniswap / jupiter / cetus-amm / lido / maker / compound-v3 / curve-dex
  - 输出：protocol_tvl, protocol_tvl_change_24h, protocol_tvl_change_7d
- `network_usage/collector.py` — 重写
  - 数据源：`https://api.llama.fi/overview/fees`
  - 链映射：ethereum / solana / arbitrum / base / sui / bitcoin
  - 当前输出：fees_paid（active_addresses / transaction_count 需 Etherscan，暂未接入）
  - quality_flag：partial（仅覆盖 fees_paid）
- `bridge_netflow/collector.py` — 重写
  - 数据源：`https://bridges.llama.fi/bridgevolume/{chain}`
  - 输出：bridge_inflow, bridge_outflow, bridge_netflow

所有三个 collector 均无需 API key，无频率限制。
