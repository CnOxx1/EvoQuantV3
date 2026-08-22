# 数据底座专用运行报告

**运行范围：** 仅执行 `scripts/run_public_data_layer.py` 的 17 个免费公开采集器，以及数据底座质量验证脚本。未执行 `logic_layer`、策略、信号、回测、组合、风险或交易模块。

> 采集结果：`{'collectors': 17, 'failed': []}`。
>
> 状态目录：**25 active / 0 empty / 0 disabled / 0 error**。

| 数据域或主表 | 本机验证后记录量 | 说明 |
|---|---:|---|
| `okx_market_candle_history_raw` | 8,640 | BTC/ETH 现货与永续 90 日 1 小时原始 K 线历史。 |
| `okx_funding_history_raw` | 540 | BTC/ETH 永续 90 日 OKX 资金费率历史。 |
| `deribit_funding_history_raw` | 4,320 | BTC/ETH 永续 90 日 Deribit 小时资金费率历史。 |
| `okx_derivatives_raw` | 208 | OI、清算、基差与公开资金费率原始窗口。 |
| `public_exchange_quote_snapshots` | 16 | Kraken 与 Coinbase BTC/USD、ETH/USD 报价快照。 |
| `asset_metadata_snapshots` | 250 | CoinGecko 资产元数据和供应快照。 |
| `bitcoin_onchain_history` | 1,070 | Bitcoin 公开日频交易、活跃地址、手续费事实。 |
| `ethereum_network_snapshots` | 3 | Ethereum 公开交易、区块与手续费网络快照。 |
| `stablecoin_chain_flows` | 1,399 | 免费公开稳定币供应和链分布快照/历史。 |

连续性审计显示三个新增市场/衍生品历史集均无间隔缺口。Bitcoin 历史仍有 4 个由公开上游省略日期引起的缺口；重试后已在 `data_backfill_tasks` 标为 `source_omission`，没有填零或插值。

数据底座回归测试已执行：状态目录测试与覆盖审计测试共 6 项通过。
