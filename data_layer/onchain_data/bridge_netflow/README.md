# bridge_netflow

## 当前职责

- 采集 `bridge_inflow`
- 采集 `bridge_outflow`
- 采集 `bridge_netflow`

## 目标

让 AI 看见资金是否真正跨链迁移。

## 当前实现

- 数据源：DeFiLlama Bridges `https://bridges.llama.fi/bridgevolume/{chain}`（免费，无需 API key）
- 链映射：`Ethereum→ETHEREUM, Solana→SOLANA, Arbitrum→ARBITRUM, Base→BASE, Sui→SUI, Bitcoin→BITCOIN`
- 输出因子：`bridge_inflow`（跨链流入 USD）、`bridge_outflow`（跨链流出 USD）、`bridge_netflow`（净流入 = inflow - outflow）
- 时间窗口：取最近 24h 的桥流量数据
- 频率限制：无（DeFiLlama 免费无限制）
- quality_flag：正常返回为 `ok`
