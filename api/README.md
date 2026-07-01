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

## 端点总览（v5.1.0 — 8 统一域入口）

v5.1.0 将 89 个旧路由文件精简为 8 个统一域入口，~52 个核心端点。旧路由通过 Feature Flag 禁用，可随时恢复。

### Market — 行情与交易所 `/market`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/market/tickers` | GET | 最新 Ticker 快照（支持 symbol 过滤） |
| `/market/klines/{symbol}` | GET | 合并 K 线（多交易所聚合） |
| `/market/funding-rates` | GET | 最新资金费率 |
| `/market/open-interest` | GET | 最新持仓量 |
| `/market/depth/{symbol}` | GET | 深度盘口快照 |
| `/market/info` | GET | 资产元数据 |
| `/market/announcements` | GET | 最新交易所公告 |
| `/market/announcements/listings` | GET | 上币/下币事件 |

### Technical — 技术分析 `/technical`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/technical/indicators/{symbol}` | GET | 指定资产最新技术指标 |
| `/technical/indicators` | GET | 全资产最新指标快照 |
| `/technical/klines/{symbol}` | GET | 合并 K 线 |
| `/technical/history/{symbol}` | GET | 技术指标历史序列 |
| `/technical/extremes/{symbol}` | GET | 极值检测（RSI/BB 突破） |
| `/technical/multi-tf/{symbol}` | GET | 多周期指标对比 |

### Risk — 风险与组合 `/risk`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/risk/portfolio` | GET | 组合风险快照 |
| `/risk/correlation` | GET | 相关性矩阵 |
| `/risk/relative-strength` | GET | 相对强弱排名 |
| `/risk/sector-rotation` | GET | 板块轮动状态 |
| `/risk/fund-flow` | GET | 资金流向 |
| `/risk/liquidity-regime` | GET | 流动性状态 |
| `/risk/summary` | GET | 跨资产分析摘要 |

### Sentiment — 情绪与新闻 `/sentiment`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/sentiment/news` | GET | 最新新闻及情感标注 |
| `/sentiment/news/{symbol}` | GET | 指定资产相关新闻 |
| `/sentiment/composite` | GET | 综合情绪评分（恐惧贪婪指数） |
| `/sentiment/retail-fomo` | GET | 散户 FOMO/FUD 指数 |
| `/sentiment/prediction-markets` | GET | 活跃预测市场 |
| `/sentiment/movers` | GET | 预测市场概率变动 Top N |
| `/sentiment/breadth` | GET | 市场广度快照 |

### Onchain — 链上数据 `/onchain`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/onchain/metrics/{symbol}` | GET | 链上指标时序 |
| `/onchain/alternative` | GET | 另类因子最新值 |
| `/onchain/stablecoin/flows` | GET | 稳定币链上流 |
| `/onchain/stablecoin/pulse` | GET | 稳定币脉冲 |
| `/onchain/cross-chain` | GET | 跨链消息统计 |
| `/onchain/mempool` | GET | 内存池状态 |
| `/onchain/mempool/large-txs` | GET | 大额待确认交易 |

### DeFi — DeFi 协议 `/defi`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/defi/liquidations` | GET | 最近 DeFi 清算 |
| `/defi/liquidations/by-protocol` | GET | 按协议清算统计 |
| `/defi/health-factors` | GET | 健康因子分布 |
| `/defi/stress` | GET | DeFi 压力指数 |
| `/defi/governance/proposals` | GET | 治理提案列表 |
| `/defi/governance/votes` | GET | 投票记录 |
| `/defi/smart-money` | GET | Smart Money 信念 |

### Factors — 因子与目录 `/factors`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/factors/catalogs/{domain}` | GET | 因子目录查询（alternative/onchain/options/tokenomics/macro） |
| `/factors/macro/latest` | GET | 宏观上下文快照 |
| `/factors/macro/timeseries` | GET | 宏观因子时序数据 |
| `/factors/explore` | GET | 跨域因子探索（最新值） |

### System — 系统状态 `/system`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/system/health` | GET | 基本健康检查（数据库连通性） |
| `/system/status` | GET | 域数据可用性总览 |
| `/system/status/disabled` | GET | 列出所有被禁用的路由模块 |
| `/system/data-quality` | GET | 数据质量审计快照 |
| `/system/market-structure` | GET | 市场结构快照 |
| `/system/asset-readiness` | GET | 资产数据就绪状态 |

