# 交易所基础数据采集模块 `exchange_data`

## 模块定位

`exchange_data` 是数据层的第一个模块，负责从主流中心化交易所获取统一格式的市场数据，并落库给后续逻辑处理层、AI 分析链路和 Web 层使用。

对 AI 来说，`exchange_data` 提供的是市场价格、流动性、盘口和衍生品拥挤度这条“交易执行语境”主链，但它不是完整输入。完整市场分析还应该结合 `data_layer.news_data` 的 `news_articles` 文本事件、`logic_layer.macro_context` 的跨市场宏观背景，以及下游 `technical_indicators / exchange_comparison / ai_market_context` 的结构化特征。

当前这个模块输出给 AI 的质量原则也已经固定：

- 只暴露真实采集到并落库的市场数据
- 不对缺失交易所、缺失盘口、缺失衍生品维度做伪造补齐
- 缺什么、旧到什么程度、覆盖到几家交易所，都要显式输出给下游

## 快速导航

- [模块速览](#模块速览)
- [AI 文档维护约束](#ai-文档维护约束)
- [这个模块应该获取什么数据](#这个模块应该获取什么数据)
- [为 AI 积累更多上下文样本的采集策略](#为-ai-积累更多上下文样本的采集策略)
- [当前实现中的关键优化](#当前实现中的关键优化)
- [模块代码树](#模块代码树)
- [运行方式](#运行方式)
- [数据表与样本积累说明](#数据表与样本积累说明)
- [AI 最新 bundle 的质量增强](#ai-最新-bundle-的质量增强)
- [数据质量与覆盖检查](#数据质量与覆盖检查)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 交易所范围 | `Binance / OKX / Bybit` |
| 默认交易对 | `BTC/USDT`、`ETH/USDT`、`SOL/USDT`、`SUI/USDT` |
| 核心采集表 | `market_info / tickers / klines / orderbook_snapshots / funding_rates` |
| 衍生品补充 | `trades / taker_flow / open_interest / liquidations / long_short_ratio / basis` |
| AI 主用途 | 提供价格、流动性、盘口、资金费率与拥挤度语境 |
| 公开质量原则 | 只保留真实样本，不补假数据，显式暴露时效与覆盖缺口 |

## AI 文档维护约束

这份 README 是后续 AI 开发和维护 `exchange_data` 时的工作文档，不只是功能介绍。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 交易所列表、采集字段、调度模式、环境变量或保留策略
- 数据表语义、`latest_*` 快照逻辑、上下游依赖关系
- 推荐运行方式、测试覆盖或已知边界

当前开发阶段：

- 交易所：Binance、OKX、Bybit
- 交易对：`BTC/USDT`、`ETH/USDT`、`SOL/USDT`、`SUI/USDT`
- 数据库：项目根目录下 [`database`](../../database) 的 `crypto_data.db`

## 这个模块应该获取什么数据

为了后续做 AI 量化，不建议只抓“币种基本信息”。最低可用版本应该至少覆盖下面五类数据：

### 1. 交易对静态信息 `market_info`

作用：告诉系统这个交易对能不能交易、怎么下单、限价和精度是什么。

建议字段：

- `symbol` / `exchange_symbol`
- `base` / `quote`
- `exchange`
- `market_type`
- `status`
- `is_spot` / `is_margin` / `is_swap` / `is_future`
- `is_contract` / `is_linear` / `is_inverse`
- `price_precision` / `amount_precision`
- `min_price` / `max_price`
- `min_amount` / `max_amount`
- `min_cost` / `max_cost`
- `maker_fee` / `taker_fee`
- `contract_size`
- `settle_currency`
- `raw_info_json`

这些字段主要用于：

- 下单前校验
- 不同交易所统一标准化
- 后续扩展到合约、杠杆和跨交易所套利

### 2. 实时行情快照 `tickers`

作用：为 AI 和策略层提供当前价格、成交量、成交额和盘口紧张程度。

建议字段：

- `last_price`
- `open_24h`
- `high_24h` / `low_24h`
- `bid` / `ask`
- `bid_volume` / `ask_volume`
- `mid_price`
- `spread` / `spread_bps`
- `vwap_24h`
- `volume_24h`
- `quote_volume_24h`
- `change_abs_24h`
- `change_24h`
- `timestamp`

其中 `quote_volume_24h`、`spread_bps`、`mid_price` 对 AI 判断“流动性是否够、滑点是否高、当前价格是否异常”很有价值。

当前时间语义约束：

- ticker 优先使用交易所返回的事件时间
- 如果 `timestamp` 缺失，但 `datetime` 仍然可信，会继续使用该事件时间
- 如果事件时间整体缺失或损坏，这条 ticker 会被直接跳过，不再回退成“当前时间”伪装成最新行情

### 3. K线数据 `klines`

作用：为趋势、波动率、动量、均值回归、特征工程提供基础时序。

建议字段：

- `symbol`
- `exchange`
- `timeframe`
- `open_time`
- `open` / `high` / `low` / `close`
- `volume`

当前已经支持：

- `1m`、`5m`、`15m`
- `1h`、`4h`、`1d`

当前字段语义约束：

- K 线的 `open / high / low / close / volume` 都必须来自真实返回值
- 如果上游任一核心 OHLCV 字段缺失或损坏，该行会直接跳过
- `volume` 不再因为缺失被压成 `0`

### 4. 盘口快照 `orderbook_snapshots`

作用：让 AI 看见“价格之外”的供需结构。

建议字段：

- 前 N 档 `bids_json` / `asks_json`
- `snapshot_depth`
- `best_bid` / `best_ask`
- `mid_price`
- `spread` / `spread_bps`
- `bid_depth_notional`
- `ask_depth_notional`
- `depth_imbalance`
- `timestamp`

这组数据适合做：

- 流动性过滤
- 盘口失衡判断
- 超短期方向预测
- 滑点估计

当前时间语义约束：

- orderbook 优先使用交易所返回的事件时间
- 如果 `timestamp` 缺失，但 `datetime` 仍然可信，会继续使用该事件时间
- 如果事件时间整体缺失或损坏，这条 orderbook 快照会被直接跳过，不再回退成“当前时间”伪装成最新盘口

### 5. 资金费率 `funding_rates`

作用：给合约交易和跨市场择时提供多空拥挤度信息。

建议字段：

- `funding_rate`
- `mark_price`
- `index_price`
- `next_funding_time`
- `timestamp`

当前时间语义约束：

- funding 当前快照优先保存交易所返回的事件时间
- 如果 `timestamp` 缺失或损坏，会直接跳过该 funding 行，不再回退成“当前时间”伪装成最新拥挤度快照
- 历史 funding 回填同样会跳过缺失或损坏时间戳的行，避免把坏历史样本混进时间序列

### 6. 衍生品结构子模块

为了让 AI 更好识别“拥挤度、杠杆位置和被动/主动压力”，当前模块已经补了第二阶段的独立子模块，并且每个子模块都拆成单独目录维护：

- `trades/`
  - 采集逐笔成交并沉淀 `trade_flow_bars / latest_trade_flow_bars`
  - 给 AI 提供主动买卖方向、成交脉冲和短时 taker 压力
  - 只有方向可判定、且成交额可证明的真实成交才会进入聚合；`side` 缺失的成交不再被默认当成 `sell`，缺失 `price / amount / cost` 的成交也不再被压成 `0`
  - 如果某个 bar 没有任何可用成交，这个 bar 会被直接跳过，而不是伪装成“零主动买卖流”
  - `raw_payload_json` 会额外保留 `usable_trade_count / excluded_missing_side_count / excluded_missing_notional_count` 等诊断
- `taker_flow/`
  - 基于成交流归一化成主动买卖强弱视角
  - 当前与 `trades` 共享 `trade_flow_bars` 存储语义，避免重复表
- `open_interest/`
  - 采集持仓量快照并沉淀 `open_interest_snapshots / latest_open_interest_snapshots`
  - 用来判断加杠杆与去杠杆
  - 如果上游时间戳缺失或不可解析，会直接跳过该行，而不是回退成当前时间伪装成最新快照
  - 即使 source 级通过 AI-ready，bundle 仍会继续做行级过滤；既没有 `open_interest_usd` 也没有 `open_interest_contracts` 的真实行只会保留在 `raw_open_interest`
- `liquidations/`
  - 聚合清算压力并沉淀 `liquidation_bars / latest_liquidation_bars`
  - 用来判断被动平仓和 squeeze 风险
  - 如果 `open_time` 缺失或不可解析，会直接跳过该 bar，避免把坏时间写成“最新清算压力”
  - 缺失清算字段不会再被伪装成 `0`；只有总清算额明确存在，或多空两侧清算额都明确存在的真实行，才会进入 AI 主视图 `liquidations`
  - 字段缺失或只给出部分清算字段的真实行会继续保留在 `raw_liquidations`，并通过 `liquidations_quality_summary / liquidations_missing_metrics / liquidations_incomplete_metrics_present` 显式提示“未知”与“零清算压力”不是一回事
- `long_short_ratio/`
  - 采集多空比并沉淀 `positioning_snapshots / latest_positioning_snapshots`
  - 用来判断市场站位是否过于单边
  - 如果上游时间戳缺失或不可解析，会直接跳过该行，避免把低频背景因子伪装成当前切片
  - 即使 source 级通过 AI-ready，bundle 仍会继续做行级过滤；只给出单边账户比例/单边大户比例的真实行会保留在 `raw_positioning`
- `basis/`
  - 基于 `latest_tickers + latest_funding_rates` 计算 `basis_snapshots / latest_basis_snapshots`
  - 用来判断现货和合约的溢价状态
  - 当前实现会先把 `timestamp / next_funding_time` 统一标准化成 UTC naive 时间，避免调度过程中因 aware / naive 混用导致 basis 任务异常退出
  - 如果 `funding_timestamp` 本身坏掉，该行 basis 会被直接跳过，不再回退成“当前时间”伪装最新快照
  - 如果只有 `next_funding_time` 或 `ticker_timestamp` 语义异常，该行仍会保留真实价差，但 bundle 会显式输出 `basis_missing_ticker_timestamp / basis_component_time_gap_wide / basis_annualization_unavailable_present`
  - `basis` 现在还会进一步拆成 AI-visible `basis` 和诊断用 `raw_basis`；行级时间对齐不达标的真实 basis 不会继续混入主视图

## 为 AI 积累更多上下文样本的采集策略

对于 `ticker` 和 `orderbook`，标准 REST 接口通常不能像 K 线那样直接大规模回填历史，所以开发阶段要分两类处理：

### 可回填的

- `klines`
- `funding_rates`

### 只能从现在开始积累的

- `tickers`
- `orderbook_snapshots`

因此推荐做法是：

1. 先用 `bootstrap` 回填 K 线。
2. 再用 `funding-backfill` 回填最近 `30` 天资金费率。
3. 再用 `context-burst` 或长期 `scheduler` 高频积累 `ticker` 和 `orderbook` 样本。

## 默认更高频的上下文采样

当前调度默认值已经调整成更适合 AI 上下文积累的频率：

- `ticker_interval`: `5s`
- `orderbook_interval`: `3s`
- `funding_interval`: `15m`

也可以通过环境变量覆盖：

- `TICKER_INTERVAL_SECONDS`
- `ORDERBOOK_INTERVAL_SECONDS`
- `FUNDING_INTERVAL_SECONDS`

高频快照保留策略也支持通过环境变量覆盖：

- `TICKER_RETENTION_DAYS`
- `ORDERBOOK_RETENTION_DAYS`
- `FUNDING_RETENTION_DAYS`
- `EXCHANGE_DATA_CLEANUP_INTERVAL_SECONDS`

## 当前实现中的关键优化

为了让这个模块可以长期稳定跑，而不是只能偶尔手动执行一次，当前实现已经补上了几项基础优化：

- 调度线程隔离：
  - SQLite 连接和交易所客户端都按线程懒加载，避免 `scheduler` 模式下复用主线程对象导致跨线程访问错误。
- 市场信息缓存：
  - `market_info` 在同一进程内会复用已加载 markets，只有首次启动、显式 `force=True` 或到达低频刷新窗口时才会强制 reload。
- `ticker` 批量拉取优先：
  - 如果交易所支持 `fetchTickers`，会优先按交易所批量拉取目标交易对，再回退到单 symbol 接口。
- K 线游标增量更新：
  - 增量任务不再固定拉最近 `5` 根，而是从数据库中该 `exchange + symbol + timeframe` 的最新 `open_time` 往后追平，并保留少量重叠窗口修正最新未收盘区间。
- K 线按周期拆分调度：
  - `1m / 5m / 15m / 1h / 4h / 1d` 会分别按各自周期独立调度，而不是统一按一个固定间隔轮询。
- funding 分页回填：
  - 历史资金费率会按时间戳继续翻页，直到拿完为止，不再只请求第一页。
- funding 快照时间语义修正：
  - 当前资金费率优先保存交易所返回的事件时间戳，而不是仅使用本地采集时间。
  - 如果 funding `timestamp` 缺失或损坏，该行会被直接跳过，不再用本地时钟伪装成交易所事件时间。
- AI 最新上下文快照表：
  - 在保留历史表 `tickers / orderbook_snapshots / funding_rates` 的同时，还会同步维护 `latest_tickers / latest_orderbook_snapshots / latest_funding_rates`。
  - 这样下游 AI 模块读取“当前市场状态”时，不需要再扫描整张历史表取最新一条。
- 衍生品字段语义诚实化：
  - `open_interest / liquidations / positioning / basis` 都已经补上 source 级 AI-ready 之外的行级语义过滤。
  - `trade_flow` 现在也不再把缺失方向的真实成交默认归到 `sell`，也不再把缺失成交额的真实成交压成 `0`；只有可证明方向和成交额的真实成交才会进入 bar 聚合。
  - 真实但不完整、时间坏掉或不足以直接解释成“当前市场压力”的行，不会再混进 AI 主视图，而是保留在对应 `raw_*` 与 `*_quality_summary` 中。
- 现货上下文字段时间语义诚实化：
  - `ticker / orderbook / funding` 都不再把缺失或损坏的事件时间回退成“当前时间”伪装成最新快照。
  - 如果交易所仍给出可信的 `datetime` 事件时间，则会优先保留该真实时间，而不是为了严格跳过而白白丢样本。
- K 线字段语义诚实化：
  - `klines` 不再把缺失 `volume` 的行压成 `0`；任何缺少核心 OHLCV 字段的真实行都会被直接跳过。
- 旧历史样本自动迁移：
  - `DBManager.init_tables()` 会从已有历史表中回灌 `latest_*` 快照表，升级后不必等下一轮实时采集才有当前上下文。
- 最新快照按事件时间保护：
  - `latest_*` upsert 只会接受时间戳更晚的数据，避免 funding 历史回填或补数把更旧样本覆盖成“当前状态”。
- 调度容错显式化：
  - `coalesce`、`max_instances`、`misfire_grace_time` 已在 job 级别显式配置，避免网络轻微抖动时任务过早判定失约。
- 高频数据自动清理：
  - `tickers / orderbook_snapshots / funding_rates` 支持定时删除超过保留期的历史快照，避免 SQLite 长期膨胀。
- 面向技术指标模块的限界读取：
  - 下游 `technical_indicators` 在增量刷新时，只读取计算窗口需要的上下文快照，并额外保留每个交易所 cutoff 前最后一条锚点样本，不再全历史扫描。
- 熔断器保护：
  - 交易所 API 调用集成熔断器（`circuit_breaker.py`），连续失败 5 次后进入 OPEN 状态，60s 冷却后探测恢复。
  - 避免交易所宕机时反复重试浪费资源和级联失败。
  - 配置：`CB_FAILURE_THRESHOLD`（默认 5）、`CB_RECOVERY_TIMEOUT`（默认 60s）。
- HTTP 客户端升级：
  - `normalized_derivatives.py` 从 `urllib.request` 迁移到 `httpx`，支持连接池复用和 HTTP/2。
  - `liquidations/collector.py` 从 `requests` 迁移到 `httpx`，减少连接建立开销。

## 为什么这些数据适合 AI 量化

如果只有静态币种信息，AI 无法判断市场状态。至少要让它同时看到：

- 价格：`last_price`、`open/high/low/close`
- 成交：`volume_24h`、`quote_volume_24h`
- 流动性：`bid/ask`、`spread_bps`
- 微观结构：`bid_depth_notional`、`ask_depth_notional`、`depth_imbalance`
- 合约情绪：`funding_rate`

这能支持后续做下面几类特征：

- 趋势特征：收益率、均线偏离、突破
- 波动特征：ATR、振幅、标准差
- 流动性特征：成交额、价差、盘口厚度
- 结构特征：盘口不平衡、买卖盘压力
- 跨市场特征：同一币种多交易所价格差、成交量分布差异

## 模块代码树

下面代码树省略 `__pycache__` 等缓存目录，只保留维护这个模块最常用的源码文件：

```text
data_layer/
  README.md                      # 数据层总览文档
  exchange_data/
    README.md                    # 模块说明、运行方式与维护约束
    __init__.py                  # 模块包入口
    normalized_derivatives.py    # 衍生品标准化辅助工具
    client.py                    # 交易所客户端管理与线程内复用
    models.py                    # 交易所市场数据模型
    market_info.py               # 静态交易对信息采集
    ticker.py                    # 实时行情快照采集
    kline.py                     # K 线增量采集与历史回填
    orderbook.py                 # 盘口快照采集与深度特征计算
    funding.py                   # 资金费率采集与历史回填
    service.py                   # 模块编排、调度与清理任务
    runner.py                    # CLI 运行入口
    trades/
      README.md                  # 成交流子模块维护入口
      __init__.py
      collector.py
    taker_flow/
      README.md                  # 主动买卖流子模块维护入口
      __init__.py
      collector.py
    open_interest/
      README.md                  # 持仓量子模块维护入口
      __init__.py
      collector.py
    liquidations/
      README.md                  # 清算子模块维护入口
      __init__.py
      collector.py
    long_short_ratio/
      README.md                  # 多空比子模块维护入口
      __init__.py
      collector.py
    basis/
      README.md                  # basis 子模块维护入口
      __init__.py
      collector.py
```

## 当前运行模式

`runner.py` 当前支持 7 种模式：

- `bootstrap`
  - 初始化市场静态信息并回填历史 K 线
- `once`
  - 执行一次完整采集
- `scheduler`
  - 按调度配置长期运行（默认 `BlockingScheduler`，加 `--async-scheduler` 切换为 `AsyncIOScheduler`）
- `funding-backfill`
  - 单独回填历史资金费率
- `context-burst`
  - 高频循环采样 `ticker / funding / orderbook / trades`
- `derivatives-once`
  - 单独执行一轮衍生品结构采集
- `liquidations-repair`
  - 基于 `raw_payload_json` 修复旧版 `liquidations` 把未知字段写成 `0` 的历史污染

### 异步调度模式（推荐）

`scheduler` 模式支持通过 `--async-scheduler` 参数切换为 `AsyncIOScheduler`：

```bash
proxychains4 python -m data_layer.exchange_data.runner --mode scheduler --async-scheduler
```

优势：
- 利用 asyncio 事件循环，采集任务间无阻塞等待
- 配合 `collect_once_async()` 方法，独立采集任务并发执行
- 适合高频采集场景（ticker 5s / orderbook 3s），降低调度延迟

## 推荐开发阶段执行顺序

如果你的目标是尽快为 AI 训练积累可用样本，建议按下面顺序执行：

1. `bootstrap`
   - 先补静态市场信息和 K 线主时序
2. `funding-backfill`
   - 补最近 `30` 天或更长时间资金费率
3. `context-burst`
   - 连续跑几百轮，快速补 `ticker / orderbook` 快照
4. `scheduler`
   - 长期运行，持续沉淀真实市场上下文

这样做的核心原因是：

- K 线和资金费率可以回填
- `ticker` 和 `orderbook` 只能从当前开始积累
- 逻辑处理层的综合特征现在已经会用到这三类上下文数据

## 运行方式

初始化并执行一次完整采集：

```bash
python -m data_layer.exchange_data.runner --mode once
```

如果你要通过 `proxychains4` 访问交易所：

```bash
proxychains4 python -m data_layer.exchange_data.runner --mode once --skip-backfill
```

启动长期调度：

```bash
proxychains4 python -m data_layer.exchange_data.runner --mode scheduler
```

快速积累 `ticker / funding / orderbook` 上下文样本：

```bash
proxychains4 python -m data_layer.exchange_data.runner --mode context-burst --cycles 300 --interval-seconds 3 --funding-every 20 --funding-history-days 30
```

只回填历史资金费率：

```bash
proxychains4 python -m data_layer.exchange_data.runner --mode funding-backfill --funding-history-days 30
```

修复旧库里被旧版 collector 写坏的清算字段语义：

```bash
python -m data_layer.exchange_data.runner --mode liquidations-repair
```

这个修复只会依据数据库里已经保存的 `raw_payload_json` 回写 `liquidation_bars / latest_liquidation_bars`：

- 如果原始 payload 明确给出 `0`，会继续保留真实零值
- 如果原始 payload 缺失该字段，旧库里的伪 `0` 会被还原成 `NULL`
- 如果 `raw_payload_json` 本身不包含清算字段，就不会猜测修复

## 编排入口

- `ExchangeClientManager`：统一管理交易所客户端，按线程维护懒加载缓存。
- `MarketInfoCollector`：低频静态信息同步，带进程内 markets 缓存。
- `TickerCollector`：实时行情与 24h 成交量/成交额，优先批量接口。
- `KlineCollector`：历史回填、按数据库游标增量更新、按周期拆分调度。
- `OrderBookCollector`：盘口前 N 档快照和深度特征。
- `FundingRateCollector`：合约市场资金费率，支持分页回填。
- `ExchangeDataService`：模块级统一编排。
- `runner.py`：模块级命令行入口。

新增能力：

- `backfill_funding_history(days)`：回填历史资金费率。
- `collect_market_context_burst(...)`：短周期循环采样，快速积累 `ticker / funding / orderbook` 样本。
- `cleanup_historical_data()`：清理超过保留期的高频历史快照。

## 数据表与样本积累说明

### `tickers`

- 默认每 `5s` 采一轮
- 优先按交易所批量获取目标交易对，减少高频 REST 请求数
- 历史表 `tickers` 用于时间序列回看，`latest_tickers` 用于 AI / 对比模块直接读取当前市场横截面
- 适合积累跨交易所价格、价差、24h 成交额等上下文

### `klines`

- 增量采集会优先参考数据库中的最新 `open_time`
- 会自动保留少量重叠区间，减少最新几根 candle 因未收盘而产生的脏数据
- `1m / 5m / 15m / 1h / 4h / 1d` 在调度器中分开运行，避免长周期重复无效更新
- 比固定拉最近若干根更适合长期调度和断点续跑

### `orderbook_snapshots`

- 默认每 `3s` 采一轮
- 支持按保留期自动清理旧快照
- 历史表 `orderbook_snapshots` 保留微观结构演变，`latest_orderbook_snapshots` 提供当前可直接消费的盘口状态
- 适合积累盘口厚度、价差、深度不平衡等微观结构特征

### `funding_rates`

- 默认每 `15m` 采一轮
- 当前快照优先使用交易所事件时间
- 也支持按时间戳分页历史回填，适合补衍生品情绪特征
- 历史表 `funding_rates` 用于回看和并表，`latest_funding_rates` 用于当前拥挤度语境
- 同样支持按保留期清理旧快照

### 对逻辑层的影响

逻辑处理层 `technical_indicators` 现在会将 `ticker / funding / orderbook` 作为市场上下文特征一起并表，因此数据层越稳定、越高频，后续 AI 特征质量越高。

同时现在又多了一层对 AI 更友好的读取方式：

- `technical_indicators` 走“历史表 + 增量窗口限界读取”，保留时间对齐能力
- `exchange_comparison` 走 `latest_*` 快照表，直接读取当前市场横截面
- 两条链路共享同一份采集结果，但分别针对“时序特征”和“当前上下文”优化

如果从 AI 最终消费视角看，`exchange_data` 现在主要负责两件事：

- 给 `technical_indicators` 和 `exchange_comparison` 提供市场微观结构输入
- 与 `news_articles`、`macro_context` 一起拼成更完整的分析上下文，而不是单独承担全部市场解释

## AI 最新 bundle 的质量增强

`load_latest_market_context_bundle()` 现在除了返回各个原始 section，还会同时输出一组明确区分“AI 直接可见载荷”和“真实原始诊断”的质量字段。

需要先明确当前 bundle 的边界：

- `spot / orderbook / funding / trade_flow / open_interest / liquidations / positioning / basis`
  - 这里只保留 `is_ready_for_ai=true` 的真实市场快照
  - 不会把覆盖不完整、stale 或语义不够完整的 source 继续直接暴露给 AI
- `raw_open_interest / raw_positioning / raw_basis`
  - 这里保留“source 本身是真的、但某些行的数值语义还不够完整”的真实快照
  - 这类行不会被删除，只是不再直接混入 AI 主视图
- `raw_as_of / raw_row_count / raw_source_counts / ai_excluded_sources / source_health`
  - 这里保留“真实存在但当前还不适合直接给 AI 用”的原始市场来源
  - 这些字段不会伪造补值，只会明确告诉下游：哪些来源被排除、为什么排除、原始快照还剩多少
- `trade_flow_scope / coverage_summary / cross_exchange_diagnostics / data_quality_flags / quality_notes`
  - 这些 symbol 级诊断仍然基于真实原始快照计算
  - 这样即使某个 source 暂时不 AI-ready，也不会被误判成“市场里完全没这类数据”

### `configured_universe_summary`

- `tracked_symbols / tracked_exchanges`
  - 当前 bundle 默认是基于哪些目标资产和目标交易所生成的
- `asset_count / exchange_count`
  - 当前默认市场宇宙实际宽度
- `minimum_asset_count_for_market_breadth / minimum_exchange_count_for_market_breadth`
  - 用来判断“这份市场数据更像核心执行监控，还是已经够宽可做更广市场 breadth 观察”的建议门槛
- `breadth_status / is_market_breadth_sufficient`
  - 默认宇宙过窄时会显式标记 `limited`

需要强调：

- 这层不是补值，也不是伪造更多市场数据
- 它只是把当前默认采集宇宙有多宽结构化暴露出来
- 如果默认只覆盖少数核心资产和交易所，AI 应把它理解为“核心执行市场视角”，而不是“全市场 breadth 已足够”

### `coverage_summary`

- `configured_section_coverage_ratio`
  - 当前 symbol 在所有已配置 section 上的平均交易所覆盖率
- `complete_sections / partial_sections / missing_sections / stale_sections / unconfigured_sections`
  - 直接告诉 AI：哪些 section 是完整的，哪些不完整，哪些根本缺失，哪些虽然有但已经 stale
- `section_statuses`
  - 每个 section 都会给出：
  - `exchange_count / coverage_ratio`
  - `observed_exchanges / missing_exchanges`
  - `freshest_timestamp / oldest_timestamp`
  - `freshest_age_seconds / oldest_age_seconds`
  - `stale_exchange_count`

### `cross_exchange_diagnostics`

- `spot_last_price_range_bps`
- `spot_mid_price_range_bps`
- `orderbook_mid_price_range_bps`
- `funding_mark_price_range_bps`
- `basis_range_bps`
- `max_derivatives_core_time_gap_seconds`

这组字段不替 AI 下判断，但会告诉 AI 当前不同交易所之间的快照离散度到底有多大。

### `derivatives_core_alignment`

- 这是 symbol 级新增的核心衍生品时间切片诊断
- 只检查 `funding / open_interest / basis`
  - 因为这三组字段最容易被直接拼成“当前合约拥挤状态”
- `status`
  - `ready / partial / wide / insufficient / missing`
- `wide_exchange_names / partial_exchange_names / insufficient_exchange_names`
  - 明确列出哪些交易所虽然有真实数据，但时间切片不够同步，或者核心三元组仍不完整
- `pair_summaries`
  - 分别统计 `funding_vs_open_interest / funding_vs_basis / open_interest_vs_basis`
  - 会给出可比较交易所数量、超阈值数量和最大时间差

这层不会伪造同步时间，也不会删掉真实数据；它只是防止 AI 把“真的存在但不同步”的衍生品字段误当成同一瞬时市场状态。

### `data_quality_flags / quality_notes`

当前会显式标记下面几类问题：

- `missing_*`
- `*_exchange_coverage_incomplete`
- `exchange_configured_market_breadth_limited`
- `stale_subsection_present`
- `missing_orderbook_for_some_spot_exchanges`
- `missing_trade_flow_derivatives_for_some_funding_exchanges`
- `basis_missing_spot_price`
- `open_interest_missing_value`
- `positioning_missing_metrics`
- `positioning_incomplete_metrics_present`
- `funding_missing_mark_or_index_price`
- `ticker_crossed_market_present`
- `orderbook_crossed_book_present`
- `derivatives_core_time_gap_wide`

这层增强的目标很直接：不要让 AI 把“结构不完整、交易所不齐、时间不新鲜、字段不完整”的快照误当成完整市场事实。

### `raw_* / ai_excluded_* / source_health`

- `raw_as_of / raw_row_count / raw_source_counts`
  - bundle 里全部真实原始快照的最新时间和数量统计
- `ai_ready_source_names / ai_excluded_source_names`
  - 当前哪些 source 已达到 AI 直用门槛，哪些虽然采到了但被排除
- `ai_excluded_sources`
  - source 级排除清单，会显式给出 `excluded_reason / raw_row_count / raw_symbol_count / raw_symbols / semantic_scope / data_quality_flags / quality_notes`
- `source_health_summary / source_health`
  - 当前 source 总数、ready 数、AI-ready 数，以及每路 source 自身的健康状态
- 每个 `symbol`
  - 还会额外暴露 `row_count / raw_row_count / source_counts / raw_source_counts / ai_ready_source_names / ai_excluded_source_names`

这一层的目标不是给 AI 直接喂更多脏数据，而是让运维、检查器和后续扩展模块能继续看到真实市场数据到底采到了什么、为什么没进 AI 主载荷。

## 后续扩展规划

当前版本先统一接入 ccxt 的标准接口，后续可以按下面方向扩展，而不破坏现在的目录结构：

### Phase 2

- 增加 `trades` 明细成交采集
- 增加 `open_interest`、`long_short_ratio`、`liquidation` 等合约数据
- 增加更多交易所，如 Coinbase、Kraken、Bitget、Gate

### Phase 3

- 为高频场景增加 WebSocket 实时流
- 将盘口和成交拆到独立高频存储
- 增加跨交易所统一时间同步和补数机制

### Phase 4

- 将 `exchange_data` 作为“市场数据总线”的一个子模块
- 对接链上数据、新闻情绪、宏观数据，进入更完整的数据层体系

## 更新日志

### v1.1.0 (2026-05-05)

- 补充 `data_layer` 层级说明
- 为 `exchange_data` 增加模块级运行入口
- 扩展行情、盘口、资金费率和市场静态信息字段
- 数据库初始化支持旧表自动补齐新增字段

### v1.2.0 (2026-05-05)

- 提高默认 `ticker / funding / orderbook` 调度频率
- 增加 `funding-backfill` 历史资金费率回填
- 增加 `context-burst` 高频上下文采样模式
- 为逻辑处理层的上下文特征并表准备更稳定的数据积累路径

### v1.3.0 (2026-05-06)

- 为数据库连接和交易所客户端增加线程隔离，修复调度模式下的资源复用风险
- `ticker` 采集优先使用交易所批量接口，降低高频轮询的请求开销
- K 线增量改成基于数据库游标的断点续拉，并保留重叠窗口修正最新区间
- funding 历史回填支持分页，当前 funding 快照优先写入交易所事件时间
- 调度任务显式配置 `coalesce / max_instances / misfire_grace_time`

### v1.4.0 (2026-05-06)

- `market_info` 增加进程内缓存，减少重复 `load_markets(reload=True)` 开销
- K 线任务按 `timeframe` 拆分调度，降低长周期无效轮询
- 增加高频快照保留策略与自动清理任务，控制 SQLite 长期体积增长
- 为高频时间戳字段补充清理友好的索引

### v1.5.0 (2026-05-06)

- 增加 `latest_tickers / latest_orderbook_snapshots / latest_funding_rates`，为 AI 和横截面对比模块提供 O(1) 风格的当前市场上下文读取
- 采集写库改成“历史样本追加 + 最新快照 upsert”双写模式
- `latest_*` 快照按事件时间戳保护，避免历史回填覆盖更晚的当前状态
- 数据库初始化会自动从已有历史表回灌 `latest_*`，降低升级迁移成本
- `technical_indicators` 的上下文读取改成按增量计算窗口限界读取，避免高频快照表全历史扫描

### v1.6.0 (2026-05-08)

- 新增 `load_source_coverage()`，统一暴露 `configuration_ready / health_status / is_ready_for_ai / quality_notes`
- `runner.py` 新增 `--print-coverage`，可以直接检查 source 覆盖、最近运行状态和新鲜度
- 调度器里的 `market_info / kline / ticker / funding / orderbook / trade_flow / open_interest / liquidations / long_short_ratio / basis` 现在都会写入 `collection_runs`
- `trade_flow` 在 AI bundle 和 coverage 中显式标记 `semantic_scope=spot_only`
- `liquidations / long_short_ratio` 在 URL 未配置时会直接显示为 `unconfigured`，不再和空数据混淆
- `open_interest` 新增 `5m / 1h / 24h` 变化字段回填
- `basis` 的 `interval` 字段改为独立使用 `EXCHANGE_BASIS_INTERVAL`

### v1.7.0 (2026-05-08)

- `funding / open_interest / trade_flow` 改为显式走 swap client，避免衍生品 source 误用 spot market 配置
- `trade_flow` 现在会同时采集现货与线性合约逐笔成交，并统一写入 `trade_flow_bars / latest_trade_flow_bars`
- `load_latest_market_context_bundle()` 在 `trade_flow` 同时存在 spot 和 derivatives 时，兼容字段会优先返回 derivatives
- `load_source_coverage()` 的 `trade_flow.semantic_scope` 改为动态计算：`spot_only / derivatives_only / mixed / missing`
- `trade_flow` coverage 新增 `latest_market_type_count / latest_spot_pair_count / latest_derivatives_pair_count`

### v1.8.0 (2026-05-11)

- `load_latest_market_context_bundle()` 新增 `coverage_summary / cross_exchange_diagnostics / data_quality_flags / quality_notes`
- 每个 symbol 现在会显式暴露 section 级 `exchange_count / coverage_ratio / missing_exchanges / stale_exchange_count`
- bundle 新增跨交易所离散度和结构异常诊断，例如 `spot_last_price_range_bps`、`orderbook_crossed_book_present`、`basis_missing_spot_price`
- `load_source_coverage()` 新增 `latest_coverage_ratio / latest_missing_pair_count / latest_stale_pair_count / latest_non_stale_coverage_ratio / coverage_gaps`
- `trade_flow` coverage 进一步拆成现货和合约两个维度，分别暴露 `latest_spot_coverage_ratio / latest_derivatives_coverage_ratio`

### v1.9.0 (2026-05-15)

- `load_source_coverage()` 的 `is_ready_for_ai` 不再等同于 `health_status=ready`
- 现在只有在 `latest_non_stale_coverage_ratio=1.0`、没有 `exchange_coverage_incomplete / stale_pairs_present` 等关键缺陷时，source 才会被标成 `is_ready_for_ai=true`
- `trade_flow` 额外要求合约维度真实存在且覆盖完整；`spot_only` 或合约覆盖不完整都不会再被视为 AI-ready
- source coverage 新增 `ready_for_ai_source_count / not_ready_for_ai_source_count`

### v1.10.0 (2026-05-16)

- `load_latest_market_context_bundle()` 新增 `configured_universe_summary`
- 当前默认 `TARGET_SYMBOLS / TARGET_EXCHANGES` 宇宙如果仍偏窄，会显式追加 `exchange_configured_market_breadth_limited`
- 这层诊断不补假数据，只告诉 AI：当前交易所数据更适合核心执行市场监控，还是已经足够承担更广市场 breadth 观察

### v1.11.0 (2026-05-17)

- `load_latest_market_context_bundle()` 现在会严格把 AI 主载荷和原始真实诊断分开
- `spot / orderbook / funding / trade_flow / open_interest / liquidations / positioning / basis` 这些 section 只保留 `is_ready_for_ai=true` 的真实快照
- 非 AI-ready 的真实市场来源不会被删除，而是保留在 `raw_as_of / raw_row_count / raw_source_counts / ai_excluded_sources / source_health`
- symbol 级的 `trade_flow_scope / coverage_summary / cross_exchange_diagnostics / data_quality_flags / quality_notes` 继续基于真实原始快照计算，避免把“已采到但暂不达标”的 source 误判成完全缺失
- symbol 级新增 `row_count / raw_row_count / source_counts / raw_source_counts / ai_ready_source_names / ai_excluded_source_names`，方便后续检查当前 AI 实际看到了什么，以及还有哪些真实数据被质量门槛挡在外面

## 数据质量与覆盖检查

查看当前 source 覆盖率：

```bash
python -m data_layer.exchange_data.runner --print-coverage
```

重点字段说明：

- `configuration_ready`
  - 该 source 是否具备运行所需配置
- `health_status`
  - `ready / stale / error / empty / missing / unconfigured / disabled`
- `is_ready_for_ai`
  - 当前 source 是否可直接作为 AI 市场判断输入
  - `health_status=ready` 只表示最近一次运行成功且快照未整体过期，不代表覆盖已经足够 AI 直接使用
  - 当前实现要求至少满足：`latest_non_stale_coverage_ratio=1.0`，且不存在 `exchange_coverage_incomplete / stale_pairs_present` 等关键质量缺陷
- `semantic_scope`
  - 用来描述“这份数据到底覆盖了什么语义范围”
- `latest_coverage_ratio`
  - 当前 source 对目标 `symbol x exchange` 的实时覆盖比例
- `latest_missing_pair_count`
  - 当前还缺多少个目标 `symbol|exchange`
- `latest_undercovered_symbol_count / latest_missing_symbol_count`
  - 还有多少目标 symbol 没覆盖满，或者完全没有数据
- `latest_stale_pair_count / latest_non_stale_coverage_ratio`
  - 当前 source 里有多少 pair 已经超过采样窗口，扣掉 stale pair 之后还剩多少真实可用覆盖
- `coverage_gaps`
  - 明确列出每个 symbol 还缺哪些交易所
- `data_quality_flags`
  - source 级别的覆盖不足、stale pair、trade_flow 语义不足等告警
- `quality_notes`
  - 用来显式记录当前 source 的已知局限
- `ready_for_ai_source_count / not_ready_for_ai_source_count`
  - 当前 source 列表里，真正达到 AI 可直接消费门槛的来源数量，以及尚未达到门槛的来源数量

`trade_flow` 还有额外字段：

- `latest_spot_coverage_ratio / latest_derivatives_coverage_ratio`
- `latest_spot_missing_pair_count / latest_derivatives_missing_pair_count`
- `spot_coverage_gaps / derivatives_coverage_gaps`

这些字段可以帮助 AI 或上游检查器区分：

- trade_flow 本身有数据
- 但只有现货，没有合约
- 或者现货/合约都存在，但覆盖交易所并不对称

需要强调：

- 这些质量字段全部来自数据库中的 `latest_*` 真实快照
- 不会用插值、默认值或伪造价格去“补齐”缺失交易所
- 缺什么就明确告诉下游缺什么

当前需要特别注意：

- `trade_flow_scope=spot_only` 时，说明当前仍然只有现货成交流，缺少合约逐笔成交维度。
- 这时即使 `health_status=ready`，`is_ready_for_ai` 也会是 `false`，因为对交易判断更关键的合约主动买卖流还没有补齐。
- `trade_flow_scope=mixed` 时，说明现货和合约成交流都已存在，读取时应结合 `market_type` 区分语义。
- 兼容字段 `trade_flow` 会优先返回 derivatives；更严格的读取方式仍然应该分别读取 `trade_flow_spot / trade_flow_derivatives`。
- `liquidations` 和 `long_short_ratio` 现在已改为通过 ccxt 直接采集，不再依赖额外 URL 配置。
- `open_interest / liquidations / long_short_ratio` 现在会统一把合法时间戳标准化成 UTC-naive；如果时间字段缺失或损坏，会直接跳过该行，而不是回退成本地当前时间伪装成最新快照。
- `basis` 现在会对 `funding_timestamp / next_funding_time` 分别做 UTC-naive 归一化；如果上游只污染了 `next_funding_time`，该行 basis 快照仍会保留真实价格与 funding 数据，只降级 `annualized_basis_bps`，不会因为单条脏时间字段打断整批 basis 采集。
- 如果 `funding_timestamp` 自身缺失或无法解析，该行 basis 现在会被直接丢弃，避免把坏时间戳回退成“当前最新”。
- `basis` 现在还会把 `ticker_timestamp_status / component_timestamp_gap_seconds / annualization_status` 沉淀到原始诊断里，并在 symbol 级 `data_quality_flags / quality_notes` 和 source coverage 中显式暴露时间对齐问题。
- `basis` 在 source 级通过 `is_ready_for_ai` 之后，仍然会继续做行级可见性过滤；真正给 AI 的 `basis` 只保留时间语义也可信的行，其余真实 basis 会保留在 `raw_basis / basis_quality_summary`。
- bundle 现在还会额外输出 `derivatives_core_alignment`，专门审计 `funding / open_interest / basis` 是否仍落在同一可联合解释的时间切片；如果核心时间差过大，会显式输出 `derivatives_core_time_gap_wide`，而不是让 AI 静默混用这些字段。

### v1.12.0 (2026-05-28)

- `liquidations/collector.py` 重写为 ccxt 直接采集模式
  - 通过 `ExchangeClientManager` 调用 `fetch_liquidations()`
  - 覆盖 Binance / OKX / Bybit × TARGET_SYMBOLS
  - 按 5 分钟窗口聚合 long/short/total notional
  - 不再依赖 `NormalizedDerivativesClient` 和外部 URL 配置
- `long_short_ratio/collector.py` 重写为 ccxt 直接采集模式
  - 通过 `ExchangeClientManager` 调用 `fetch_long_short_ratio_history()`
  - 1h 粒度，48h 回溯窗口
  - 不再依赖 `NormalizedDerivativesClient` 和外部 URL 配置
