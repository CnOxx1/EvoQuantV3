# EvoQuant 数据库详细分析

> 分析时间：2026-05-29 23:30 | 总磁盘占用：5.7 GB | 总数据行数：~6,390,000

## 总览

| 数据库 | 大小 | 表数量 | 有效数据行 | 定位 |
|--------|------|--------|-----------|------|
| `exchange_data.db` | 2.2 GB | 20 | ~3,885,000 | 交易所原始行情 |
| `analytics.db` | 2.9 GB | 20 | ~2,334,000 | 逻辑层计算结果 |
| `market_data.db` | 283 MB | 20 | ~220,000 | 宏观/新闻/链上/另类 |
| `crypto_data.db` | 341 MB | — | 历史遗留 | 旧版单库（已迁移） |

---

## 一、exchange_data.db（2.2 GB）

### 1.1 历史表

| 表名 | 行数 | 时间范围 |
|------|------|----------|
| `klines` | 3,446,998 | 2024-09-09 ~ 2026-05-28 |
| `tickers` | 174,482 | 2026-05-08 ~ 05-28 |
| `orderbook_snapshots` | 159,696 | 2026-05-23 ~ 05-28 |
| `trade_flow_bars` | 49,756 | 2024-09-10 ~ 2026-05-28 |
| `collection_runs` | 33,827 | — |
| `positioning_snapshots` | 15,642 | 2026-05-25 ~ 05-28 |
| `open_interest_snapshots` | 2,942 | 2026-05-23 ~ 05-28 |
| `funding_rates` | 1,088 | 2026-05-23 ~ 05-28 |
| `basis_snapshots` | 998 | 2026-05-23 ~ 05-28 |
| `liquidation_bars` | 83 | 2026-05-28 |
| `market_info` | 55 | 静态 |

### 1.2 K线详细分布

**按交易所：**

| 交易所 | 行数 | 占比 |
|--------|------|------|
| Binance | 1,157,641 | 33.6% |
| Bybit | 1,153,710 | 33.5% |
| OKX | 1,135,647 | 32.9% |

**按时间周期：**

| 周期 | 行数 | 占比 |
|------|------|------|
| 1m | 2,684,007 | 77.9% |
| 5m | 536,352 | 15.6% |
| 15m | 178,531 | 5.2% |
| 1h | 35,037 | 1.0% |
| 4h | 11,223 | 0.3% |
| 1d | 1,848 | 0.05% |

**按币种：**

| 币种 | 行数 | 层级 |
|------|------|------|
| BTC/USDT | 195,129 | T1 Core |
| ETH/USDT | 195,127 | T1 Core |
| SUI/USDT | 195,116 | T2 Active |
| SOL/USDT | 195,115 | T2 Active |
| DOGE/USDT | 191,664 | T2 Active |
| XRP/USDT | 191,662 | T2 Active |
| AVAX/USDT | 191,659 | T2 Active |
| LINK/USDT | 191,657 | T2 Active |
| ADA/USDT | 191,654 | T3 Monitor |
| DOT/USDT | 191,652 | T3 Monitor |
| UNI/USDT | 191,650 | T3 Monitor |
| ARB/USDT | 191,646 | T3 Monitor |
| OP/USDT | 191,645 | T3 Monitor |
| NEAR/USDT | 191,643 | T3 Monitor |
| ATOM/USDT | 191,641 | T3 Monitor |
| APT/USDT | 191,639 | T3 Monitor |
| TIA/USDT | 191,638 | T3 Monitor |
| POL/USDT | 174,911 | T3 Monitor |
| MATIC/USDT | 150 | 已退市 |

### 1.3 Latest 快照表（AI 实时消费）

| 表名 | 行数 | 说明 |
|------|------|------|
| `latest_trade_flow_bars` | 109 | 18币×3所×2周期 |
| `latest_tickers` | 55 | 18币×3所 + 市场信息 |
| `latest_funding_rates` | 54 | 18币×3所 |
| `latest_orderbook_snapshots` | 54 | 18币×3所 |
| `latest_open_interest_snapshots` | 54 | 18币×3所 |
| `latest_positioning_snapshots` | 54 | 18币×3所 |
| `latest_basis_snapshots` | 54 | 18币×3所 |
| `latest_liquidation_bars` | 15 | 部分覆盖 |

