# API 路由模块 `api/routers`

## 模块定位

`api/routers` 包含所有 FastAPI 路由定义。v5.1.0 后采用 **8 个统一域入口**，每个文件对应一个功能域。88 个旧路由文件已移至 `_legacy/` 子目录，通过 Feature Flag 全部禁用。

## 目录结构

```text
api/routers/
├── __init__.py
├── _helpers.py          # 共享工具函数（normalize/safe_float/zscore/percentile）
├── _legacy/             # 88 个旧路由文件（全部 FF 禁用，改 .env 可恢复）
│   ├── __init__.py
│   ├── aggregate.py
│   ├── ...
│   └── ws.py
├── README.md
├── status.py            # 向后兼容的 /status 端点
├── v3_market.py         # /market — 行情与交易所
├── v3_technical.py      # /technical — 技术分析
├── v3_risk.py           # /risk — 风险与组合
├── v3_sentiment.py      # /sentiment — 情绪与新闻
├── v3_onchain.py        # /onchain — 链上数据
├── v3_defi.py           # /defi — DeFi 协议
├── v3_factors.py        # /factors — 因子目录与宏观
└── v3_system.py         # /system — 系统状态
```

## 端点总览

| 域 | 前缀 | 端点数 | 说明 |
|---|---|---|---|
| Market | `/market` | 8 | 最新报价、合并K线、资金费率、持仓量、深度盘口、资产元数据、交易所公告、上币事件 |
| Technical | `/technical` | 6 | 最新指标、全资产快照、合并K线、指标历史、极值检测、多周期对比 |
| Risk | `/risk` | 7 | 组合风险快照、相关性矩阵、相对强弱、板块轮动、资金流向、流动性状态、摘要 |
| Sentiment | `/sentiment` | 7 | 最新新闻、资产新闻、综合情绪、散户FOMO、预测市场、概率变动、市场广度 |
| Onchain | `/onchain` | 7 | 链上指标、另类因子、稳定币流、稳定币脉冲、跨链消息、内存池状态、大额交易 |
| DeFi | `/defi` | 7 | 最近清算、按协议清算、健康因子、压力指数、治理提案、投票记录、Smart Money |
| Factors | `/factors` | 4 | 因子目录查询、宏观快照、宏观时序、跨域因子探索 |
| System | `/system` | 6 | 健康检查、域数据可用性、禁用路由列表、数据质量审计、市场结构、资产就绪度 |

**合计：~52 个核心端点**

## 路由注册

`api/router_registry.py` 自动发现路由模块并注册。扫描两个位置：

1. `api/routers/` 顶层 — v3_* 活跃路由
2. `api/routers/_legacy/` — 旧路由（默认禁用）

88 个旧路由文件通过 `core/feature_flags.py` 检查 `FF_{MODULE}_ENABLED` 环境变量，值为 `0` 时跳过加载。

## Feature Flag 控制

在 `.env` 中设置以下格式的环境变量可启用/禁用任意路由模块：

```env
# 禁用（默认）
FF_WHALE_TRACKER_ENABLED=0

# 启用
FF_WHALE_TRACKER_ENABLED=1
```

查看所有被禁用的模块：`GET /system/status/disabled`

## 设计原则

- 每个路由文件只做参数校验和响应格式化
- 业务逻辑下沉到 `logic_layer` 或直接查询数据库
- 共享的符号归一化逻辑在各 v3 文件中定义 `_norm()` 函数
- 所有端点返回 JSON，字段命名使用 snake_case
- 无数据时返回 404 + 明确的 detail 消息，不返回空数组

## 禁用的旧路由（88 个）

旧路由文件位于 `_legacy/` 子目录，按以下原因分类禁用：

- **付费 API 依赖**（9 个）：whale_tracker、whale_pnl、social_sentiment、nft_market、dex_trade_flow、regulatory、onchain_address、derivatives_sentiment、onchain_holder
- **数据表为空**（32 个）：alpha_decay、anomaly、basis_curve、bridge_flow、cefi_lending 等
- **被 v3 统一入口替代**（47 个）：aggregate、ai_context、alternative、analytics_ts、bundle、catalogs、cross_asset 等

如需恢复任意旧路由，在 `.env` 中设置对应的 `FF_{MODULE}_ENABLED=1` 即可。`router_registry.py` 会自动扫描 `_legacy/` 目录并加载已启用的模块。
