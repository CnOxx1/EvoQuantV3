# EvoQuant Data API

AI 市场数据供给层对外 REST 接口。基于 FastAPI 构建，为 AI 消费者和 Sui Bridge 提供结构化、质量自知的市场信息。

## 启动

```bash
# 独立启动
python -m api.app --port 8000

# 开发模式（热重载）
python -m api.app --port 8000 --reload

# 通过 main.py 统一管理
python main.py --modules api_server
```

启动后访问自动生成的交互式文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## 端点总览

### 基础 / 元数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/symbols` | GET | 资产宇宙列表（含 tier、sector） |
| `/health/` | GET | 管道整体健康 + WMI 摘要 |
| `/domains/` | GET | 各数据域健康状态 |

### AI Bundle

| 端点 | 方法 | 说明 |
|---|---|---|
| `/bundle/{symbol}` | GET | 单资产完整 AI 市场上下文 bundle |
| `/bundle/` | GET | 全资产 WMI + 质量摘要 |

### 综合信号（Bridge 核心接口）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/signals/{symbol}` | GET | 单资产完整信号 bundle（趋势/风险/资金费率/AI判断） |
| `/signals/` | GET | 全资产信号摘要，支持按风险等级过滤 |

### 技术指标 & K线

| 端点 | 方法 | 说明 |
|---|---|---|
| `/technical/indicators/{symbol}` | GET | 单资产技术指标（RSI/MACD/BB/ATR/ADX） |
| `/technical/indicators` | GET | 所有资产最新技术指标快照 |
| `/technical/klines/{symbol}` | GET | 合并 K 线（多交易所聚合 OHLCV） |

### 风险指标

| 端点 | 方法 | 说明 |
|---|---|---|
| `/risk/portfolio/latest` | GET | 最新组合风险快照（VaR/波动率/集中度） |
| `/risk/portfolio/history` | GET | 组合风险历史序列 |
| `/risk/volatility` | GET | 所有资产当前日/年化波动率 |
| `/risk/score/{symbol}` | GET | 单资产风险评分（0-100，附 risk_level 标签） |

### 交易所数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/exchange/funding/{symbol}` | GET | 单资产资金费率（含各交易所） |
| `/exchange/funding` | GET | 全资产资金费率摘要 |
| `/exchange/orderbook/{symbol}` | GET | 订单簿快照（价差、深度、不平衡度） |
| `/exchange/ticker/{symbol}` | GET | 实时 Ticker（价格、成交量、涨跌幅） |
| `/exchange/comparison/{symbol}` | GET | 跨交易所对比快照（价差、执行偏好） |
| `/exchange/open-interest/{symbol}` | GET | 持仓量快照 |
| `/exchange/liquidations/{symbol}` | GET | 清算数据 |
| `/exchange/trade-flow/{symbol}` | GET | 买卖压力（按交易所，含 CVD） |
| `/exchange/basis/{symbol}` | GET | 现货-期货基差（按交易所） |
| `/exchange/positioning/{symbol}` | GET | 多空比（按交易所） |

### 宏观数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/macro/latest` | GET | 最新宏观上下文快照（AI 聚合结果） |
| `/macro/history` | GET | 宏观快照历史序列 |
| `/macro/factors` | GET | 原始宏观因子时序（DXY/VIX/利率等） |
| `/macro/regime` | GET | 当前宏观情绪摘要（risk_on/risk_off） |

### 跨资产分析

| 端点 | 方法 | 说明 |
|---|---|---|
| `/cross-asset/correlation` | GET | 跨资产相关性矩阵 |
| `/cross-asset/relative-strength` | GET | 各资产相对 BTC 强弱排名 |
| `/cross-asset/sector-rotation` | GET | 板块轮动状态 |
| `/cross-asset/fund-flow` | GET | 资金流向（净主动买卖、OI 变化） |
| `/cross-asset/summary` | GET | 跨资产分析摘要（Dashboard 快速消费） |

### 链上数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/onchain/exchange-flow/{symbol}` | GET | 交易所净流量（bullish/bearish 信号） |
| `/onchain/whale-activity/{symbol}` | GET | 鲸鱼活动（积累/派发信号） |
| `/onchain/stablecoin` | GET | 稳定币供应量与流动性 |
| `/onchain/protocol-tvl` | GET | DeFi 协议 TVL |
| `/onchain/network/{symbol}` | GET | 网络使用状况（活跃地址/交易量） |
| `/onchain/summary` | GET | 链上数据全局摘要 |

### 新闻情感 & 市场广度

| 端点 | 方法 | 说明 |
|---|---|---|
| `/sentiment/news/latest` | GET | 最新新闻列表（含情感标注） |
| `/sentiment/news/score/{symbol}` | GET | 单资产新闻情感评分（-1~+1） |
| `/sentiment/market-breadth` | GET | 市场广度快照（多空比、价格广度） |
| `/sentiment/market-breadth/history` | GET | 市场广度历史序列 |
| `/sentiment/summary` | GET | 情感 + 广度合并摘要 |
| `/sentiment/signal/{symbol}` | GET | 情绪-价格信号（reversal/confirmation/divergence） |
| `/sentiment/causality/{symbol}` | GET | Granger 因果检验（情绪是否领先价格） |

### 数据质量 & 就绪度

| 端点 | 方法 | 说明 |
|---|---|---|
| `/data-quality/audit/latest` | GET | 最新数据质量审计快照（含解析后的 JSON 字段） |
| `/data-quality/audit/history` | GET | 审计历史（摘要列，默认 48 条） |
| `/data-quality/readiness/latest` | GET | 最新资产就绪度快照（含解析后的 bundle） |
| `/data-quality/readiness/history` | GET | 就绪度趋势（默认 48 条） |
| `/data-quality/market-structure` | GET | 最新市场结构快照 |
| `/data-quality/collection-runs` | GET | 数据采集运行记录（支持 module/status 过滤） |

### 特征标准化

| 端点 | 方法 | 说明 |
|---|---|---|
| `/features/composites/{symbol}` | GET | 单资产所有复合分数 |
| `/features/composites?name=` | GET | 指定复合分数的跨资产排名 |
| `/features/details/{symbol}` | GET | 单资产所有标准化特征明细 |
| `/features/ranking?feature=` | GET | 指定特征的跨资产排名 |

### 另类数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/alternative/developer/{symbol}` | GET | GitHub 开发者活动指标 |
| `/alternative/stablecoin-flows` | GET | 稳定币供应/流动数据（支持 entity 过滤） |
| `/alternative/factors` | GET | 通用因子探索（支持 category 过滤） |

### 聚合查询

| 端点 | 方法 | 说明 |
|---|---|---|
| `/aggregate/asset-profile/{symbol}` | GET | 单资产全维度画像（价格+衍生品+技术+风险+因子），替代 6+ 次请求 |
| `/aggregate/multi-asset-compare` | GET | 2-5 资产横向对比 + 排名 + 分歧检测 |
| `/aggregate/sector-snapshot` | GET | 板块聚合视图（领涨/领跌、板块统计、轮动阶段） |
| `/aggregate/derivatives-heatmap` | GET | 全市场衍生品热力图（资金费率/OI/基差） |
| `/aggregate/market-regime` | GET | 市场体制判断（趋势/震荡/恐慌/狂热） |
| `/aggregate/correlation-context/{symbol}` | GET | 单资产相关性上下文（Beta、最相关/最不相关） |
| `/aggregate/watchlist` | GET | 自定义观察列表批量查询 |

### AI/策略辅助