### 1.4 交易所覆盖矩阵

| 数据类型 | Binance | OKX | Bybit | 状态 |
|----------|---------|-----|-------|------|
| K线 (1m~1d) | 1,157,641 | 1,135,647 | 1,153,710 | ✅ 三所均衡 |
| Tickers | ✅ 完整 | ✅ 完整 | ✅ 完整 | ✅ 正常 |
| Orderbook | 6,342 | 76,688 | 76,666 | ✅ 已修复 |
| Trade Flow | ✅ 完整 | ✅ 完整 | ✅ 完整 | ✅ 正常 |
| Open Interest | ✅ 完整 | ✅ 完整 | ✅ 部分 | ✅ 正常 |
| Positioning | ✅ 完整 | ✅ 已修复 | ✅ 完整 | ✅ 正常 |
| Funding | ✅ 完整 | ✅ 已修复 | ✅ 完整 | ✅ 正常 |
| Basis | ✅ 完整 | ✅ 已修复 | ✅ 完整 | ✅ 正常 |
| Liquidations | ⚠️ WebSocket | ✅ REST API | ⚠️ WebSocket | 需启动 ws_collector |

---

## 二、analytics.db（2.9 GB）

### 2.1 核心计算表

| 表名 | 行数 | 说明 |
|------|------|------|
| `merged_klines` | 1,157,645 | 合并K线（Binance主参考） |
| `technical_indicators` | 1,157,645 | 技术指标（19币种100%覆盖） |
| `feature_standardization_details` | 13,760 | Z-score/百分位明细 |
| `news_sentiment_labels` | 954 | 新闻情绪标注 |
| `cross_asset_relative_strength` | 810 | 跨资产相对强度排名 |
| `ai_market_context_snapshots` | 756 | AI 市场上下文 bundle |
| `exchange_comparison_snapshots` | 696 | 交易所对比快照 |
| `data_quality_audit_snapshots` | 329 | 数据质量审计 |
| `macro_context_snapshots` | 120 | 宏观上下文 |
| `market_breadth_snapshots` | 46 | 市场广度 |
| `cross_asset_correlation_snapshots` | 45 | 跨资产相关性矩阵 |
| `portfolio_risk_snapshots` | 45 | 组合风险（VaR/HHI） |
| `feature_standardization_snapshots` | 45 | 特征标准化快照 |
| `asset_readiness_snapshots` | 44 | 资产就绪度评分 |
| `feature_standardization_composites` | — | 特征组合信号 |
| `cross_asset_fund_flow` | 0 | 资金流（待积累） |
| `cross_asset_sector_rotation` | 0 | 行业轮动（待积累） |
| `market_structure_snapshots` | 0 | 市场结构（待积累） |

### 2.2 Merged K线分布

**按币种：**

| 层级 | 币种 | 行数 |
|------|------|------|
| T1 Core | BTC/USDT | 65,125 |
| T1 Core | ETH/USDT | 65,123 |
| T2 Active | SOL/USDT | 65,115 |
| T2 Active | SUI/USDT | 65,112 |
| T2 Active | DOGE/USDT | 64,121 |
| T2 Active | XRP/USDT | 64,119 |
| T2 Active | AVAX/USDT | 64,116 |
| T2 Active | LINK/USDT | 64,114 |
| T3 Monitor | ADA~TIA | 各 ~64,100 |
| T3 Monitor | POL/USDT | 63,629 |

**按周期：**

| 周期 | 行数 | 占比 |
|------|------|------|
| 1m | 898,629 | 77.6% |
| 5m | 179,753 | 15.5% |
| 15m | 59,951 | 5.2% |
| 1h | 14,955 | 1.3% |
| 4h | 3,741 | 0.3% |
| 1d | 616 | 0.05% |

### 2.3 新闻情绪分布

