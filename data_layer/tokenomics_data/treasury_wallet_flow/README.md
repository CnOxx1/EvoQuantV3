# treasury_wallet_flow

## 当前职责

- 采集 `treasury_wallet_inflow`
- 采集 `treasury_wallet_outflow`
- 采集 `foundation_wallet_netflow`

## 目标

让 AI 感知基金会、国库、多签或官方钱包的真实抛压/回流。

## 维护约束

- 这里只能接真实钱包组口径的数据，不能伪造地址集合。
- `registry/treasury_wallet_groups.json` 现在不仅是说明文档，也是质量门槛的一部分。
- 如果某个资产的钱包组仍然只是 placeholder，或者没有可核验地址数量、来源引用，`treasury_wallet_flow` 仍可落库，但不能被标成 `is_ready_for_ai=true`。
- 如果钱包组 registry 还没达到 AI-ready 门槛，`load_latest_context_bundle()` 现在还会把这一路 source 从 AI 直接消费的 tokenomics 视图里排除，只在 `source_health / coverage_summary / ai_excluded_sources / raw_*` 诊断字段里保留。
- 这里收紧的是“钱包组定义是否可信”，不是补值逻辑；如果上游没有真实钱包流向，就保持缺失，不做推断。