| 端点 | 方法 | 说明 |
|---|---|---|
| `/strategy/multi-factor-score/{symbol}` | GET | 6 维多因子打分（趋势/动量/资金流/情绪/波动/价值） |
| `/strategy/entry-exit/{symbol}` | GET | 入场/出场价位建议（基于 BB/ATR/支撑阻力） |
| `/strategy/regime-strategy` | GET | 当前体制下的策略推荐（趋势跟踪/均值回归/套利等） |
| `/strategy/divergence-scanner` | GET | 全市场价格-指标背离扫描 |
| `/strategy/funding-arb` | GET | 资金费率套利机会（做空永续+做多现货） |
| `/strategy/squeeze-detector` | GET | 空头/多头挤压检测 |
| `/strategy/mean-reversion-candidates` | GET | 统计极端延伸资产（z-score 筛选） |
| `/strategy/portfolio-signals` | GET | 全市场信号排行（多/空候选 + 组合指标） |

### 实时监控

| 端点 | 方法 | 说明 |
|---|---|---|
| `/monitor/alerts` | GET | 主告警端点（汇总所有类型告警，按严重度排序） |
| `/monitor/price-breakouts` | GET | 价格突破检测（BB/EMA 突破） |
| `/monitor/funding-anomalies` | GET | 资金费率异常告警 |
| `/monitor/liquidation-surges` | GET | 清算激增检测 |
| `/monitor/volume-spikes` | GET | 成交量异常放大检测 |
| `/monitor/positioning-extremes` | GET | 持仓极端告警（拥挤度） |
| `/monitor/oi-divergence` | GET | OI 与价格背离检测 |

### 订单流智能

| 端点 | 方法 | 说明 |
|---|---|---|
| `/orderflow/cvd/{symbol}` | GET | CVD 时序 + 价格背离检测 |
| `/orderflow/aggression/{symbol}` | GET | 多交易所买卖侵略性对比 |
| `/orderflow/whale-trades/{symbol}` | GET | 大单检测（百分位筛选） |
| `/orderflow/depth-heatmap/{symbol}` | GET | 订单簿深度热力图（挂单墙检测） |
| `/orderflow/imbalance-history/{symbol}` | GET | 订单簿失衡时序 + 趋势检测 |
| `/orderflow/market-impact/{symbol}` | GET | 滑点估算 + 最优执行交易所 |
| `/orderflow/summary` | GET | 全市场订单流摘要排名 |

### 衍生品复合信号

| 端点 | 方法 | 说明 |
|---|---|---|
| `/derivatives/health/{symbol}` | GET | 统一衍生品健康评分（funding+basis+positioning+OI+liquidation） |
| `/derivatives/leverage-map` | GET | 全市场杠杆热力图（哪些资产最拥挤） |
| `/derivatives/funding-curve/{symbol}` | GET | 资金费率历史 + 体制检测 + 均值回归信号 |
| `/derivatives/oi-divergence/{symbol}` | GET | OI vs 价格背离（挤压风险检测） |
| `/derivatives/liquidation-levels/{symbol}` | GET | 清算集中区域估算 |
| `/derivatives/positioning-extremes` | GET | 全市场持仓极端筛选（拥挤交易=反转风险） |
| `/derivatives/funding-prediction/{symbol}` | GET | 下期资金费率预测（均值回归+动量模型） |
| `/derivatives/basis-signal/{symbol}` | GET | 基差均值回归信号（contango/backwardation/flat） |

### 新闻情报

| 端点 | 方法 | 说明 |
|---|---|---|
| `/news-intel/signal` | GET | 新闻驱动交易信号（加权情感动量） |
| `/news-intel/events/upcoming` | GET | 即将到来的市场事件（解锁、日历） |
| `/news-intel/narrative/{symbol}` | GET | 单资产主导叙事提取 |
| `/news-intel/cross-asset-sentiment` | GET | 全资产情感热力图 |
| `/news-intel/regulatory-radar` | GET | 监管新闻过滤（突发风险） |
| `/news-intel/source-reliability` | GET | 新闻源可靠性统计 |

### AI 决策上下文

| 端点 | 方法 | 说明 |
|---|---|---|
| `/ai-context/decision-bundle/{symbol}` | GET | AI 决策所需全部信息一次返回 |
| `/ai-context/market-state` | GET | 全局市场状态（结构+就绪度+广度） |
| `/ai-context/factor-regime` | GET | 全资产因子体制矩阵 |
| `/ai-context/arbitrage-opportunities` | GET | 跨交易所套利机会 |
| `/ai-context/data-freshness` | GET | 数据新鲜度报告（哪些数据过期） |
| `/ai-context/trading-readiness/{symbol}` | GET | 单资产可交易性评估 |

### 技术指标深度分析

| 端点 | 方法 | 说明 |
|---|---|---|
| `/technical-deep/indicator/{symbol}` | GET | 单指标时序提取（指定字段名） |
| `/technical-deep/multi/{symbol}` | GET | 多指标批量提取（逗号分隔字段） |
| `/technical-deep/extremes/{symbol}` | GET | 极端读数检测（RSI/BB/Stoch/CCI 超买超卖） |
| `/technical-deep/divergences/{symbol}` | GET | 价格 vs 指标背离检测（RSI/MACD/OBV） |
| `/technical-deep/regime/{symbol}` | GET | 技术体制分类（趋势/震荡/高波动，基于 ADX+ATR+BB） |
| `/technical-deep/scanner` | GET | 全市场指标条件扫描（gt/lt/cross_above/cross_below） |
| `/technical-deep/available-fields` | GET | 列出所有可用指标字段（PRAGMA 动态获取） |

### 组合分析

| 端点 | 方法 | 说明 |
|---|---|---|
| `/portfolio/snapshot` | GET | 最新组合风险快照（权重/VaR/集中度完整解析） |
| `/portfolio/drawdown` | GET | 最大回撤 + 当前回撤 + 回撤区间 |
| `/portfolio/concentration` | GET | HHI 集中度 + 有效资产数 + 趋势 |
| `/portfolio/var-decomposition` | GET | VaR 分解（各资产风险贡献） |
| `/portfolio/correlation-risk` | GET | 组合相关性聚类风险（高相关配对检测） |
| `/portfolio/risk-trend` | GET | 风险指标趋势（VaR/vol 斜率 + 方向） |

### 市场微观结构

| 端点 | 方法 | 说明 |
|---|---|---|
| `/microstructure/volatility-profile/{symbol}` | GET | 多时间框架波动率结构（1h/4h/1d） |
| `/microstructure/volume-profile/{symbol}` | GET | 成交量分布（VPOC/VAH/VAL + 分 bin 明细） |
| `/microstructure/spread-history/{symbol}` | GET | 历史买卖价差演变 |
| `/microstructure/session-stats/{symbol}` | GET | 日内时段统计（亚洲/欧洲/美洲） |
| `/microstructure/gap-analysis/{symbol}` | GET | 价格跳空分析（方向 + 幅度） |
| `/microstructure/liquidity-heatmap/{symbol}` | GET | 按小时/星期聚合流动性热力图 |

### 跨资产历史

| 端点 | 方法 | 说明 |
|---|---|---|
| `/cross-asset-history/correlation` | GET | 相关性矩阵历史趋势 |
| `/cross-asset-history/correlation/pair` | GET | 两资产配对相关性历史 |
| `/cross-asset-history/relative-strength/{symbol}` | GET | 单资产 RS 排名历史 |
| `/cross-asset-history/sector-rotation` | GET | 板块轮动阶段历史 |
| `/cross-asset-history/fund-flow` | GET | 资金流历史趋势 |
| `/cross-asset-history/exchange-comparison/{symbol}` | GET | 跨交易所对比历史 |

### 因子探索

| 端点 | 方法 | 说明 |
|---|---|---|
| `/factors/search` | GET | 全域因子搜索（关键字匹配 name/description/category） |
| `/factors/timeseries/{domain}/{factor_id}` | GET | 统一因子时序获取 |
| `/factors/correlation` | GET | 任意两因子相关性计算（Pearson） |
| `/factors/summary` | GET | 全域因子概览（数量/新鲜度/覆盖率） |
| `/factors/domains` | GET | 列出所有因子域及其 catalog |

### 社交情绪

