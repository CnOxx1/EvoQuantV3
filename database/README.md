# 数据库存储

项目数据库统一放在 [`database`](../database) 目录。

当前采用 **3 域拆分架构**，按写入频率隔离数据库文件，消除跨域写锁竞争：

| 域 | 文件 | 写入频率 | 包含内容 |
|---|---|---|---|
| exchange_data | `exchange_data.db` | 3-60s | 行情、盘口、K 线、资金费率、衍生品结构 |
| market_data | `market_data.db` | 5min-6h | 宏观、链上、Tokenomics、期权、新闻、事件 |
| analytics | `analytics.db` | 按需 | 技术指标、跨所对比、市场结构、AI 上下文 |

逻辑层通过 `ATTACH DATABASE` + `TEMP VIEW` 透明读取其他域数据，现有 SQL 查询无需修改。

向后兼容：设置 `DB_SPLIT_ENABLED=0` 可退化为单文件模式（`crypto_data.db`）。

这份文档重点记录两件事：

- 数据库里当前有哪些表、各自保存什么数据
- 每张表的数据是通过哪个模块、哪个任务写入的，以及 AI 如何读取关键快照表

## AI 文档维护约束

这份 README 是后续 AI 开发和维护数据库结构时使用的工作文档，不只是表说明。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 数据库代码树、数据库文件或初始化入口
- 新增/删除/重命名数据表、字段、索引或唯一键
- 表归属、写入链路、上下游依赖关系或初始化迁移行为
- 与 AI 直接读取相关的快照表、特征表或语义说明

## 快速导航