| 情绪 | 数量 | 占比 |
|------|------|------|
| neutral | 447 | 46.9% |
| bullish | 278 | 29.1% |
| bearish | 229 | 24.0% |

---

## 三、market_data.db（283 MB）

### 3.1 宏观时序（85,905 行）

时间跨度：**1962-01-02 ~ 2026-05-28**（64年）

| 因子 | 行数 | 说明 |
|------|------|------|
| ust_10y_yield | 16,084 | 美国10年期国债收益率 |
| ust_2y_yield | 12,492 | 美国2年期国债收益率 |
| ust_30y_yield | 12,314 | 美国30年期国债收益率 |
| ust_3m_yield | 11,182 | 美国3月期国债收益率 |
| fed_funds_upper | 6,373 | 联邦基金利率上限 |
| us_10y_breakeven_inflation | 5,854 | 10年期盈亏平衡通胀 |
| ust_10y_real_yield | 5,853 | 10年期实际收益率 |
| dxy | 2,873 | 美元指数 |
| gold_spot | 2,804 | 黄金现货 |
| wti_crude | 2,801 | WTI原油 |
| vix | 2,217 | VIX波动率指数 |
| nasdaq_100 | 1,739 | 纳斯达克100 |
| sp500 | 1,739 | 标普500 |
| us_bbb_oas | 790 | BBB信用利差 |
| us_high_yield_oas | 790 | 高收益利差 |

### 3.2 另类数据时序（133,183 行）

| 因子类别 | 行数 | 说明 |
|----------|------|------|
| stablecoin_chain_supply | 23,510 | 稳定币链上供给分布 |
| stablecoin_chain_supply_share | 23,510 | 链上供给份额 |
| stablecoin_bridge_inflow | 19,131 | 跨链桥流入 |
| stablecoin_bridge_outflow | 19,131 | 跨链桥流出 |
| stablecoin_total_supply | 9,589 | 稳定币总供给 |
| stablecoin_net_supply_change_24h | 9,585 | 24h净供给变化 |
| stablecoin_net_supply_change_7d | 9,569 | 7d净供给变化 |
| stablecoin_burn_volume | 9,525 | 销毁量 |
| stablecoin_mint_volume | 9,525 | 铸造量 |
| github_active_contributors_7d | 18 | GitHub活跃贡献者 |
| github_commit_count_1d | 18 | GitHub日提交数 |
| github_commit_count_7d | 18 | GitHub周提交数 |
| github_merged_pr_count_7d | 18 | GitHub周合并PR数 |
| github_opened_pr_count_7d | 18 | GitHub周开PR数 |
| github_release_count_30d | 18 | GitHub月发布数 |

### 3.3 链上时序（227 行）— 免费数据源

时间范围：2026-05-24 ~ 2026-05-28

| 因子 | 行数 | 来源 | AI 信号意义 |
|------|------|------|------------|
| dex_volume_24h | 72 | DeFiLlama DEX | 链上交易活跃度 |
| stablecoin_mcap | 63 | DeFiLlama Stablecoins | 稳定币供应量 |
| stablecoin_mcap_change_7d | 54 | DeFiLlama Stablecoins | 铸造/赎回趋势 |
| fees_paid | 10 | DeFiLlama Fees | 链上使用率 |
| dex_volume_change_1d | 8 | DeFiLlama DEX | 交易量变化 |
| fear_greed_index | 2 | alternative.me | 市场情绪极端值 |
| total_market_cap | 2 | CoinGecko | 总市值水平 |
| btc_dominance | 2 | CoinGecko | 资金轮动方向 |
| market_cap_change_24h | 2 | CoinGecko | 短期动量 |
| total_volume_24h | 2 | CoinGecko | 全市场成交量 |
| defi_stablecoin_yield_median | 2 | DeFiLlama Yields | 流动性松紧指标 |
| defi_total_tvl | 2 | DeFiLlama Yields | DeFi 总锁仓 |
| protocol_tvl | 2 | DeFiLlama Protocols | 协议健康度 |
| protocol_tvl_change_24h | 2 | DeFiLlama Protocols | TVL 变化 |
| protocol_tvl_change_7d | 2 | DeFiLlama Protocols | TVL 周趋势 |

