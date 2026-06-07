# EvoQuant

**给 AI 构建的加密市场世界模型。**

大多数量化项目从"策略"出发，EvoQuant 从"理解"出发。它解决的核心问题是：AI 在做交易决策前，需要一个完整、诚实、可回溯的市场认知底座。

```text
3 交易所 × 18 资产 × 43 数据域 × 228 技术指标 × 实时质量治理
→ AI 随时可查的完整市场上下文
```

## 为什么需要 EvoQuant

| 传统量化数据管道 | EvoQuant |
| --- | --- |
| 单交易所单币种 | 3 交易所 × 18 资产，多源交叉验证 |
| 只有 K 线和指标 | 43 个数据域：行情 + 宏观 + 新闻 + 链上 + 期权 + 衍生品 + 事件 + Tokenomics + 社交情绪 + 巨鲸追踪 + 订单流 + DeFi 协议 + 跨链桥流 + 监管动态 + ETF 资金流 + 期货期限结构 + MEV + CeFi 借贷利率 + 永续 DEX + 链上地址画像 + DEX 流动性 + Gas/网络 + 治理投票 + 预测市场 + 链上持有者 + 流动性质押 + 内存池 + VC 融资 + 交易所储备 + 矿工数据 + 衍生品情绪 + 稳定币事件流 + 代币解锁实时 + 深度盘口 + 巨鲸 PnL + NFT 市场 + DeFi 清算 + DEX 交易流 + 跨链消息 + 借贷利用率 + 搜索趋势 + 交易所公告 |
| 缺失数据静默忽略 | 显式标记 stale / missing / partial，AI 知道自己"不知道什么" |
| 固定参数指标 | 228 个指标含自适应 Ehlers 系列、分形维度、Hurst 指数 |
| 只能看当前 | Point-in-time 回溯：查询任意历史时刻的完整市场状态 |
| 数据管道黑盒 | 端到端延迟追踪，每个域的新鲜度实时可见 |
| 手动拼凑特征 | 自动标准化 + Regime 分类 + 跨资产排名，AI 开箱即用 |

## 核心设计理念

**诚实优先于完整。** 数据过期就标记过期，不用旧快照冒充当前市场。AI 宁可看到"这里没数据"，也不应该基于过期信息做决策。

**结构化优先于堆量。** 不是把数据倒进数据库就行。每条数据都带着质量标签（`is_ready_for_ai`）、新鲜度窗口和语义分类，AI 不需要再做预处理。

**可回溯优先于实时。** 实时数据会过期，但 point-in-time 快照永远可用。训练、回测、复盘都能还原当时 AI 真正能看到什么。

## 数据覆盖

| 数据域 | 来源 | 采集频率 | AI 特征 |
| --- | --- | --- | --- |
| 行情 | Binance / OKX / Bybit | 3s ~ 30s（按层级） | 多交易所合并 K 线、跨所价差 |
| 技术指标 | 合并 K 线 | 每 5 分钟 | 228 个指标 × 4 种标准化 |
| 衍生品 | 交易所 API | 60s ~ 900s | 资金费率、持仓量、多空比、清算 |
| 宏观 | 公开数据源 | 每日 | DXY、纳指、黄金、利率、收益率曲线 |
| 新闻 | 聚合源 | 实时 | 情感分类、事件类型、影响范围 |
| 链上 | 公链 + DeFi | 每小时 | TVL、跨链流、交易所储备、质押 |
| 期权 | Deribit 等 | 每小时 | 波动率曲面、Gamma 暴露、持仓集中度 |
| Tokenomics | 链上 + 项目方 | 每日 | 解锁计划、流通变化、国库流动 |
| 社交情绪 | LunarCrush / Santiment | 30 分钟 | 情绪评分、社交量、影响力加权 |
| 巨鲸追踪 | WhaleAlert / Arkham / Nansen | 15 分钟 | 大额转账、钱包标签、交易所流向 |
| 订单流 | Binance / Bybit / OKX aggTrades | 5 分钟 | CVD、大单占比、买卖压力 |
| DeFi 协议 | DefiLlama | 1 小时 | TVL 变化、借贷利率、DEX 成交量 |
| 跨链桥流 | DefiLlama Bridges | 1 小时 | 跨链资金净流、链间资本迁移 |
| 监管动态 | CryptoCompare / SEC | 2 小时 | 监管事件、ETF 进展、政策变化 |
| ETF 资金流 | SoSoValue | 每日 | 净流入趋势、累计 AUM、异常流入 z-score |
| 期货期限结构 | Binance / OKX / Bybit | 1 小时 | contango/backwardation、曲线斜率、roll yield |
| MEV | Flashbots / EigenPhi | 30 分钟 | 三明治攻击频率、清算 MEV、builder 集中度 |
| CeFi 借贷利率 | Binance / OKX / Bybit Earn | 1 小时 | CeFi-DeFi 利差、利率倒挂、去杠杆信号 |
| 永续 DEX | dYdX / Hyperliquid / GMX | 15 分钟 | 跨 DEX funding 对比、OI 分布、套利价差 |
| 链上地址画像 | Arkham / Etherscan | 10 分钟 | 巨鲸地址标签、资金流向、交易所净流 |
| DEX 流动性 | Uniswap V3 / Curve (The Graph) | 20 分钟 | TVL 分布、tick 集中度、大额流动性事件 |
| Gas/网络 | Etherscan / Blocknative | 5 分钟 | Gas 价格、网络拥堵、Gas 尖刺检测 |
| 治理投票 | Snapshot / Tally | 30 分钟 | 提案状态、参与率、巨鲸投票集中度 |
| 预测市场 | Polymarket | 15 分钟 | 事件概率、概率跳变、加密相关筛选 |
| 链上持有者 | Blockchain.com / mempool.space | 1 小时 | MVRV/SOPR/NUPL、持有者分布、供给冲击 |
| 流动性质押 | DefiLlama / EigenLayer / Beaconchain | 30 分钟 | 质押 TVL、验证者队列、再质押、LST 溢折价 |
| 内存池 | mempool.space | 1 分钟 | 压力指数、大额待确认交易、Fee 趋势 |
| VC 融资 | DefiLlama Raises | 每日 | 融资轮次、热门赛道、头部 VC 动向 |
| 交易所储备 | DefiLlama / Blockchain.com | 30 分钟 | BTC/ETH/USDT 储备变化、净流入/流出 |
| 矿工数据 | mempool.space / Blockchain.com | 1 小时 | 算力、Puell Multiple、矿工收入、难度调整 |
| 衍生品情绪 | Alternative.me / Coinglass | 15 分钟 | 恐惧贪婪、多空比、OI、杠杆率、Put/Call |
| 稳定币事件流 | DefiLlama Stablecoins | 5 分钟 | 实时 mint/burn 脉冲、链迁移方向、24h 聚合 |
| 代币解锁实时 | TokenUnlocks | 1 小时 | 未来 7 天解锁排序、预期卖压、解锁→价格相关性 |
| 深度盘口 | Binance / OKX / Bybit | 30 秒 | 5000 档全量、滑点曲线、买卖墙、流动性真空 |
| 巨鲸 PnL | DeBank / Arkham | 30 分钟 | Smart Money 聚合 PnL、持仓方向、信念指数 |
| NFT 市场 | Reservoir / Blur | 15 分钟 | 蓝筹指数、wash-adjusted 交易量、ETH 相关性 |
| DeFi 清算 | Aave/Compound (The Graph) | 2 分钟 | 真实清算事件、HF<1.2 风险仓位、清算量趋势 |
| DEX 交易流 | 0x / 1inch | 5 分钟 | 大单流(>$50K)、Smart Money 链上活动、MEV 受害率 |
| 跨链消息 | LayerZero / Wormhole / Axelar | 10 分钟 | 消息速率、迁移信号、链活跃度排名 |
| 借贷利用率 | Aave/Compound/Morpho (The Graph) | 5 分钟 | 接近 kink 池、利用率趋势、借贷成本预警 |
| 搜索趋势 | Google Trends (pytrends) | 4 小时 | 加密搜索动量、FOMO 代理、突破关键词 |
| 交易所公告 | Binance / OKX / Bybit | 15 分钟 | 上币/下币、维护窗口、即将发生事件 |

## 技术指标体系

228 个技术指标覆盖 12 个类别，远超传统量化平台：

