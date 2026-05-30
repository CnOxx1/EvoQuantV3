# protocol_tvl

## 当前职责

- 采集 `protocol_tvl`
- 采集 `protocol_tvl_change_24h`
- 采集 `protocol_tvl_change_7d`

## 目标

让 AI 判断生态资金是否在回流协议层。

## 当前实现

- 数据源：DeFiLlama `https://api.llama.fi/protocols`（免费，无需 API key）
- 协议映射：`aave→AAVE, uniswap→UNISWAP, jupiter→JUPITER, cetus-amm→CETUS, lido→LIDO, maker→MAKER, compound-v3→COMPOUND, curve-dex→CURVE`
- 输出因子：`protocol_tvl`（当前 TVL）、`protocol_tvl_change_24h`（24h 变化率）、`protocol_tvl_change_7d`（7d 变化率）
- 频率限制：无（DeFiLlama 免费无限制）
- quality_flag：正常返回为 `ok`，change 字段缺失时为 `partial`