| 端点 | 方法 | 说明 |
|---|---|---|
| `/social-sentiment/score/{symbol}` | GET | 单资产社交情绪评分（加权情绪、多空比、KOL 情绪） |
| `/social-sentiment/history/{symbol}` | GET | 社交情绪时序（最近 N 条聚合记录） |
| `/social-sentiment/ranking` | GET | 全资产社交情绪排名 |
| `/social-sentiment/summary` | GET | 市场整体社交情绪概览（市场情绪、多空分布） |

### 巨鲸追踪

| 端点 | 方法 | 说明 |
|---|---|---|
| `/whale-tracker/recent` | GET | 最近大额转账列表（可按 symbol/type 过滤） |
| `/whale-tracker/flow/{symbol}` | GET | 单资产巨鲸净流（deposit vs withdrawal） |
| `/whale-tracker/ranking` | GET | 按 24h 巨鲸活跃度排名 |
| `/whale-tracker/alerts` | GET | 异常大额转账预警（超过阈值） |

### 微观订单流（新数据源）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/orderflow-micro/pressure/{symbol}` | GET | 买卖压力分析（CVD + aggression_ratio） |
| `/orderflow-micro/large-trades/{symbol}` | GET | 大单统计（次数、金额） |
| `/orderflow-micro/cross-exchange/{symbol}` | GET | 跨交易所订单流对比 |
| `/orderflow-micro/summary` | GET | 全市场订单流概览 |

### DeFi 协议

| 端点 | 方法 | 说明 |
|---|---|---|
| `/defi/tvl` | GET | TVL 排名（按协议，支持链过滤） |
| `/defi/tvl/{protocol}` | GET | 单协议 TVL 详情 + 链分布 |
| `/defi/lending-rates` | GET | 借贷利率一览（按资产/协议） |
| `/defi/dex-volume` | GET | DEX 成交量排名 |
| `/defi/summary` | GET | DeFi 整体概览（总 TVL、DEX 量、平均利率） |

### 跨链桥流

| 端点 | 方法 | 说明 |
|---|---|---|
| `/bridge-flow/chains` | GET | 各链净流入/流出排名 |
| `/bridge-flow/bridges` | GET | 各桥成交量排名 |
| `/bridge-flow/migration` | GET | 资本迁移方向（L1→L2 / L2→L1 判定） |

### 监管动态

| 端点 | 方法 | 说明 |
|---|---|---|
| `/regulatory/events` | GET | 最近监管事件列表（支持 jurisdiction/severity 过滤） |
| `/regulatory/etf-tracker` | GET | ETF 申请状态追踪 |
| `/regulatory/risk-signal` | GET | 当前监管风险信号（基于事件密度和严重度） |
| `/regulatory/summary` | GET | 监管环境概览（30d 事件分布 + ETF 状态） |

### 市场状态（Regime）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/regime/current/{symbol}` | GET | 单资产当前 regime（price/vol/correlation/momentum） |
| `/regime/current` | GET | 全资产当前 regime 快照 |
| `/regime/history/{symbol}` | GET | regime 状态历史 |
| `/regime/transitions/{symbol}` | GET | regime 转换记录 |

### 异常检测

| 端点 | 方法 | 说明 |
|---|---|---|
| `/anomaly/recent` | GET | 最近异常事件列表（支持 symbol/severity 过滤） |
| `/anomaly/active/{symbol}` | GET | 单资产当前活跃异常 |
| `/anomaly/market-risk` | GET | 市场整体异常风险评估 |

### 流动性分析

| 端点 | 方法 | 说明 |
|---|---|---|
| `/liquidity/score/{symbol}` | GET | 流动性评分（0-100）+ 组成分解 |
| `/liquidity/slippage/{symbol}` | GET | 滑点估算（10K/100K/1M USD） |
| `/liquidity/alerts` | GET | 流动性预警列表（价差/深度异常） |
| `/liquidity/ranking` | GET | 全资产流动性排名 |

### 波动率预测

| 端点 | 方法 | 说明 |
|---|---|---|
| `/volatility/forecast/{symbol}` | GET | EWMA 波动率预测 + regime 分类 |
| `/volatility/cone/{symbol}` | GET | 波动率锥（历史分位） |
| `/volatility/ranking` | GET | 全资产波动率排名 |
| `/volatility/rv-iv-spread/{symbol}` | GET | RV-IV 价差信号 |

### ETF 资金流

| 端点 | 方法 | 说明 |
|---|---|---|
| `/etf-flow/daily` | GET | ETF 每日资金流列表 |
| `/etf-flow/summary` | GET | ETF 资金流汇总（含累计净流入） |
| `/etf-flow/issuer-ranking` | GET | 按净流入排名各发行商 |
| `/etf-flow/premium-discount/{asset}` | GET | ETF 溢价/折价追踪 |
| `/etf-flow/flow-streak/{asset}` | GET | 连续流入/流出天数统计 |
| `/etf-flow/anomalies` | GET | 异常流入检测（z-score 超阈值） |
| `/etf-flow/context` | GET | ETF 资金流 AI 上下文 bundle |

### 期货期限结构（Basis Curve）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/basis-curve/term-structure` | GET | 最新期限结构数据 |
| `/basis-curve/snapshot` | GET | 最新曲线快照（contango/backwardation 判定） |
| `/basis-curve/roll-yield/{symbol}` | GET | 7 日 roll yield 分析 |
| `/basis-curve/slope-history/{symbol}` | GET | 曲线斜率历史趋势 |
| `/basis-curve/exchange-comparison/{symbol}` | GET | 跨交易所 basis 对比 |
| `/basis-curve/anomalies` | GET | 期限溢价/凸度异常检测 |
| `/basis-curve/context` | GET | 期限结构 AI 上下文 bundle |

### MEV 数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/mev/blocks` | GET | 最近 MEV 区块数据 |
| `/mev/aggregation` | GET | MEV 聚合数据（按时间窗口） |
| `/mev/builder-ranking` | GET | Builder 按 MEV 提取量排名 |
| `/mev/sandwich-analysis` | GET | 三明治攻击频率和量 |
| `/mev/liquidation-pressure` | GET | 清算 MEV 趋势 |
| `/mev/concentration` | GET | Builder 集中度（HHI）趋势 |
| `/mev/context` | GET | MEV AI 上下文 bundle |

### CeFi 借贷利率

| 端点 | 方法 | 说明 |
|---|---|---|
| `/cefi-lending/rates` | GET | 最新 CeFi 借贷利率 |
| `/cefi-lending/spread` | GET | CeFi vs DeFi 利率价差 |
| `/cefi-lending/platform-ranking/{asset}` | GET | 各平台利率排名 |
| `/cefi-lending/inversion-signals` | GET | 利率倒挂检测（DeFi > CeFi） |
| `/cefi-lending/rate-history/{asset}` | GET | 利率历史趋势 |
| `/cefi-lending/utilization/{asset}` | GET | 资金利用率追踪 |
| `/cefi-lending/context` | GET | CeFi 借贷利率 AI 上下文 bundle |

### 时间模式识别

| 端点 | 方法 | 说明 |
|---|---|---|
| `/temporal-pattern/patterns` | GET | 最新时间模式检测结果 |
| `/temporal-pattern/seasonal/{symbol}` | GET | 季节性统计画像 |
| `/temporal-pattern/hourly/{symbol}` | GET | 小时级季节性效应 |
| `/temporal-pattern/day-of-week/{symbol}` | GET | 星期效应 |
| `/temporal-pattern/halving-cycle` | GET | 减半周期相位 |
| `/temporal-pattern/funding-cycle/{symbol}` | GET | Funding 8h 周期模式 |
| `/temporal-pattern/context` | GET | 时间模式 AI 上下文 bundle |

### 资金流分解