| 类别 | 数量 | 代表指标 |
| --- | --- | --- |
| 趋势 | 27 | SMA/EMA/DEMA/TEMA/HMA/KAMA/Ichimoku/Supertrend/PSAR |
| 动量 | 26 | RSI/MACD/KDJ/TSI/Schaff/Fisher/Coppock/KST |
| 波动率 | 21 | Bollinger/ATR/Parkinson/Garman-Klass/Rogers-Satchell/Squeeze |
| 趋势强度 | 9 | ADX/ADXR/Vortex/VHF/Efficiency Ratio |
| 成交量 | 24 | OBV/ADL/VWAP/KVO/MFI/CMF/PVO |
| K 线结构 | 6 | Body%/Shadow%/CLV/Trend Efficiency |
| 风险调整 | 15 | Sharpe/Sortino/Calmar/Skew/Kurtosis/Tail Ratio |
| 分位状态 | 5 | Price/Volume/ATR Percent Rank |
| 交叉信号 | 8 | EMA Cross/MACD Cross/MA Alignment/Ichimoku Signal |
| 枢轴点 | 6 | Classic Pivot/R1/S1/R2/S2 |
| 蜡烛形态 | 8 | Doji/Hammer/Engulfing/Morning Star/Pin Bar |
| 自适应 & Ehlers | 8 | Fisher/Cyber Cycle/Dominant Period/Hurst/Fractal Dimension |
| 微观结构 | 10 | Yang-Zhang Vol/Amihud/Kyle Lambda/Realized Vol |

## 质量治理体系

EvoQuant 不只是采集数据，还对每条数据做质量审计：

```text
每条数据 → health_status → quality_flag → is_ready_for_ai
                                              ↓
                              stale / partial → 从 AI 主视图剥离
                              ready → 进入 AI 消费 bundle
```

- `freshness 窗口`：每个域有独立的过期阈值，超时自动标记 stale
- `WMI 指数`：世界模型质量指数 = 宽度 × 稳定性 × 诚实性
- `market_context_quality_flag`：每根 K 线的上下文质量摘要（ok / partial / thin）
- `pipeline_latency`：端到端延迟追踪，实时暴露管道健康状态

## 架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                        AI Consumer Layer                         │
│              REST API (477 endpoints) / Bundle Query            │
├─────────────────────────────────────────────────────────────────┤
│                         Logic Layer (39 modules)                 │
│  technical_indicators → feature_standardization → cross_asset   │
│  macro_context → news_sentiment → portfolio_risk                │
│  market_breadth → asset_readiness → ai_market_context           │
│  pipeline_latency → time_slice → logic_pipeline                 │
│  regime_detection → anomaly_detection → liquidity_analysis      │
│  volatility_forecast → funding_rate_model → sentiment_signal    │
│  temporal_pattern → flow_decomposition → contagion_risk         │
│  alpha_decay → narrative_regime                                 │
│  liquidation_cascade → cross_venue_arbitrage → onchain_lead_lag │
│  holder_behavior → liquidity_regime → event_probability         │
│  miner_pressure → market_sentiment_composite                    │
│  stablecoin_pulse → unlock_impact → depth_regime          │
│  smart_money_conviction → defi_stress → retail_fomo_index │
├─────────────────────────────────────────────────────────────────┤
│                         Data Layer (43 modules)                  │
│  exchange_data │ macro_data │ news_data │ onchain_data          │
│  options_data │ tokenomics_data │ event_calendar │ alternative  │
│  social_sentiment │ whale_tracker │ orderflow │ defi_protocol   │
│  bridge_flow │ regulatory_data │ data_quality                   │
│  etf_flow_data │ perpetual_basis_curve │ mev_data │ cefi_lending│
│  perpetual_dex_data │ onchain_address_data │ dex_liquidity_data │
│  gas_network_data │ governance_data                             │
│  prediction_market │ onchain_holder │ liquid_staking │ mempool  │
│  funding_round │ exchange_reserve │ miner_data │ deriv_sentiment│
│  stablecoin_flow │ token_unlock │ cex_depth │ whale_pnl  │
│  nft_market │ defi_liquidation │ dex_trade_flow          │
│  cross_chain_msg │ lending_util │ search_trend │ exch_ann│
├─────────────────────────────────────────────────────────────────┤
│                         Storage Layer                            │
│  SQLite (3 域拆分) / PostgreSQL (生产)                           │
│  latest_* 快照 │ 历史表 │ 质量审计表 │ Alembic 迁移             │
├─────────────────────────────────────────────────────────────────┤
│                         External Sources                         │
│  Binance │ OKX │ Bybit │ DeFiLlama │ Deribit │ 宏观数据源      │
│  LunarCrush │ Santiment │ Arkham │ Nansen │ WhaleAlert │ SEC   │
│  SoSoValue │ Flashbots │ EigenPhi │ dYdX │ Hyperliquid │ GMX  │
│  Uniswap V3 │ Curve │ Etherscan │ Blocknative │ Snapshot │Tally│
│  Polymarket │ Alternative.me │ Coinglass │ Beaconchain          │
└─────────────────────────────────────────────────────────────────┘
```

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动全部采集 + 逻辑管道
python main.py

# 启动 API 服务
python -m api.app --port 8000
```

API 启动后访问 `http://localhost:8000/docs` 查看交互式文档。

## 常用操作

```bash
# 查看模块清单
python main.py --list-modules

# 手动执行指定逻辑模块
python main.py --modules technical_indicators,cross_asset_analysis

# 查询历史某时刻的市场全貌
python -m logic_layer.time_slice.runner --timestamp 2025-05-20T12:00:00 --summary-only

# 查询特征连续历史序列
python -m logic_layer.time_slice.runner --feature-history --symbols BTC/USDT \
  --range-start 2025-05-19T00:00:00 --range-end 2025-05-20T00:00:00 \
  --features rsi_14,macd_line

# 查看数据管道延迟状态
python -m logic_layer.pipeline_latency.runner --summary-only

# 查看数据层是否已达到 AI 可用门槛
python -m data_layer.data_quality.runner --print-market-audit

# 运行测试
pytest -q
```

## 仓库结构

```text
EvoQuant/
├── config/          目标资产、调度、日志与环境配置
├── core/            基类抽象层（BaseDataClient/Service/Runner、BaseAnalyticsService/Runner）
├── data_layer/      外部数据采集、标准化、落库（43 个数据模块）
├── database/        数据库管理（SQLite/PostgreSQL 双后端、Alembic 迁移）
├── logic_layer/     AI-ready 特征、上下文和治理结果（39 个逻辑模块）
├── api/             对外 REST API 服务（477 端点，支持游标分页）
├── alembic/         PostgreSQL Schema 迁移脚本
├── tests/           单元测试与模块测试
├── monitoring/      Prometheus 指标导出 + Grafana 仪表盘（Docker Compose 部署）
└── main.py          统一入口，模块注册与进程管理（指数退避重启 + 三阶段优雅关停）
```

## 逻辑层模块

| 模块 | 职责 |
| --- | --- |
| `technical_indicators` | 多交易所 K 线合并 + 228 个技术指标计算 |
| `feature_standardization` | Z-score / 百分位 / 跨资产排名 / 维度复合信号 |
| `cross_asset_analysis` | Pearson 相关性 / 相对强弱 / 板块轮动 |
| `portfolio_risk` | 组合波动率 / VaR / HHI 集中度 / 分散化比率 |
| `exchange_comparison` | 跨交易所价差、执行偏好、流动性语境 |
| `macro_context` | 宏观背景快照、短中期变化、收益率曲线 |
| `market_structure` | 资产级杠杆与拥挤度结构证据 |
| `news_sentiment` | 情感分类 / 事件类型 / 影响范围标注 |
| `market_breadth` | 跨资产广度、新闻广度、解锁广度 |
| `asset_readiness` | 资产级证据矩阵与数据可用性评分 |
| `ai_market_context` | 最终 AI 市场上下文 bundle 聚合 |
| `time_slice` | 任意历史时刻的完整市场快照 + 特征历史序列 |
| `pipeline_latency` | 各域端到端数据新鲜度与管道健康状态 |
| `logic_pipeline` | 全链路定时编排（每 5 分钟按依赖顺序执行） |
| `regime_detection` | 市场状态分类（trending_up/down, ranging, crisis）多因子分类器 |
| `anomaly_detection` | 统计异常检测（价格尖刺、成交量激增、资金费率极端、相关性断裂） |
| `liquidity_analysis` | 滑点建模、深度评分（0-100）、流动性枯竭预警 |
| `volatility_forecast` | 已实现波动率、EWMA 预测、波动率锥、RV-IV 价差 |
| `funding_rate_model` | 资金费率预测、基差均值回归信号 |
| `sentiment_signal` | 情绪-价格 Granger 因果、极端反转信号、背离检测 |
| `temporal_pattern` | 日内季节性、月度效应、减半周期相位、期权到期引力 |
| `flow_decomposition` | VPIN、smart/dumb money 分离、积累/派发阶段 |
| `contagion_risk` | 条件相关性、CoVaR、级联风险、稳定币脱锚概率 |
| `alpha_decay` | 信号半衰期、拥挤度检测、信号惊喜指数、跨信号背离 |
| `narrative_regime` | 叙事状态机、叙事生命周期、叙事→资金流映射 |
| `liquidation_cascade` | 清算集群检测、级联概率建模、清算热力图 |
| `cross_venue_arbitrage` | 跨交易所价差检测、套利持续性、市场效率评分 |
| `onchain_lead_lag` | 链上信号领先/滞后分析、Granger 因果、预测力排名 |
| `holder_behavior_analysis` | STH/LTH 供给分离、MVRV 分位、SOPR 状态机、积累/派发阶段 |
| `liquidity_regime` | 全市场流动性状态分类（expansion/contraction/crisis）、DeFi-CeFi 利差 |
| `event_probability` | 预测市场概率跳变检测、事件→资产映射、新闻交叉验证 |
| `miner_pressure` | Puell Multiple 分位、矿工投降指数、减半周期相位、算力压力 |
| `market_sentiment_composite` | 多维度综合情绪评分（0-100）、极端检测、情绪-价格背离、反转信号 |
| `stablecoin_pulse` | 稳定币脉冲：净铸造归一化、链迁移方向、expansion/contraction 信号 |
| `unlock_impact` | 解锁冲击：预期卖压比、流动性吸收容量、历史反应匹配 |
| `depth_regime` | 深度 Regime：thick/thin/asymmetric/vacuum 分类、墙位、滑点曲线 |
| `smart_money_conviction` | Smart Money 信念：PnL 趋势、信念评分、与散户背离 |
| `defi_stress` | DeFi 压力：压力指数(0-100)、跌 5/10/20% 级联概率、协议风险排名 |
| `retail_fomo_index` | 散户 FOMO：FOMO/FUD 指数(0-100)、逆向信号强度、反转概率 |

