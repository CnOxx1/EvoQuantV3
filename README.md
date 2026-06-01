# EvoQuant

**给 AI 构建的加密市场世界模型。**

大多数量化项目从"策略"出发，EvoQuant 从"理解"出发。它解决的核心问题是：AI 在做交易决策前，需要一个完整、诚实、可回溯的市场认知底座。

```text
3 交易所 × 18 资产 × 23 数据域 × 228 技术指标 × 实时质量治理
→ AI 随时可查的完整市场上下文
```

## 为什么需要 EvoQuant

| 传统量化数据管道 | EvoQuant |
| --- | --- |
| 单交易所单币种 | 3 交易所 × 18 资产，多源交叉验证 |
| 只有 K 线和指标 | 23 个数据域：行情 + 宏观 + 新闻 + 链上 + 期权 + 衍生品 + 事件 + Tokenomics + 社交情绪 + 巨鲸追踪 + 订单流 + DeFi 协议 + 跨链桥流 + 监管动态 + ETF 资金流 + 期货期限结构 + MEV + CeFi 借贷利率 + 永续 DEX + 链上地址画像 + DEX 流动性 + Gas/网络 + 治理投票 |
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
│              REST API (330+ endpoints) / Bundle Query            │
├─────────────────────────────────────────────────────────────────┤
│                         Logic Layer (28 modules)                 │
│  technical_indicators → feature_standardization → cross_asset   │
│  macro_context → news_sentiment → portfolio_risk                │
│  market_breadth → asset_readiness → ai_market_context           │
│  pipeline_latency → time_slice → logic_pipeline                 │
│  regime_detection → anomaly_detection → liquidity_analysis      │
│  volatility_forecast → funding_rate_model → sentiment_signal    │
│  temporal_pattern → flow_decomposition → contagion_risk         │
│  alpha_decay → narrative_regime                                 │
│  liquidation_cascade → cross_venue_arbitrage → onchain_lead_lag │
├─────────────────────────────────────────────────────────────────┤
│                         Data Layer (24 modules)                  │
│  exchange_data │ macro_data │ news_data │ onchain_data          │
│  options_data │ tokenomics_data │ event_calendar │ alternative  │
│  social_sentiment │ whale_tracker │ orderflow │ defi_protocol   │
│  bridge_flow │ regulatory_data │ data_quality                   │
│  etf_flow_data │ perpetual_basis_curve │ mev_data │ cefi_lending│
│  perpetual_dex_data │ onchain_address_data │ dex_liquidity_data │
│  gas_network_data │ governance_data                             │
├─────────────────────────────────────────────────────────────────┤
│                         Storage Layer                            │
│  SQLite (3 域拆分) │ latest_* 快照 │ 历史表 │ 质量审计表       │
├─────────────────────────────────────────────────────────────────┤
│                         External Sources                         │
│  Binance │ OKX │ Bybit │ DeFiLlama │ Deribit │ 宏观数据源      │
│  LunarCrush │ Santiment │ Arkham │ Nansen │ WhaleAlert │ SEC   │
│  SoSoValue │ Flashbots │ EigenPhi │ dYdX │ Hyperliquid │ GMX  │
│  Uniswap V3 │ Curve │ Etherscan │ Blocknative │ Snapshot │Tally│
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
├── data_layer/      外部数据采集、标准化、落库（24 个数据模块）
├── database/        SQLite 建表、迁移、路由和读写入口
├── logic_layer/     AI-ready 特征、上下文和治理结果（28 个逻辑模块）
├── api/             对外 REST API 服务（330+ 端点）
├── tests/           单元测试与模块测试
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

## API

330+ REST 端点，覆盖：

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

启动后访问 `/docs`（Swagger）或 `/redoc`（ReDoc）查看完整接口文档。

## 文档导航

- 项目总览：[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)
- 数据层入口：[data_layer/README.md](data_layer/README.md)
- 逻辑层入口：[logic_layer/README.md](logic_layer/README.md)
- API 接口文档：[api/README.md](api/README.md)
- 数据库说明：[database/README.md](database/README.md)
- AI 数据能力总览：[AI_DATA_CAPABILITIES.md](AI_DATA_CAPABILITIES.md)

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

### P2 — 进行中

- [ ] 增量导出：Parquet/Arrow 格式，供 ML pipeline 批量训练
- [ ] 监控告警：数据断流自动推送
- [ ] 预测验证框架：AI 预测 → 对比实际 → 统计准确率
- [ ] 数据保留策略：K 线/资金费率保留 2 年+

### P3 — 长期方向

- [ ] 信号引擎：趋势/均值回归/事件驱动信号生成
- [ ] 风控引擎：仓位管理、止损、波动率约束
- [ ] 执行层：下单、滑点控制、跨所路由
- [ ] 组合层：多资产权重、再平衡、回撤控制

## 更新记录

### 2025-06-01

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