| 端点 | 方法 | 说明 |
|---|---|---|
| `/flow-decomposition/vpin/{symbol}` | GET | VPIN 最新值和历史 |
| `/flow-decomposition/decomposition/{symbol}` | GET | 资金流分解结果 |
| `/flow-decomposition/smart-money/{symbol}` | GET | Smart money 方向 |
| `/flow-decomposition/accumulation/{symbol}` | GET | 积累/派发阶段 |
| `/flow-decomposition/vpin-alerts` | GET | VPIN 高风险告警（>0.8） |
| `/flow-decomposition/ranking` | GET | 全资产 VPIN 排名 |
| `/flow-decomposition/context` | GET | 资金流分解 AI 上下文 bundle |

### 传染风险

| 端点 | 方法 | 说明 |
|---|---|---|
| `/contagion-risk/metrics` | GET | 最新传染风险指标 |
| `/contagion-risk/cascade` | GET | 当前级联风险评估 |
| `/contagion-risk/systemic-score` | GET | 系统性风险总评分 |
| `/contagion-risk/covar/{symbol}` | GET | 单资产 CoVaR 分析 |
| `/contagion-risk/tail-beta/{symbol}` | GET | 尾部 Beta 放大倍数 |
| `/contagion-risk/stablecoin-health` | GET | 稳定币脱锚概率 |
| `/contagion-risk/context` | GET | 传染风险 AI 上下文 bundle |

### 信号衰减（Alpha Decay）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/alpha-decay/decay` | GET | 信号衰减分析结果 |
| `/alpha-decay/crowding` | GET | 最新信号拥挤度指数 |
| `/alpha-decay/half-life/{signal_name}` | GET | 单信号半衰期历史 |
| `/alpha-decay/signal-ranking` | GET | 按衰减速率排名信号 |
| `/alpha-decay/divergence` | GET | 跨信号背离检测 |
| `/alpha-decay/crowding-history` | GET | 拥挤度历史趋势 |
| `/alpha-decay/context` | GET | 信号衰减 AI 上下文 bundle |

### 叙事状态机（Narrative Regime）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/narrative-regime/active` | GET | 当前活跃的市场叙事列表 |
| `/narrative-regime/transitions` | GET | 叙事阶段转换记录 |
| `/narrative-regime/by-phase/{phase}` | GET | 按生命周期阶段过滤 |
| `/narrative-regime/attention-ranking` | GET | 按注意力评分排名 |
| `/narrative-regime/tokens/{narrative_id}` | GET | 叙事关联 token |
| `/narrative-regime/emerging` | GET | 新兴叙事（早期机会） |
| `/narrative-regime/context` | GET | 叙事状态机 AI 上下文 bundle |

### 永续 DEX

| 端点 | 方法 | 说明 |
|---|---|---|
| `/perpetual-dex/funding` | GET | 跨 DEX 最新 funding rate |
| `/perpetual-dex/volume` | GET | 各 DEX 24h 成交量 |
| `/perpetual-dex/funding-comparison` | GET | CEX vs DEX funding 对比 |
| `/perpetual-dex/oi-distribution` | GET | 跨 DEX OI 分布 |
| `/perpetual-dex/funding-history/{symbol}` | GET | 单资产 funding 历史 |
| `/perpetual-dex/arb-spread` | GET | CEX-DEX 套利价差 |
| `/perpetual-dex/context` | GET | 永续 DEX AI 上下文 bundle |

### 链上地址画像

| 端点 | 方法 | 说明 |
|---|---|---|
| `/onchain-address/whale-moves` | GET | 最近巨鲸大额转账 |
| `/onchain-address/flows/{address}` | GET | 单地址资金流 |
| `/onchain-address/labels` | GET | 地址标签列表 |
| `/onchain-address/net-flow` | GET | 追踪地址净流入/流出 |
| `/onchain-address/top-movers` | GET | 最活跃地址排名 |
| `/onchain-address/exchange-flow` | GET | 交易所流入/流出汇总 |
| `/onchain-address/context` | GET | 链上地址 AI 上下文 bundle |

### DEX 流动性

| 端点 | 方法 | 说明 |
|---|---|---|
| `/dex-liquidity/pools` | GET | Top 池列表（TVL 排序） |
| `/dex-liquidity/tvl-distribution` | GET | TVL 分布统计 |
| `/dex-liquidity/ticks/{pool_address}` | GET | 池 tick 流动性分布 |
| `/dex-liquidity/events` | GET | 最近 mint/burn 事件 |
| `/dex-liquidity/concentration` | GET | 流动性集中度（Top 5 占比） |
| `/dex-liquidity/large-events` | GET | 大额流动性事件（>$100k） |
| `/dex-liquidity/context` | GET | DEX 流动性 AI 上下文 bundle |

### Gas/网络

| 端点 | 方法 | 说明 |
|---|---|---|
| `/gas-network/current` | GET | 当前 Gas 价格 |
| `/gas-network/history` | GET | Gas 价格历史 |
| `/gas-network/congestion` | GET | 网络拥堵状态 |
| `/gas-network/spikes` | GET | Gas 尖刺事件 |
| `/gas-network/avg-fee` | GET | 平均交易费用 |
| `/gas-network/utilization` | GET | 区块利用率 |
| `/gas-network/context` | GET | Gas/网络 AI 上下文 bundle |

### 治理投票

| 端点 | 方法 | 说明 |
|---|---|---|
| `/governance/proposals` | GET | 活跃提案列表 |
| `/governance/votes/{proposal_id}` | GET | 单提案投票详情 |
| `/governance/activity` | GET | 治理活跃度指标 |
| `/governance/whale-votes` | GET | 巨鲸投票记录 |
| `/governance/participation` | GET | 参与率趋势 |
| `/governance/quorum-risk` | GET | 法定人数风险提案 |
| `/governance/protocol-ranking` | GET | 协议治理活跃度排名 |
| `/governance/context` | GET | 治理投票 AI 上下文 bundle |

### 清算级联

| 端点 | 方法 | 说明 |
|---|---|---|
| `/liquidation-cascade/clusters` | GET | 清算集群分布 |
| `/liquidation-cascade/cascade-risk` | GET | 级联风险评估 |
| `/liquidation-cascade/heatmap/{symbol}` | GET | 单资产清算热力图 |
| `/liquidation-cascade/critical-levels` | GET | 关键清算价位 |
| `/liquidation-cascade/leverage-distribution` | GET | 杠杆分布统计 |
| `/liquidation-cascade/proximity-alert` | GET | 接近清算价位告警 |
| `/liquidation-cascade/estimated-cascade` | GET | 级联链模拟 |
| `/liquidation-cascade/context` | GET | 清算级联 AI 上下文 bundle |

### 跨交易所套利

| 端点 | 方法 | 说明 |
|---|---|---|
| `/cross-venue-arb/opportunities` | GET | 当前套利机会 |
| `/cross-venue-arb/spreads` | GET | 跨所价差快照 |
| `/cross-venue-arb/persistence` | GET | 套利持续性分析 |
| `/cross-venue-arb/efficiency-score` | GET | 市场效率评分 |
| `/cross-venue-arb/venue-ranking` | GET | 交易所价格偏离排名 |
| `/cross-venue-arb/cross-type` | GET | 按类型分类套利机会 |
| `/cross-venue-arb/historical` | GET | 历史套利统计 |
| `/cross-venue-arb/context` | GET | 跨所套利 AI 上下文 bundle |

### 链上领先/滞后

| 端点 | 方法 | 说明 |
|---|---|---|
| `/onchain-lead-lag/signals` | GET | 最新领先/滞后信号 |
| `/onchain-lead-lag/relations/{symbol}` | GET | 单资产信号关系 |
| `/onchain-lead-lag/alerts` | GET | 信号触发告警 |
| `/onchain-lead-lag/predictive-ranking` | GET | 信号预测力排名 |
| `/onchain-lead-lag/optimal-lag/{signal_name}` | GET | 单信号最优滞后期 |
| `/onchain-lead-lag/granger/{symbol}` | GET | Granger 因果检验结果 |
| `/onchain-lead-lag/signal-history/{signal_name}` | GET | 信号历史序列 |
| `/onchain-lead-lag/cross-signal` | GET | 跨信号相关性 |
| `/onchain-lead-lag/context` | GET | 链上领先滞后 AI 上下文 bundle |