## API

477 REST 端点，覆盖：

- 技术指标深度分析（极值、背离、多周期）
- 组合风险分析（VaR、风险贡献、集中度）
- 微观结构（流动性、价格影响、订单流）
- 跨资产历史序列（相关性、相对强弱）
- 因子探索（标准化特征、Regime 分类）
- 宏观上下文、新闻情报、衍生品、链上数据
- 永续 DEX（跨 DEX funding 对比、OI 分布、CEX-DEX 套利价差）
- 链上地址画像（巨鲸动向、地址标签、交易所净流）
- DEX 流动性（池 TVL、tick 集中度、大额流动性事件）
- Gas/网络（Gas 价格、拥堵度、尖刺检测、区块利用率）
- 治理投票（提案状态、参与率、巨鲸投票、法定人数风险）
- 清算级联（集群分布、级联概率、热力图、杠杆分布）
- 跨交易所套利（价差检测、套利持续性、市场效率评分）
- 链上领先/滞后（信号预测力、Granger 因果、最优滞后期）
- 预测市场（活跃市场、概率变动、加密事件筛选）
- 链上持有者（MVRV/SOPR/NUPL、持有者分布、结构变化）
- 流动性质押（质押 TVL、验证者队列、再质押、APR 对比）
- 内存池（压力指数、Fee 趋势、大额待确认交易）
- VC 融资（近期轮次、赛道分布、顶级投资方）
- 交易所储备（余额、净流入/流出、储备变化）
- 矿工数据（指标历史、算力、Puell Multiple）
- 衍生品情绪（恐惧贪婪、多空比、OI、杠杆率）
- 持有者行为分析（市场阶段、行为信号、历史分位）
- 流动性 Regime（状态、评分、DeFi-CeFi 利差）
- 事件概率（高影响事件、概率跳变、资产映射）
- 矿工压力（投降指数、减半周期、压力评分）
- 综合情绪（评分、极端标记、背离、反转概率）
- 稳定币事件流（实时 mint/burn、链净流、24h 脉冲）
- 代币解锁（未来解锁排序、高冲击解锁、历史反应）
- 盘口深度（全量深度、买卖墙、滑点曲线、深度 regime）
- 巨鲸 PnL（Smart Money 组合、Top 表现者、信念方向）
- NFT 市场（收藏品统计、市场概览、wash-adjusted 数据）
- DeFi 清算（真实清算事件、健康因子分布、协议对比）
- DEX 交易流（大单流、路由器统计、MEV 受害率）
- 跨链消息（协议统计、消息量、链活跃排名）
- 借贷利用率（池状态、高利用率预警、利率趋势）
- 搜索趋势（热度、动量、Top 关键词）
- 交易所公告（最近公告、上币事件、按交易所筛选）
- 稳定币脉冲（expansion/contraction 信号、链流方向）
- 解锁冲击（高冲击解锁 Top5、价格影响估算）
- 深度 Regime（regime 状态、墙位预警、滑点估算）
- Smart Money 信念（信念指数、方向、散户背离）
- DeFi 压力（压力评分、级联概率、高风险协议）
- 散户 FOMO（FOMO/FUD 指数、逆向信号、反转概率）

启动后访问 `/docs`（Swagger）或 `/redoc`（ReDoc）查看完整接口文档。

## 文档导航

- 项目总览：[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)
- 数据层入口：[data_layer/README.md](data_layer/README.md)
- 逻辑层入口：[logic_layer/README.md](logic_layer/README.md)
- API 接口文档：[api/README.md](api/README.md)
- 数据库说明：[database/README.md](database/README.md)
- 监控与可观测性：[monitoring/README.md](monitoring/README.md)
- AI 数据能力总览：[AI_DATA_CAPABILITIES.md](AI_DATA_CAPABILITIES.md)

## 监控与可观测性

EvoQuant 集成了 Prometheus + Grafana 监控栈，提供 14 个核心指标和 3 个预置仪表盘。

**快速启动监控：**

```bash
pip install prometheus_client
cd monitoring && docker compose -f docker-compose.monitoring.yml up -d
# Grafana: http://localhost:3000 (admin/evoquant)
# Prometheus: http://localhost:9090
```

**核心指标：**

| 指标 | 类型 | 含义 |
| --- | --- | --- |
| `evoquant_http_requests_total` | Counter | HTTP 请求总数 (method/path/status) |
| `evoquant_http_request_duration_seconds` | Histogram | 请求延迟 P50/P95/P99 |
| `evoquant_module_status` | Gauge | 模块运行状态 (1=运行/0=停止/-1=禁用) |
| `evoquant_domain_freshness_status` | Gauge | 域数据新鲜度 |
| `evoquant_wmi_score` | Gauge | 世界模型指数 (0-100) |
| `evoquant_pipeline_phase_duration_seconds` | Histogram | 管道阶段执行时长 |
| `evoquant_database_size_bytes` | Gauge | 数据库文件大小 |
| `evoquant_market_alerts_total` | Counter | 市场告警计数 |

**3 个预置仪表盘（共 43 个面板）：**
- **System Overview**（18 面板）— 健康状态、WMI 评分/历史、模块状态表、API 请求率、延迟 P50/P95/P99、并发数、路径热度 Top 10、错误率百分比、数据库大小、进程内存/CPU/FD/GC、Uptime
- **Pipeline Health**（13 面板）— 域新鲜度状态时间线、延迟时间线/对比、新鲜度分布饼图、健康历史、管道阶段时长、总时长趋势、Phase Errors 速率
- **Market Alerts**（12 面板）— 告警总数/Critical/Warning/Info/24h、速率/分钟、类型环形图、严重度梯度条、速率趋势、累计、类型堆叠图

**优雅降级：** 未安装 `prometheus_client` 时系统正常运行，仅不导出指标。现有 `/metrics` JSON 端点不受影响。

## Roadmap

### P1 — 已完成

