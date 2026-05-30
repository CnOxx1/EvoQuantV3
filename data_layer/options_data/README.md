# options_data 模块

`options_data` 只负责一件事：把期权市场里最能帮助 AI 判断未来波动预期、dealer 对冲状态、尾部保护需求和持仓拥挤度的数据，标准化成稳定因子并落库。

它不负责策略，不负责下单，也不负责解释这些因子该怎么交易。

当前 `is_ready_for_ai` 的质量门槛已经与 `data_layer/data_quality` 对齐：latest 快照默认必须至少有 `ok` 样本，且不能混入 `partial / fallback / stale / unknown`，然后再叠加期权模块自己的实体、因子和推荐 venue 完整性约束。

当前 `load_latest_context_bundle()` 还会额外输出 `configured_universe_summary`，专门回答一个数据层问题：

- 当前期权模块覆盖的是“核心执行资产视角”
- 还是已经足够支撑更广的市场 breadth 判断

它不会补任何假资产数据，只会诚实描述当前配置宇宙本身有多宽。

同时，`load_latest_context_bundle()` 现在已经明确区分：

- AI 直接消费视图
  - 只保留 `is_ready_for_ai=True` 的真实 source，并把它们体现在 `row_count / entity_count / source_counts / leaders / sources / latest_quality_*`
- 原始真实诊断视图
  - 所有真实已落库但暂未达到 AI-ready 门槛的 source，统一保留在 `raw_as_of / raw_row_count / raw_entity_count / raw_source_counts / raw_latest_quality_* / ai_excluded_sources`

这意味着模块不会为了让 AI 看起来“数据更全”而把不达标的期权快照继续混进主视图，也不会伪造任何缺失资产或缺失 venue 的数据。

## 快速导航