### 预测市场

| 端点 | 方法 | 说明 |
|---|---|---|
| `/prediction-market/markets` | GET | 活跃预测市场列表 |
| `/prediction-market/crypto-markets` | GET | 加密相关预测市场 |
| `/prediction-market/movers` | GET | 概率变化最大的市场 |
| `/prediction-market/history/{market_id}` | GET | 单市场概率历史 |
| `/prediction-market/context` | GET | 预测市场 AI 上下文 bundle |

### 链上持有者

| 端点 | 方法 | 说明 |
|---|---|---|
| `/onchain-holder/distribution/{symbol}` | GET | 持有者分布（短期/长期/鲸鱼） |
| `/onchain-holder/metrics/{symbol}` | GET | 链上指标（MVRV/SOPR/NUPL） |
| `/onchain-holder/supply-profit/{symbol}` | GET | 供给盈利比例 |
| `/onchain-holder/ranking` | GET | 按 MVRV 排名资产 |
| `/onchain-holder/context` | GET | 链上持有者 AI 上下文 bundle |

### 流动性质押

| 端点 | 方法 | 说明 |
|---|---|---|
| `/liquid-staking/overview` | GET | 流动性质押全局概览（总质押/APR/队列） |
| `/liquid-staking/protocols` | GET | 各协议质押详情（Lido/Rocket Pool） |
| `/liquid-staking/validator-queue` | GET | 验证者进出队列状态 |
| `/liquid-staking/restaking` | GET | 再质押 TVL（EigenLayer） |
| `/liquid-staking/context` | GET | 流动性质押 AI 上下文 bundle |

### Mempool

| 端点 | 方法 | 说明 |
|---|---|---|
| `/mempool/stats` | GET | 当前 mempool 状态（pending 数/vsize/费率） |
| `/mempool/large-txs` | GET | 大额 pending 交易列表 |
| `/mempool/fee-trend` | GET | 手续费趋势（快/中/慢） |
| `/mempool/pressure-index` | GET | Mempool 压力指数 |
| `/mempool/context` | GET | Mempool AI 上下文 bundle |

### 融资轮次

| 端点 | 方法 | 说明 |
|---|---|---|
| `/funding-round/recent` | GET | 最近融资轮次列表 |
| `/funding-round/by-category` | GET | 按赛道分类融资统计 |
| `/funding-round/top-investors` | GET | 头部 VC 活跃度排名 |
| `/funding-round/trends` | GET | 融资趋势（月度金额/数量） |
| `/funding-round/context` | GET | 融资轮次 AI 上下文 bundle |

### 交易所储备

| 端点 | 方法 | 说明 |
|---|---|---|
| `/exchange-reserve/btc` | GET | BTC 交易所储备数据 |
| `/exchange-reserve/eth` | GET | ETH 交易所储备数据 |
| `/exchange-reserve/stablecoin` | GET | 稳定币交易所储备数据 |
| `/exchange-reserve/netflow` | GET | 净流入/流出汇总 |
| `/exchange-reserve/context` | GET | 交易所储备 AI 上下文 bundle |

### 矿工数据

| 端点 | 方法 | 说明 |
|---|---|---|
| `/miner/stats` | GET | 矿工核心指标（算力/难度/收入） |
| `/miner/outflows` | GET | 矿工链上流出数据 |
| `/miner/hashrate-history` | GET | 算力历史趋势 |
| `/miner/puell-multiple` | GET | Puell Multiple 当前值与历史分位 |
| `/miner/context` | GET | 矿工数据 AI 上下文 bundle |

### 衍生品情绪

| 端点 | 方法 | 说明 |
|---|---|---|
| `/derivatives-sentiment/fear-greed` | GET | 恐惧贪婪指数 |
| `/derivatives-sentiment/long-short` | GET | 多空比（BTC/ETH） |
| `/derivatives-sentiment/open-interest` | GET | 全市场 OI 总量与变化 |
| `/derivatives-sentiment/put-call` | GET | 看跌/看涨比率 |
| `/derivatives-sentiment/context` | GET | 衍生品情绪 AI 上下文 bundle |

### 持有者行为分析

| 端点 | 方法 | 说明 |
|---|---|---|
| `/holder-behavior/state/{symbol}` | GET | 单资产持有者行为状态 |
| `/holder-behavior/market-phase` | GET | 当前市场阶段（积累/派发） |
| `/holder-behavior/signals` | GET | 持有者行为信号列表 |
| `/holder-behavior/historical/{symbol}` | GET | 持有者行为历史分位 |
| `/holder-behavior/context` | GET | 持有者行为 AI 上下文 bundle |

### 流动性 Regime

| 端点 | 方法 | 说明 |
|---|---|---|
| `/liquidity-regime/state` | GET | 当前流动性状态（expansion/contraction/crisis） |
| `/liquidity-regime/score` | GET | 流动性评分（0-100） |
| `/liquidity-regime/spread` | GET | DeFi-CeFi 利差方向 |
| `/liquidity-regime/stablecoin-pulse` | GET | 稳定币供给脉冲 |
| `/liquidity-regime/context` | GET | 流动性 Regime AI 上下文 bundle |

### 事件概率

| 端点 | 方法 | 说明 |
|---|---|---|
| `/event-probability/high-impact` | GET | 高影响力事件列表 |
| `/event-probability/jumps` | GET | 概率跳变检测（24h > 10%） |
| `/event-probability/asset-mapping` | GET | 事件→资产映射 |
| `/event-probability/cross-validation` | GET | 事件-新闻交叉验证 |
| `/event-probability/context` | GET | 事件概率 AI 上下文 bundle |

### 矿工压力

| 端点 | 方法 | 说明 |
|---|---|---|
| `/miner-pressure/score` | GET | 矿工压力评分 |
| `/miner-pressure/capitulation` | GET | 矿工投降指数 |
| `/miner-pressure/halving-phase` | GET | 减半周期相位 |
| `/miner-pressure/historical` | GET | 矿工压力历史 |
| `/miner-pressure/context` | GET | 矿工压力 AI 上下文 bundle |

### 综合情绪

| 端点 | 方法 | 说明 |
|---|---|---|
| `/sentiment-composite/score` | GET | 综合情绪评分（0-100） |
| `/sentiment-composite/extremes` | GET | 极端情绪检测 |
| `/sentiment-composite/divergence` | GET | 情绪-价格背离 |
| `/sentiment-composite/reversal` | GET | 反转信号概率 |
| `/sentiment-composite/context` | GET | 综合情绪 AI 上下文 bundle |

### 时间切片（历史回溯）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/time-slice/` | GET | 指定历史时刻的全市场快照 |
| `/time-slice/range` | GET | 时间范围内多个等间隔快照 |
| `/time-slice/feature-history` | GET | 特征连续历史序列 |

---

## 端点详细说明

### GET /signals/{symbol}

**Bridge 最核心接口**，一次调用获取指定资产的完整信号 bundle。

**路径参数：**
- `symbol` — 资产符号，支持 `BTC`、`BTC-USDT`、`BTC/USDT`

**响应示例：**

```json
{
  "symbol": "BTC/USDT",
  "generated_at": "2025-05-24T12:00:00",
  "trend_signal": {
    "direction": "bullish",
    "score": 1.0,
    "signals": ["rsi_bullish", "macd_positive"]
  },
  "volatility": {
    "regime": "elevated",
    "annualized_vol": 0.85,
    "daily_vol": 0.044,
    "var_95_daily": 0.0724
  },
  "funding_anomaly": {
    "is_anomaly": true,
    "direction": "long_biased",
    "rate": 0.0012,
    "annualized_rate": 1.314
  },
  "risk_score": 62.5,
  "risk_level": "high",
  "standardized_features": {
    "rsi_14": {"zscore_30d": 1.2, "percentile_30d": 88.5, "regime_label": "high"}
  },
  "ai_context": {
    "data_quality_flag": "ok",
    "coverage_score": 0.85,
    "world_model_index": {"wmi": 0.72, "interpretation": "sufficient"}
  },
  "raw_indicators": {
    "rsi_14": 62.3,
    "macd_hist": 0.0015,
    "atr_14": 1250.0,
    "adx_14": 28.5
  }
}
```