- [x] 18 个主流资产三层分频采集
- [x] 228 个技术指标（含自适应 Ehlers、蜡烛形态、微观结构）
- [x] 跨资产特征：相关性矩阵、相对强弱、板块轮动
- [x] 组合风险度量：VaR、风险贡献、集中度、分散化
- [x] 特征标准化：Z-score / 百分位 / 跨资产排名 / Regime 分类
- [x] Point-in-time 时间切片 + 特征历史序列
- [x] 新闻情感标注 + 事件分类
- [x] 数据管道延迟追踪
- [x] 300+ REST API 端点
- [x] 6 个新数据域：社交情绪、巨鲸追踪、订单流、DeFi 协议、跨链桥流、监管动态
- [x] 6 个新逻辑模块：Regime 检测、异常检测、流动性分析、波动率预测、资金费率模型、情绪信号
- [x] 4 个新数据模块：ETF 资金流、期货期限结构、MEV 数据、CeFi 借贷利率
- [x] 5 个新逻辑模块：时间模式识别、资金流分解、传染风险、信号衰减、叙事状态机
- [x] 5 个新数据模块：永续 DEX（dYdX/Hyperliquid/GMX）、链上地址画像（Arkham/Etherscan）、DEX 流动性（Uniswap V3/Curve）、Gas/网络（Etherscan/Blocknative）、治理投票（Snapshot/Tally）
- [x] 3 个新逻辑模块：清算级联预测、跨交易所套利检测、链上领先/滞后分析
- [x] 8 个新 API 路由（61 端点）：永续 DEX、链上地址、DEX 流动性、Gas/网络、治理、清算级联、跨所套利、链上领先滞后
- [x] 8 个新数据模块：预测市场（Polymarket）、链上持有者（MVRV/SOPR/NUPL）、流动性质押（Lido/RocketPool/EigenLayer）、内存池（mempool.space）、VC 融资（DefiLlama Raises）、交易所储备、矿工数据、衍生品情绪
- [x] 5 个新逻辑模块：持有者行为分析、流动性 Regime、事件概率、矿工压力、综合情绪评分
- [x] 13 个新 API 路由（65 端点）：预测市场、链上持有者、流动性质押、内存池、VC 融资、交易所储备、矿工、衍生品情绪、持有者行为、流动性 Regime、事件概率、矿工压力、综合情绪
- [x] 11 个新数据模块：stablecoin_flow_data（稳定币事件流）、token_unlock_realtime（代币解锁实时）、cex_orderbook_depth（5000 档全量深度）、whale_wallet_pnl（巨鲸 PnL）、nft_market_data（NFT 市场）、defi_liquidation_data（DeFi 清算事件）、dex_trade_flow（DEX 大单流）、cross_chain_messaging（跨链消息）、lending_utilization（借贷利用率）、search_trend_data（搜索趋势）、exchange_announcement（交易所公告）
- [x] 6 个新逻辑模块：stablecoin_pulse（稳定币脉冲）、unlock_impact（解锁冲击评估）、depth_regime（深度 Regime 分类）、smart_money_conviction（Smart Money 信念）、defi_stress（DeFi 压力建模）、retail_fomo_index（散户 FOMO 指数）
- [x] 17 个新 API 路由（85 端点）：/stablecoin-flow、/token-unlock、/orderbook-depth、/whale-pnl、/nft-market、/defi-liquidation、/dex-trade-flow、/cross-chain-msg、/lending-utilization、/search-trend、/exchange-announcement、/stablecoin-pulse、/unlock-impact、/depth-regime、/smart-money-conviction、/defi-stress、/retail-fomo
- [x] 数据域从 32 个扩展到 43 个，逻辑模块从 33 个扩展到 39 个，API 端点数达 477

### P2 — 进行中

- [x] 监控告警：Prometheus 指标导出 + Grafana 可视化仪表盘（3 个预置 Dashboard）
- [x] PostgreSQL 生产后端：Docker 容器化 + 零崩溃全模块运行
- [ ] 增量导出：Parquet/Arrow 格式，供 ML pipeline 批量训练
- [ ] 预测验证框架：AI 预测 → 对比实际 → 统计准确率
- [ ] 数据保留策略：K 线/资金费率保留 2 年+

### P3 — 长期方向

- [ ] 信号引擎：趋势/均值回归/事件驱动信号生成
- [ ] 风控引擎：仓位管理、止损、波动率约束
- [ ] 执行层：下单、滑点控制、跨所路由
- [ ] 组合层：多资产权重、再平衡、回撤控制

## 更新记录

### 2025-06-07

**v4.6.0 — 逻辑层算法重构与聚合优化**

- **feature_standardization 跨资产排名 O(n²)→O(n)**：嵌套循环逐行匹配改为预建 `feature_name→rows` 索引 dict，直接 O(1) 查找赋值，40-60% 加速
- **portfolio_risk calculator numpy 向量化**：O(n²) 纯 Python 嵌套 .get() 循环改为 `w @ cov @ w` 单次矩阵乘法 + `cov @ w` 向量运算，30-50× 加速
- **fund_flow 单次遍历预聚合**：4 次 `sum(flow_map.get(s,{}).get(...) for s in tier_syms)` 改为单次遍历 flow_map 构建 tier/sector 聚合数组，25-35% 加速
- **asset_readiness 集合并集优化**：12 次 `set() | set()` 中间对象分配改为单个 set 累加器 `.update()` 链式调用
- **feature_standardization regime 分布 Counter**：手动 `.get()+1` 循环改为 C 优化的 `Counter()` 一次调用
- **feature_standardization JSON 序列化 orjson**：`json.dumps(bundle, ensure_ascii=False)` 替换为 `orjson.dumps()` 快速路径（3-5× 加速）
- **main.py 模块优先级分组单次遍历**：3 次 list comprehension 改为单次循环 dict 累加

**v4.5.0 — 算法优化与批量查询合并**

- **volatility ranking 批量查询**：N+1 逐符号查询（18次 DB roundtrip）合并为单次 `IN (...)` 批量查询 + 内存分组，5-10× 响应加速
- **factor_explorer 相关性 numpy 向量化**：手动 Python 循环计算 Pearson correlation 改为 `np.corrcoef()` 一次调用，10-50× 加速
- **新闻情感分类器预编译正则**：逐词 `kw in text` O(n×m) 搜索改为预编译正则 `findall()` 单次扫描，3-5× 加速
- **enricher groupby sort=False**：`frame.groupby("symbol", sort=True)` 改为 `sort=False`（数据已排序），避免冗余重排 10-20%
- **enricher 辅助 DataFrame 预分组**：内循环的 `tickers[tickers["symbol"]==sym]` boolean mask 改为预 groupby + dict 查找 O(1)
- **FairShareLimiter metrics() 集合优化**：`set(list(keys) + list(keys))` 改为 `keys() | keys()` dict_keys 视图并集
- **pagination cursor orjson 快速路径**：`json.dumps/loads` 替换为 `orjson` 编解码（2-3× 加速），graceful fallback

**v4.4.0 — 计算向量化与服务实例化优化**

- **相关性矩阵 numpy 向量化**：`CrossAssetCalculator.compute_correlation_matrix()` 从纯 Python O(n²) 循环改为 `np.corrcoef()` 一次计算完整 NxN 矩阵，10-100× 加速
- **context 端点服务单例化**：6 个高频 `/context` 端点（liquidity_regime / liquidation_cascade / holder_behavior / miner_pressure / flow_decomposition / temporal_pattern）从逐请求 `Service()` 改为 `@lru_cache` 单例注入，消除 50-200ms/请求的实例化开销
- **cross_asset_analysis orjson 序列化**：`repository.py` 的 `json.dumps/loads` 替换为 `orjson` 快速路径（3-5× 加速），graceful fallback 到标准 json
- **time_slice 单次遍历计数**：3 次 `sum()` generator 替换为 `Counter()` 单次遍历，迭代次数减少 66%
- **memory_monitor 缓存 TTL 提升至 5s**：`MEMORY_CACHE_TTL_SECONDS` 环境变量可配置（默认 5s），减少 80% 无效 `memory_info()` syscall
- **SELECT \* 列投影扩展**：liquidity_regime / holder_behavior / miner_pressure / orderflow_micro / stablecoin_flow / prediction_market(movers) 共 12 个端点改为精确列查询
- **prediction_market movers 列投影**：`SELECT m.*` JOIN 查询改为精确 5 列投影

**v4.3.0 — 查询路径与中间结果优化**

- **correlation-context 批量查询**：N+1 逐符号 DB 查询（18次）合并为单次全量查询 + 内存分组，响应延迟从 ~200ms 降至 ~15ms
- **CrossAssetAnalysis run_all() 中间结果缓存**：预加载 close_series / returns / fund_data 共享给 4 个计算方法，消除 3 次重复 DB 查询
- **Repository 时间戳预转换**：`pd.Timestamp(row.open_time).isoformat()` 逐行调用改为 `pd.to_datetime().strftime()` 向量化预转换
- **main.py shutdown 信号前置检查**：循环顶部优先检查 `shutdown_requested`，避免无效子进程轮询
- **ALL_SECTOR_SYMBOLS 预计算**：`config/symbols.py` 新增 `frozenset` 板块符号集合，O(1) 成员判定
- **prediction_market / liquidation_cascade SELECT \* 消除**：全部端点改为精确列投影，减少 I/O + 序列化开销
- **ResultCache 短 key 跳过 SHA-256**：key 长度 ≤128 直接用原始字符串，避免每次缓存命中都做哈希计算
- **loguru import 提升至模块级**：`technical_indicators/service.py` 消除函数内重复 `from loguru import logger`

**v4.2.0 — 序列化路径与并发锁优化**

