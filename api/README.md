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
    ├── bundle.py            # /bundle — AI 市场上下文 bundle
    ├── domains.py           # /domains — 各域健康状态
    ├── health.py            # /health — 管道健康 + WMI
    ├── time_slice.py        # /time-slice — 历史快照与特征序列
    ├── signals.py           # /signals — 综合量化信号（Bridge 核心）
    ├── technical.py         # /technical — 技术指标 + K线
    ├── risk.py              # /risk — 组合风险 / VaR / 波动率
    ├── exchange.py          # /exchange — 资金费率 / 订单簿 / 基差 / 多空比
    ├── macro.py             # /macro — 宏观因子快照
    ├── cross_asset.py       # /cross-asset — 跨资产分析
    ├── onchain.py           # /onchain — 链上数据
    ├── sentiment.py         # /sentiment — 新闻情感 + 市场广度
    ├── data_quality.py      # /data-quality — 审计 / 就绪度 / 市场结构
    ├── features.py          # /features — 特征标准化复合分数与明细
    └── alternative.py       # /alternative — 另类数据（开发者 / 稳定币 / 因子）
```

---

## 设计原则

1. **只读** — API 不写入任何数据，纯查询层
2. **薄封装** — 直接查询已由 logic_layer 计算并落库的结果，不重复业务逻辑
3. **延迟加载** — 数据库连接和服务实例在首次请求时才初始化
4. **独立进程** — 不影响数据采集管道运行
5. **容错** — 单域失败不影响其他域返回

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
