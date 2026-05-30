# network_usage

## 当前职责

- 采集 `active_addresses`
- 采集 `transaction_count`
- 采集 `fees_paid`

## 目标

让 AI 看见链上真实使用强度，而不是只看价格。

## 当前实现

- 数据源：DeFiLlama `https://api.llama.fi/overview/fees`（免费，无需 API key）
- 链映射：`ethereum→ETHEREUM, solana→SOLANA, arbitrum→ARBITRUM, base→BASE, sui→SUI, bitcoin→BITCOIN`
- 当前覆盖因子：`fees_paid`（24h 链级手续费，USD）
- 未覆盖因子：`active_addresses`、`transaction_count`（需 Etherscan 类 API，免费 tier 5 calls/s，暂未接入）
- quality_flag：仅有 fees_paid 时为 `partial`
- 频率限制：无（DeFiLlama 免费无限制）