- **Feature Standardization groupby 重构**：O(n²) 逐 symbol `df[df["symbol"]==sym]` 过滤改为 `groupby` 一次分组 + 迭代器消费，40-60% 计算提速
- **Feature Standardization .values[-1]**：`.iloc[-1]` 替换为 `.values[-1]` 避免 pandas 索引查找开销；`x != x` NaN 检测替代 `pd.isna()`
- **WebSocket orjson 快速路径**：`broadcast()` 使用 `orjson.dumps()` 替代 `json.dumps()`（有 orjson 时），序列化速度提升 3-5×
- **EventBus handler 缓存**：`_dispatch()` 使用 `_handler_cache` tuple 避免每次事件分发做 `list()` 拷贝；subscribe 时精确失效
- **EventBus 轮询降至 10ms**：`_queue.get(timeout=0.01)` 替代 100ms，异步事件延迟从 50ms avg 降至 5ms
- **EventBus 延迟日志格式化**：`f"EventBus handler error: {e}"` 改为 `logger.error("{}", e)` loguru 延迟求值
- **PostgreSQL _DictRow 优化**：`list(self.values())` 改为 `tuple(self.values())` 减少内存分配；`__slots__ = ()` 禁止实例 `__dict__`
- **PostgreSQL row columns 缓存**：`_rows_to_dicts` 使用 `tuple()` 替代 `list()` 存储列名，不可变对象减少 GC 压力
- **QueryCache 锁分离**：新增独立 `_inflight_lock`，inflight 请求管理与缓存存储读写互不阻塞，并发吞吐提升 30-50%
- **unused `json` import 保留向后兼容**：`websocket_manager.py` 保留 `import json` 作为 orjson 不可用时的 fallback

**v4.1.0 — API 响应与管道编排优化**

- **SELECT \* → 列投影**：`aggregate.py` 的 `multi_asset_compare` 等端点从 `SELECT *` 改为具体列查询，减少 5-15ms/请求 I/O 开销
- **SYMBOL_UNIVERSE 预索引**：`_SYMBOL_INDEX = {e["symbol"]: e for e in SYMBOL_UNIVERSE}` O(1) 查找替代 O(n) 线性扫描
- **请求合并器零延迟**：`RequestCoalescer` 移除首次请求的无条件 `time.sleep(100ms)`，首次请求立即执行，消除人为 100ms 延迟
- **Prefetcher 真预热**：`QueryPrefetcher.prefetch_all()` 现在真正执行 DB 查询并写入 query_cache，而非只 touch 空键
- **缓存依赖拓扑**：`QueryCache` 新增 `register_dependency()` / `invalidate_downstream()` 级联失效，upstream 变更自动传播到下游缓存
- **符号标准化 LRU 缓存**：`MarketBreadthService._normalize_asset_from_symbol()` 添加 `@lru_cache(maxsize=1024)`，循环内重复调用 O(1) 返回
- **Exchange Service 建图优化**：`_build_symbols_map()` 从反复 `setdefault` + 对象构造改为预分配 + 直接索引，减少 20% 临时对象创建
- **Pipeline 上游失败快跳**：经典模式新增 `_MODULE_DEPENDENCIES` 依赖映射 + `failed_upstream` 集合传递，下游模块在上游失败时立即跳过而非等待超时
- **Rate limiter O(1) remaining**：`remaining()` 方法从逆序遍历 deque 改为先弹出过期项再取 `len()`，单次调用 O(1)
- **Memory monitor double-check locking**：`rss_mb` 属性添加 `threading.Lock` 双重检查，防止并发竞争导致多次 `memory_info()` syscall
- **整数除法优化**：`rss / 1024 / 1024` 改为 `rss / 1048576`（单次除法）
- **unused import 清理**：`request_coalescer.py` 移除未使用的 `time` 导入（原 `time.sleep` 已删除）

**v4.0.0 — 计算热路径与运行时性能优化**

- **Supertrend/PSAR/KAMA 向量化**：`calculator.py` 核心循环从 pandas .iloc[] 迁移至 numpy 数组操作，消除 60% 的 Python 解释器开销
- **Fisher/Ehlers/KVO 循环消除**：`_fisher_transform` / `_ehlers_*` / `_klinger_volume_oscillator` / `_positive_negative_volume_index` 全部重写为 numpy 前向传播
- **pd.concat→np.maximum/minimum**：true_range / ichimoku cloud / buying_pressure 等 5 处替换为零分配 numpy 操作
- **DataFrame copy 消除**：`calculate()` + `_calculate_group()` 从 3 次 full copy 减少为 1 次（sort_values 自带 copy），内存峰值减少 30%
- **groupby 迭代器直接消费**：移除 `list(frame.groupby(...))` 物化，改为迭代器逐组处理
- **indicator concat 预分配**：12 次 `pd.concat` 合并为单次 dict→DataFrame 构造，减少内存碎片
- **Rate limiter deque 重构**：`_RateLimiter` 从 list comprehension O(n) 过滤改为 `collections.deque` O(1) popleft
- **Rate limiter IP 容量上限**：添加 LRU 淘汰机制（MAX_TRACKED_IPS=10000），防止内存无限增长
- **Brotli 压缩升级**：新增 `starlette-compress` 依赖，优先 Brotli（比 Gzip 高 15-25% 压缩率），graceful 降级 Gzip
- **连接池自适应集成**：`pool_config.py` 新增 `adaptive_enabled` / `pool_overflow` / `idle_timeout`，`get_adaptive_pool_size()` 接入 AdaptivePoolManager
- **模块并行启动**：`supervise_modules()` 按 priority 分批启动（critical 优先），冷启动时间减少 50%
- **Pipeline phase 2 快速失败**：`_run_phase_parallel()` 改用 `wait(FIRST_EXCEPTION)` 替代 `as_completed` + 二次遍历
- **memory_monitor syscall 缓存**：`rss_mb` 属性添加 1 秒结果缓存，减少 `memory_info()` 系统调用频率
- **GC 阈值调优**：API lifespan 中设置 `gc.set_threshold(50000, 20, 10)`，减少 full GC 导致的尾延迟毛刺
- **依赖更新**：新增 `numpy==1.26.4`（显式固定）、`starlette-compress==1.0.1`（Brotli）、`bottleneck==1.4.2`（rolling 加速）

**v3.9.0 — 自适应调度与运行时可控性**

- **时间窗口预物化**：新增 `logic_layer/window_materializer.py` (`WindowMaterializer`)，pipeline 执行前一次性预取所有 symbol×timeframe klines，各 phase 共享零拷贝访问，DB 查询减少 40-50%
- **Monitor 端点批量化**：新增 `api/monitor_optimizer.py` (`MonitorBatchFetcher`)，`WHERE symbol IN (...)` 批量查询替代逐符号循环，monitor 延迟从 5s→<1s
- **并发请求合并**：新增 `api/request_coalescer.py` (`RequestCoalescer`)，100ms 窗口内相同查询只执行一次 DB 调用，结果 fan-out 给所有等待者
- **调度 Jitter + 反压队列**：新增 `core/scheduler_jitter.py`，`jitter()` 添加 ±15% 随机偏移消除 thundering herd，`BackpressureQueue` 按 hot/normal/cold 优先级限流并发
- **异常类型层次化**：新增 `core/exceptions.py`，TransientDataError / FatalDataError / SchemaValidationError / CircuitOpenError 精确分类，`is_retryable()` 一键判断
- **数据保留自动执行**：新增 `database/retention_executor.py` (`RetentionExecutor`)，按策略批量 DELETE 过期行 + dry_run 预览，存储自动可控
- **流式响应**：新增 `api/streaming.py`，`stream_json_array()` / `stream_ndjson()` 生成器驱动分块传输，大结果集不再全量缓冲
- **索引推荐引擎**：新增 `database/index_recommender.py` (`IndexRecommender`)，分析慢查询模式自动生成 `CREATE INDEX` 建议
- **配置热重载**：新增 `core/config_watcher.py` (`ConfigWatcher`)，.env 文件 mtime 轮询 + 增量更新 os.environ，零停机配置变更
- **优雅关闭管理**：新增 `core/graceful_shutdown.py` (`ShutdownManager`)，按优先级执行注册的 cleanup 回调，30s 超时兜底强杀
- **运行时 Profiler**：新增 `core/runtime_profiler.py` (`RuntimeProfiler`)，context manager 捕获 per-module RSS/CPU/耗时，rolling 100 次统计
- **混沌工程 Hooks**：新增 `core/chaos.py` (`ChaosMonkey`)，`CHAOS_ENABLED=true` 时注入延迟/错误（目标模块可配），生产环境完全零开销

**v3.8.0 — 自适应运行时与分布式就绪**