- [当前代码树](#当前代码树)
- [表级来源总览](#表级来源总览)
- [表组速览](#表组速览)
- [各表详细说明](#各表详细说明)

## 当前代码树

下面代码树省略 `__pycache__` 等缓存目录：

```text
database/
  README.md                      # 数据库结构、写入链路与维护约束
  __init__.py                    # 数据库包入口，导出 DBManager / DatabaseRouter / Domain
  db_manager.py                  # SQLite 初始化、建表、迁移与域表管理
  router.py                      # 域路由器：按写入频率分配 DBManager 实例
  schemas.py                     # 表名常量与域映射（init 方法 / 物理表名）
  migrate_split.py               # 从 crypto_data.db 迁移到 3 域文件的脚本
  exchange_data.db               # 高频交易所数据（运行时生成）
  market_data.db                 # 中低频市场数据（运行时生成）
  analytics.db                   # 逻辑层输出与审计（运行时生成）
  crypto_data.db                 # 旧单文件数据库（向后兼容）
```

## 域拆分架构

### 设计动机

所有 14 个模块共用单一 SQLite 文件时，高频写入（orderbook 3s、ticker 5s）与低频模块共享同一写锁，导致 `database is locked` 和写入排队。拆分后按写入频率隔离域，消除跨域写锁竞争。

### 使用方式

```python
from database.router import DatabaseRouter, Domain

# 数据层模块
router = DatabaseRouter()
db = router.get_manager(Domain.EXCHANGE_DATA)   # 或 MARKET_DATA

# 逻辑层模块（自动 ATTACH 其他域 + 创建 TEMP VIEW）
db = router.get_analytics_db()
```

### 向后兼容

- `DB_SPLIT_ENABLED=0` 环境变量 → 退化为单文件模式
- `DBManager(db_path=":memory:")` + `init_tables()` 不变 → 所有现有测试无需修改
- 测试环境通过 `tests/conftest.py` 自动设置 `DB_SPLIT_ENABLED=0`

### 数据迁移

```bash
# 预览迁移（不实际执行）
python -m database.migrate_split --dry-run

# 执行迁移
python -m database.migrate_split
```

## 表组速览

| 表组 | 主要作用 | 代表表 |
| --- | --- | --- |
| 交易所基础数据 | 行情、盘口、K 线、资金费率 | `tickers`、`orderbook_snapshots`、`funding_rates` |
| 交易所衍生品结构 | 拥挤度、清算、持仓、basis | `trade_flow_bars`、`open_interest_snapshots`、`basis_snapshots` |
| 文本与事件 | 新闻和未来催化剂 | `news_articles`、`event_calendar_events` |
| 宏观 / 链上 / 补充特征 | 跨市场背景与非价格证据 | `macro_timeseries`、`onchain_timeseries`、`alternative_timeseries` |
| Tokenomics / Options | 供给压力与期权结构 | `tokenomics_timeseries`、`token_unlock_events`、`options_timeseries` |
| 逻辑层聚合 | AI-ready 上下文与治理结果 | `technical_indicators`、`market_breadth_snapshots`、`ai_market_context_snapshots` |

## 表级来源总览

| 表名 | 数据类型 | 写入模块 | 直接写入入口 |
| --- | --- | --- | --- |
| `collection_runs` | 通用采集运行台账、状态、耗时与样本数 | 多个 `data_layer` 模块 | `DBManager.record_collection_run()` |
| `market_info` | 交易对静态信息、交易规则 | `data_layer.exchange_data` | `MarketInfoCollector.collect()` |
| `klines` | 多周期交易所原始 OHLCV K 线 | `data_layer.exchange_data` | `KlineCollector.collect()` / `KlineCollector.backfill_all()` |
| `tickers` | 实时行情快照、24h 成交量/成交额、价差 | `data_layer.exchange_data` | `TickerCollector.collect()` |
| `latest_tickers` | 每个 `symbol + exchange` 的最新行情快照 | `data_layer.exchange_data` | `TickerCollector.save_to_db()` |
| `funding_rates` | 资金费率、标记价格、指数价格 | `data_layer.exchange_data` | `FundingRateCollector.collect()` / `FundingRateCollector.backfill_all_history()` |
| `latest_funding_rates` | 每个 `symbol + exchange` 的最新资金费率快照 | `data_layer.exchange_data` | `FundingRateCollector.save_to_db()` |
| `orderbook_snapshots` | 盘口前 N 档快照、深度特征 | `data_layer.exchange_data` | `OrderBookCollector.collect()` |
| `latest_orderbook_snapshots` | 每个 `symbol + exchange` 的最新盘口快照 | `data_layer.exchange_data` | `OrderBookCollector.save_to_db()` |
| `trade_flow_bars` | 成交流聚合、主动买卖压力 | `data_layer.exchange_data` | `TradesCollector.collect()` |
| `latest_trade_flow_bars` | 每个 `symbol + exchange` 的最新成交流聚合快照 | `data_layer.exchange_data` | `TradesCollector.save_to_db()` |
| `open_interest_snapshots` | 持仓量、持仓变化和合约杠杆语境 | `data_layer.exchange_data` | `OpenInterestCollector.collect()` |
| `latest_open_interest_snapshots` | 每个 `symbol + exchange` 的最新持仓量快照 | `data_layer.exchange_data` | `OpenInterestCollector.save_to_db()` |
| `liquidation_bars` | 清算聚合和 squeeze 压力；清算指标字段允许为 `NULL`，避免把未知误写成 `0` | `data_layer.exchange_data` | `LiquidationsCollector.collect()` / `ExchangeDataService.repair_liquidation_semantics_from_raw_payload()` |
| `latest_liquidation_bars` | 每个 `symbol + exchange` 的最新清算聚合快照；缺失字段保留 `NULL`，真实零值继续保留 | `data_layer.exchange_data` | `LiquidationsCollector.save_to_db()` / `ExchangeDataService.repair_liquidation_semantics_from_raw_payload()` |
| `positioning_snapshots` | 多空比、站位拥挤度 | `data_layer.exchange_data` | `LongShortRatioCollector.collect()` |
| `latest_positioning_snapshots` | 每个 `symbol + exchange` 的最新多空比快照 | `data_layer.exchange_data` | `LongShortRatioCollector.save_to_db()` |
| `basis_snapshots` | 现货与合约基差结构 | `data_layer.exchange_data` | `BasisCollector.collect()` |
| `latest_basis_snapshots` | 每个 `symbol + exchange` 的最新 basis 快照 | `data_layer.exchange_data` | `BasisCollector.save_to_db()` |
| `news_articles` | 新闻、公告、论坛文本事件 | `data_layer.news_data` | `NewsCollector.collect()` / `NewsCollector.collect_async()` |
| `event_calendar_events` | 未来已知事件日历与状态变更 | `data_layer.event_calendar_data` | `EventCalendarCollector.save_to_db()` |
| `macro_factor_catalog` | 宏观因子目录、频率、来源与新鲜度规则，当前已覆盖美元、利率曲线、政策利率、美股、VIX、黄金与原油代理 | `data_layer.macro_data` | `MacroDataService.sync_factor_catalog()` |
| `macro_timeseries` | 宏观历史时序，统一 `value` / `observation_time` 语义 | `data_layer.macro_data` | `MacroMarketCollector.save_to_db()` / `MacroRateCollector.save_to_db()` |
| `latest_macro_timeseries` | 每个 `factor_id + interval` 的最新宏观快照，供 AI 当前上下文和 coverage 检查直接读取 | `data_layer.macro_data` | `MacroMarketCollector.save_to_db()` / `MacroRateCollector.save_to_db()` |
| `onchain_factor_catalog` | 链上因子目录、实体范围、来源与版本元数据 | `data_layer.onchain_data` | `OnchainDataService.sync_factor_catalog()` |
| `onchain_timeseries` | 链上历史时序，统一 `value` / `observation_time` / `dimensions` 语义 | `data_layer.onchain_data` | `OnchainDataService.save_to_db()` |
| `latest_onchain_timeseries` | 每个链上实体的当前最新快照 | `data_layer.onchain_data` | `OnchainDataService.save_to_db()` |
| `alternative_factor_catalog` | 补充特征因子目录、实体范围、来源与版本元数据 | `data_layer.alternative_data` | `AlternativeDataService.sync_factor_catalog()` |
| `alternative_timeseries` | 补充特征历史时序，统一 `value` / `observation_time` / `dimensions` 语义 | `data_layer.alternative_data` | `AlternativeCollectorBase.save_to_db()` |
| `latest_alternative_timeseries` | 每个补充特征实体的最新快照，供 AI 当前上下文读取 | `data_layer.alternative_data` | `AlternativeCollectorBase.save_to_db()` |
| `tokenomics_factor_catalog` | Tokenomics 因子目录、实体范围、来源与版本元数据 | `data_layer.tokenomics_data` | `TokenomicsDataService.sync_factor_catalog()` |
| `tokenomics_timeseries` | Tokenomics 历史时序，统一 `value` / `observation_time` / `dimensions` 语义 | `data_layer.tokenomics_data` | `Collector.save_to_db()` / `TokenomicsCollectorBase.save_to_db()` |
| `latest_tokenomics_timeseries` | 每个 tokenomics 实体的最新快照，供 AI 当前上下文读取 | `data_layer.tokenomics_data` | `Collector.save_to_db()` / `TokenomicsCollectorBase.save_to_db()` |
| `options_factor_catalog` | 期权因子目录、期限语义与来源元数据 | `data_layer.options_data` | `OptionsDataService.sync_factor_catalog()` |
| `options_timeseries` | 期权历史时序，统一 `value` / `observation_time` / `dimensions` 语义 | `data_layer.options_data` | `OptionsCollectorBase.save_to_db()` |
| `latest_options_timeseries` | 每个期权实体的最新快照，供 AI 当前上下文读取 | `data_layer.options_data` | `OptionsCollectorBase.save_to_db()` |
| `token_unlock_events` | 未来解锁事件明细与状态 | `data_layer.tokenomics_data` | `UnlockScheduleCollector.fetch_unlock_events()` / `TokenomicsDataService.save_unlock_events()` |
| `data_quality_audit_snapshots` | 跨模块数据质量审计快照、市场世界模型健康状态 | `data_layer.data_quality` | `DataLayerAuditService.save_market_world_audit_snapshot()` |
| `macro_context_snapshots` | AI 可直接消费的宏观上下文快照与变化特征 | `logic_layer.macro_context` | `MacroContextService.build_latest_snapshots()` |
| `market_breadth_snapshots` | 跨资产市场广度快照、真实可见资产 breadth、新闻 breadth、解锁 breadth | `logic_layer.market_breadth` | `MarketBreadthService.save_snapshot()` |
| `asset_readiness_snapshots` | 资产级真实证据可用性矩阵快照、band 缺口、资产 readiness 分布 | `logic_layer.asset_readiness` | `AssetReadinessService.save_snapshot()` |
| `merged_klines` | 多交易所合并后的统一主 K 线 | `logic_layer.technical_indicators` | `TechnicalIndicatorService.merge_klines()` |
| `technical_indicators` | 技术指标与市场上下文特征 | `logic_layer.technical_indicators` | `TechnicalIndicatorService.calculate_indicators()` / `refresh_all()` |
| `exchange_comparison_snapshots` | 跨交易所价格偏离、净价差、执行偏好、funding 语境与市场背景特征 | `logic_layer.exchange_comparison` | `ExchangeComparisonService.build_latest_snapshots()` / `refresh_latest()` |
| `ai_market_context_snapshots` | AI 最终市场上下文快照、覆盖率和完整 bundle | `logic_layer.ai_market_context` | `AIMarketContextService.build_latest_snapshots()` |

## 2026-05 第二阶段扩展表组

为了让 AI 在读取数据库时能拿到更完整的市场证据，当前数据库已补上三组关键表：

- 交易所衍生品结构表组
  - `trade_flow_bars / latest_trade_flow_bars`
  - `open_interest_snapshots / latest_open_interest_snapshots`
  - `liquidation_bars / latest_liquidation_bars`
  - `positioning_snapshots / latest_positioning_snapshots`
  - `basis_snapshots / latest_basis_snapshots`

其中 `liquidation_bars / latest_liquidation_bars` 当前已经明确采用“未知即 `NULL`、真实零值保留”的语义；如果数据库里仍残留旧版 collector 写成 `0` 的未知清算字段，需要通过 `exchange_data` 的 `liquidations-repair` 维护命令，按已保存的 `raw_payload_json` 做可审计修复，而不是直接猜测覆盖。
- Tokenomics 表组
  - `tokenomics_factor_catalog`
  - `tokenomics_timeseries / latest_tokenomics_timeseries`
  - `token_unlock_events`
- Options 表组
  - `options_factor_catalog`
  - `options_timeseries / latest_options_timeseries`
- AI 最终聚合表
  - `ai_market_context_snapshots`
- 资产级证据治理表
  - `market_breadth_snapshots`
  - `asset_readiness_snapshots`

这些新增表的目标不是替代原始表，而是补齐 AI 在“当前市场分析”时最缺的几类证据：

- 衍生品拥挤度与被动平仓压力
- 供给释放与潜在抛压
- 期权市场对未来波动、尾部风险、dealer gamma regime、增量成交意图、到期桶风险分布、动态对冲压力、波动率凸性冲击、gamma 时间衰减、墙位与 pinning 风险的定价
- 多模块最终统一后的 AI 上下文快照
- 当前资产宇宙到底够不够宽
- 具体哪些资产现在证据链够完整，哪些资产仍只是局部可见

## 各表详细说明

### `collection_runs`

- 保存内容：
  - 每个模块、每个 source 的采集运行台账
  - 包括 `module_name`、`source_name`、`job_name`
  - `status`、`item_count`
  - `started_at`、`finished_at`、`duration_seconds`
  - `message`、`metadata_json`
- 写入模块：
  - 当前已接入 [`news_data`](../data_layer/news_data)
  - 当前已接入 [`event_calendar_data`](../data_layer/event_calendar_data)
  - 当前已接入 [`onchain_data`](../data_layer/onchain_data)
  - 当前已接入 [`tokenomics_data`](../data_layer/tokenomics_data)
  - 当前已接入 [`options_data`](../data_layer/options_data)
  - 当前已接入 [`data_quality`](../data_layer/data_quality)
- 具体写入链路：
  - [`DBManager.record_collection_run()`](../database/db_manager.py)
- 用途：
  - 判断某个 source 最近是否成功采集
  - 判断某类数据是否进入 stale 状态
  - 为各模块的 `--print-coverage` 提供运行台账基础

### `data_quality_audit_snapshots`

- 保存内容：
  - 跨模块真实证据带审计快照
  - 包括 `audit_scope`、`snapshot_time`
  - `world_model_status`
  - `is_market_data_ready_for_ai`
  - `required_band_count / required_ready_band_count`
  - `optional_band_count / optional_ready_band_count`
  - `critical_gap_count`
  - `critical_gap_band_names_json / blocked_band_names_json / partial_band_names_json`
  - `bands_json`
  - `raw_audit_json`
- 写入模块：
  - [`data_layer.data_quality`](../data_layer/data_quality)
- 具体写入链路：
  - [`DataLayerAuditService.run_market_world_audit()`](../data_layer/data_quality/audit.py)
  - [`DataLayerAuditService.save_market_world_audit_snapshot()`](../data_layer/data_quality/audit.py)
- 运行入口：
  - `python -m data_layer.data_quality.runner --save-market-audit`
  - `python -m data_layer.data_quality.runner --mode once`
  - `python -m data_layer.data_quality.runner --mode scheduler`
- 用途：
  - 记录“当前整套数据层是否已经足够支撑 AI 看市场”的历史快照
  - 区分 required 证据带里的 `ready / stale / insufficient / unconfigured / missing`
  - 回看数据层质量是在改善还是恶化，而不是只看某次临时 `print-coverage`

### `market_info`

- 保存内容：
  - 交易对静态信息与交易规则
  - 例如 `symbol`、`exchange_symbol`、`base`、`quote`
  - `market_type`、`status`
  - 精度、最小下单量、手续费、合约面值、结算币种
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入类 / 方法：
  - [`MarketInfoCollector.collect()`](../data_layer/exchange_data/market_info.py)
- 运行入口：
  - [`ExchangeDataService.bootstrap()`](../data_layer/exchange_data/service.py#L35)
  - [`ExchangeDataService.collect_once()`](../data_layer/exchange_data/service.py#L41)
  - [`ExchangeDataService.build_scheduler()`](../data_layer/exchange_data/service.py#L84) 中的 `market_info` job
- 上游外部来源：
  - Binance / OKX / Bybit 交易所市场元数据
- 用途：
  - 给策略层、下单层和数据标准化层提供交易规则基础

### `klines`

- 保存内容：
  - 多交易所、多周期原始 OHLCV K 线
  - 包括 `symbol`、`exchange`、`timeframe`
  - `open_time`、`open`、`high`、`low`、`close`、`volume`
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入类 / 方法：
  - [`KlineCollector.collect()`](../data_layer/exchange_data/kline.py)
  - [`KlineCollector.backfill_all()`](../data_layer/exchange_data/kline.py)
- 运行入口：
  - `bootstrap` 模式会优先回填
  - `once` / `scheduler` 模式会持续增量更新
- 上游外部来源：
  - Binance / OKX / Bybit 的历史和增量 K 线接口
- 用途：
  - 是逻辑处理层 `merged_klines` 和 `technical_indicators` 的主时序输入

### `tickers`

- 保存内容：
  - 实时行情快照
  - 包括 `last_price`、`bid`、`ask`、`mid_price`
  - `spread`、`spread_bps`
  - `volume_24h`、`quote_volume_24h`
  - `vwap_24h`、`change_24h`
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入类 / 方法：
  - [`TickerCollector.collect()`](../data_layer/exchange_data/ticker.py#L108)
- 运行入口：
  - `once`
  - `scheduler`
  - `context-burst`
- 上游外部来源：
  - Binance / OKX / Bybit ticker / 行情接口
- 用途：
  - 为 `technical_indicators` 表补充跨交易所价格、价差、成交额等上下文特征
  - 也是 `exchange_comparison` 模块做跨交易所价格偏离和最佳买卖场所判断的主价格输入

### `latest_tickers`

- 保存内容：
  - 每个 `symbol + exchange` 当前最新一条 ticker 快照
  - 字段与 `tickers` 保持同构，方便下游直接读取
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入链路：
  - [`TickerCollector.save_to_db()`](../data_layer/exchange_data/ticker.py)
- 直接输入来源：
  - `tickers`
- 用途：
  - 给 AI 当前市场分析提供“每个交易所此刻状态”的直接入口
  - 给 `exchange_comparison` 提供无需扫历史表的最新横截面输入

### `funding_rates`

- 保存内容：
  - 衍生品市场资金费率和相关价格
  - 包括 `funding_rate`、`mark_price`、`index_price`
  - `next_funding_time`、`timestamp`
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入类 / 方法：
  - [`FundingRateCollector.collect()`](../data_layer/exchange_data/funding.py#L182)
  - [`FundingRateCollector.backfill_all_history()`](../data_layer/exchange_data/funding.py#L142)
- 运行入口：
  - `once`
  - `scheduler`
  - `funding-backfill`
  - `context-burst`
- 上游外部来源：
  - Binance / OKX / Bybit 合约资金费率接口
- 用途：
  - 为逻辑层提供衍生品情绪、拥挤度和 basis 上下文
  - 也是 `exchange_comparison` 在回退路径下读取 funding 历史候选集的来源

### `latest_funding_rates`

- 保存内容：
  - 每个 `symbol + exchange` 当前最新一条 funding 快照
  - 字段与 `funding_rates` 保持同构
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入链路：
  - [`FundingRateCollector.save_to_db()`](../data_layer/exchange_data/funding.py)
- 直接输入来源：
  - `funding_rates`
- 用途：
  - 给后续 AI 和横截面分析模块提供当前资金费率语境
  - 避免“最新 funding”读取时扫描整张历史表
  - 给 `exchange_comparison` 提供当前衍生品市场的 funding 横截面

### `orderbook_snapshots`

- 保存内容：
  - 盘口前 N 档快照和深度衍生特征
  - 包括 `bids_json`、`asks_json`
  - `best_bid`、`best_ask`、`mid_price`
  - `spread`、`spread_bps`
  - `bid_depth_notional`、`ask_depth_notional`
  - `depth_imbalance`
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入类 / 方法：
  - [`OrderBookCollector.collect()`](../data_layer/exchange_data/orderbook.py#L137)
- 运行入口：
  - `once`
  - `scheduler`
  - `context-burst`
- 上游外部来源：
  - Binance / OKX / Bybit orderbook / depth 接口
- 用途：
  - 为逻辑层提供流动性、盘口厚度和深度失衡上下文
  - 也是 `exchange_comparison` 模块估算滑点、深度差和执行质量的核心输入

### `latest_orderbook_snapshots`

- 保存内容：
  - 每个 `symbol + exchange` 当前最新一条盘口快照
  - 字段与 `orderbook_snapshots` 保持同构
- 写入模块：
  - [`exchange_data`](../data_layer/exchange_data)
- 具体写入链路：
  - [`OrderBookCollector.save_to_db()`](../data_layer/exchange_data/orderbook.py)
- 直接输入来源：
  - `orderbook_snapshots`
- 用途：
  - 给 AI 当前盘口分析提供直接入口
  - 给 `exchange_comparison` 提供最新盘口，再叠加历史窗口做最近邻对齐

### `news_articles`

- 保存内容：
  - 新闻、博客、论坛、监管公告等文本事件
  - 包括 `source`、`feed_url`、`category`
  - `title`、`summary`、`content_text`
  - `url`、`url_hash`
  - `author`、`published_at`、`collected_at`
  - `relevance_symbols`、`tags`
  - `image_url`、`external_id`、`raw_payload_json`
- 写入模块：
  - [`news_data`](../data_layer/news_data)
- 具体写入链路：
  - [`NewsFeedClient`](../data_layer/news_data/client.py) 负责下载 RSS / Atom
  - [`NewsCollector.collect()`](../data_layer/news_data/collector.py#L188) / [`collect_async()`](../data_layer/news_data/collector.py#L205) 负责筛选、去重、落库
- 运行入口：
  - [`NewsDataService.collect_once()`](../data_layer/news_data/service.py#L25)
  - [`NewsDataService.collect_once_async()`](../data_layer/news_data/service.py#L37)
  - [`NewsDataService.build_scheduler()`](../data_layer/news_data/service.py#L66)
- 上游外部来源：
  - 默认 57 个公开 RSS / Atom 新闻源
  - 覆盖综合媒体、研究、安全、监管、生态博客和治理论坛
- 用途：
  - 给 AI 和逻辑层提供文本事件输入，后续可做情绪、事件类型、叙事跟踪和新闻价格联动分析

### `event_calendar_events`

- 保存内容：
  - 未来已知事件与状态变更
  - 包括 `event_key`、`event_type`、`title`
  - `symbol`、`scheduled_at`、`timezone`
  - `importance_score`、`status`
  - `source_name`、`source_url`、`external_id`
  - `tags`、`raw_payload_json`
- 写入模块：
  - [`event_calendar_data`](../data_layer/event_calendar_data)
- 具体写入链路：
  - [`EventCalendarClient.fetch_events()`](../data_layer/event_calendar_data/client.py) 负责请求标准化 JSON 或 ICS
  - [`EventCalendarCollector.collect()`](../data_layer/event_calendar_data/collector.py) 负责标准化、去重和状态更新
  - [`EventCalendarCollector.save_to_db()`](../data_layer/event_calendar_data/collector.py)
- 运行入口：
  - [`EventCalendarDataService.collect_once()`](../data_layer/event_calendar_data/service.py)
  - [`EventCalendarDataService.build_scheduler()`](../data_layer/event_calendar_data/service.py)
- 上游外部来源：
  - 宏观日历、ETF 节点、升级日历、解锁日历的标准化 JSON / ICS 源
- 用途：
  - 给 AI 提供“未来将发生什么”的结构化背景
  - 避免未来事件和即时新闻正文混读

### `macro_factor_catalog`

- 保存内容：
  - 宏观因子目录与采集规则
  - 包括 `factor_id`、`category`、`factor_type`
  - `default_interval`、`source_name`、`source_symbol`
  - `staleness_ttl_seconds`、`is_intraday_enabled`、`enabled`
- 写入模块：
  - [`macro_data`](../data_layer/macro_data)
- 具体写入链路：
  - [`MacroDataService.sync_factor_catalog()`](../data_layer/macro_data/service.py)
- 上游定义来源：
  - [`sources.py`](../data_layer/macro_data/sources.py) 中的内置因子清单
- 用途：
  - 给采集器、AI 服务和后续逻辑层提供统一因子注册表
  - 显式记录哪些因子已启用，哪些仍属于 P1 扩展

### `macro_timeseries`

- 保存内容：
  - 标准化后的宏观历史时序
  - 包括 `factor_id`、`factor_type`、`interval`
  - `observation_time`、`value`
  - 对 `market_price` 因子还保留 `open/high/low/close/volume`
  - 同时保存 `quality_flag`、`source_priority`、`raw_payload_json`
- 写入模块：
  - [`macro_data`](../data_layer/macro_data)
- 具体写入链路：
  - [`MacroMarketCollector.save_to_db()`](../data_layer/macro_data/market.py)
  - [`MacroRateCollector.save_to_db()`](../data_layer/macro_data/rates.py)
- 上游外部来源：
  - `yahoo_finance` 图表接口：`dxy`、`nasdaq_100`、`gold_spot`
  - `fred` CSV：`ust_2y_yield`、`ust_10y_yield`
- 用途：
  - 给 AI 提供可回看、可拼接、可对齐的跨市场宏观背景
  - 是后续做宏观 regime、风险偏好对照和跨市场联动分析的主输入

### `latest_macro_timeseries`

- 保存内容：
  - 每个 `factor_id + interval` 当前最新一条宏观快照
  - 字段与 `macro_timeseries` 的核心语义保持一致
  - 重点保留 `value`、`observation_time`、`quality_flag`
- 写入模块：
  - [`macro_data`](../data_layer/macro_data)
- 具体写入链路：
  - [`MacroMarketCollector.save_to_db()`](../data_layer/macro_data/market.py)
  - [`MacroRateCollector.save_to_db()`](../data_layer/macro_data/rates.py)
- 直接输入来源：
  - `macro_timeseries`
- 用途：
  - 给 AI 当前市场分析直接提供最新美元、利率、纳指、黄金上下文
  - 避免每次都扫描完整历史时序表

### `onchain_factor_catalog`

- 保存内容：
  - 链上因子目录与采集元数据
  - 包括 `factor_id`、`name`、`category`、`factor_type`
  - `entity_scope`、`entity_type`
  - `default_interval`、`source_name`、`source_symbol`
  - `config_version`、`staleness_ttl_seconds`、`enabled`
  - `raw_meta_json`
- 写入模块：
  - [`onchain_data`](../data_layer/onchain_data)
- 具体写入链路：
  - [`OnchainDataService.sync_factor_catalog()`](../data_layer/onchain_data/service.py)
- 上游定义来源：
  - [`sources.py`](../data_layer/onchain_data/sources.py) 中的默认 source / factor / entity 配置
- 用途：
  - 给链上采集器、CLI 和 AI 读取层提供统一因子目录

### `onchain_timeseries`

- 保存内容：
  - 标准化后的链上历史时序
  - 包括 `factor_id`、`category`、`factor_type`
  - `entity_type`、`entity_key`、`interval`
  - `observation_time`、`value`、`unit`
  - `quality_flag`
  - `dimensions_key`、`dimensions_json`
  - `config_version`、`source_name`、`source_symbol`
  - `raw_payload_json`、`collected_at`、`updated_at`
- 写入模块：
  - [`onchain_data`](../data_layer/onchain_data)
- 具体写入链路：
  - [`ExchangeFlowCollector.collect()`](../data_layer/onchain_data/collectors/exchange_flow.py)
  - [`WhaleActivityCollector.collect()`](../data_layer/onchain_data/collectors/whale_activity.py)
  - [`StablecoinFlowCollector.collect()`](../data_layer/onchain_data/collectors/stablecoin_flow.py)
  - 公共 upsert 逻辑落在 [`OnchainDataService.save_to_db()`](../data_layer/onchain_data/service.py)
- 上游外部来源：
  - 交易所净流、鲸鱼异动、稳定币交易所流入的标准化 JSON 接口
- 用途：
  - 给 AI 和后续逻辑层提供可回看的链上背景历史

### `latest_onchain_timeseries`

- 保存内容：
  - 每个 `factor_id + entity_key + interval + dimensions_key + source_name + config_version` 的当前最新链上快照
  - 字段与 `onchain_timeseries` 的核心语义保持一致
- 写入模块：
  - [`onchain_data`](../data_layer/onchain_data)
- 具体写入链路：
  - 与 `onchain_timeseries` 同步由 [`OnchainDataService.save_to_db()`](../data_layer/onchain_data/service.py) upsert
  - 仅当新样本 `observation_time` 不早于旧样本时才覆盖现有 latest 记录
- 直接输入来源：
  - `onchain_timeseries`
- 用途：
  - 给 [`OnchainDataService.load_latest_context_bundle()`](../data_layer/onchain_data/service.py) 提供读取入口
  - 避免 AI 每次取当前链上背景时扫描完整历史表

### `alternative_factor_catalog`

- 保存内容：
  - 补充特征因子目录与采集元数据
  - 包括 `factor_id`、`name`、`category`、`factor_type`
  - `entity_scope`、`entity_type`
  - `default_interval`、`source_name`、`source_symbol`
  - `config_version`、`staleness_ttl_seconds`、`enabled`
  - `raw_meta_json`
- 写入模块：
  - [`alternative_data`](../data_layer/alternative_data)
- 具体写入链路：
  - [`AlternativeDataService.sync_factor_catalog()`](../data_layer/alternative_data/service.py)
- 上游定义来源：
  - [`sources.py`](../data_layer/alternative_data/sources.py) 中的因子定义
  - `registry/*.json` 中的 query group / repo group / stablecoin asset 注册表快照
- 用途：
  - 给 `alternative_data` 采集器和 AI 读取层提供统一因子目录
  - 记录当前补充特征的版本、实体范围和注册表指纹

### `alternative_timeseries`

- 保存内容：
  - 标准化后的补充特征历史时序
  - 包括 `factor_id`、`category`、`factor_type`
  - `entity_type`、`entity_key`、`interval`
  - `observation_time`、`value`、`unit`
  - `quality_flag`
  - `dimensions_key`、`dimensions_json`
  - `config_version`、`source_name`、`source_symbol`
  - `raw_payload_json`、`collected_at`、`updated_at`
- 写入模块：
  - [`alternative_data`](../data_layer/alternative_data)
- 具体写入链路：
  - [`GoogleTrendsCollector.save_to_db()`](../data_layer/alternative_data/google_trends.py)
  - [`GitHubActivityCollector.save_to_db()`](../data_layer/alternative_data/github_activity.py)
  - [`StablecoinSupplyCollector.save_to_db()`](../data_layer/alternative_data/stablecoin_supply.py)
  - 公共 upsert 逻辑落在 [`AlternativeCollectorBase.save_to_db()`](../data_layer/alternative_data/base.py)
- 上游外部来源：
  - Google Trends 公开网页接口
  - GitHub REST / Search API
  - 稳定币供给与链分布接口
- 用途：
  - 给 AI 和后续逻辑层提供可回看的补充背景历史
  - 支撑 Google Trends 长历史、stablecoin 链级迁移和事件化流量回看

### `latest_alternative_timeseries`

- 保存内容：
  - 每个 `factor_id + entity_key + interval + dimensions_key + source_name + config_version` 的当前最新补充特征快照
  - 字段与 `alternative_timeseries` 的核心语义保持一致
- 写入模块：
  - [`alternative_data`](../data_layer/alternative_data)
- 具体写入链路：
  - 与 `alternative_timeseries` 同步由 [`AlternativeCollectorBase.save_to_db()`](../data_layer/alternative_data/base.py) upsert
  - 仅当新样本 `observation_time` 不早于旧样本时才覆盖现有 latest 记录
- 直接输入来源：
  - `alternative_timeseries`
  - 更准确地说，是同一批 `AlternativeTimeSeriesPoint` 在落历史表时同步回写的最新快照
- 用途：
  - 给 [`AlternativeDataService.load_latest_context()`](../data_layer/alternative_data/service.py) 和 [`AlternativeDataService.load_latest_context_bundle()`](../data_layer/alternative_data/service.py) 提供读取入口
  - 给 CLI `python -m data_layer.alternative_data.runner --print-context` 提供 AI 可消费上下文
  - 避免 AI 每次取当前背景时扫描完整 `alternative_timeseries`

### `macro_context_snapshots`

- 保存内容：
  - AI 可直接消费的宏观上下文快照
  - 包括 `latest_value`
  - `change_1d_abs / change_1d_pct`
  - `change_5d_abs / change_5d_pct`
  - 对利率类因子还包括 `change_1d_bps / change_5d_bps`
  - `freshness_seconds`、`is_stale`、`context_completeness_score`
- 写入模块：
  - [`macro_context`](../logic_layer/macro_context)
- 具体写入链路：
  - [`MacroContextService.build_latest_snapshots()`](../logic_layer/macro_context/service.py)
  - [`MacroContextRepository.save_context_snapshots()`](../logic_layer/macro_context/repository.py)
- 直接输入来源：
  - `latest_macro_timeseries`
  - `macro_timeseries`
  - `macro_factor_catalog`
- 用途：
  - 给 AI 提供不需要再临时回看原始时序的宏观背景特征
  - 统一沉淀美元、利率、纳指、黄金的短中期变化和 stale 判断

### `merged_klines`

- 保存内容：
  - 多交易所合并后的统一主 K 线
  - 包括 `symbol`、`timeframe`、`open_time`
  - `open`、`high`、`low`、`close`、`volume`
  - `exchange_count`、`source_exchanges`、`merge_method`
- 写入模块：
  - [`technical_indicators`](../logic_layer/technical_indicators)
- 具体写入链路：
  - [`TechnicalIndicatorService.merge_klines()`](../logic_layer/technical_indicators/service.py#L37)
  - [`TechnicalIndicatorRepository.save_merged_klines()`](../logic_layer/technical_indicators/repository.py#L197)
- 直接输入来源：
  - `klines`
- 上游模块来源：
  - 原始 `klines` 数据由 `exchange_data` 模块写入
- 用途：
  - 为统一技术指标计算提供单一主时间序列

### `technical_indicators`

- 保存内容：
  - 技术指标结果
  - 同时并入市场上下文特征
  - 当前除 `close`、`volume` 外，还包含大量趋势、动量、波动、量价结构、风险调整特征
  - 另外并入 `ticker / funding / orderbook` 聚合特征
- 写入模块：
  - [`technical_indicators`](../logic_layer/technical_indicators)
- 具体写入链路：
  - [`TechnicalIndicatorService.calculate_indicators()`](../logic_layer/technical_indicators/service.py#L66)
  - [`TechnicalIndicatorService.refresh_all()`](../logic_layer/technical_indicators/service.py#L103)
  - [`TechnicalIndicatorRepository.save_technical_indicators()`](../logic_layer/technical_indicators/repository.py#L238)
- 直接输入来源：
  - `merged_klines`
  - `tickers`
  - `funding_rates`
  - `orderbook_snapshots`
- 上游模块来源：
  - `merged_klines` 由 `technical_indicators` 模块自己生成
  - `tickers / funding_rates / orderbook_snapshots` 由 `exchange_data` 模块写入
- 用途：
  - 作为后续 AI 模型、规则策略、回测和监控的统一特征表
  - 当前读取 `tickers / funding_rates / orderbook_snapshots` 时，会按增量计算窗口限界读取，而不是全历史扫描
  - 也给 `exchange_comparison` 提供 symbol 级趋势、波动与横截面背景

### `exchange_comparison_snapshots`

- 保存内容：
  - 同一交易对在不同交易所之间的最新横向对比结果
  - 包括 `exchange_a / exchange_b`
  - `last / mid / bid / ask` 偏离
  - `funding_rate / mark_price / index_price` 偏离
  - `cross_spread_ab_bps / cross_spread_ba_bps`
  - `estimated_fee_bps / estimated_slippage_*`
  - `net_cross_spread_*`
  - `market_regime_label / funding_regime_label`
  - `context_rsi_14 / context_macd_hist / context_atr_pct_14` 等技术背景
  - `best_buy_exchange / best_sell_exchange`
  - `signal_label / is_actionable / anomaly_score`
  - `context_completeness_score`
  - `data_quality_flag / raw_context_json`
- 写入模块：
  - [`exchange_comparison`](../logic_layer/exchange_comparison)
- 具体写入链路：
  - [`ExchangeComparisonService.build_latest_snapshots()`](../logic_layer/exchange_comparison/service.py)
  - [`ExchangeComparisonService.refresh_latest()`](../logic_layer/exchange_comparison/service.py)
  - [`ExchangeComparisonRepository.save_comparison_snapshots()`](../logic_layer/exchange_comparison/repository.py)
- 直接输入来源：
  - `latest_tickers`
  - `latest_orderbook_snapshots`
  - `orderbook_snapshots`
  - `latest_funding_rates`
  - `funding_rates`
  - `market_info`
  - `technical_indicators`
- 上游模块来源：
  - `latest_tickers / latest_orderbook_snapshots / orderbook_snapshots / latest_funding_rates / funding_rates / market_info` 由 `exchange_data` 模块写入
  - `technical_indicators` 由 `logic_layer.technical_indicators` 模块写入
- 用途：
  - 给 AI 提供跨交易所横截面状态特征
  - 给后续策略和执行层提供最佳买卖场所、净价差和质量过滤依据
  - 让 AI 同时看到“当前交易所差异”和“当前市场背景”

## 当前表之间的关系

### 数据层原始输入表

- `market_info`
  - 来自 `exchange_data`
  - 保存交易规则与静态市场定义
- `klines`
  - 来自 `exchange_data`
  - 是技术指标计算的主时序底座
- `tickers`
  - 来自 `exchange_data`
  - 提供跨交易所价格和流动性快照
- `latest_tickers`
  - 来自 `exchange_data`
  - 提供当前最新行情横截面
- `funding_rates`
  - 来自 `exchange_data`
  - 提供衍生品市场情绪和 basis 上下文
- `latest_funding_rates`
  - 来自 `exchange_data`
  - 提供当前最新资金费率横截面
- `orderbook_snapshots`
  - 来自 `exchange_data`
  - 提供盘口厚度与深度不平衡
- `latest_orderbook_snapshots`
  - 来自 `exchange_data`
  - 提供当前最新盘口横截面
- `news_articles`
  - 来自 `news_data`
  - 提供新闻、公告和文本事件输入
- `macro_factor_catalog`
  - 来自 `macro_data`
  - 保存 AI 宏观上下文因子的目录、来源和新鲜度规则
- `macro_timeseries`
  - 来自 `macro_data`
  - 提供跨市场宏观历史时序
- `latest_macro_timeseries`
  - 来自 `macro_data`
  - 提供当前最新宏观横截面
- `alternative_factor_catalog`
  - 来自 `alternative_data`
  - 保存 AI 补充背景因子的目录、来源和注册表版本
- `alternative_timeseries`
  - 来自 `alternative_data`
  - 提供搜索注意力、开发者活跃度和稳定币流动性的历史时序
- `latest_alternative_timeseries`
  - 来自 `alternative_data`
  - 提供当前最新补充背景横截面

### 逻辑层派生输出表

- `macro_context_snapshots`
  - 由 `macro_context` 从 `macro_factor_catalog + macro_timeseries + latest_macro_timeseries` 计算生成
- `merged_klines`
  - 由 `technical_indicators` 从 `klines` 合并生成
- `technical_indicators`
  - 由 `technical_indicators` 从 `merged_klines + tickers + funding_rates + orderbook_snapshots` 计算生成
- `exchange_comparison_snapshots`
  - 由 `exchange_comparison` 从 `latest_tickers + latest_orderbook_snapshots + orderbook_snapshots + latest_funding_rates + funding_rates + market_info + technical_indicators` 计算生成

## 当前数据库写入与读取链路

### 1. 市场数据写入链路

- 外部交易所 API
- `data_layer.exchange_data`
- 写入 `market_info / klines / tickers / latest_tickers / funding_rates / latest_funding_rates / orderbook_snapshots / latest_orderbook_snapshots`

### 2. 新闻文本写入链路

- 外部 RSS / Atom feed
- `data_layer.news_data`
- 写入 `news_articles`
  - 同时写入 `collection_runs`

### 3. 事件日历写入链路

- 外部标准化 JSON / ICS 事件源
- `data_layer.event_calendar_data`
- 写入 `event_calendar_events`
  - 同时写入 `collection_runs`

### 4. 宏观原始数据写入链路

- 外部公开宏观数据源
- `data_layer.macro_data`
- 写入 `macro_factor_catalog / macro_timeseries / latest_macro_timeseries`

### 5. 链上因子元数据与时序写入链路

- `data_layer.onchain_data.sources`
- `OnchainDataService.sync_factor_catalog()`
- 写入 `onchain_factor_catalog`
- 同时：
  - 外部链上标准化接口
  - `data_layer.onchain_data.client`
  - `ExchangeFlowCollector / WhaleActivityCollector / StablecoinFlowCollector`
  - `OnchainDataService.save_to_db()`
  - 写入 `onchain_timeseries / latest_onchain_timeseries`
  - 同时写入 `collection_runs`

### 6. 补充特征元数据与时序写入链路

- `data_layer/alternative_data/registry/*.json`
- `data_layer.alternative_data.sources`
- `AlternativeDataService.sync_factor_catalog()`
- 写入 `alternative_factor_catalog`
- 同时：
  - 外部 Google Trends / GitHub / Stablecoin 接口
  - `data_layer.alternative_data.client`
  - `GoogleTrendsCollector / GitHubActivityCollector / StablecoinSupplyCollector`
  - `AlternativeCollectorBase.save_to_db()`
  - 写入 `alternative_timeseries / latest_alternative_timeseries`

### 7. 链上上下文到 AI 的读取链路

- 读取 `latest_onchain_timeseries`
- `OnchainDataService.load_latest_context_bundle()`
- 输出 `exchange_flow / whale_activity / stablecoin_flow` 链上背景 bundle
- 当前直接消费入口：
  - `python -m data_layer.onchain_data.runner --print-context`

### 8. 补充特征到 AI 的读取链路

- 读取 `latest_alternative_timeseries`
- `AlternativeDataService.load_latest_context()`
- `AlternativeDataService.load_latest_context_bundle()`
- 同时结合 `registry/*.json` 的实体名称与说明
- 输出 `google_trends / github / stablecoin` 三段式 AI 上下文
- 当前直接消费入口：
  - `python -m data_layer.alternative_data.runner --print-context`

### 9. 宏观上下文特征写入链路

- 读取 `macro_factor_catalog / macro_timeseries / latest_macro_timeseries`
- `logic_layer.macro_context`
- 写入 `macro_context_snapshots`

### 10. 特征派生写入链路

- 读取 `klines / tickers / funding_rates / orderbook_snapshots`
- `logic_layer.technical_indicators`
- 写入 `merged_klines / technical_indicators`
  - 其中 `tickers / funding_rates / orderbook_snapshots` 会按增量窗口限界读取

### 11. 跨交易所横向特征写入链路

- 读取 `latest_tickers / latest_orderbook_snapshots / orderbook_snapshots / latest_funding_rates / funding_rates / market_info / technical_indicators`
- `logic_layer.exchange_comparison`
- 写入 `exchange_comparison_snapshots`

## 初始化与迁移

- 所有表都由 `DBManager` 的域专用方法创建：
  - `init_exchange_data_tables()` — 交易所高频表
  - `init_market_data_tables()` — 中低频市场表
  - `init_analytics_tables()` — 逻辑层输出表
  - `init_tables()` — 全部表（向后兼容）
- 如果旧表缺少新字段，会自动 `ALTER TABLE` 补列
- `latest_*` 快照表会在初始化时从现有历史快照表自动回灌
- 不需要手工删库再重建
- 历史 funding 回填、新闻表字段扩展、技术指标扩列、交易所横截面对比扩列都兼容现有数据库

初始化方式：

```bash
# 单文件模式（向后兼容）
python -c "from database.db_manager import DBManager; DBManager().init_tables()"

# 域拆分模式（生产推荐）
python -c "from database.router import DatabaseRouter, Domain; r = DatabaseRouter(); r.get_manager(Domain.EXCHANGE_DATA); r.get_manager(Domain.MARKET_DATA); r.get_analytics_db()"
```

如果数据库中已经有旧表结构，初始化方法会自动补齐新增字段，不需要手动删库。
