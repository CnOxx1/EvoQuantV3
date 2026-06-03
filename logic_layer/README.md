# 逻辑处理层设计

`logic_layer` 用来存放所有"基于数据层结果做计算和决策准备"的模块。

这一层的职责：

- 对数据层产出的原始数据做清洗、对齐、聚合和标准化
- 计算技术指标、因子、特征和策略输入
- 为 AI 市场预测提供结构化、标准化、可回溯的数据接口

这一层不负责：

- 直接从外部交易所抓取数据
- 下单执行
- 前端展示

## AI 文档维护约束

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块目录结构或新增/删除源码文件
- 特征生产链路、输入输出表、运行入口或模块边界
- AI 直接消费结构、上下游依赖关系或组合方式
- 当前模块清单、实现现状或维护约束

## 快速导航

- [模块速览](#模块速览)
- [数据流全景](#数据流全景)
- [当前代码树](#当前代码树)
- [各模块详述](#各模块详述)
- [AI 输出结构](#ai-输出结构)

## 模块速览

| 模块 | 输入 | 输出 |
| --- | --- | --- |
| `technical_indicators` | `klines` + 高频上下文快照 | 趋势、动量、波动、量价特征 |
| `exchange_comparison` | 多交易所 `latest_*` 快照 | 横截面价差、执行偏好、质量语境 |
| `macro_context` | `macro_timeseries` | 宏观背景、变化率、收益率曲线 |
| `market_structure` | `exchange_data` AI-ready bundle | 资产级杠杆与拥挤结构 |
| `market_breadth` | `exchange / news / tokenomics` 主视图 | 广度分数、资产覆盖、解锁覆盖 |
| `asset_readiness` | 多模块真实 bundle | 资产级证据矩阵与 readiness |
| `cross_asset_analysis` | `merged_klines` + `trade_flow_bars` | 相关性矩阵、相对强弱、板块轮动、资金流向 |
| `portfolio_risk` | 相关性矩阵 + 资产波动率 | 组合波动率、VaR、集中度、分散化评分 |
| `feature_standardization` | `technical_indicators` 30d 窗口 | Z-score、百分位、跨资产排名、复合信号 |
| `time_slice` | 所有已落库的历史数据表 | 任意时刻市场快照 + 特征历史序列 |
| `news_sentiment` | `news_articles` 表 | 情感/事件类型/影响范围/持续时间标注 |
| `pipeline_latency` | 所有域最新数据时间戳 | 端到端延迟指标与管道健康评估 |
| `ai_market_context` | 所有上游结果 | 最终 AI 市场上下文 bundle |
| `logic_pipeline` | 所有逻辑层模块 | 全链路定时编排（5 阶段依赖执行） |
| `regime_detection` | 技术指标 + 波动率 + 成交量 + 相关性 | 市场状态分类（trending_up/down, ranging, crisis） |
| `anomaly_detection` | 价格 + 成交量 + 资金费率 + 相关性矩阵 | 统计异常事件（spike, surge, extreme, break） |
| `liquidity_analysis` | 盘口深度 + 成交量 + 价格影响 | 滑点模型、深度评分（0-100）、流动性枯竭预警 |
| `volatility_forecast` | 历史收益率 + IV + 已实现波动率 | EWMA 预测、波动率锥、RV-IV 价差 |
| `funding_rate_model` | 资金费率历史 + 基差 + 持仓量 | 费率预测、基差均值回归信号 |
| `sentiment_signal` | 社交情绪 + 价格序列 | Granger 因果、极端反转信号、情绪-价格背离 |
| `temporal_pattern` | `klines` + `funding_rates` | 日内季节性、月度效应、减半周期相位、期权到期引力 |
| `flow_decomposition` | orderflow_data + whale_tracker | VPIN、smart/dumb money 分离、积累/派发阶段 |
| `contagion_risk` | cross_asset + onchain + defi_protocol | 条件相关性、CoVaR、级联风险（→`contagion_cascade_risk`）、稳定币脱锚概率 |
| `alpha_decay` | 所有逻辑层信号 | 信号半衰期、拥挤度检测、信号惊喜指数、跨信号背离 |
| `narrative_regime` | news + social_sentiment + alternative (stubbed) | 叙事状态机、叙事生命周期、叙事→资金流映射 |
| `liquidation_cascade` | open_interest_snapshots + klines | 清算集群检测、级联概率建模、清算热力图 |
| `cross_venue_arbitrage` | klines（多 exchange）+ tickers | 跨交易所价差检测、套利持续性、市场效率评分 |
| `onchain_lead_lag` | onchain_data + exchange_data 价格 | 链上信号领先/滞后、Granger 因果、预测力排名 |
| `holder_behavior_analysis` | holder_metrics + exchange_reserves | STH/LTH 行为分离、MVRV 分位、SOPR 状态机、供给冲击概率 |
| `liquidity_regime` | staking_positions + exchange_reserves + lending_pools | 流动性状态（expansion/contraction/crisis）、DeFi-CeFi 利差、稳定币脉冲 |
| `event_probability` | prediction_market_data + news_data + regulatory_data | 事件市场定价概率、概率跳变检测、事件→资产映射 |
| `miner_pressure` | miner_metrics + exchange_reserves | Puell Multiple 分位、矿工投降指数、减半周期相位、Hash Price |
| `market_sentiment_composite` | sentiment_index + derivatives_sentiment + klines | 综合情绪评分(0-100)、极端检测、情绪-价格背离、反转信号 |
| `stablecoin_pulse` | stablecoin_mint_burns + stablecoin_chain_flows + klines | 净铸造脉冲、链迁移方向、expansion/contraction 信号 |
| `unlock_impact` | upcoming_unlocks + klines + orderbook_snapshots | 预期卖压、历史解锁→价格反应、冲击评分 |
| `depth_regime` | depth_snapshots + klines | 深度 regime 分类、买卖墙强度、滑点曲线建模 |
| `smart_money_conviction` | whale_portfolios + exchange_reserves | Smart Money 聚合 PnL、信念评分、与散户背离 |
| `defi_stress` | defi_liquidations + lending_pools | DeFi 压力指数、级联概率、协议风险排名 |
| `retail_fomo_index` | search_trends + sentiment_index | FOMO/FUD 指数、逆向信号、反转概率 |

## 数据流全景

```text
data_layer (采集)
    │
    ▼
technical_indicators ──────────────────────────┐
    │                                          │
    ▼                                          ▼
feature_standardization              exchange_comparison
    │                                          │
    ▼                                          │
cross_asset_analysis ──► portfolio_risk        │
    │                        │                 │
    │    macro_context ◄─────┘                 │
    │    market_structure ◄────────────────────┘
    │    market_breadth
    │    asset_readiness
    │         │
    ▼         ▼
ai_market_context (最终聚合)
    │
    ▼
time_slice (历史回溯查询)
```

## 当前代码树

```text
logic_layer/
  README.md
  __init__.py
  technical_indicators/
    aggregator.py, calculator.py, enricher.py, repository.py
    runner.py, service.py, utils.py, models.py
  exchange_comparison/
    aligner.py, comparator.py, models.py, repository.py
    runner.py, service.py
  macro_context/
    models.py, repository.py, runner.py, service.py
  market_structure/
    runner.py, service.py
  market_breadth/
    runner.py, service.py
  asset_readiness/
    runner.py, service.py
  cross_asset_analysis/
    calculator.py, models.py, repository.py, runner.py, service.py
  portfolio_risk/
    calculator.py, models.py, repository.py, runner.py, service.py
  feature_standardization/
    calculator.py, models.py, registry.py, repository.py
    runner.py, service.py
  time_slice/
    models.py, repository.py, runner.py, service.py
  news_sentiment/
    classifier.py, models.py, repository.py, runner.py, service.py
  pipeline_latency/
    models.py, repository.py, runner.py, service.py
  ai_market_context/
    models.py, repository.py, runner.py, service.py
  logic_pipeline/
    runner.py, service.py
  regime_detection/
    detector.py, models.py, repository.py, runner.py, service.py
  anomaly_detection/
    detector.py, models.py, repository.py, runner.py, service.py
  liquidity_analysis/
    calculator.py, models.py, repository.py, runner.py, service.py
  volatility_forecast/
    calculator.py, models.py, repository.py, runner.py, service.py
  funding_rate_model/
    calculator.py, models.py, repository.py, runner.py, service.py
  sentiment_signal/
    calculator.py, models.py, repository.py, runner.py, service.py
  temporal_pattern/
    calculator.py, models.py, repository.py, runner.py, service.py
  flow_decomposition/
    calculator.py, models.py, repository.py, runner.py, service.py
  contagion_risk/
    calculator.py, models.py, repository.py, runner.py, service.py
  alpha_decay/
    calculator.py, models.py, repository.py, runner.py, service.py
  narrative_regime/
    analyzer.py, models.py, repository.py, runner.py, service.py
  liquidation_cascade/
    calculator.py, models.py, repository.py, runner.py, service.py
  cross_venue_arbitrage/
    calculator.py, models.py, repository.py, runner.py, service.py
  onchain_lead_lag/
    calculator.py, models.py, repository.py, runner.py, service.py
  holder_behavior_analysis/
    calculator.py, models.py, repository.py, runner.py, service.py
  liquidity_regime/
    calculator.py, models.py, repository.py, runner.py, service.py
  event_probability/
    calculator.py, models.py, repository.py, runner.py, service.py
  miner_pressure/
    calculator.py, models.py, repository.py, runner.py, service.py
  market_sentiment_composite/
    calculator.py, models.py, repository.py, runner.py, service.py
  stablecoin_pulse/
    calculator.py, repository.py, runner.py, service.py
  unlock_impact/
    calculator.py, repository.py, runner.py, service.py
  depth_regime/
    calculator.py, repository.py, runner.py, service.py
  smart_money_conviction/
    calculator.py, repository.py, runner.py, service.py
  defi_stress/
    calculator.py, repository.py, runner.py, service.py
  retail_fomo_index/
    calculator.py, repository.py, runner.py, service.py
```

## 各模块详述

### technical_indicators

多交易所 K 线合并、技术指标计算、市场上下文特征并表。`ticker / funding / orderbook` 上下文只在 freshness 窗口内并入，过期置空。输出 `market_context_quality_flag`（ready / partial / stale_only / missing）。

### exchange_comparison

跨交易所横向对比。读取 `latest_tickers / orderbook / funding / market_info / technical_indicators`，生成价格偏离、净价差、执行偏好、funding 分化和 market regime。技术背景按 `ticker_timestamp` backward 对齐并受 freshness 约束。

### macro_context

宏观上下文。读取 `macro_factor_catalog / macro_timeseries`，计算 `1d / 5d` 变化和收益率曲线差值。拆分 `AI-visible factors` 与 `raw_factors`，stale 因子降级到诊断字段。

### market_structure

市场结构重组。读取 `exchange_data` AI-ready bundle，按资产重组 funding / basis / OI / liquidations / trade_flow / positioning，区分 raw 覆盖与 AI-visible 覆盖。

### market_breadth

市场广度诊断。基于 `exchange_data / news_data / tokenomics_data` 的 AI-ready 主视图输出跨资产广度、新闻广度和解锁广度，防止 AI 在极窄资产宇宙时误判。

### asset_readiness

资产级证据可用性矩阵。读取 8 个数据域的真实 bundle，判断每个资产各 band 是 `ready / limited / missing / untracked`，计算 `readiness_score`。

### cross_asset_analysis

跨资产分析。基于 `merged_klines` 1h 收盘价计算 18 资产滚动相关性矩阵（1d/3d/7d）、相对强弱排名、板块轮动阶段和聚合资金流向。

### portfolio_risk

组合风险度量。基于相关性矩阵和资产波动率构建协方差矩阵，计算年化波动率、日度 VaR(95%/99%)、风险贡献、HHI 集中度和分散化比率。

### feature_standardization

特征标准化。对 27 个核心特征计算 7d/30d 滚动 Z-score、30d 百分位排名和跨资产排名，按 momentum/volatility/leverage/flow 四维聚合为复合信号。只输出显著特征（|z|>1.5）和极端度评分。

### time_slice

时间切片查询。纯只读模块，不创建新表。给定任意历史时间戳 T，返回该时刻 10 个域的完整市场快照，每域标注 freshness 状态（ready/stale/missing）。支持单点查询、范围查询和特征历史序列查询（`get_feature_history`）。

### news_sentiment

新闻情感标注。基于规则的 NLP 分类器，对 `news_articles` 表中的新闻进行情感（bullish/bearish/neutral）、事件类型（regulatory/hack/partnership/tokenomics/technical/macro）、影响范围（market_wide/sector_wide/asset_specific）和持续时间分类。结果写入 `news_sentiment_labels` 表并回写 `news_articles.sentiment_label`。

### pipeline_latency

数据管道延迟追踪。纯只读模块，查询各域最新数据时间戳，计算端到端延迟并按阈值分类（fresh/acceptable/stale/unavailable）。输出全管道健康评估（healthy/degraded/unhealthy），帮助 AI 消费者判断数据新鲜度。

### ai_market_context

最终聚合。把所有上游模块结果组合成统一 bundle，集成 `cross_asset_context`、`portfolio_risk_context`、`feature_standardization_context`、`news_sentiment_context` 和 `pipeline_latency_context`。计算世界模型质量指数 WMI（$B_t \times U_t \times H_t$），显式暴露 `world_model_index`（含 breadth/stability/honesty 分项和 should_ai_abstain 信号）、`data_readiness / coverage_score / quality_notes`。

### logic_pipeline

全链路定时编排。按依赖顺序执行逻辑层全部模块，每 5 分钟（`LOGIC_PIPELINE_INTERVAL_SECONDS`）一次。分 5 个阶段：Phase 1 technical_indicators → Phase 2 feature_standardization/cross_asset/exchange_comparison/macro_context/news_sentiment → Phase 3 portfolio_risk/market_breadth/asset_readiness → Phase 4 ai_market_context → Phase 5 pipeline_latency。各阶段内模块独立执行，单个失败不阻断后续阶段。由 `main.py` 作为 autostart daemon 自动拉起。

### temporal_pattern

时间模式识别。基于 `klines` VIEW 和 `funding_rates` VIEW 历史数据，计算日内季节性（按小时/星期聚合历史收益率和成交量）、月度效应（按月统计历史表现）、减半周期相位（距下次减半天数 + 历史类比匹配）、期权到期引力（距最近到期日天数 + max pain 距离）和 Funding 8h 结算周期模式。结果写入 `temporal_patterns` 和 `seasonal_profiles` 表。

### flow_decomposition

资金流分解。基于 `orderflow_data` 和 `whale_tracker` 数据，计算 VPIN（将成交量按 bucket 分组，计算买卖不平衡概率）、smart money 识别（大单 + 低波动时段 = informed）、散户识别（小单 + 高波动时段 = uninformed）和积累/派发阶段检测。结果写入 `flow_decomposition` 和 `vpin_history` 表。VPIN > 0.8 标记为闪崩高风险。

### contagion_risk

传染风险建模。基于 `cross_asset_analysis`、`onchain_data` 和 `defi_protocol_data` 数据，计算条件相关性（下跌 >2σ 时的相关性 vs 正常时期）、CoVaR（资产 B 在资产 A 处于 5% 尾部时的 VaR）、尾部 Beta（极端下跌时的 beta 放大倍数）和稳定币脱锚概率。结果写入 `contagion_metrics` 和 `contagion_cascade_risk` 表。输出系统性风险评分（0-100）。

### alpha_decay

信号衰减与拥挤度。读取所有逻辑层信号输出，计算信号半衰期（信号发出后收益率的自相关衰减速度）、拥挤度（多个独立信号同时强烈看多/看空 = 拥挤）、信号惊喜指数（当前信号值偏离近期分布的 z-score）和跨信号背离（基本面 vs 技术面方向不一致）。结果写入 `signal_decay` 和 `crowding_index` 表。

### narrative_regime

叙事状态机。基于 `news_data`（`news_sentiment_labels`）、`social_sentiment_data` 和 `alternative_data`（stubbed）数据，通过关键词聚类提取市场叙事，判断叙事生命周期阶段（emerging/growing/peak/decaying），计算叙事 attention 与相关 token 价格/成交量的相关性，检测叙事传染路径。结果写入 `market_narratives` 和 `narrative_transitions` 表。

### liquidation_cascade

清算级联预测。基于 `exchange_data` 的 OI、价格和杠杆分布数据，按杠杆倍数（5x/10x/20x/50x/100x）模拟仓位分布，计算清算集群（按价格区间聚合）、级联概率（基于 size/volume 比率 + 距离衰减）、级联严重度分类（critical/high/medium/low）和清算热力图。结果写入 `liquidation_clusters`、`cascade_risk` 和 `liquidation_heatmap` 表。

### cross_venue_arbitrage

跨交易所套利检测。基于 `exchange_data` 多交易所价格数据，计算所有交易所配对的价差（bps）、检测超阈值套利机会、分析套利持续性（机会存续时间）、计算交易所间价格相关性和市场效率评分（0-100）。结果写入 `arb_opportunities`、`arb_persistence` 和 `venue_spreads` 表。

### onchain_lead_lag

链上信号领先/滞后分析。基于 `onchain_data` 和 `exchange_data` 价格序列，对 5 种链上信号（whale_net_flow、exchange_inflow、gas_spike、funding_rate、open_interest_change）× 3 个目标资产（BTC/ETH/SOL）计算交叉相关性、最优滞后期、Granger 因果检验和预测力（R²）。结果写入 `lead_lag_signals`、`onchain_price_relations` 和 `signal_alerts` 表。

### holder_behavior_analysis

持有者行为分析。基于 `onchain_holder_data` 和 `exchange_reserve_data` 数据，计算长短期持有者行为分离（STH/LTH supply ratio 变化）、MVRV 分位判断（极值区 = 顶/底信号）、SOPR 状态机（>1 获利了结, <1 割肉投降）、供给冲击概率（illiquid supply 变化率）和积累/派发阶段判断。结果写入 `holder_behavior_states` 表。

### liquidity_regime

流动性状态判断。基于 `liquid_staking_data`、`defi_protocol_data`、`cefi_lending_rate` 和 `exchange_reserve_data` 数据，计算全市场流动性状态（expansion/neutral/contraction/crisis）、DeFi-CeFi 利差方向（套利信号）、稳定币供给脉冲（M2 crypto proxy）、质押/解质押净流动影响和流动性得分（0-100）。结果写入 `liquidity_regime_states` 表。

### event_probability

事件概率提取。基于 `prediction_market_data`、`news_data` 和 `regulatory_data` 数据，提取关键事件的市场定价概率、检测概率跳变（24h 变化 > 10%）、构建事件→资产映射（哪些事件影响哪些币）、与新闻情绪交叉验证。结果写入 `event_probability_states` 表。

### miner_pressure

矿工压力评估。基于 `miner_data` 和 `exchange_reserve_data` 数据，计算 Puell Multiple 分位（极低=矿工投降, 极高=过热）、矿工储备变化趋势、Hash Price vs 电力成本估算、减半周期相位（距上次/下次减半天数）和矿工投降指数。结果写入 `miner_pressure_states` 表。

### market_sentiment_composite

综合情绪评分。基于 `derivatives_sentiment_data`、`social_sentiment_data`、`funding_rate_model` 和 `prediction_market_data` 数据，计算综合情绪评分（0-100, 多维度加权）、情绪极端检测（极度恐惧/贪婪）、情绪-价格背离检测、反转信号强度和与 funding rate 的一致性/背离。结果写入 `composite_sentiment_states` 表。

### stablecoin_pulse

稳定币脉冲分析。基于 `stablecoin_flow_data` 和 `exchange_reserve_data` 数据，计算净铸造脉冲（24h 滚动净 mint 归一化）、链迁移方向（最大净流入链）、expansion/contraction 信号分类和与 BTC 价格方向的 Pearson 相关性。结果写入 `stablecoin_pulse_states` 表。

### unlock_impact

解锁冲击评估。基于 `token_unlock_realtime`、`merged_klines` 和 `liquidity_analysis` 数据，计算预期卖压（unlock_amount / daily_volume）、历史解锁→价格反应、流动性吸收容量和复合冲击评分。结果写入 `unlock_impact_states` 表。

### depth_regime

深度 regime 分类。基于 `cex_orderbook_depth` 和 `merged_klines` 数据，计算深度 regime（thick/thin/asymmetric/vacuum）、买卖墙强度与持续性、迭代滑点曲线建模和深度-价格背离。结果写入 `depth_regime_states` 表。

### smart_money_conviction

Smart Money 信念分析。基于 `whale_wallet_pnl`、`onchain_holder_data` 和 `flow_decomposition` 数据，计算 Smart Money 聚合 PnL 趋势、信念评分（高 PnL + 加仓 = 最高信念）、5 级方向分类和与散户流的背离。结果写入 `smart_money_conviction_states` 表。

### defi_stress

DeFi 压力建模。基于 `defi_liquidation_data`、`lending_utilization` 和 `liquid_staking_data` 数据，计算 DeFi 压力指数（0-100）、级联概率（HF 分布→价格跌 X% 时预期清算量）、协议风险排名和系统性阈值检测。结果写入 `defi_stress_states` 表。

### retail_fomo_index

散户 FOMO 指数。基于 `search_trend_data`、`social_sentiment_data`、`derivatives_sentiment_data` 和 `exchange_announcement` 数据，计算 FOMO 复合指数（搜索 + 社交量 + 上币热度 + 恐贪极端）、逆向信号、FUD 复合指数和历史极端→反转相关性。结果写入 `retail_fomo_states` 表。

## AI 输出结构

当前逻辑层输出 31 类 AI 可消费结果：

| 输出 | 核心价值 |
| --- | --- |
| `technical_indicators` | 趋势、动量、波动、量价时序特征 |
| `exchange_comparison` | 跨交易所价差、执行偏好、流动性语境 |
| `macro_context` | 宏观背景、短中期变化、收益率曲线 |
| `market_structure` | funding/basis/OI/清算/trade flow 结构证据 |
| `market_breadth` | 跨资产广度，防止极窄视角过度自信 |
| `asset_readiness` | 资产级证据矩阵，判断数据是否足够完整 |
| `cross_asset_analysis` | 相关性、RS 排名、板块轮动、资金流向 |
| `portfolio_risk` | 组合波动率、VaR、集中度、分散化评分 |
| `feature_standardization` | Z-score、百分位、跨资产排名、复合信号 |
| `time_slice` | 任意历史时刻的完整市场快照回溯 + 特征历史序列 |
| `news_sentiment` | 新闻情感/事件类型/影响范围结构化标注 |
| `pipeline_latency` | 各域端到端延迟与管道健康状态 |
| `temporal_pattern` | 日内季节性、月度效应、减半周期、期权到期引力 |
| `flow_decomposition` | VPIN、smart/dumb money 分离、积累/派发阶段 |
| `contagion_risk` | 条件相关性、CoVaR、级联风险、稳定币脱锚概率 |
| `alpha_decay` | 信号半衰期、拥挤度、信号惊喜、跨信号背离 |
| `narrative_regime` | 叙事状态机、生命周期、叙事→资金流映射 |
| `liquidation_cascade` | 清算集群、级联概率、清算热力图 |
| `cross_venue_arbitrage` | 跨交易所价差、套利持续性、市场效率评分 |
| `onchain_lead_lag` | 链上信号领先/滞后、Granger 因果、预测力排名 |
| `holder_behavior_analysis` | STH/LTH 行为分离、MVRV 分位、SOPR 状态机、供给冲击概率 |
| `liquidity_regime` | 流动性状态、DeFi-CeFi 利差、稳定币脉冲、流动性评分 |
| `event_probability` | 事件市场定价概率、概率跳变检测、事件→资产映射 |
| `miner_pressure` | 矿工压力评分、Puell Multiple、投降信号、减半相位 |
| `market_sentiment_composite` | 综合情绪评分、极端检测、情绪-价格背离、反转信号 |
| `stablecoin_pulse` | 净铸造脉冲、expansion/contraction 信号、链迁移方向 |
| `unlock_impact` | 预期卖压比、冲击评分、历史反应匹配 |
| `depth_regime` | 深度 regime 分类、墙位预警、滑点估算 |
| `smart_money_conviction` | Smart Money 信念指数、方向、散户背离 |
| `defi_stress` | DeFi 压力指数、级联概率、最高风险协议 |
| `retail_fomo_index` | FOMO/FUD 指数、逆向信号强度、反转概率 |

最终由 `ai_market_context` 统一聚合为单一 bundle 供 AI 消费。

## 推荐的后续模块

- `signal_engine`：入场/出场条件、趋势与反转信号
- `prediction_validator`：AI 预测记录、对比实际走势、统计准确率