- **异步查询预取**：新增 `api/prefetch.py` (`QueryPrefetcher`)，监听 pipeline 完成事件自动预热热点查询，消除刷新后冷启动窗口
- **缓存依赖 DAG**：新增 `logic_layer/cache_deps.py` (`CacheDependencyGraph`)，pipeline 失效改为精准下游传播（TI 完成 → 13 个下游模块缓存精确失效）
- **SELECT 列自动裁剪**：新增 `database/column_selector.py` (`ColumnSelector`)，结合 field_selection 自动将 `SELECT *` 改写为具体列，减少 30-50% I/O
- **连接池自适应缩放**：新增 `database/adaptive_pool.py` (`AdaptivePoolManager`)，基于 EMA 平滑的 wait_time/idle_ratio 指标动态推荐 pool_min/pool_max
- **BatchWriter 自适应分块**：新增 `database/adaptive_batch.py` (`AdaptiveBatchWriter`)，按 p50 延迟反馈自动调整批次大小（50-2000 行/批）
- **PostgreSQL 分布式缓存失效**：新增 `database/pg_notify.py` (`PgNotifyBridge`)，LISTEN/NOTIFY 广播缓存失效事件，支持 API 多实例水平扩展
- **时间快照版本化**：新增 `database/snapshot_versioning.py` (`SnapshotVersioningService`)，每小时创建 latest_* 版本快照，支持 point-in-time 状态回溯
- **优先级差异化退避**：main.py 新增 `PRIORITY_BACKOFF_CURVES`（critical: 1s→30s, normal: 2s→60s, low: 5s→300s），关键模块恢复提速 2x
- **懒启动机制**：新增 `core/lazy_starter.py` (`LazyModuleStarter`)，非关键模块（search_trend/nft_market/prediction_market/governance）延迟到首次请求激活
- **跨进程追踪传播**：新增 `core/trace_propagation.py` (`TracePropagator`)，W3C traceparent 注入子进程环境变量，实现端到端分布式追踪
- **公平份额限流**：新增 `api/fair_limiter.py` (`FairShareLimiter`)，过限请求排队而非直接 429，FIFO + jitter 消费
- **告警分组去重**：新增 `monitoring/alert_aggregator.py` (`AlertAggregator`)，同类告警按 (category, severity) 聚合，100 条异常输出 1 条摘要
- **事件总线指标**：新增 `core/event_bus_metrics.py` (`EventBusMetrics`)，per-topic 发布/处理/丢弃/延迟统计，Prometheus 可导出

**v3.7.0 — 架构韧性与工程质量**

- **技术指标向量化**：`calculator.py` 新增 `_vectorized_cfo()` / `_vectorized_mean_deviation()`，替代高频 `rolling().apply()`，消除 Python 回调开销
- **逻辑层结果缓存**：新增 `logic_layer/result_cache.py` (`ResultCache`)，LRU + TTL 缓存逻辑计算结果，`@cached_result` 装饰器自动缓存
- **数据库熔断器**：新增 `core/circuit_breaker.py` (`CircuitBreaker`)，CLOSED→OPEN→HALF_OPEN 三态机保护 DB 调用，`@circuit_protected` 装饰器 + fallback 支持
- **多级降级策略**：新增 `core/degradation.py` (`DegradationManager`)，NORMAL→REDUCED→MINIMAL→EMERGENCY 四级降级，按模块优先级自动剪裁
- **特性开关**：新增 `core/feature_flags.py` (`FeatureFlags`)，`FF_{MODULE}_ENABLED` 环境变量控制模块运行时开关，main.py + pipeline 联动
- **字段选择 API**：新增 `api/field_selection.py`，`?fields=price,volume` 稀疏字段集，减少无用数据传输
- **ETag 条件请求**：新增 `api/etag_middleware.py` (`ETagMiddleware`)，If-None-Match 匹配时返回 304，节省带宽
- **API 版本化**：新增 `api/versioning.py` (`VersionedRouter`)，/v1/ 前缀 + Sunset 头 + 版本常量
- **数据异常检测**：新增 `core/data_anomaly_detector.py` (`DataAnomalyDetector`)，Z-score + 空值尖刺 + 量降检测，severity 分级
- **数据保留策略**：新增 `core/data_retention.py` (`DataRetentionService`)，按表定义 hot/warm/archive 层 + rollup SQL 生成
- **数据血缘追踪**：新增 `core/data_lineage.py` (`DataLineageTracker`)，记录 source→target 数据流转事件，支持 trace 回溯
- **告警规则引擎**：新增 `monitoring/alerting.py` (`AlertEvaluator`)，6 条默认规则（错误率/延迟/内存/连接池/数据新鲜度/熔断器），cooldown 防抖
- **结构化日志**：新增 `core/structured_logging.py`，correlation_id 上下文传播 + JSON 格式输出（`STRUCTURED_LOGS=true`），request_id 自动关联
- **事件总线**：新增 `core/event_bus.py` (`EventBus`)，topic 订阅 + 同步/异步发布 + 后台消费者线程，模块间松耦合通信
- **X-API-Version 头**：所有响应携带 API 版本号

**v3.6.0 — 数据采集效率与运行时优化**

- **采集器符号批量化**：funding 优先 `fetchFundingRates` 批量 API（回退并行获取），kline 改为 `parallel_fetch()` 并行采集（默认 6 并发），新增 `data_layer/exchange_data/batch_utils.py`
- **请求级去重缓存**：新增 `data_layer/request_dedup_cache.py`，同一采集周期内相同请求直接返回缓存（TTL 60s），避免重复外部 API 调用
- **httpx 连接池优化**：`AsyncBaseDataClient` 添加 `httpx.Limits(max_connections=20, max_keepalive=10)`，复用 TCP 连接
- **批量写入强制化**：新增 `database/batch_writer.py` (`BatchWriter`)，自动分块 500 行/批，防止 WAL 压力
- **JSON 序列化加速**：引入 `orjson`，FastAPI 默认使用 `ORJSONResponse`，减少 20-30% 序列化开销
- **连接池动态扩容**：`DB_POOL_MAX` 默认提升至 50，新增 `DB_POOL_OVERFLOW=10` + `DB_POOL_IDLE_TIMEOUT=300`
- **聚合端点查询合并**：`/asset-profile` 从 5 次 DB 查询合并为 1 次 JOIN + 1 次 klines，`/watchlist` 用 `IN` 批量查询替代 N+1
- **符号索引预建**：`config/symbols.py` 新增 `_SYMBOL_INDEX` dict，`get_symbol_sector/tier` 从 O(n) 降为 O(1)
- **端点差异化限流**：昂贵端点（/aggregate/）消耗 5 倍配额，添加 `X-RateLimit-Limit`/`X-RateLimit-Remaining` 响应头
- **模块优先级分级**：`ModuleSpec` 新增 `priority` 字段（critical/normal/low），按优先级差异化重启次数（10/3/1）
- **采集器崩溃快照缓冲**：新增 `core/snapshot_buffer.py`，维护最近 3 次采集快照，崩溃恢复时可注入

**v3.5.0 — 运行时可靠性与可观测性**

- **子进程资源限制**：`launch_module()` 添加 `preexec_fn` + `setrlimit`，每个守护子进程受 `SUBPROCESS_MEM_LIMIT_MB`（默认 2048）和 `SUBPROCESS_CPU_LIMIT_SECONDS`（默认 3600）限制，OOM (SIGKILL) 自动告警
- **技术指标增量跳过**：`merge_klines()` / `calculate_indicators()` 循环前快速比对 raw vs merged / merged vs indicators 最新时间戳，无新数据时 O(1) 跳过（替代完整 fetch+计算）
- **WebSocket 实时推送**：新增 `api/websocket_manager.py` + `api/routers/ws.py`，支持频道级广播（pipeline / health / indicators:{symbol}），管道完成时自动推送事件
- **热数据预加载**：新增 `api/preloader.py`，API 启动时自动预热 latest_* 快照表到 QueryCache，消除冷启动延迟
- **OpenTelemetry 分布式追踪**：新增 `core/tracing.py` + `core/trace_decorators.py`，可选启用（`OTEL_ENABLED=true`），自动注入 FastAPI span + `@traced` 装饰器
- **深度健康检查**：`/health/collectors` 按模块报告采集新鲜度（超阈值标记 stale），`/health/external` 并发探测 Binance / CoinGecko / Deribit 连通性

**v3.4.0 — 性能与架构优化**

- **异步 HTTP 客户端基类**：新增 `core/async_base_data_client.py`，提供 `AsyncBaseDataClient`（异步熔断器 + 令牌桶限流 + 指数退避），与同步 `BaseDataClient` 接口对称，数据层模块可直接继承获得异步能力
- **API 路由自动发现**：新增 `api/router_registry.py`，自动扫描 `api/routers/` 目录注册路由，`app.py` 从 400+ 行精简至 230 行，新增路由模块无需手动注册
- **数据库模块化拆分**：新增 `database/managers/` 包（ConnectionMixin + SchemaUtilsMixin + QueryMethodsMixin），db_manager.py 核心方法提取为可复用 Mixin
- **数据库查询优化**：新增 `database/query_profiler.py`（EXPLAIN QUERY PLAN 分析、慢查询统计、自动 ANALYZE）+ `database/partial_indexes.py`（部分索引 + 覆盖索引）
- **内存与 DataFrame 管控**：新增 `database/chunked_query.py`（分块查询生成器）+ `core/memory_monitor.py`（RSS 监控 + DataFrame 大小检测），技术指标计算增加 `INDICATOR_MAX_HISTORY` 截断保护
- **缓存失效策略增强**：`QueryCache` 新增 `invalidate_prefix()`、`invalidate_group()` 方法 + stale-while-revalidate 模式 + per-key TTL，管道刷新改为按模块前缀精准失效（替代全量清空）