**risk_level 枚举：** `low` | `medium` | `high` | `extreme`

---

### GET /signals/

全资产信号摘要，支持按风险等级过滤。

**查询参数：**

| 参数 | 必填 | 说明 |
|---|---|---|
| `risk_level` | 否 | 过滤：`low` / `medium` / `high` / `extreme` |

**响应示例：**

```json
{
  "symbol_count": 18,
  "filter_risk_level": null,
  "signals": {
    "BTC/USDT": {
      "trend": "bullish",
      "trend_score": 1.0,
      "volatility_regime": "elevated",
      "annualized_vol": 0.85,
      "risk_score": 62.5,
      "risk_level": "high",
      "funding_anomaly": true,
      "funding_direction": "long_biased"
    }
  }
}
```

---

### GET /technical/indicators/{symbol}

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `timeframe` | 否 | `1h` | K 线周期：`1m/5m/15m/1h/4h/1d` |
| `limit` | 否 | `1` | 返回最近 N 条（最多 500） |

**响应包含字段：**
`rsi_14`、`macd_line`、`macd_signal`、`macd_hist`、`bb_upper`、`bb_lower`、`bb_mid`、`atr_14`、`adx_14`、`ema_20`、`ema_50`

---

### GET /risk/score/{symbol}

返回单资产风险评分，设计用于 Sui Move 合约直接消费。

**响应示例：**

```json
{
  "symbol": "ETH/USDT",
  "risk_level": "high",
  "risk_score": 58.3,
  "annualized_vol": 0.91,
  "daily_vol": 0.0476,
  "var_95_daily": 0.0783,
  "var_99_daily": 0.1107,
  "sample_bars": 167
}
```

**risk_score 映射：**

| 分值区间 | risk_level |
|---|---|
| 0 – 25 | `low` |
| 25 – 50 | `medium` |
| 50 – 75 | `high` |
| 75 – 100 | `extreme` |

---

### GET /exchange/funding/{symbol}

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `limit` | 否 | `1` | `1` 返回最新快照，`>1` 返回历史序列 |

**响应示例（limit=1）：**

```json
{
  "symbol": "BTC/USDT",
  "average_funding_rate": 0.00012,
  "annualized_rate": 0.1314,
  "is_elevated": false,
  "by_exchange": {
    "binance": {"funding_rate": 0.00011, "mark_price": 67500.0},
    "okx":     {"funding_rate": 0.00013, "mark_price": 67502.0}
  }
}
```

---

### GET /macro/regime

精简宏观情绪摘要，Bridge 和 Dashboard 可直接消费。

**响应示例：**

```json
{
  "snapshot_time": "2025-05-24T12:00:00",
  "risk_regime": "risk_on",
  "macro_regime": "reflationary",
  "vix_level": 14.5,
  "vix_regime": "low",
  "dxy_level": 104.2,
  "dxy_trend": "falling",
  "us10y_level": 4.35,
  "btc_macro_tailwind": true,
  "btc_macro_headwind": false,
  "overall_stance": "risk_on"
}
```

**overall_stance 枚举：** `risk_on` | `risk_off` | `neutral`

---

### GET /cross-asset/relative-strength

**查询参数：**

| 参数 | 必填 | 说明 |
|---|---|---|
| `symbol` | 否 | 指定单个资产，不传则返回全部排名 |

**响应示例（全部排名）：**

```json
{
  "symbol_count": 18,
  "ranked_by": "rs_vs_btc_7d",
  "data": [
    {"symbol": "SOL/USDT", "rs_rank": 1, "rs_vs_btc_7d": 0.12, "rs_momentum": "accelerating"},
    {"symbol": "BTC/USDT", "rs_rank": 2, "rs_vs_btc_7d": 0.0,  "rs_momentum": "stable"}
  ]
}
```

---

### GET /sentiment/news/score/{symbol}

**响应示例：**

```json
{
  "symbol": "SUI/USDT",
  "sentiment_score": 0.42,
  "sentiment_label": "positive",
  "article_count": 31,
  "distribution": {"positive": 18, "neutral": 10, "negative": 3},
  "window": "3d"
}
```

**sentiment_score 区间：**

| 分值 | 标签 |
|---|---|
| > 0.3 | `positive` |
| -0.3 ~ 0.3 | `neutral` |
| < -0.3 | `negative` |

---

### GET /time-slice/

**查询参数：**

| 参数 | 必填 | 说明 |
|---|---|---|
| `timestamp` | 是 | ISO 格式，如 `2025-05-20T12:00:00` |
| `symbols` | 否 | 逗号分隔，如 `BTC/USDT,ETH/USDT` |
| `domains` | 否 | 逗号分隔，如 `klines,cross_asset` |

---

### GET /time-slice/range

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `start` | 是 | — | 范围起始时间 |
| `end` | 是 | — | 范围结束时间 |
| `interval` | 否 | `3600` | 采样间隔（秒） |
| `symbols` | 否 | 全部 | 逗号分隔的资产列表 |
| `domains` | 否 | 全部 | 逗号分隔的域列表 |

---

### GET /time-slice/feature-history

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `symbol` | 是 | — | 如 `BTC/USDT` |
| `start` | 是 | — | 起始时间 |
| `end` | 是 | — | 结束时间 |
| `features` | 否 | 全部 | 逗号分隔，如 `rsi_14,macd_line` |
| `timeframe` | 否 | `1h` | K线周期 |

---

### GET /aggregate/asset-profile/{symbol}

单资产全维度画像，一次请求替代 6+ 次调用。

**路径参数：**
- `symbol` — 资产符号，支持 `BTC`、`BTC-USDT`、`BTC/USDT`

**响应示例：**

```json
{
  "symbol": "BTC/USDT",
  "sector": "store_of_value",
  "tier": "core",
  "price": {"price": 67500.0, "change_24h": 2.3, "volume_24h": 1200000000},
  "derivatives": {"funding_rate": 0.00012, "annualized_funding": 0.1314, "open_interest": 5800000000},
  "risk": {"daily_volatility": 0.044, "annualized_volatility": 0.85, "risk_score": 62.5, "risk_level": "high"}
}
```

---

### GET /aggregate/multi-asset-compare

**查询参数：**

| 参数 | 必填 | 说明 |
|---|---|---|
| `symbols` | 是 | 逗号分隔的 2-5 个符号，如 `BTC,ETH,SOL` |

**响应包含：** 各资产价格/涨跌/资金费率 + 排名 + 分歧检测（`has_divergence`）

---

### GET /aggregate/market-regime

市场体制判断，基于 BTC 价格趋势和全市场资金费率。

**regime 枚举：** `euphoria` | `trending_up` | `ranging` | `trending_down` | `panic`

---

### GET /strategy/multi-factor-score/{symbol}

6 维多因子打分，返回 0-100 的复合分数和方向信号。

**响应示例：**

```json
{
  "symbol": "ETH/USDT",
  "composite_score": 63.2,
  "factors": {"trend": 72.0, "momentum": 58.5, "flow": 65.0, "sentiment": 55.0, "volatility": 70.0, "value": 59.0},
  "signal": "buy"
}
```

**signal 枚举：** `strong_buy` | `buy` | `neutral` | `sell` | `strong_sell`

---

### GET /strategy/entry-exit/{symbol}

基于 BB/ATR/支撑阻力的入场/出场价位建议。

**响应包含：**
- `entry_zones` — aggressive_long / conservative_long / support
- `exit_zones` — take_profit_1 / take_profit_2 / resistance
- `stop_loss` — tight / normal / wide
- `indicators` — bb_upper / bb_lower / ma20 / atr14