---

## 旧端点（已禁用）

v5.1.0 之前的 ~395 个端点已通过 Feature Flag 全部禁用。如需查看旧端点列表，参考 git 历史或 `GET /system/status/disabled`。

恢复方式：在 `.env` 中设置 `FF_{MODULE}_ENABLED=1`。

---

## 分页

v3.2 引入标准化分页机制，防止大表全量返回导致 OOM。分页工具位于 `api/pagination.py`。

### 两种模式

| 模式 | 适用场景 | 参数 |
|------|---------|------|
| 游标分页（Keyset） | 大数据集、时序数据 | `cursor`, `limit` |
| 偏移分页（Offset） | 小数据集、简单列表 | `page`, `page_size` |

### 游标分页端点（示范）

| 端点 | 说明 |
|------|------|
| `/exchange/funding-rates/paginated/{symbol}` | 资金费率游标分页 |
| `/technical/indicators/paginated/{symbol}` | 技术指标游标分页 |
| `/stablecoin-flow/events/paginated` | 稳定币事件游标分页 |
| `/whale-pnl/history/paginated` | 巨鲸 PnL 游标分页 |
| `/defi-liquidation/events/paginated` | DeFi 清算事件游标分页 |

### 响应格式

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJ0cyI6IjIwMjQtMDEtMDEiLCJpZCI6MTAwfQ==",
    "has_more": true,
    "page_size": 50,
    "total_count": 1234
  }
}
```

### 限制

- 默认 `limit=50`，最大 `limit=1000`（ABSOLUTE_MAX_LIMIT）
- `cursor=null` 时等价于无分页（向后兼容）

---

## 代码结构

```
api/
├── __init__.py
├── __main__.py              # python -m api 入口
├── app.py                   # FastAPI 应用 + uvicorn 启动
├── dependencies.py          # 延迟加载的 DB 单例
├── router_registry.py       # 路由自动发现 + Feature Flag 检查
├── models.py                # Pydantic response schemas
└── routers/
    ├── __init__.py
    ├── _helpers.py          # 共享工具函数
    ├── _legacy/             # 88 个旧路由文件（全部 FF 禁用）
    ├── v3_market.py         # /market — 行情与交易所（活跃）
    ├── v3_technical.py      # /technical — 技术分析（活跃）
    ├── v3_risk.py           # /risk — 风险与组合（活跃）
    ├── v3_sentiment.py      # /sentiment — 情绪与新闻（活跃）
    ├── v3_onchain.py        # /onchain — 链上数据（活跃）
    ├── v3_defi.py           # /defi — DeFi 协议（活跃）
    ├── v3_factors.py        # /factors — 因子与目录（活跃）
    └── v3_system.py         # /system — 系统状态（活跃）
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

### /metrics/prometheus 端点

`GET /metrics/prometheus` 返回 Prometheus text exposition 格式的指标数据，供 Prometheus 服务器抓取。

**导出的 14 个指标：**

| 指标名 | 类型 | 含义 |
|--------|------|------|
| `evoquant_http_requests_total` | Counter | HTTP 请求总数 (method/path/status) |
| `evoquant_http_request_duration_seconds` | Histogram | 请求延迟分布 |
| `evoquant_http_requests_in_progress` | Gauge | 当前并发请求数 |
| `evoquant_module_status` | Gauge | 模块运行状态 |
| `evoquant_module_restart_count` | Gauge | 模块重启次数 |
| `evoquant_module_uptime_seconds` | Gauge | 模块运行时长 |
| `evoquant_domain_latency_seconds` | Gauge | 域数据延迟 |
| `evoquant_domain_freshness_status` | Gauge | 域新鲜度 |
| `evoquant_wmi_score` | Gauge | 世界模型指数 |
| `evoquant_health_status` | Gauge | 整体健康状态 |
| `evoquant_pipeline_phase_duration_seconds` | Histogram | 管道阶段执行时长 |
| `evoquant_pipeline_total_duration_seconds` | Histogram | 管道总执行时长 |
| `evoquant_database_size_bytes` | Gauge | 数据库文件大小 |
| `evoquant_market_alerts_total` | Counter | 市场告警计数 |

配合 Grafana 可视化，详见 [monitoring/README.md](../monitoring/README.md)。

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