### 2025-06-04

**v3.3.2 — PostgreSQL 连接池稳定性与子进程修复**

- 读操作自动提交：fetch_one/fetch_all 成功后自动 COMMIT，消除 idle-in-transaction 连接泄漏
- PostgreSQL 调优：max_connections=200 + idle_in_transaction_session_timeout=60s
- 子进程启动修复：subprocess.Popen 添加 cwd=PROJECT_ROOT，解决 ModuleNotFoundError
- 服务依赖解耦：AIMarketContextService/AssetReadinessService 不再共享 analytics 连接池给数据层子服务
- datetime 类型兼容：pipeline_latency 服务正确处理 PostgreSQL 返回的 datetime 对象
- Pydantic 验证修复：DomainListItem.latest_data_time 确保转为字符串

**v3.3.1 — PostgreSQL 生产后端全面兼容（零崩溃）**

- PostgreSQL Docker 容器化集成：Docker Compose 一键部署 PostgreSQL 16 + 三 Schema 自动初始化
- SQL 方言适配增强：ON CONFLICT 冲突键智能推断（15+ 模式）、INSERT OR IGNORE 支持、保留字自动引用
- 自动回滚机制：psycopg2 事务失败后自动 ROLLBACK，消除 InFailedSqlTransaction 级联错误
- Schema 自动补齐：CREATE TABLE IF NOT EXISTS 拦截 + ALTER TABLE ADD COLUMN 自动补齐缺失列
- 类型兼容修复：布尔→整数类型转换（market_info）、TIMESTAMP 比较修复（news_data）
- 环境变量自动加载：python-dotenv 集成，子进程自动继承 .env 配置
- 34 个数据采集模块 + API 服务全部在 PostgreSQL 上零崩溃运行

### 2025-06-03

**v3.3 — 监控与可观测性（Prometheus + Grafana）**

- `monitoring/` 目录：完整 Prometheus 指标导出 + Docker Compose 部署 Grafana/Prometheus
- 14 个 Prometheus 指标：HTTP 请求（Counter/Histogram/Gauge）、模块状态/重启/Uptime、域延迟/新鲜度、WMI 评分、管道阶段时长、数据库大小、市场告警
- FastAPI 中间件自动记录请求延迟和并发数（路径归一化防止高基数）
- 3 个预置 Grafana 仪表盘：System Overview、Pipeline Health、Market Alerts
- Docker Compose 一键部署：Prometheus（15s 抓取、30 天保留）+ Grafana（自动 provision 数据源和仪表盘）
- 优雅降级：`prometheus_client` 未安装时系统正常运行，所有监控代码用 try/except ImportError 保护
- 现有文件最小侵入：api/app.py (+5 行)、main.py (+15 行)、logic_layer/logic_pipeline/service.py (+12 行)

**v3.2 — 核心基础设施升级（基类抽象 + API 分页 + PostgreSQL 后端）**

- `core/` 基类抽象层：BaseDataClient（熔断器 + 令牌桶限流 + 指数退避重试）、BaseDataService、BaseDataRunner、BaseAnalyticsRepository、BaseAnalyticsService、BaseAnalyticsRunner，新模块继承后只需实现业务逻辑
- API 分页机制：`api/pagination.py` 提供游标分页（keyset）+ 偏移分页，ABSOLUTE_MAX_LIMIT=1000 防止 OOM，5 个示范端点（exchange/technical/stablecoin_flow/whale_pnl/defi_liquidation）
- PostgreSQL 生产后端：`database/backends/` 多后端抽象（SQLite 默认 / PostgreSQL 生产），psycopg2 ThreadedConnectionPool（min=5, max=20），SQL 方言自动适配（? → %s、datetime() → NOW()、INSERT OR REPLACE → UPSERT）
- Alembic 迁移：`alembic/` 目录支持 PostgreSQL 3 Schema（exchange_data/market_data/analytics）迁移管理
- `/health/db` 端点：连接池状态监控
- 向后兼容：默认 DB_BACKEND=sqlite，所有 89 个现有路由和测试无需修改
- Bug 修复：`database/router.py` 添加 `get_market_data_db()` 方法别名，修复 8 个 v3.1 逻辑模块 AttributeError
- Bug 修复：`data_quality/audit.py` 注册 5 个缺失模块到 service_factories，修复 KeyError 崩溃
- Bug 修复：修复 13 个逻辑层模块 SQL schema 不匹配问题（错误的表名/列名/数据库域引用），所有 Phase1-3 模块零错误运行
- Bug 修复：修复 6 个逻辑层模块运行时错误（VIEW 索引冲突、表名冲突、错误 schema 引用）及 search_trend_data 网络超时崩溃——technical_indicators/exchange_comparison 忽略 index-on-VIEW 错误；funding_rate_model 表重命名避免 VIEW 冲突；contagion_risk 表重命名避免 liquidation_cascade 冲突；temporal_pattern 修正 VIEW 名（klines/funding_rates）；narrative_regime 修正输入表名（news_sentiment_labels）并 stub 缺失社交/alternative 表；search_trend_data lazy-load TrendReq 防止网络超时崩溃

### 2025-06-02

**v3.1 — AI 认知盲区补全**

- 11 个新数据采集模块：stablecoin_flow_data（稳定币链上 mint/burn 事件流）、token_unlock_realtime（代币解锁实时追踪）、cex_orderbook_depth（5000 档全量深度盘口）、whale_wallet_pnl（巨鲸钱包 PnL 追踪）、nft_market_data（NFT 市场数据）、defi_liquidation_data（DeFi 真实清算事件）、dex_trade_flow（DEX 大单交易流）、cross_chain_messaging（跨链消息协议）、lending_utilization（借贷协议利用率）、search_trend_data（搜索趋势热度）、exchange_announcement（交易所公告）
- 6 个新逻辑分析模块：stablecoin_pulse（净铸造脉冲 + expansion/contraction 信号）、unlock_impact（预期卖压 + 流动性吸收 + 冲击评分）、depth_regime（深度 regime 分类 + 墙位预警 + 滑点建模）、smart_money_conviction（Smart Money 信念指数 + 散户背离）、defi_stress（DeFi 压力指数 + 级联概率 + 协议风险排名）、retail_fomo_index（FOMO/FUD 指数 + 逆向信号 + 反转概率）
- 17 个新 API 路由（85 端点）：/stablecoin-flow、/token-unlock、/orderbook-depth、/whale-pnl、/nft-market、/defi-liquidation、/dex-trade-flow、/cross-chain-msg、/lending-utilization、/search-trend、/exchange-announcement、/stablecoin-pulse、/unlock-impact、/depth-regime、/smart-money-conviction、/defi-stress、/retail-fomo
- 数据域从 32 个扩展到 43 个，逻辑模块从 33 个扩展到 39 个，API 端点数达 477
- 逻辑管道 Phase 2 新增 6 个并行模块 + DAG 节点 + 缓存失效映射
- 文档同步更新：README.md、data_layer/README.md、logic_layer/README.md、api/routers/README.md 全部对齐 v3.1 模块清单

**v3.0 — AI 交易决策关键维度扩展**

- 8 个新数据采集模块：prediction_market_data（Polymarket 预测市场概率）、onchain_holder_data（MVRV/SOPR/NUPL 链上持有者指标）、liquid_staking_data（Lido/RocketPool/EigenLayer 质押与再质押）、mempool_data（BTC 内存池压力与大额交易）、funding_round_data（VC 融资轮次与投资方动向）、exchange_reserve_data（交易所 BTC/ETH/USDT 储备净流动）、miner_data（算力/Puell Multiple/矿工收入/难度调整）、derivatives_sentiment_data（恐惧贪婪/多空比/OI/杠杆率）
- 5 个新逻辑分析模块：holder_behavior_analysis（STH/LTH 分离 + SOPR 状态机 + 积累/派发阶段判定）、liquidity_regime（流动性状态分类 + DeFi-CeFi 利差 + 稳定币脉冲）、event_probability（预测市场概率跳变 + 事件→资产映射 + 新闻交叉验证）、miner_pressure（Puell 分位 + 矿工投降指数 + 减半周期相位）、market_sentiment_composite（多维度情绪加权评分 + 极端检测 + 背离反转信号）
- 13 个新 API 路由（65 端点）：/prediction-market、/onchain-holder、/liquid-staking、/mempool、/funding-round、/exchange-reserve、/miner、/derivatives-sentiment、/holder-behavior、/liquidity-regime、/event-probability、/miner-pressure、/sentiment-composite
- 数据域从 23 个扩展到 31 个，逻辑模块从 28 个扩展到 33 个，API 端点数达 390+
- 逻辑管道 Phase 2 新增 5 个并行模块 + DAG 节点 + 缓存失效映射
- 文档同步更新：README.md、ARCHITECTURE.md、data_layer/README.md、logic_layer/README.md、api/README.md 全部对齐 v3.0 模块清单与端点表

