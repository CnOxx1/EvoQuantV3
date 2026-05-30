# 交易所对比模块 `exchange_comparison`

## 模块定位

`exchange_comparison` 属于逻辑处理层，目标不是做一张“交易所价格展示表”，而是把多个交易所的同标的数据整理成 AI 可直接消费的横截面状态特征。

这个模块当前聚焦三个问题：

- 同一交易对在不同交易所之间是否存在真实可交易的净价差
- 当前应该优先在哪家交易所买、在哪家交易所卖
- 当前价差是机会、流动性假信号，还是数据质量异常

它不直接连接交易所，也不负责下单。它只读取数据库中的上游表，做时间对齐、差异计算、质量标记和结果落库。

## 快速导航

- [模块速览](#模块速览)
- [AI 文档维护约束](#ai-文档维护约束)
- [为什么这个模块对 AI 很重要](#为什么这个模块对-ai-很重要)
- [当前已实现范围](#当前已实现范围)
- [模块代码树](#模块代码树)
- [核心处理流程](#核心处理流程)
- [输出表](#输出表)
- [当前计算逻辑](#当前计算逻辑)
- [数据质量与信号规则](#数据质量与信号规则)
- [运行方式](#运行方式)
- [当前实现状态](#当前实现状态)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 核心任务 | 把多交易所同标数据整理成 AI 可直接消费的横截面执行语境 |
| 主要输入 | `latest_tickers / latest_orderbook_snapshots / latest_funding_rates / market_info / technical_indicators` |
| 关键动作 | 最近邻时间对齐、净价差计算、深度与费用比较、质量标记 |
| 输出表 | `exchange_comparison_snapshots` |
| AI 主价值 | 解释“哪里更贵、哪里更深、价差是否真实可交易” |
| 质量原则 | 只使用窗口内真实样本，不让 stale ticker/orderbook/funding 继续冒充当前横截面 |

## AI 文档维护约束

这份 README 是后续 AI 开发和维护 `exchange_comparison` 时的工作文档，不只是功能介绍。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 对齐窗口、比较逻辑、输出字段、数据质量规则或信号规则
- 输入表依赖、AI 直接消费特征或实现边界
- 当前运行方式、测试覆盖或扩展计划

## 为什么这个模块对 AI 很重要

只给 AI 一家交易所的 K 线、ticker 或深度是不够的。

AI 真正更需要的是：

- 哪个交易所更贵
- 哪个交易所更便宜
- 哪个交易所更深
- 当前价差扣费和滑点后是否仍成立
- 当前偏离是否可能只是薄盘口或数据延迟

`exchange_comparison` 的核心价值就是把这些“跨交易所执行语境”直接结构化成特征行。

## 当前已实现范围

当前实现的是第一阶段 MVP，但已经是可运行版本，不只是方案文档。

### 已接入输入

- `latest_tickers`
  - 提供 `last_price / bid / ask / mid_price / spread_bps / quote_volume_24h`
- `latest_orderbook_snapshots`
  - 提供当前最新 `best_bid / best_ask / mid_price / spread_bps / depth / imbalance`
- `orderbook_snapshots`
  - 提供 `best_bid / best_ask / depth / imbalance`
- `latest_funding_rates`
  - 提供当前最新 `funding_rate / mark_price / index_price`
- `funding_rates`
  - 提供 funding 最近邻对齐候选集
- `market_info`
  - 提供 `maker_fee / taker_fee / market_type`
- `technical_indicators`
  - 提供 `rsi / macd / atr_pct / volatility / adx / zscore` 等市场背景特征

### 当前不做

- `klines` 历史偏离序列
- 历史聚合 bars
- lead-lag / 统计套利 / 自动执行

## 模块代码树

下面代码树省略 `__pycache__` 等缓存目录，只保留维护这个模块最常用的源码文件：

```text
logic_layer/
  exchange_comparison/
    README.md                    # 模块说明、输出特征与维护约束
    __init__.py                  # 模块包入口
    models.py                    # 配置模型与输出快照模型
    aligner.py                   # ticker / orderbook / funding 时间对齐
    comparator.py                # 价差、流动性与执行特征计算
    repository.py                # 上游读取与结果落库
    service.py                   # 模块编排入口
    runner.py                    # CLI 运行入口
```

各文件职责：

- `models.py`
  - 定义配置模型 `ExchangeComparisonConfig`
  - 定义输出模型 `ExchangeComparisonSnapshot`
- `aligner.py`
  - 把 `ticker + orderbook + funding + market_info + indicator context` 对齐成每交易所单行快照
- `comparator.py`
  - 生成规范交易所对并计算价格、流动性、净价差、资金费率背景和市场 regime 特征
- `repository.py`
  - 读取 `latest_tickers`
  - 读取 `latest_orderbook_snapshots` + 回看窗口内 `orderbook_snapshots`
  - 读取 `latest_funding_rates` + 回看窗口内 `funding_rates`
  - 读取 `market_info`
  - 读取 `technical_indicators`
  - 写入 `exchange_comparison_snapshots`
- `service.py`
  - 模块总入口
- `runner.py`
  - CLI 运行入口

## 核心处理流程

### 1. 读取最新 ticker

模块优先从 `latest_tickers` 读取每个 `symbol + exchange` 的当前最新 ticker 快照，作为当前横向对比的基准时刻。

这样做的目的不是单纯提速，而是给 AI 一个明确的“当前市场横截面”入口，避免每次都去历史表里做最新值聚合。

### 2. 读取 orderbook 候选集

模块会读取：

- `latest_orderbook_snapshots` 中每个 `symbol + exchange` 的最新 orderbook
- 回看窗口内的 orderbook 候选快照

这样做的原因是：

- 如果最新盘口恰好比 ticker 晚或早几秒，可以做最近邻匹配
- 如果盘口整体陈旧，仍能识别为 stale，而不是完全丢失上下文
- AI 既能看到“当前盘口状态”，也能看到与 ticker 最近邻的可对齐样本

### 3. 最近邻时间对齐

`aligner.py` 使用最近邻时间匹配，将 orderbook、funding 和技术背景对齐到 ticker：

- 默认 `orderbook_window_seconds = 5`
- 默认 `funding_window_seconds = 1800`
- 默认 `max_indicator_age_seconds = 21600`
- `orderbook / funding / technical_indicators` 都只允许使用不晚于当前 ticker 的历史样本
- 超出对应窗口则视为当前上下文缺失，而不是继续拖尾旧样本

同时会并入：

- `taker_fee / maker_fee`
- `market_type`
- `technical_indicators` 的 symbol 级背景特征

### 4. 生成规范交易所对

同一 `symbol` 下按交易所名称字典序生成唯一 pair：

- `binance - bybit`
- `binance - okx`
- `bybit - okx`

只保存一套方向，不会同时写入 `A-B` 和 `B-A` 两条镜像记录。

但在单行内部，会同时计算：

- `A sell / B buy`
- `B sell / A buy`

## 输出表

### `exchange_comparison_snapshots`

一行表示：

- 同一 `symbol`
- 同一对齐窗口
- 一个规范交易所对

### 关键字段分组

#### 标识字段

- `symbol`
- `exchange_a`
- `exchange_b`
- `compare_window_seconds`
- `timestamp`

这里实际实现使用 `exchange_a / exchange_b`，没有用 `base_exchange / quote_exchange`，目的是避免和交易对里的 `base / quote` 语义混淆。

#### 时间与对齐字段

- `ticker_timestamp_a`
- `ticker_timestamp_b`
- `orderbook_timestamp_a`
- `orderbook_timestamp_b`
- `funding_timestamp_a`
- `funding_timestamp_b`
- `inter_exchange_ticker_gap_ms`
- `inter_exchange_funding_gap_ms`

#### 价格输入字段

- `last_price_a`
- `last_price_b`
- `mid_price_a`
- `mid_price_b`
- `bid_a`
- `ask_a`
- `bid_b`
- `ask_b`

#### 流动性输入字段

- `spread_bps_a`
- `spread_bps_b`
- `quote_volume_24h_a`
- `quote_volume_24h_b`
- `bid_depth_notional_a`
- `bid_depth_notional_b`
- `ask_depth_notional_a`
- `ask_depth_notional_b`
- `depth_imbalance_a`
- `depth_imbalance_b`

#### 衍生品上下文字段

- `funding_rate_a`
- `funding_rate_b`
- `mark_price_a`
- `mark_price_b`
- `index_price_a`
- `index_price_b`
- `funding_rate_diff_abs`
- `funding_rate_diff_bps`
- `mark_price_diff_bps`
- `index_price_diff_bps`

#### 差异与机会字段

- `last_diff_abs`
- `last_diff_bps`
- `mid_diff_abs`
- `mid_diff_bps`
- `bid_diff_bps`
- `ask_diff_bps`
- `cross_spread_ab_bps`
- `cross_spread_ba_bps`
- `estimated_fee_bps`
- `estimated_slippage_ab_bps`
- `estimated_slippage_ba_bps`
- `estimated_slippage_bps`
- `net_cross_spread_ab_bps`
- `net_cross_spread_ba_bps`
- `net_cross_spread_max_bps`

#### 横截面特征字段

- `quote_volume_ratio`
- `bid_depth_ratio`
- `ask_depth_ratio`
- `total_depth_ratio`
- `spread_bps_gap`
- `depth_imbalance_gap`

#### 技术背景字段

- `context_timeframe`
- `context_open_time`
- `context_age_seconds`
- `context_close`
- `context_rsi_14`
- `context_macd_hist`
- `context_atr_pct_14`
- `context_volatility_20`
- `context_adx_14`
- `context_bb_width`
- `context_price_zscore_20`
- `context_volume_ratio_20`
- `context_cross_exchange_last_price_range_bps`
- `context_funding_basis_bps_mean`
- `context_orderbook_total_depth_notional`

#### 决策字段

- `best_buy_exchange`
- `best_sell_exchange`
- `opportunity_type`
- `signal_label`
- `signal_strength`
- `is_actionable`
- `anomaly_score`
- `execution_preference_score`
- `market_regime_label`
- `funding_regime_label`
- `context_completeness_score`
- `data_quality_flag`

#### 调试字段

- `raw_context_json`
  - 当前会额外保留 `indicator_context_alignment_gap_ms`
  - 用来解释当前 symbol 级技术背景距离 ticker 基准时刻到底有多远

## 当前计算逻辑

### 1. 价格偏离

当前直接输出：

- `last` 偏离
- `mid` 偏离
- `bid` 偏离
- `ask` 偏离

其中 `mid_diff_bps` 是最核心的横向价格偏离特征。

### 2. 可交易价差

模块不会只比较 `last_price`，而是优先比较真正能成交的双边报价：

- `cross_spread_ab_bps`
  - 在 `exchange_a` 卖、`exchange_b` 买
- `cross_spread_ba_bps`
  - 在 `exchange_b` 卖、`exchange_a` 买

### 3. 手续费估算

优先使用 `market_info.taker_fee`：

- 如果存在 `taker_fee`，直接使用
- 如果没有 `taker_fee`，回退到 `maker_fee`
- 如果仍缺失，使用 `config.default_taker_fee_rate`

当前默认两腿都按 taker 执行估算，因为这是更保守、也更接近真实落地的做法。

### 4. 滑点估算

当前滑点不是逐档回放，而是轻量启发式估算：

- 以 `target_notional` 作为目标成交额
- 使用卖出腿 `bid_depth_notional` 与买入腿 `ask_depth_notional`
- 根据深度压力和本地 spread 增加经验惩罚

这样做的目的不是得到精确成交回测，而是先给 AI 一条稳定的“执行难度特征”。

### 5. 净价差

最终核心字段：

- `net_cross_spread_ab_bps`
- `net_cross_spread_ba_bps`
- `net_cross_spread_max_bps`

其中：

- `gross spread`
- 减去 `estimated_fee_bps`
- 再减去方向性 `estimated_slippage`

这比单看交易所间价差更接近真实交易环境。

### 6. funding 背景

当 `market_type` 设为 `swap / future` 时，模块会尝试并入 funding 上下文：

- `funding_rate_diff_bps`
- `mark_price_diff_bps`
- `index_price_diff_bps`
- `funding_regime_label`

这样 AI 不只是看到“现在有价差”，还能看到这个价差是否发生在资金费率分化、方向拥挤冲突或 basis 偏离环境里。

### 7. 技术背景

模块不会再简单读取“最新一行” `technical_indicators` 作为 symbol 级背景。

当前实现已经改成：

- 先按 `symbol + timeframe` 读取 `as_of - max_indicator_age_seconds` 窗口内的候选行
- 额外保留 cutoff 前最后一条 anchor 行，避免漏掉刚好跨窗边界但仍可能可用的背景
- 再按每个 ticker 的时间做 `merge_asof(direction="backward")`
- 只允许使用 `ticker_timestamp` 之前、且不超过 `max_indicator_age_seconds` 的指标背景
- 未来时间的指标行不会泄漏进当前横截面对比
- 超过 freshness 窗口的旧技术背景会被剥离为 `missing_indicator_context`

当前会并入的背景特征包括：

- `context_rsi_14`
- `context_macd_hist`
- `context_atr_pct_14`
- `context_volatility_20`
- `context_adx_14`
- `context_price_zscore_20`
- `context_volume_ratio_20`

并进一步生成：

- `market_regime_label`
- `context_completeness_score`

这类字段不是替代 AI，而是把“当前机会所处的市场背景”先结构化出来。

这样做的目的，是确保 symbol 级背景代表的是“当前横截面真正还能成立的 merged-kline regime”，而不是“数据库里最近一次算出来的任意一行”。

## 数据质量与信号规则

### 数据质量标记

当前会标记的主要问题：

- `missing_ticker_a / missing_ticker_b`
- `stale_ticker_a / stale_ticker_b`
- `missing_orderbook_a / missing_orderbook_b`
- `stale_orderbook_a / stale_orderbook_b`
- `missing_bid_ask_a / missing_bid_ask_b`
- `cross_exchange_ticker_gap`
- `cross_exchange_orderbook_gap`
- `missing_funding_a / missing_funding_b`
- `stale_funding_a / stale_funding_b`
- `cross_exchange_funding_gap`
- `missing_indicator_context`
- `stale_indicator_context`

这些标记会被汇总到 `data_quality_flag`。

其中真正阻断可执行判断的仍然是 ticker / orderbook / bid-ask 相关问题；funding 和 indicator 缺失会降低上下文完整度，但默认不会直接把机会打成不可执行。

需要注意的是：

- `missing_indicator_context` 现在不只是“从来没有算出技术背景”
- 也可能表示“确实存在历史技术背景，但相对当前 ticker 已经超出 freshness 窗口，因此被主动剥离”
- 这是为了防止旧 regime 被误当成当前市场背景

### 信号标签

当前支持：

- `tradable_spread`
  - 净价差为正，流动性和滑点也满足阈值
- `liquidity_warning`
  - 有毛价差，但深度不足或执行缓冲不够
- `price_divergence`
  - 中间价偏离较大，但不一定可执行
- `data_quality_warning`
  - 输入快照缺失、陈旧或跨交易所时间差过大
- `normal`

### `is_actionable` 当前判定

必须同时满足：

- 选中方向的 `net_cross_spread_max_bps` 超过阈值
- 两腿深度满足 `liquidity_buffer_ratio`
- 估算滑点不超过 `max_slippage_bps`
- 不存在阻断型质量问题

## 对 AI 的直接价值

`exchange_comparison_snapshots` 现在已经可以直接提供这些 AI 特征：

- 哪个交易所更适合买
- 哪个交易所更适合卖
- 当前最大净价差是多少
- 当前偏离是否真实可执行
- 当前差异是否更像流动性问题或质量问题
- 当前交易对在不同交易所之间的横截面强弱关系
- 当前机会所处的 `market_regime`
- 当前 funding 是否发生显著分化
- 当前上下文完整度是否足够高

这类特征后续可以和：

- `technical_indicators`
- `macro_context`
- `news_articles`

一起送入 AI 分析层。

## 运行方式

### 直接运行

```bash
python -m logic_layer.exchange_comparison.runner
```

### 按交易对过滤

```bash
python -m logic_layer.exchange_comparison.runner --symbol BTC/USDT
```

### 调整对比窗口与目标成交额

```bash
python -m logic_layer.exchange_comparison.runner \
  --symbol BTC/USDT \
  --market-type swap \
  --indicator-timeframe 1h \
  --compare-window-seconds 5 \
  --orderbook-window-seconds 5 \
  --target-notional 10000
```

### 只计算不落库

```bash
python -m logic_layer.exchange_comparison.runner --no-save
```

## 当前实现状态

当前模块已经完成：

- 模块目录与文档
- 配置模型与输出模型
- `ticker + orderbook + funding + market_info + technical_indicators` 对齐
- 跨交易所 pair 生成
- 价差、流动性、净价差、funding 背景、market regime、信号和质量标记计算
- 结果表 `exchange_comparison_snapshots` 落库
- 基础单元测试
- 最新快照优先读取与历史表回退

## 下一阶段建议

下一阶段更值得做的是继续增强 AI 可用特征，而不是过早做展示层：

### Phase 2

- 增加 `exchange_comparison_bars`
- 让 AI 能直接读取偏离持续性、均值回归和 regime 切换历史

### Phase 3

- 引入 `klines`
- 输出更稳定的偏离序列统计特征，而不只是一条 snapshot

### Phase 4

- 为 Web/API 提供查询接口
- 为后续执行层提供更细的执行偏好与交易所路由依据