---

### GET /strategy/funding-arb

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `min_rate` | 否 | `0.0005` | 最低资金费率阈值 |

返回所有超过阈值的资金费率套利机会，含年化收益和方向建议。

---

### GET /strategy/mean-reversion-candidates

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `zscore_threshold` | 否 | `2.0` | z-score 阈值 |
| `limit` | 否 | `10` | 返回数量 |

返回统计极端延伸的资产（超买/超卖），含回归目标价。

---

### GET /monitor/alerts

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `severity` | 否 | `all` | 过滤：`all` / `high` / `medium` / `low` |

汇总所有类型告警（价格突破、成交量异常、资金费率极端），按严重度排序。

**响应示例：**

```json
{
  "count": 3,
  "alerts": [
    {"symbol": "SOL/USDT", "type": "volume_spike", "severity": "high", "detail": "Volume 1500000 is 4.2x average"},
    {"symbol": "DOGE/USDT", "type": "funding_anomaly", "severity": "high", "detail": "Extreme funding rate: 0.003500"},
    {"symbol": "ETH/USDT", "type": "price_breakout_up", "severity": "medium", "detail": "Price above BB upper"}
  ]
}
```

---

### GET /monitor/volume-spikes

**查询参数：**

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `multiplier` | 否 | `2.5` | 相对 20h 均值的倍数阈值 |

---

## Sui Bridge 推荐调用流程

Bridge 每 5 分钟从 EvoQuantV3 拉取数据并推送到 Sui 链，建议按以下顺序调用：

```
1. GET /health/                          检查数据管道是否健康
   ↓ status == "healthy"
2. GET /signals/                         获取所有资产信号摘要
3. GET /signals/{symbol}                 获取重点资产详细信号（SUI/BTC/ETH）
4. GET /macro/regime                     获取宏观情绪
5. GET /sentiment/summary                获取新闻情感摘要
6. GET /cross-asset/summary              获取跨资产分析摘要
   ↓
7. 组装 payload → 提交 Sui Move 合约
```

---

## 代码结构

```
api/
├── __init__.py
├── __main__.py              # python -m api 入口
├── app.py                   # FastAPI 应用 + uvicorn 启动（v2.0.0）
├── dependencies.py          # 延迟加载的服务单例（含所有新服务）
├── models.py                # Pydantic response schemas
└── routers/
    ├── __init__.py
    ├── _helpers.py          # 共享工具函数（normalize/safe_float/zscore/percentile/slope/divergence）
    ├── bundle.py            # /bundle — AI 市场上下文 bundle
    ├── domains.py           # /domains — 各域健康状态
    ├── health.py            # /health — 管道健康 + WMI
    ├── time_slice.py        # /time-slice — 历史快照与特征序列
    ├── signals.py           # /signals — 综合量化信号（Bridge 核心）
    ├── technical.py         # /technical — 技术指标 + K线
    ├── technical_deep.py    # /technical-deep — 技术指标深度分析（时序/极端/背离/体制/扫描）
    ├── risk.py              # /risk — 组合风险 / VaR / 波动率
    ├── exchange.py          # /exchange — 资金费率 / 订单簿 / 基差 / 多空比
    ├── macro.py             # /macro — 宏观因子快照
    ├── cross_asset.py       # /cross-asset — 跨资产分析
    ├── cross_asset_history.py # /cross-asset-history — 跨资产历史序列
    ├── onchain.py           # /onchain — 链上数据
    ├── sentiment.py         # /sentiment — 新闻情感 + 市场广度
    ├── data_quality.py      # /data-quality — 审计 / 就绪度 / 市场结构
    ├── features.py          # /features — 特征标准化复合分数与明细
    ├── alternative.py       # /alternative — 另类数据（开发者 / 稳定币 / 因子）
    ├── aggregate.py         # /aggregate — 聚合查询（全维度画像 / 对比 / 热力图）
    ├── strategy.py          # /strategy — AI 策略辅助（多因子 / 入场出场 / 套利）
    ├── monitor.py           # /monitor — 实时监控（告警 / 突破 / 异常检测）
    ├── orderflow.py         # /orderflow — 订单流智能（CVD / 大单 / 深度 / 滑点）
    ├── derivatives.py       # /derivatives — 衍生品复合信号（健康评分 / 杠杆 / 挤压 / 资金费率预测 / 基差信号）
    ├── news_intel.py        # /news-intel — 新闻情报（信号 / 事件 / 叙事 / 监管）
    ├── ai_context.py        # /ai-context — AI 决策上下文（bundle / 状态 / 套利 / 新鲜度）
    ├── portfolio_analytics.py # /portfolio — 组合分析（快照/回撤/集中度/VaR分解/趋势）
    ├── microstructure.py    # /microstructure — 市场微观结构（波动率/成交量/价差/跳空）
    ├── factor_explorer.py   # /factors — 因子探索（搜索/时序/相关性/概览）
    ├── social_sentiment.py  # /social-sentiment — 社交情绪（评分/时序/排名/概览）
    ├── whale_tracker.py     # /whale-tracker — 巨鲸追踪（转账/净流/排名/预警）
    ├── orderflow_micro.py   # /orderflow-micro — 微观订单流（压力/大单/跨所/概览）
    ├── defi.py              # /defi — DeFi 协议（TVL/借贷利率/DEX量/概览）
    ├── bridge_flow.py       # /bridge-flow — 跨链桥流（链净流/桥排名/迁移方向）
    ├── regulatory.py        # /regulatory — 监管动态（事件/ETF追踪/风险信号/概览）
    ├── regime.py            # /regime — 市场状态（当前/历史/转换）
    ├── anomaly.py           # /anomaly — 异常检测（最近/活跃/市场风险）
    ├── liquidity.py         # /liquidity — 流动性分析（评分/滑点/预警/排名）
    ├── volatility.py        # /volatility — 波动率预测（EWMA/锥/排名/RV-IV）
    ├── etf_flow.py          # /etf-flow — ETF 资金流（日流/发行商排名/溢折价/异常）
    ├── basis_curve.py       # /basis-curve — 期限结构（快照/roll yield/斜率/跨所对比）
    ├── mev.py               # /mev — MEV 数据（区块/builder排名/三明治/集中度）
    ├── cefi_lending.py      # /cefi-lending — CeFi 借贷（利率/排名/倒挂/利用率）
    ├── temporal_pattern.py  # /temporal-pattern — 时间模式（季节性/小时/星期/减半/funding）
    ├── flow_decomposition.py # /flow-decomposition — 资金流分解（VPIN/smart money/排名）
    ├── contagion_risk.py    # /contagion-risk — 传染风险（系统评分/CoVaR/尾部Beta）
    ├── alpha_decay.py       # /alpha-decay — 信号衰减（半衰期/排名/背离/拥挤度）
    ├── narrative_regime.py  # /narrative-regime — 叙事状态机（活跃/转换/注意力/新兴）
    ├── perpetual_dex.py     # /perpetual-dex — 永续 DEX（funding/volume/OI/套利价差）
    ├── onchain_address.py   # /onchain-address — 链上地址（巨鲸/流向/标签/交易所流）
    ├── dex_liquidity.py     # /dex-liquidity — DEX 流动性（池/TVL/ticks/事件/集中度）
    ├── gas_network.py       # /gas-network — Gas/网络（价格/拥堵/尖刺/利用率）
    ├── governance.py        # /governance — 治理投票（提案/投票/参与率/巨鲸/排名）
    ├── liquidation_cascade.py # /liquidation-cascade — 清算级联（集群/风险/热力图/杠杆）
    ├── cross_venue_arb.py   # /cross-venue-arb — 跨所套利（机会/价差/持续性/效率）
    ├── onchain_lead_lag.py  # /onchain-lead-lag — 链上领先滞后（信号/Granger/预测力）
    ├── prediction_market.py # /prediction-market — 预测市场（活跃市场/概率变化/历史）
    ├── onchain_holder.py    # /onchain-holder — 链上持有者（分布/MVRV/SOPR/NUPL）
    ├── liquid_staking.py    # /liquid-staking — 流动性质押（概览/协议/队列/再质押）
    ├── mempool.py           # /mempool — Mempool（状态/大额TX/费率趋势/压力指数）
    ├── funding_round.py     # /funding-round — 融资轮次（最近/赛道/VC排名/趋势）
    ├── exchange_reserve.py  # /exchange-reserve — 交易所储备（BTC/ETH/稳定币/净流）
    ├── miner.py             # /miner — 矿工数据（算力/流出/Puell/历史）
    ├── derivatives_sentiment.py # /derivatives-sentiment — 衍生品情绪（恐贪/多空比/OI/PC比）
    ├── holder_behavior.py   # /holder-behavior — 持有者行为（状态/市场阶段/信号/历史）
    ├── liquidity_regime.py  # /liquidity-regime — 流动性Regime（状态/评分/利差/脉冲）
    ├── event_probability.py # /event-probability — 事件概率（高影响/跳变/资产映射）
    ├── miner_pressure.py    # /miner-pressure — 矿工压力（评分/投降/减半相位/历史）
    └── sentiment_composite.py # /sentiment-composite — 综合情绪（评分/极端/背离/反转）
```

