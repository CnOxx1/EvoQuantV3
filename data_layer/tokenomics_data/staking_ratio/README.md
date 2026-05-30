# staking_ratio

## 当前职责

- 采集 `staking_ratio`
- 采集 `staking_ratio_change_7d`

## 目标

让 AI 判断可流通筹码约束和长期锁仓强度。

## 当前实现

- 数据源：CoinGecko `https://api.coingecko.com/api/v3/coins/{coin_id}` + 内置已知比例表
- 实现方式：优先从 CoinGecko 获取，若无 staking 数据则使用 `KNOWN_STAKING_RATIOS` 静态映射
- KNOWN_STAKING_RATIOS 覆盖：ETH≈28%, SOL≈67%, SUI≈79%, AVAX≈56%, MATIC≈38%, ATOM≈63%, DOT≈53%
- quality_flag：CoinGecko 实时数据为 `ok`，静态映射为 `fallback`
- staking_ratio_change_7d：当前未覆盖（需历史对比），暂不输出
- 频率限制：每次请求间隔 2.5s（CoinGecko 免费 tier）