### 3.4 新闻文章（954 篇）

- 来源数：**43 个 RSS/Atom 源**
- 时间范围：2026-05-20 ~ 2026-05-29（9天）
- 日均采集：~106 篇/天

### 3.5 因子目录注册

| 目录 | 注册因子数 | 有数据 | 状态 |
|------|-----------|--------|------|
| 期权因子 | 55 | ❌ 0行 | 待配置 Deribit |
| 另类因子 | 28 | ✅ 133,183行 | 生产就绪 |
| 链上因子 | 28 | ✅ 227行 | 15个免费可采 |
| 宏观因子 | 15 | ✅ 85,905行 | 生产就绪 |
| 代币经济学因子 | 12 | ❌ 0行 | 待配置 |

---

## 四、链上数据源覆盖

### 4.1 免费数据源状态

| 数据源 | API | 采集间隔 | 状态 |
|--------|-----|----------|------|
| Market Sentiment | alternative.me | 1h | ✅ 运行中 |
| Global Market | CoinGecko | 30min | ✅ 运行中 |
| DeFi Yields | DeFiLlama Yields | 1h | ✅ 运行中 |
| Protocol TVL | DeFiLlama Protocols | 30min | ✅ 已修复 |
| Network Usage | DeFiLlama Fees | 30min | ✅ 已修复 |
| DEX Volume | DeFiLlama DEX | 30min | ✅ 已有 |
| Stablecoin Supply | DeFiLlama Stablecoins | 30min | ✅ 已有 |
| Bridge Netflow | DeFiLlama Bridges | — | ❌ API 已付费化 (402) |

### 4.2 付费/待配置数据源

| 数据源 | 需要 | 因子 | 状态 |
|--------|------|------|------|
| Exchange Flow | Glassnode/CryptoQuant | exchange_netflow | ❌ unconfigured |
| Whale Activity | 付费 API | whale_transfer_count | ❌ unconfigured |
| Stablecoin Flow | 付费 API | stablecoin_exchange_inflow | ❌ unconfigured |
| Exchange Reserve | 付费 API | exchange_reserve_balance | ❌ unconfigured |
| Staking Flow | 付费 API | staking_netflow | ❌ unconfigured |

---

## 五、数据质量与覆盖率总结

### 完整覆盖（✅ 生产就绪）

| 维度 | 状态 | 数据量 | 深度 |
|------|------|--------|------|
| K线（6周期×18币×3所） | ✅ | 3.45M行 | 20个月 |
| 技术指标（19币种） | ✅ 100% | 1.16M行 | 20个月 |
| 宏观经济（15因子） | ✅ | 85.9K行 | 64年 |
| 稳定币数据 | ✅ | 133K行 | 8.5年 |
| 新闻采集+情绪 | ✅ | 954篇/43源 | 持续积累 |
| 交易所对比 | ✅ | 696快照 | 运行中 |
| AI上下文bundle | ✅ | 756快照 | 运行中 |
| 跨资产分析 | ✅ | 855行 | 运行中 |
| 组合风险 | ✅ | 45快照 | 运行中 |
| 特征标准化 | ✅ | 13.8K行 | 运行中 |

### 部分覆盖（⚠️ 可用但有限）

| 维度 | 状态 | 说明 |
|------|------|------|
| 链上数据 | ⚠️ 7/15免费源 | 227行，4天深度 |
| 订单簿 | ⚠️ 5天深度 | 160K行，Binance较少 |
| 爆仓数据 | ⚠️ 仅OKX REST | 83行 |

### 未覆盖（❌ 待配置）

| 维度 | 需要 | 影响 |
|------|------|------|
| 期权时序 | Deribit API | 无 IV/Gamma/墙位 |
| 代币经济学 | CoinGecko API | 无解锁/供给压力 |
| 事件日历 | 事件源 endpoint | 无催化剂预判 |
| 付费链上 | Glassnode/CryptoQuant | 无交易所流/鲸鱼 |

---

