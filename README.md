# EvoQuant

EvoQuant 是一个面向 AI 的加密市场数据基础设施项目。它持续采集多源市场证据，写入 SQLite 历史表与 `latest_*` 快照表，并在逻辑层进一步重组为 AI 可直接消费的市场上下文。

```text
外部数据源
-> data_layer 采集与标准化
-> SQLite 历史表 / latest_* 快照
-> logic_layer 聚合、标准化与治理
-> AI-ready market context bundle + 历史回溯
```

## 这不是什么

- 不是自动交易机器人
- 不是下单执行系统
- 不是单一交易所爬虫脚本集合

这个仓库更接近"AI 市场理解底座"，重点是数据覆盖、结构化语义和质量治理。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 多源采集 | 交易所、宏观、新闻、事件、链上、Tokenomics、期权和补充特征 |
| 快照语义 | 用 `latest_*` 表和 bundle 表达"当前市场状态" |
| 质量门控 | 显式区分 `health_status`、`quality_flag`、`is_ready_for_ai` |
| 特征标准化 | Z-score、百分位排名、跨资产归一化、维度复合信号 |
| 时间回溯 | 任意历史时刻的完整市场快照查询（point-in-time） |
| 特征历史 | 连续特征序列查询，支持指定特征/资产/时间范围 |
| 新闻情感 | 规则分类器对新闻做情感/事件类型/影响范围标注 |
| 延迟追踪 | 各域端到端数据新鲜度指标，暴露管道健康状态 |
| 上下文聚合 | 生成 AI 直接消费的统一 market context bundle |
| 对外 API | REST 接口供 AI 消费者远程调用（FastAPI） |
| WMI 指数 | 世界模型质量指数 = 宽度 × 稳定性 × 诚实性 |

## 当前范围

- 默认交易对：18 个币种，分三层管理
  - **T1 核心**（3s orderbook）：`BTC/USDT`、`ETH/USDT`
  - **T2 活跃**（10s orderbook）：`SOL/USDT`、`SUI/USDT`、`DOGE/USDT`、`XRP/USDT`、`AVAX/USDT`、`LINK/USDT`
  - **T3 监控**（30s orderbook）：`ADA/USDT`、`DOT/USDT`、`POL/USDT`、`UNI/USDT`、`ARB/USDT`、`OP/USDT`、`NEAR/USDT`、`ATOM/USDT`、`APT/USDT`、`TIA/USDT`
- 默认交易所：`binance`、`okx`、`bybit`
- 存储层：SQLite（三域拆分：exchange_data / market_data / analytics）
- 入口：[`main.py`](main.py)

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

查看模块清单：

```bash
python main.py --list-modules
```

启动默认常驻采集模块：

```bash
python main.py
```

逻辑层全链路由 `logic_pipeline` 自动编排（每 5 分钟），也可手动触发单个模块：

```bash
# logic_pipeline 已随 main.py 自动启动，按 Phase 1-5 依赖顺序执行全部逻辑模块
# 如需手动执行单个逻辑模块：
python main.py --modules technical_indicators,cross_asset_analysis,ai_market_context
```

查询历史某时刻的市场全貌：

```bash
python -m logic_layer.time_slice.runner --timestamp 2025-05-20T12:00:00 --summary-only
```

查询特征连续历史序列：

```bash
python -m logic_layer.time_slice.runner --feature-history --symbols BTC/USDT --range-start 2025-05-19T00:00:00 --range-end 2025-05-20T00:00:00 --features rsi_14,macd_line
```

查看数据管道延迟状态：

```bash
python -m logic_layer.pipeline_latency.runner --summary-only
```

对新闻进行情感标注：

```bash
python -m logic_layer.news_sentiment.runner --print-context
```

启动 API 服务（供 AI 消费者调用）：

```bash
python -m api.app --port 8000
# 或通过 main.py 统一管理
python main.py --modules api_server
```

查看数据层是否已达到 AI 可用门槛：

```bash
python -m data_layer.data_quality.runner --print-market-audit
```

运行测试：

```bash
pytest -q
```

## 仓库结构