### 2025-06-01

**v2.9 — 异常治理与架构可视化**

- 项目级异常层次结构：`exceptions.py` 提供 `EvoQuantError` 基类 + 分层子类（DataLayerError / LogicLayerError / DatabaseError / APIError），携带 error_code 和 context
- API 错误响应标准化：`api/errors.py` 统一返回 `{error_code, detail, request_id, timestamp}` 格式，覆盖 HTTPException / ValidationError / 兜底 Exception
- 集成测试：`tests/integration/` 新增 7 个跨层测试（数据层→逻辑层流、多模块共享 DB、API 端点格式验证）
- 架构图：`ARCHITECTURE.md` 包含 6 张 Mermaid 图（系统总览、数据流时序、DAG 调度、模块结构、质量治理、进程管理）

**v2.8 — 测试覆盖扩展与工程治理**

- 单元测试大幅扩展：新增 24 个测试文件，覆盖 10 个数据层模块和 14 个逻辑层模块，测试文件总数达 54 个
- 结构化 JSON 日志：`config/logging.py` 重写为 JSON 格式输出，`LOG_LEVEL` 支持环境变量配置
- 开发依赖管理：新增 `requirements-dev.txt`（pytest、ruff、mypy 等）
- 预存测试修复：更新 `test_main.py` 和 `test_health.py` 以匹配当前模块注册表

**v2.7 — 工程化加固**

- 8 个新模块单元测试（33 tests）：perpetual_dex_data、onchain_address_data、dex_liquidity_data、gas_network_data、governance_data、liquidation_cascade、cross_venue_arbitrage、onchain_lead_lag
- 调度间隔集中化：8 个新数据模块的采集频率统一收入 `config/settings.py`，支持环境变量覆盖
- 模块自动启动：5 个新数据模块注册到 `main.py`（autostart=True, daemon 模式）
- 逻辑管道集成：3 个新逻辑模块接入 Phase 2 并行执行 + DAG 模式 + 事件驱动缓存失效
- 数据质量审计扩展：5 个新数据模块纳入 `data_quality/audit.py` 证据带覆盖
- 8 个模块级 README.md 文档

**v2.6 — 数据域与逻辑层第三轮扩展**

- 5 个新数据采集模块：perpetual_dex_data（dYdX/Hyperliquid/GMX 永续 DEX funding 和成交量）、onchain_address_data（Arkham/Etherscan 巨鲸地址画像和资金流）、dex_liquidity_data（Uniswap V3/Curve 池流动性 via The Graph）、gas_network_data（Etherscan/Blocknative Gas 和网络指标）、governance_data（Snapshot/Tally DAO 治理提案和投票）
- 3 个新逻辑分析模块：liquidation_cascade（清算集群检测、级联概率、热力图）、cross_venue_arbitrage（跨交易所价差、套利持续性、市场效率评分）、onchain_lead_lag（链上信号领先/滞后、Granger 因果、预测力排名）
- 8 个新 API 路由（61 端点）：/perpetual-dex(7)、/onchain-address(7)、/dex-liquidity(7)、/gas-network(7)、/governance(8)、/liquidation-cascade(8)、/cross-venue-arb(8)、/onchain-lead-lag(9)
- 数据域从 18 个扩展到 23 个，逻辑模块从 25 个扩展到 28 个，API 端点数达 330+

**v2.5 — 基础设施优化**

- 数据库索引优化：16 个复合索引覆盖高频查询列（symbol+exchange+timestamp DESC），初始化时自动创建
- DAG 调度器：逻辑管道支持基于依赖图的并行执行（`LOGIC_PIPELINE_USE_DAG=1`），无依赖模块可跨阶段并行
- 异步采集基础设施：`gather_with_concurrency()` + `run_in_thread()` 支持并行化交易所 API 调用
- 事件驱动缓存失效：按模块粒度清空受影响的缓存前缀，替代全量清空
- 分块批量写入：`execute_many_chunked()` 支持大批量 INSERT 分块提交，降低 WAL 积压
- Gzip 响应压缩：GZipMiddleware 自动压缩 >1KB 响应体，减少 60-80% 传输体积
- mypy 类型检查：渐进式严格配置，api/database/config 模块强制类型注解
- 依赖版本锁定：requirements.txt 全部 pin 到精确版本
- .gitignore 补充：排除根目录 *.db 文件（防止 6GB+ 误提交）

**v2.4 — 9 路由端点扩展**

- 9 个新路由从 3 端点扩展到 7 端点（+36 端点），API 总端点数达 270+
- ETF 资金流：新增发行商排名、溢折价追踪、连续流入/流出统计、异常流入检测
- 期货期限结构：新增 roll yield、曲线斜率历史、跨交易所 basis 对比、凸度异常检测
- MEV 数据：新增 builder 排名、三明治攻击分析、清算 MEV 趋势、集中度（HHI）
- CeFi 借贷利率：新增平台排名、利率倒挂检测、利率历史、资金利用率
- 时间模式识别：新增小时级季节性、星期效应、减半周期相位、Funding 8h 周期
- 资金流分解：新增 smart money 方向、积累/派发阶段、VPIN 告警、全资产 VPIN 排名
- 传染风险：新增系统性评分、CoVaR 分析、尾部 Beta、稳定币脱锚概率
- 信号衰减：新增半衰期历史、信号排名、跨信号背离、拥挤度历史
- 叙事状态机：新增按阶段过滤、注意力排名、关联 token、新兴叙事

### 2025-05-31

**v2.3 — 数据域扩展与逻辑层增强**

- 6 个新数据采集模块：social_sentiment_data（社交情绪）、whale_tracker_data（巨鲸追踪）、orderflow_data（订单流）、defi_protocol_data（DeFi 协议）、bridge_flow_data（跨链桥流）、regulatory_data（监管动态）
- 6 个新逻辑分析模块：regime_detection（市场状态分类）、anomaly_detection（异常检测）、liquidity_analysis（流动性分析）、volatility_forecast（波动率预测）、funding_rate_model（资金费率模型）、sentiment_signal（情绪信号）
- 数据域从 8 个扩展到 14 个，逻辑模块从 14 个扩展到 20 个
- 所有新模块遵循项目标准：独立目录、README.md、runner/service/client/models/repository 结构

**v2.2 — 可靠性与性能加固**

- 熔断器模式：交易所 API 连续失败 5 次自动熔断，60s 冷却后探测恢复
- API 输入验证：symbol 校验 SYMBOL_UNIVERSE、时间范围上限 90 天防全表扫描
- httpx 替代 urllib/requests：连接池复用、HTTP/2 支持
- 服务层查询缓存：多端点共享 DB 查询结果 + 请求合并（并发去重）

**v2.1 — 生产运维加固**

- 慢查询日志：超过阈值的 SQL 自动 WARNING（`DB_SLOW_QUERY_THRESHOLD_MS`）
- 缓存命中率指标：hits / misses / hit_rate_pct
- Phase 2 超时保护：并行模块超时不阻塞其他模块（默认 300s）
- 启动配置校验：`validate_config()` 检查调度间隔、保留策略合理性
- 指数退避重启：daemon 崩溃后 2s → 4s → 8s ... 最高 60s 退避
- 三阶段优雅关停：SIGINT → SIGTERM → SIGKILL
- `/metrics` 端点：缓存、查询缓存、限流器运维指标

**v2.0 — API 安全与中间件**

- 请求追踪：每个请求注入 `X-Request-ID`
- 滑动窗口限流：按 IP 限制请求频率（默认 200/min）
- 全局异常处理：未捕获异常返回安全 JSON，不泄露 traceback
- CORS 限制：通过环境变量配置允许来源
- 结构化日志：全 router 统一 loguru + 异常上下文

**v1.1 — 数据层优化**

- API TTL 缓存：高频只读端点短期内存缓存 + 管道刷新后自动失效
- Phase 2 并行执行：逻辑管道独立模块 ThreadPoolExecutor 并行
- AsyncIOScheduler：7 个数据层模块支持异步调度
- N+1 批量化：aggregate 路由 WHERE IN 替代循环逐条查询
- SQL GROUP BY 优化：funding 聚合改为数据库侧计算

**v1.0 — 基础架构**

- 3 交易所 × 18 资产 × 8 数据域完整采集
- 228 个技术指标（含 Ehlers 自适应、分形维度、微观结构）
- 14 个逻辑层模块：标准化、跨资产、风险、AI 上下文
- 100+ REST API 端点
- 3 域数据库拆分（exchange_data / market_data / analytics）
- 数据质量治理：WMI 指数、freshness 窗口、is_ready_for_ai
- Point-in-time 时间切片 + 特征历史序列

---

## License

本仓库使用 [`GPL-3.0`](LICENSE) 许可证。