- [当前目标](#当前目标)
- [当前目录](#当前目录)
- [当前因子](#当前因子)
- [上游标准化 payload 约定](#上游标准化-payload-约定)
- [数据库存储](#数据库存储)
- [CLI](#cli)
- [质量约束](#质量约束)
- [维护建议](#维护建议)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 目标 | 给 AI 提供波动预期、墙位、gamma、flow、expiry 与对冲压力证据 |
| 默认资产 | `BTC / ETH / SOL / SUI` |
| source 数量 | `vol_surface / relative_value / strike_concentration / gamma_exposure / flow_activity / expiry_structure / hedge_pressure / positioning` |
| 核心输出 | `options_*` 系列表与 `load_latest_context_bundle()` |
| 直接用途 | 识别事件风险重定价、dealer gamma regime、期权拥挤与对冲压力 |
| 质量原则 | AI 主视图只保留达标 source，真实但未达标样本保留在 `raw_*` 诊断字段 |

## AI 文档维护约束

后续如果有 AI 修改下面任一内容，必须同步更新当前 README：

- 目录结构、collector 划分或新增/删除源码文件
- 上游标准化 payload 约定
- 当前 factor 清单、字段语义、计算公式或默认调度频率
- `options_*` 三张数据库表的写入语义
- `--print-context / --print-coverage` 的输出结构

## 当前目标

当前模块优先补齐八类证据：

- `vol_surface`
  - 给 AI 提供市场对未来波动的定价
  - 包括短端/中端 ATM IV、term structure、skew、butterfly
- `relative_value`
  - 给 AI 提供隐含波动率相对真实波动的贵/便宜程度
  - 包括 realized vol 和 IV-RV spread
- `strike_concentration`
  - 给 AI 提供行权价墙位、max pain 和 pinning 风险
  - 包括 wall distance、top strike concentration、ATM strike concentration
- `gamma_exposure`
  - 给 AI 提供 dealer gamma regime、gamma flip 和 gamma wall 证据
  - 包括 net gamma、gamma flip distance、call/put gamma wall distance、gamma concentration
- `flow_activity`
  - 给 AI 提供期权增量成交、开仓意图和 block flow 证据
  - 包括 call/put buyer premium share、net call/put premium flow、opening flow、near expiry flow、block flow
- `expiry_structure`
  - 给 AI 提供按到期桶拆分的 OI、gamma 和 premium flow 分布
  - 包括 `7d / 30d / 90d+` OI share、`7d / 30d` gamma share、`7d / 30d` premium flow share
- `hedge_pressure`
  - 给 AI 提供 dealer 动态对冲压力证据
  - 包括 vanna、charm、volga、vomma、color、vanna/charm flip distance、near expiry charm/color share
- `positioning`
  - 给 AI 提供期权持仓结构与到期拥挤度
  - 包括 put/call OI ratio、call OI share、总 OI notional、近到期集中度

这些 source 合起来，解决的是现货/永续数据无法回答的几个问题：

- 市场是否在给未来短期事件风险重新定价
- 市场保护需求更偏向下行还是上行
- 当前价格附近是否存在明确的期权墙位和 pinning 风险
- 当前更接近 `long gamma` 还是 `short gamma`，以及离 `gamma flip` 有多近
- 今天的期权 tape 更偏向追涨 call、买保护 put，还是以平仓/换仓为主
- 风险究竟堆在 `7d` 事件窗、`30d` 月度窗，还是更长端的 back-end
- 波动率变化和时间流逝是否会把 dealer 的被动对冲推向同一方向
- 波动率凸性冲击和 gamma 的时间衰减会不会触发 dealer 二次被动对冲放大
- 期权 OI 是否在单一到期点过度拥挤
- 当前期权仓位是否集中在近到期，导致 gamma/roll 风险放大

当前默认目标资产宇宙与交易所层保持一致：

- `BTC`
- `ETH`
- `SOL`
- `SUI`

默认值来自 `OPTIONS_ASSET_ENTITY_KEYS`，如果后续要扩大或缩小期权覆盖范围，应优先改这个注册表入口，而不是在 collector 里写死例外逻辑。

## 当前目录

```text
data_layer/options_data/
  README.md
  __init__.py
  base.py
  client.py
  deribit_client.py
  models.py
  runner.py
  service.py
  sources.py
  vol_surface/
    README.md
    __init__.py
    collector.py
  relative_value/
    README.md
    __init__.py
    collector.py
  strike_concentration/
    README.md
    __init__.py
    collector.py
  gamma_exposure/
    README.md
    __init__.py
    collector.py
  flow_activity/
    README.md
    __init__.py
    collector.py
  expiry_structure/
    README.md
    __init__.py
    collector.py
  hedge_pressure/
    README.md
    __init__.py
    collector.py
  positioning/
    README.md
    __init__.py
    collector.py
```

## 当前因子

`vol_surface`

- `options_atm_iv_7d`
- `options_atm_iv_30d`
- `options_iv_term_structure_7d_30d`
- `options_25d_risk_reversal_30d`
- `options_25d_butterfly_30d`

`relative_value`

- `options_realized_vol_7d`
- `options_realized_vol_30d`
- `options_iv_rv_spread_7d`
- `options_iv_rv_spread_30d`

`strike_concentration`

- `options_max_pain_distance_pct`
- `options_call_wall_distance_pct`
- `options_put_wall_distance_pct`
- `options_top_strike_oi_share`
- `options_near_expiry_top_strike_oi_share`
- `options_atm_strike_oi_share`

`gamma_exposure`

- `options_net_gamma_exposure`
- `options_net_gamma_exposure_ratio`
- `options_gamma_flip_distance_pct`
- `options_call_gamma_wall_distance_pct`
- `options_put_gamma_wall_distance_pct`
- `options_top_gamma_strike_share`
- `options_near_expiry_gamma_share`

`flow_activity`

- `options_call_buyer_premium_share`
- `options_put_buyer_premium_share`
- `options_net_call_premium_flow_ratio`
- `options_net_put_premium_flow_ratio`
- `options_opening_flow_share`
- `options_near_expiry_flow_share`
- `options_block_trade_flow_share`

`expiry_structure`

- `options_oi_share_7d`
- `options_oi_share_30d`
- `options_oi_share_90d_plus`
- `options_gamma_share_7d`
- `options_gamma_share_30d`
- `options_premium_flow_share_7d`
- `options_premium_flow_share_30d`

`hedge_pressure`

- `options_vanna_exposure`
- `options_vanna_exposure_ratio`
- `options_charm_exposure`
- `options_charm_exposure_ratio`
- `options_vanna_flip_distance_pct`
- `options_charm_flip_distance_pct`
- `options_near_expiry_charm_share`
- `options_volga_exposure`
- `options_volga_exposure_ratio`
- `options_vomma_exposure`
- `options_vomma_exposure_ratio`
- `options_color_exposure`
- `options_color_exposure_ratio`
- `options_near_expiry_color_share`

`positioning`

- `options_put_call_oi_ratio_30d`
- `options_call_oi_share_30d`
- `options_total_oi_notional_30d`
- `options_near_expiry_oi_share`
- `options_largest_expiry_oi_share`

## 上游标准化 payload 约定

当前模块故意不把代码耦合到某一家期权交易所 API，而是要求上游先输出“标准化期权快照”。

### `vol_surface`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "terms": [
    {"tenor": "7d", "atm_iv": 0.62},
    {"tenor": "30d", "atm_iv": 0.58, "risk_reversal_25d": -0.03, "butterfly_25d": 0.012}
  ]
}
```

### `relative_value`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "realized_vol_7d": 0.49,
  "realized_vol_30d": 0.52,
  "atm_iv_7d": 0.62,
  "atm_iv_30d": 0.58
}
```

### `strike_concentration`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "spot_price": 100000.0,
  "max_pain_price": 98500.0,
  "largest_call_wall_strike": 105000.0,
  "largest_put_wall_strike": 96000.0,
  "total_open_interest_notional": 3100000000.0,
  "top_strike_open_interest_notional": 775000000.0,
  "near_expiry_total_open_interest_notional": 900000000.0,
  "near_expiry_top_strike_open_interest_notional": 315000000.0,
  "atm_band_open_interest_notional": 1302000000.0
}
```

### `gamma_exposure`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "spot_price": 100000.0,
  "net_gamma_exposure": 45000000.0,
  "gross_gamma_exposure": 120000000.0,
  "gamma_flip_price": 99200.0,
  "call_gamma_wall_strike": 103000.0,
  "put_gamma_wall_strike": 97000.0,
  "top_gamma_strike_exposure": 36000000.0,
  "near_expiry_gamma_exposure": 66000000.0
}
```

### `flow_activity`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "total_premium_notional": 120000000.0,
  "call_buyer_initiated_premium": 42000000.0,
  "put_buyer_initiated_premium": 18000000.0,
  "call_seller_initiated_premium": 12000000.0,
  "put_seller_initiated_premium": 9000000.0,
  "opening_premium_notional": 78000000.0,
  "near_expiry_premium_notional": 66000000.0,
  "block_trade_premium_notional": 24000000.0
}
```

### `expiry_structure`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "total_open_interest_notional": 3200000000.0,
  "gross_gamma_exposure": 120000000.0,
  "total_premium_notional": 120000000.0,
  "expiry_buckets": [
    {"bucket": "7d", "open_interest_notional": 960000000.0, "gamma_exposure": 60000000.0, "premium_notional": 54000000.0},
    {"bucket": "30d", "open_interest_notional": 1120000000.0, "gamma_exposure": 36000000.0, "premium_notional": 40800000.0},
    {"bucket": "90d_plus", "open_interest_notional": 480000000.0, "gamma_exposure": 12000000.0, "premium_notional": 9600000.0}
  ]
}
```

### `hedge_pressure`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "spot_price": 100000.0,
  "gross_gamma_exposure": 120000000.0,
  "total_charm_exposure": 30000000.0,
  "total_color_exposure": 18000000.0,
  "vanna_exposure": 18000000.0,
  "charm_exposure": -9000000.0,
  "volga_exposure": 10800000.0,
  "vomma_exposure": 13200000.0,
  "color_exposure": -7200000.0,
  "vanna_flip_price": 101500.0,
  "charm_flip_price": 98800.0,
  "near_expiry_charm_exposure": 21000000.0,
  "near_expiry_color_exposure": 12600000.0
}
```

如果上游已经稳定产出 `volga_exposure_ratio / vomma_exposure_ratio / color_exposure_ratio / near_expiry_color_share`，也可以直接透传；当前 collector 会优先读取显式字段，不存在时再回退到标准化公式推导。

### `positioning`

最小建议字段：

```json
{
  "entity_key": "BTC",
  "observation_time": "2026-05-08T08:00:00+00:00",
  "interval": "1h",
  "quality_flag": "ok",
  "call_open_interest_notional_30d": 1400000000,
  "put_open_interest_notional_30d": 1050000000,
  "total_open_interest_notional_30d": 2450000000,
  "total_open_interest_notional_all": 3100000000,
  "near_expiry_open_interest_notional": 550000000,
  "largest_expiry_open_interest_notional": 950000000
}
```

## 数据库存储

当前模块统一写入三张表：

- `options_factor_catalog`
- `options_timeseries`
- `latest_options_timeseries`

其中：

- `options_timeseries` 保存历史
- `latest_options_timeseries` 保存每个 `factor + entity + interval + dimensions` 的当前最新快照
- `options_factor_catalog` 保存因子目录和新鲜度语义

## CLI

列出注册表：

```bash
python -m data_layer.options_data.runner --list-sources
python -m data_layer.options_data.runner --list-factors
python -m data_layer.options_data.runner --list-entities
```

执行一次采集：

```bash
python -m data_layer.options_data.runner --mode once
python -m data_layer.options_data.runner --mode once --sources vol_surface --entities BTC
```

输出 AI 可直接消费的上下文：

```bash
python -m data_layer.options_data.runner --print-context
```

检查质量与覆盖率：

```bash
python -m data_layer.options_data.runner --print-coverage
```

## 质量约束

当前模块不是“拿到一点期权数据就算完成”，而是明确要求能回答下面几件事：

- 是否真的覆盖了目标资产集合，而不是只有 BTC
- 是否真的覆盖了设计内的全部关键 factor，而不是只落了一个 ATM IV
- 是否真的覆盖了 `IV vs RV` 这类定价相对值证据，而不是只有绝对 IV 水平
- 是否真的覆盖了 `wall / max pain / strike crowding`，而不是没有任何 pinning 风险证据
- 是否真的覆盖了 `net gamma / gamma flip / gamma wall`，而不是看不到 dealer 对冲状态
- 是否真的覆盖了 `incremental options flow`，而不是完全看不到当日新增仓位和保护需求
- 是否真的覆盖了 `expiry bucket structure`，而不是不知道风险堆在短端还是长端
- 是否真的覆盖了 `vanna / charm / volga / vomma / color hedge pressure`，而不是完全看不到动态对冲会如何放大价格路径
- 最近一次采集是否成功
- 数据是否 stale
- source 是否只是 enabled，但其实还没配 endpoint

这些状态统一由 `load_source_coverage()` 输出，字段与其他数据模块保持一致：

- `configuration_ready`
- `expected_entity_count`
- `expected_factor_count`
- `latest_entity_count`
- `latest_factor_count`
- `latest_point_count`
- `last_run_status`
- `health_status`
- `is_ready_for_ai`
- `recommended_venues / observed_venues / missing_recommended_venues`
- `recommended_venue_count / observed_venue_count / venue_coverage_ratio`
- `is_venue_coverage_complete`
- `latest_quality_flag_breakdown`
- `latest_quality_ready_ratio`

这里需要特别注意：

- `health_status=ready` 只表示这个 source 最近成功落到了最新快照，且没有 stale / error / unconfigured 问题
- `is_ready_for_ai=True` 还额外要求：
  - 如果 source 配置了推荐 venue，那么当前 latest 样本里必须能识别并覆盖这些推荐 venue
  - latest 里不能混入 `partial / fallback / stale / unknown`
  - source 的实体覆盖和 factor 覆盖不能低于当前过滤后的设计目标
- 也就是说，`source` 可以在运行层面是 `ready`，但仍然因为 venue 覆盖不完整、latest 样本质量不足，或结构覆盖不完整而 `is_ready_for_ai=False`

如果传了 `factor_ids / entity_keys / source_names`，这些统计会严格按过滤后的子集重算，而不是继续显示全量资产 / 全量因子的 coverage。

在 source coverage 之外，`load_latest_context_bundle()` 现在还会额外输出：

- `coverage_summary`
  - `expected_entity_count / observed_entity_count / expected_factor_count / observed_factor_count / missing_entity_keys / missing_factor_ids`
- `latest_quality_flag_breakdown`
  - latest 快照里 `ok / partial / fallback / stale / unknown` 的数量
- `latest_quality_ready_ratio`
  - 当前 latest 快照里真正 `ok` 的比例
- `source_health_summary`
  - 当前 ready/problem/stale source 数量
  - 以及 `ready_for_ai_source_count / not_ready_for_ai_source_count`
- `source_health`
  - 每个 source 的 `expected_entity_count / latest_entity_count / expected_factor_count / latest_factor_count / latest_quality_ready_ratio`
  - 以及 `recommended_venues / observed_venues / missing_recommended_venues / is_venue_coverage_complete / data_quality_flags`
- `venue_coverage_summary`
  - 聚合输出各个 source 的 venue 覆盖情况
  - 当前会给出 `complete_source_count / partial_source_count / missing_identity_source_count / observed_venues / coverage_by_source`
- `configured_universe_summary`
  - 当前默认资产宇宙到底有多宽，以及它更适合做“执行资产判断”还是更广的市场 breadth 判断
  - 当前会给出 `scope_kind / tracked_entity_keys / asset_entity_count / minimum_asset_entity_count_for_market_breadth / breadth_status`
  - 如果调用时通过 `entity_keys / factor_ids`，或通过 `source_names` 把默认 source 宇宙真实缩小成子集，`scope_kind` 会降为 `filtered`，避免把查询子集误判成默认宇宙缺失
  - 如果显式传入的 `source_names` 实际上等于完整默认 source 集合，`scope_kind` 仍保持 `default`
- `data_quality_flags / quality_notes`
  - 如果当前只覆盖了部分目标资产，bundle 会显式标记 `options_entity_coverage_incomplete`
  - 如果部分 source 只看到了部分推荐 venue，bundle 会显式标记 `options_recommended_venue_coverage_incomplete`
  - 如果部分 source 虽然最近运行成功，但 latest 样本质量或结构覆盖还不适合直接给 AI 用，bundle 会显式标记 `options_source_not_ready_for_ai_present`
  - 如果默认资产宇宙本身仍偏窄，bundle 会显式标记 `options_configured_market_breadth_limited`
  - 如果 latest 样本里出现 `partial / fallback / stale / unknown`，bundle 也会直接向上暴露，不再只停留在原始表层

## 维护建议

- 如果后续要继续增强这个模块，优先扩的是“标准化 payload 的真实覆盖面”，不是在这里提前写交易逻辑。
- 真正有价值的下一步通常是：
  - 补更多资产
  - 增加更细粒度的 expiry bucket，例如 `0dte / 3d / 7d / 14d / 30d / quarter`
  - 在 `hedge_pressure` 上继续补按 expiry bucket 拆开的 `vanna / volga / color`，特别是 `0dte / 7d` 事件窗

### 2026-05-15 本地验证记录

本轮围绕 venue 覆盖语义完成了下面这些本地验证：

- `python -m py_compile data_layer/options_data/service.py tests/options_data/test_options_module.py`
  - 通过
- `pytest -q tests/options_data/test_options_module.py`
  - `8 passed`

这轮验证说明：

- `load_source_coverage()` 现在已经能从 latest 真实 payload 里提取 `observed_venues`
- `is_ready_for_ai` 不再只看任务是否成功，也会同时检查推荐 venue、latest 样本质量、以及实体/因子覆盖是否真的达标
- `load_latest_context_bundle()` 已新增 `venue_coverage_summary`，AI 可以直接识别哪些期权 source 仍然只覆盖了部分 venue

### 2026-05-28 Deribit 公开 API 接入

新增 `deribit_client.py`，作为期权数据的免费公开数据源：

- Base URL: `https://www.deribit.com/api/v2/public`（无需认证）
- 覆盖资产：BTC、ETH（Deribit 公开 API 仅支持这两个）
- 频率限制：20 requests/s（远超当前需求）

`OptionsDataClient`（`client.py`）已改造为 Deribit fallback 模式：

- 当原有 endpoint 未配置或返回空数据时，自动回退到 Deribit 公开 API
- 所有 8 个 source 的 `fetch_*_snapshots()` 方法均已支持 Deribit fallback
- Deribit 返回数据会被转换为与原有 payload 格式一致的标准化快照
- SOL/SUI 等 Deribit 不覆盖的资产不会生成 fallback 数据

关键端点：

- `get_book_summary_by_currency?currency={}&kind=option` — OI、IV、Greeks
- `get_index_price?index_name={}_usd` — 现货参考价
- `get_historical_volatility?currency={}` — 历史波动率
- `get_instruments?currency={}&kind=option` — 期权合约列表

Deribit fallback 生成的快照 `quality_flag` 为 `ok`（数据完整度与付费源一致）。