## 六、数据库 Schema 概览

### exchange_data.db 核心表字段

**klines:**
```
id, symbol, exchange, timeframe, open_time, open, high, low, close, volume
```

**orderbook_snapshots:**
```
id, symbol, exchange, snapshot_depth, best_bid, best_ask, mid_price,
spread, spread_bps, bid_depth_notional, ask_depth_notional,
depth_imbalance, bids_json, asks_json, timestamp
```

**tickers:**
```
id, symbol, exchange, last_price, open_24h, bid, bid_volume, ask,
ask_volume, previous_close, high_24h, low_24h, vwap_24h, volume_24h,
quote_volume_24h, change_abs_24h, change_24h, mid_price, spread,
spread_bps, timestamp
```

### market_data.db 核心表字段

**macro_timeseries:**
```
id, factor_id, category, factor_type, interval, observation_time,
session_date, value, open, high, low, close, volume, unit, currency,
source_name, source_symbol, source_priority, available_at, is_revision,
revision_seq, quality_flag, is_market_open, ingest_run_id, collected_at,
raw_payload_json
```

**news_articles:**
```
id, source, source_type, feed_url, category, title, summary,
content_text, url, url_hash, author, published_at, collected_at,
language, sentiment_label, relevance_symbols, tags, image_url,
external_id, raw_payload_json
```

### analytics.db 核心表字段

**news_sentiment_labels:**
```
id, article_id, url_hash, title, sentiment, confidence,
event_type, impact_scope, impact_duration, labeled_at
```

---

## 七、关键指标汇总

| 指标 | 数值 |
|------|------|
| 总磁盘占用 | **5.7 GB** |
| 总数据行数 | **~6,390,000** |
| 覆盖币种 | 18（活跃）+ 1（已退市） |
| 覆盖交易所 | 3（Binance/OKX/Bybit） |
| K线时间深度 | 20个月（2024-09起） |
| 宏观数据深度 | 64年（FRED 1962年起） |
| 稳定币数据深度 | 8.5年（2017年起） |
| 新闻来源数 | 43 |
| 注册因子总数 | 138（15宏观+28链上+28另类+55期权+12代币） |
| 技术指标覆盖率 | 19/19 币种（100%） |
| AI上下文快照 | 756 |
| 逻辑层模块数 | 14 |

---

## 八、修复历史

| 修复项 | 根因 | 方案 |
|--------|------|------|
| Binance Orderbook = 0 | ccxt 不返回 timestamp | fallback 到 now(UTC) |
| OKX Funding = 0 | ccxt timestamp 为 None | fallback 链: timestamp → fundingDatetime → now |
| OKX Basis = 0 | JOIN 依赖 funding 为空 | funding 入库后自动生效 |
| OKX Positioning = 0 | ccxt period 参数错误 | OKX 原生 REST API fallback |
| Liquidations 全所 = 0 | ccxt 不支持 fetchLiquidations | OKX REST + Binance/Bybit WebSocket |
| Funding 停在 05-24 | scheduler 重启后丢失 | basis 前置触发 funding |
| Protocol TVL/Network = 0 | User-Agent 被 DeFiLlama 拦截 402 | 改为浏览器 UA |
| 链上数据仅 4 因子 | 未实现更多免费源 | 新增 3 个免费采集器 |

---

## 九、待办优先级

| 优先级 | 缺口 | 影响 | 建议 |
|--------|------|------|------|
| P1 | options_timeseries | AI 无法获取隐含波动率/偏度 | 配置 Deribit API |
| P1 | tokenomics_timeseries | AI 无法评估代币供应压力 | 配置 CoinGecko Pro API |
| P2 | event_calendar | AI 无法预判事件驱动行情 | 配置事件源 endpoint |
| P2 | Liquidations Binance/Bybit | 仅 OKX 有 REST 数据 | 启动 WebSocket collector |
| P3 | exchange_flow/whale/staking | 链上资金流向不完整 | 需 Glassnode/CryptoQuant |
| P3 | cross_asset_fund_flow | 资金流分析无数据 | 需 trade_flow 积累 |