```text
EvoQuant/
├── config/          目标资产、调度、日志与环境配置
├── data_layer/      外部数据采集、标准化、落库（9 个常驻数据模块）
├── database/        SQLite 建表、迁移、路由和读写入口
├── logic_layer/     AI-ready 特征、上下文和治理结果（14 个逻辑模块）
├── api/             对外 REST API 服务（FastAPI）
├── tests/           单元测试与模块测试
└── main.py          统一入口，模块注册与进程管理（11 个 autostart daemon）
```

## 逻辑层模块一览

| 模块 | 职责 |
| --- | --- |
| `technical_indicators` | 多交易所 K 线合并、技术指标计算、市场上下文并表 |
| `exchange_comparison` | 跨交易所价差、执行偏好、流动性语境 |
| `macro_context` | 宏观背景快照、短中期变化、收益率曲线 |
| `market_structure` | 资产级杠杆与拥挤度结构证据 |
| `market_breadth` | 跨资产广度、新闻广度、解锁广度 |
| `asset_readiness` | 资产级证据矩阵与数据可用性评分 |
| `cross_asset_analysis` | 相关性矩阵、相对强弱、板块轮动、资金流向 |
| `portfolio_risk` | 组合波动率、VaR、集中度、分散化评分 |
| `feature_standardization` | Z-score、百分位、跨资产排名、维度复合信号 |
| `time_slice` | 任意历史时刻的完整市场快照查询 + 特征历史序列 |
| `news_sentiment` | 新闻情感/事件类型/影响范围分类标注 |
| `pipeline_latency` | 各域端到端数据新鲜度与管道健康状态 |
| `ai_market_context` | 最终 AI 市场上下文 bundle 聚合 |
| `logic_pipeline` | 全链路定时编排（每 5 分钟按依赖顺序执行上述模块） |
| `api_server` | 对外 REST API 服务（FastAPI） |

## 运行说明

- 默认运行会生成本地 `database/*.db`、`logs/` 等运行产物，这些文件已被忽略
- 部分外部源可能需要代理或环境变量，配置入口见 [`config/settings.py`](config/settings.py)
- 仓库当前不包含交易执行层

## 文档导航

- 项目总览：[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)
- 数据层入口：[data_layer/README.md](data_layer/README.md)
- 逻辑层入口：[logic_layer/README.md](logic_layer/README.md)
- API 接口文档：[api/README.md](api/README.md)
- 数据库说明：[database/README.md](database/README.md)
- 数据库分析：[DATABASE_ANALYSIS.md](DATABASE_ANALYSIS.md)
- AI 数据能力总览：[AI_DATA_CAPABILITIES.md](AI_DATA_CAPABILITIES.md)
- 开源检查：[OPEN_SOURCE_CHECKLIST.md](OPEN_SOURCE_CHECKLIST.md)

## Roadmap

### P1 — 短期优化

- [x] 扩展资产覆盖：从 4 个币种扩展到 18 个主流资产，三层分频采集
- [x] 跨资产特征：相关性矩阵、相对强弱、板块轮动、资金流向
- [x] 组合风险度量：组合波动率、VaR、集中度、分散化评分
- [x] 新闻情感标注：规则分类器对新闻做情感/事件类型/影响范围分类
- [ ] 数据保留策略：K 线/资金费率保留 2 年+，满足回测需求

### P2 — 中期增强

- [x] 特征标准化层：Z-score / 百分位 rank / 跨资产归一化
- [x] 时间切片查询：给定 timestamp 返回当时可见的全部特征
- [x] 特征历史序列：连续特征查询接口，支持指定特征/资产/时间范围
- [x] 数据管道延迟追踪：各域端到端新鲜度指标与健康状态
- [x] DEX/稳定币流向：DEX 交易量 + 稳定币市值变化（DeFiLlama）
- [ ] 增量导出：Parquet/Arrow 格式导出，供 ML pipeline 批量训练
- [ ] 监控告警：数据断流 > N 分钟自动告警推送
- [ ] 预测验证框架：AI 预测 → 对比实际走势 → 统计准确率

### P3 — 长期方向

- [ ] 信号引擎：基于特征生成交易信号（趋势/均值回归/事件驱动）
- [ ] 风控引擎：仓位管理、止损、波动率约束
- [ ] 执行层：下单、滑点控制、跨所路由
- [ ] 组合层：多资产权重、再平衡、回撤控制

## License

本仓库使用 [`GPL-3.0`](LICENSE) 许可证。