---

## 设计原则

1. **只读** — API 不写入任何数据，纯查询层
2. **薄封装** — 直接查询已由 logic_layer 计算并落库的结果，不重复业务逻辑
3. **延迟加载** — 数据库连接和服务实例在首次请求时才初始化
4. **独立进程** — 不影响数据采集管道运行
5. **容错** — 单域失败不影响其他域返回
6. **TTL 缓存** — 高频只读端点做短期内存缓存，减少重复 SQLite 查询
7. **请求追踪** — 每个请求注入 `X-Request-ID`，用于日志关联和分布式追踪
8. **限流保护** — 按 IP 滑动窗口限流，防止单客户端过载
9. **安全响应** — 全局异常处理器捕获未处理异常，返回安全 JSON 而非 traceback

---

## API 响应缓存

API 层内置轻量级 TTL 内存缓存（`api/cache.py`），对高频只读端点做短期缓存，避免逻辑管道刷新间隔内的重复查库。

### 缓存策略

| 端点类别 | TTL | 缓存 Key 模式 |
|---|---|---|
| `/bundle/*` | 60s | `bundle:{path}` |
| `/technical/*` | 60s | `tech:{path}:{params}` |
| `/technical-deep/*` | 60s | `tech_deep:{path}:{params}` |
| `/features/*` | 120s | `features:{path}:{params}` |
| `/cross-asset/*` | 120s | `cross:{path}:{params}` |
| `/risk/*` | 120s | `risk:{path}:{params}` |
| `/macro/*` | 300s | `macro:{path}:{params}` |
| `/health` | 10s | `health:{path}` |
| `/symbols` | 3600s | `symbols:{path}` |

### 缓存失效

- 逻辑管道每次全链路执行完毕后自动调用 `cache.invalidate_all()` 清空全部缓存
- 保证管道刷新后下游消费者立即获取最新数据
- 缓存命中时响应头包含 `X-Cache: HIT`

### 使用方式

在 router 端点上添加 `@cached_response` 装饰器：

```python
from fastapi import Request
from api.routers._helpers import cached_response

@router.get("/bundle/{entity}")
@cached_response("bundle", ttl=60)
def get_bundle(entity: str, request: Request):
    ...
```

### 实现细节

- 基于 `time.monotonic()` + dict，无外部依赖
- 线程安全（threading.Lock）
- 惰性清理（get 时检查过期）+ 后台线程定期清理（30s 间隔）
- 通过 FastAPI lifespan 管理启停
- 内置命中/未命中计数器，通过 `cache.metrics` 属性暴露统计

---

## 运维与可观测性

### 请求追踪

每个 HTTP 请求自动注入 `X-Request-ID` 响应头（客户端也可在请求头中传入自定义 ID）。用于日志关联和分布式追踪。

### 限流

滑动窗口按 IP 限流，超限返回 `429 Too Many Requests`。

| 配置项 | 环境变量 | 默认值 |
|---|---|---|
| 最大请求数 | `API_RATE_LIMIT_MAX_REQUESTS` | `200` |
| 窗口时长（秒） | `API_RATE_LIMIT_WINDOW_SECONDS` | `60` |

响应头 `X-RateLimit-Remaining` 返回当前窗口剩余配额。

### CORS 限制

| 配置项 | 环境变量 | 默认值 |
|---|---|---|
| 允许来源 | `API_CORS_ORIGINS` | `http://localhost:3000,http://localhost:8080` |

仅允许 GET 方法，生产环境应配置为实际前端域名。

### 全局异常处理

所有未捕获异常返回标准 JSON 格式，包含 `error_type` 和 `request_id`，不泄露内部 traceback。

### /metrics 端点

`GET /metrics` 返回运维指标：

```json
{
  "cache": {
    "hits": 1234,
    "misses": 56,
    "total_requests": 1290,
    "hit_rate_pct": 95.7,
    "size": 42
  },
  "query_cache": {
    "hits": 500,
    "misses": 80,
    "dedup_hits": 12,
    "total_requests": 580,
    "hit_rate_pct": 86.2,
    "size": 35,
    "max_size": 500
  },
  "rate_limiter": {
    "max_requests": 200,
    "window_seconds": 60,
    "tracked_ips": 5
  }
}
```

---

## 服务层查询缓存

API 层内置两级缓存：

| 层 | 模块 | 缓存对象 | 用途 |
|---|---|---|---|
| L1 响应缓存 | `api/cache.py` | HTTP 响应 JSON | 相同 URL + 参数直接返回 |
| L2 查询缓存 | `api/query_cache.py` | DB 查询结果 | 多端点查同一张表时共享结果 |

### 查询缓存特点

- **请求合并** — 同一 key 并发请求只执行一次 DB 查询，其他请求等待结果
- **容量上限** — 默认 max_size=500，满时淘汰最早过期的条目
- **TTL 过期** — 每个查询结果可指定独立 TTL
- **管道刷新清空** — 逻辑管道执行完毕后同时清空 L1 和 L2 缓存

### 使用方式

```python
from api.query_cache import query_cache

rows = query_cache.get_or_fetch(
    "latest_tickers:binance",
    lambda: exchange_db.fetch_all("SELECT * FROM latest_tickers WHERE exchange = 'binance'"),
    ttl=30.0,
)
```

---

## 输入验证

API 层对请求参数做前置校验，避免无效查询打到数据库：

| 校验项 | 行为 | HTTP 状态码 |
|---|---|---|
| 符号不在 SYMBOL_UNIVERSE 中 | 返回合法 base 列表 | `422` |
| 时间范围 end ≤ start | 拒绝 | `400` |
| 时间范围超过 90 天 | 拒绝（防止全表扫描） | `400` |

校验函数在 `api/routers/_helpers.py`：

```python
from api.routers._helpers import validate_symbol, validate_time_range

normalized = validate_symbol("BTC")      # → "BTC/USDT" 或抛 422
start, end = validate_time_range(start_str, end_str)  # 或抛 400
```

---

## AI 消费者使用建议

1. 首先调用 `GET /health/` 检查 `should_ai_abstain`，若为 `true` 则数据不足
2. 调用 `GET /bundle/{symbol}` 获取完整 AI 上下文 bundle
3. 关注 `world_model_index.interpretation`：
   - `sufficient`（WMI ≥ 0.6）— 数据充分，可正常决策
   - `marginal`（0.3 ≤ WMI < 0.6）— 建议降低置信度
   - `insufficient`（WMI < 0.3）— 数据不足，建议等待
4. 对于实时信号消费，优先使用 `GET /signals/{symbol}`，比 `/bundle` 更轻量
5. 使用 `GET /time-slice/feature-history` 获取历史趋势做对比分析
