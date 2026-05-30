# circulating_supply

## 当前职责

- 采集 `circulating_supply`
- 采集 `float_supply`
- 采集 `inflation_rate_annualized`

## 目标

让 AI 判断供给基线和年化增发压力。

## 当前实现

- 数据源：CoinGecko `https://api.coingecko.com/api/v3/coins/{coin_id}`（免费，30 calls/min）
- 实体映射：BTC→bitcoin, ETH→ethereum, SOL→solana, SUI→sui, ARB→arbitrum, OP→optimism, AVAX→avalanche-2, MATIC→matic-network, LINK→chainlink, UNI→uniswap, AAVE→aave, MKR→maker, CRV→curve-dao-token, JUP→jupiter-exchange-solana 等（共 18 个）
- 输出因子：`circulating_supply`（流通供应量）、`float_supply`（circulating/total 比率）
- inflation_rate_annualized：需历史数据对比，当前标记为 `partial`
- 频率限制：每次请求间隔 2.5s（遵守 CoinGecko 免费 tier 30 calls/min）
- quality_flag：正常返回为 `ok`
