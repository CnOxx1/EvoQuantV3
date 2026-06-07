# EvoQuant 架构图

## 系统总览

```mermaid
graph TB
    subgraph External["外部数据源"]
        EX_CEX["Binance / OKX / Bybit"]
        EX_DEFI["DefiLlama / Uniswap / Curve"]
        EX_ONCHAIN["Etherscan / Arkham / Nansen"]
        EX_MACRO["宏观数据源"]
        EX_NEWS["新闻聚合源"]
        EX_OPTIONS["Deribit"]
        EX_MEV["Flashbots / EigenPhi"]
        EX_SOCIAL["LunarCrush / Santiment"]
        EX_GOV["Snapshot / Tally"]
        EX_PRED["Polymarket / Alternative.me / Coinglass"]
        EX_MINING["mempool.space / Blockchain.com"]
    end

    subgraph DataLayer["数据层 (32 模块)"]
        DL_CORE["exchange / macro / news / onchain\noptions / tokenomics / event_calendar / alternative"]
        DL_EXT["social_sentiment / whale_tracker / orderflow\ndefi_protocol / bridge_flow / regulatory"]
        DL_NEW["etf_flow / basis_curve / mev / cefi_lending\nperp_dex / onchain_address / dex_liquidity\ngas_network / governance"]
        DL_V3["prediction_market / onchain_holder / liquid_staking\nmempool / funding_round / exchange_reserve\nminer_data / derivatives_sentiment"]
        DL_QUALITY["data_quality (审计 + WMI)"]
        DL_PERF["batch_utils (并行采集)\nrequest_dedup_cache (去重)"]
    end

    subgraph Storage["存储层 (SQLite 三域拆分)"]
        DB_EX["exchange_data.db\n行情/衍生品/盘口"]
        DB_MK["market_data.db\n宏观/链上/期权/Tokenomics"]
        DB_AN["analytics.db\n逻辑结果/风险/指标"]
    end

    subgraph LogicLayer["逻辑层 (33 模块)"]
        LL_CORE["technical_indicators / feature_standardization\ncross_asset_analysis / portfolio_risk"]
        LL_CONTEXT["macro_context / news_sentiment / exchange_comparison\nmarket_structure / market_breadth"]
        LL_AI["asset_readiness / ai_market_context\ntime_slice / pipeline_latency"]
        LL_ANALYSIS["regime_detection / anomaly_detection\nliquidity_analysis / volatility_forecast\nfunding_rate_model / sentiment_signal"]
        LL_ADVANCED["temporal_pattern / flow_decomposition\ncontagion_risk / alpha_decay / narrative_regime\nliquidation_cascade / cross_venue_arbitrage\nonchain_lead_lag"]
        LL_V3["holder_behavior_analysis / liquidity_regime\nevent_probability / miner_pressure\nmarket_sentiment_composite"]
    end

    subgraph API["API 层 (505 端点)"]
        API_REST["FastAPI REST Server"]
        API_WS["WebSocket 实时推送\npipeline / health / indicators"]
        API_MW["中间件: CORS / 限流 / 追踪 / 压缩\nETag / 版本化 / 结构化日志"]
    end

    subgraph Observability["可观测性"]
        OTEL["OpenTelemetry\n分布式追踪 (可选)"]
        PROM["Prometheus\nHTTP 指标"]
        HEALTH["深度健康检查\n采集新鲜度 + 外部连通性"]
        ALERT["告警规则引擎\n错误率/延迟/内存/连接池"]
    end

    subgraph Orchestration["编排层"]
        MAIN["main.py\n模块注册 + 进程监督\n+ 资源限制 + 特性开关 + 降级\n+ 懒启动 + 优先级退避\n+ 优雅关闭 + 混沌注入\n+ 优先级分批并行启动"]
        PIPELINE["logic_pipeline\nDAG 调度 + Phase 并行\n+ 结果缓存 + 事件总线\n+ 缓存依赖图精准失效\n+ 窗口预物化\n+ wait(FIRST_EXCEPTION) 快速失败"]
    end

    subgraph Resilience["韧性层"]
        CB["熔断器 (circuit_breaker)\nCLOSED→OPEN→HALF_OPEN"]
        DEG["降级管理器 (degradation)\nNORMAL→REDUCED→MINIMAL→EMERGENCY"]
        FF["特性开关 (feature_flags)\nFF_{MODULE}_ENABLED"]
        EB["事件总线 (event_bus)\ntopic 订阅 + 异步发布 + 指标"]
        ANOM["数据异常检测 (anomaly_detector)\nZ-score + 空值 + 量降"]
        RET["数据保留 (data_retention)\nhot/warm/archive 分层"]
        LIN["数据血缘 (data_lineage)\nsource→target 追踪"]
        LAZY["懒启动 (lazy_starter)\n非关键模块按需激活"]
        TRACE["跨进程追踪 (trace_propagation)\nW3C traceparent 传播"]
    end

    subgraph Adaptive["自适应层"]
        APOOL["连接池自适应 (adaptive_pool)\nEMA wait_time/idle_ratio"]
        ABATCH["批量写入自适应 (adaptive_batch)\np50 延迟反馈调节 50-2000"]
        PREFETCH["查询预取 (prefetch)\npipeline 完成 → 预热热点"]
        COLSEL["列裁剪 (column_selector)\nSELECT * → 精确列"]
        PGNOTIFY["PG NOTIFY (pg_notify)\n分布式缓存失效广播"]
        SNAP["快照版本化 (snapshot_versioning)\npoint-in-time 状态回溯"]
    end

    External --> DataLayer
    DataLayer --> Storage
    Storage --> LogicLayer
    LogicLayer --> DB_AN
    Storage --> API
    DB_AN --> API
    MAIN --> DataLayer
    PIPELINE --> LogicLayer
    PIPELINE --> API_WS
    API_REST --> OTEL
    API_REST --> PROM
    HEALTH --> Storage
    CB --> Storage
    DEG --> MAIN
    FF --> MAIN
    FF --> PIPELINE
    EB --> PIPELINE
    ANOM --> DataLayer
    ALERT --> PROM
    LAZY --> MAIN
    TRACE --> MAIN
    APOOL --> Storage
    ABATCH --> Storage
    PREFETCH --> API
    COLSEL --> Storage
    PGNOTIFY --> Storage
    SNAP --> Storage
```

## 数据流

```mermaid
sequenceDiagram
    participant Ext as 外部 API
    participant Client as data_layer/*/client.py
    participant Service as data_layer/*/service.py
    participant DB as SQLite (三域)
    participant Logic as logic_layer/*/service.py
    participant API as FastAPI (505 端点)
    participant AI as AI Consumer

    Ext->>Client: HTTP/WebSocket 请求
    Client->>Service: 标准化数据
    Service->>DB: 写入历史表 + latest_* 快照
    Service->>DB: 记录 collection_runs + coverage
    DB->>Logic: 读取 latest_* + 历史窗口
    Logic->>DB: 写入分析结果 (analytics.db)
    DB->>API: 查询响应
    API->>AI: JSON 结构化上下文
```

## 逻辑管道调度 (DAG)

```mermaid
graph LR
    subgraph Phase1["Phase 1 串行"]
        TI["technical_indicators"]
    end

    subgraph Phase2["Phase 2 并行"]
        FS["feature_standardization"]
        CA["cross_asset_analysis"]
        MC["macro_context"]
        NS["news_sentiment"]
        EC["exchange_comparison"]
        MS["market_structure"]
        RD["regime_detection"]
        AD["anomaly_detection"]
        LA["liquidity_analysis"]
        VF["volatility_forecast"]
        FR["funding_rate_model"]
        SS["sentiment_signal"]
        TP["temporal_pattern"]
        FD["flow_decomposition"]
        CR["contagion_risk"]
        ALD["alpha_decay"]
        NR["narrative_regime"]
        LC["liquidation_cascade"]
        CVA["cross_venue_arbitrage"]
        OLL["onchain_lead_lag"]
        HBA["holder_behavior_analysis"]
        LR["liquidity_regime"]
        EP["event_probability"]
        MP["miner_pressure"]
        MSC["market_sentiment_composite"]
    end

    subgraph Phase3["Phase 3 串行"]
        MB["market_breadth"]
        PR["portfolio_risk"]
    end

    subgraph Phase4["Phase 4 串行"]
        AR["asset_readiness"]
    end

    subgraph Phase5["Phase 5 串行"]
        AMC["ai_market_context"]
    end

    Phase1 --> Phase2
    Phase2 --> Phase3
    Phase3 --> Phase4
    Phase4 --> Phase5
```

## 模块内部结构

```mermaid
graph LR
    subgraph Module["典型数据层模块"]
        R["runner.py\n入口 + 调度"]
        S["service.py\n编排逻辑"]
        C["client.py\nAPI 客户端"]
        M["models.py\n数据模型"]
        RP["repository.py\nDB 读写"]
    end

    R --> S
    S --> C
    S --> RP
    C --> M
    RP --> M
```

## 质量治理流

```mermaid
graph LR
    RAW["原始数据"] --> QF["quality_flag\nok / partial / stale / missing"]
    QF --> LATEST["latest_* 快照"]
    LATEST --> BUNDLE["context_bundle"]
    BUNDLE --> READY{"is_ready_for_ai?"}
    READY -->|Yes| AI["AI 消费"]
    READY -->|No| DIAG["诊断区 降级/排除"]

    DQA["data_quality_audit"] --> WMI["WMI 指数\n宽度 x 稳定性 x 诚实性"]
    WMI --> WORLD["world_model_status\nready / partial / blocked"]
```

## 进程管理

```mermaid
graph TB
    MAIN["main.py"] --> |spawn| D1["daemon: exchange_data"]
    MAIN --> |spawn| D2["daemon: macro_data"]
    MAIN --> |spawn| D3["daemon: news_data"]
    MAIN --> |spawn| DN["daemon: ... (24 autostart)"]
    MAIN --> |spawn| LP["daemon: logic_pipeline"]
    MAIN --> |spawn| API["daemon: api_server"]

    MAIN --> |supervise| RESTART["指数退避重启\n2s → 4s → 8s → ... → 60s"]
    MAIN --> |SIGINT| GRACEFUL["三阶段关停\nSIGINT → SIGTERM → SIGKILL"]
```

## 监控与可观测性

```mermaid
graph LR
    subgraph EvoQuant
        API["/metrics/prometheus\n(FastAPI endpoint)"]
        MW["PrometheusMiddleware\n(HTTP 指标)"]
        MC["module_collector\n(模块状态)"]
        PC["pipeline_collector\n(域延迟/健康)"]
        DC["database_collector\n(DB 文件大小)"]
    end

    MW --> API
    MC --> API
    PC --> API
    DC --> API

    API --> |15s scrape| PROM["Prometheus\n:9090\n30 天保留"]
    PROM --> GRAF["Grafana\n:3000"]

    subgraph Dashboards
        D1["System Overview"]
        D2["Pipeline Health"]
        D3["Market Alerts"]
    end

    GRAF --> D1
    GRAF --> D2
    GRAF --> D3
```

**指标采集链路：**
- HTTP 中间件 → `evoquant_http_requests_total` / `_duration_seconds` / `_in_progress`
- main.py 后台线程（15s）→ `evoquant_module_status` / `_restart_count` / `_uptime_seconds`
- /metrics/prometheus 后台线程（15s）→ `evoquant_domain_*` / `evoquant_wmi_score` / `evoquant_database_size_bytes`
- logic_pipeline 阶段回调 → `evoquant_pipeline_phase_duration_seconds` / `_total_duration_seconds`

## 基础设施层 (v3.4.0)

```mermaid
graph TB
    subgraph Core["core/ 基础设施"]
        BDC["BaseDataClient\n同步 HTTP + 熔断 + 限流"]
        ABDC["AsyncBaseDataClient\n异步 HTTP + 熔断 + 限流"]
        MM["MemoryMonitor\nRSS 监控 + DataFrame 检测"]
    end

    subgraph Database["database/ 数据库层"]
        DBM["db_manager.py\n(向后兼容入口)"]
        MGR["managers/ 包\nConnectionMixin + SchemaUtils + QueryMethods"]
        IDX["indexes.py + partial_indexes.py\n复合索引 + 部分索引 + 覆盖索引"]
        QP["query_profiler.py\nEXPLAIN + 慢查询 + ANALYZE"]
        CQ["chunked_query.py\n分块查询生成器"]
    end

    subgraph API_Infra["api/ 基础设施"]
        RR["router_registry.py\n路由自动发现"]
        TC["cache.py (TTLCache)\n响应缓存 + 前缀失效"]
        QC["query_cache.py (QueryCache)\n查询缓存 + SWR + 分组失效"]
    end

    BDC --> |"子类继承"| DL["data_layer 模块"]
    ABDC --> |"异步采集"| DL
    MM --> |"计算前检查"| LL["logic_layer 模块"]
    CQ --> |"分块读取"| LL
    QP --> |"慢查询分析"| DBM
    RR --> |"自动注册"| APP["api/app.py"]
    QC --> |"管道刷新失效"| PIPELINE["logic_pipeline"]
```

**v3.4.0 新增组件：**
- `core/async_base_data_client.py` — 异步 HTTP 客户端基类（AsyncCircuitBreaker + AsyncRateLimiter）
- `core/memory_monitor.py` — 进程内存监控（psutil）+ DataFrame 大小检测
- `database/managers/` — DBManager Mixin 模块化拆分（ConnectionMixin/SchemaUtilsMixin/QueryMethodsMixin）
- `database/query_profiler.py` — EXPLAIN QUERY PLAN 分析 + 自动 ANALYZE + 慢查询统计
- `database/partial_indexes.py` — 部分索引（热数据窗口）+ 覆盖索引（避免回表）
- `database/chunked_query.py` — 分块查询生成器（chunked_fetch / chunked_fetch_df）
- `api/router_registry.py` — 路由自动发现（pkgutil 扫描）
- `api/query_cache.py` 增强 — invalidate_prefix + invalidate_group + stale-while-revalidate

## 性能优化层 (v4.0.0 ~ v4.3.0)

```mermaid
graph TB
    subgraph CalcHotPath["计算热路径优化 (v4.0.0)"]
        VEC["numpy 向量化\nSupertrend/PSAR/KAMA/Fisher/Ehlers/KVO\n消除 .iloc[] 循环"]
        NPMAX["np.maximum/minimum\n替代 pd.concat().max/min\n零中间分配"]
        COPY["DataFrame copy 消除\n3次→1次 (30% 内存减少)"]
        PREALLOC["单次 dict→DataFrame\n替代 12 次 pd.concat\n减少内存碎片"]
    end

    subgraph APIPerf["API 响应路径优化 (v4.0.0 + v4.1.0)"]
        DEQUE["Rate Limiter deque\nO(1) popleft + O(1) remaining"]
        LRU["IP LRU 淘汰\nMAX_TRACKED_IPS=10000"]
        BROTLI["Brotli 压缩\n比 Gzip 高 15-25% 压缩率"]
        GC["GC 阈值调优\nset_threshold(50000,20,10)"]
        COALESCE["RequestCoalescer 零延迟\n移除 100ms sleep"]
        PREFETCH["Prefetcher 真预热\n执行 DB 查询写入 cache"]
        PROJ["SELECT 列投影\n替代 SELECT *"]
    end

    subgraph SystemPerf["系统级优化 (v4.0.0 + v4.1.0)"]
        PARALLEL["模块并行启动\ncritical→normal→low 分批"]
        FASTFAIL["Pipeline 快速失败\nwait(FIRST_EXCEPTION)"]
        SKIPFAIL["上游失败快跳\nfailed_upstream 级联跳过"]
        MEMCACHE["memory_monitor 缓存\ndouble-check locking"]
        ADAPT["连接池自适应集成\npool_overflow + idle_timeout"]
        SYMCACHE["符号标准化 LRU\n@lru_cache(1024)"]
        CACHEDEP["缓存依赖拓扑\ninvalidate_downstream 级联"]
    end
```

**v4.0.0 关键改动：**
- `logic_layer/technical_indicators/calculator.py` — 7 个核心循环函数向量化（_supertrend/_parabolic_sar/_kama/_fisher_transform/_ehlers_*/_klinger_volume_oscillator/_positive_negative_volume_index）
- `api/app.py` — _RateLimiter 重写为 deque + LRU 淘汰 + Brotli 压缩 + GC 调优
- `logic_layer/logic_pipeline/service.py` — _run_phase_parallel 改用 wait(FIRST_EXCEPTION)
- `main.py` — supervise_modules 按优先级分批并行启动
- `core/memory_monitor.py` — rss_mb 添加 1s 结果缓存
- `database/pool_config.py` — 新增 adaptive_enabled/pool_overflow/idle_timeout + get_adaptive_pool_size()
- `requirements.txt` — 新增 numpy==1.26.4 / starlette-compress==1.0.1 / bottleneck==1.4.2

**v4.1.0 关键改动：**
- `api/routers/aggregate.py` — SELECT * 改为列投影 + _SYMBOL_INDEX 预索引 O(1) 查找
- `api/request_coalescer.py` — 移除首次请求的 time.sleep(100ms)，零延迟直接执行
- `api/prefetch.py` — prefetch_all() 真正执行 DB 查询写入 query_cache
- `api/query_cache.py` — 新增 register_dependency() / invalidate_downstream() 级联失效
- `api/app.py` — remaining() 改为 O(1) deque len 计算
- `logic_layer/logic_pipeline/service.py` — 新增 _MODULE_DEPENDENCIES + failed_upstream 快跳
- `logic_layer/market_breadth/service.py` — _normalize_asset_from_symbol 添加 @lru_cache
- `data_layer/exchange_data/service.py` — _build_symbols_map 预分配 + 直接索引
- `core/memory_monitor.py` — double-check locking 防止并发 syscall

**v4.2.0 关键改动：**
- `logic_layer/feature_standardization/service.py` — O(n²) 逐 symbol 过滤改为 groupby 一次分组 + .values[-1] 替代 .iloc[-1]
- `api/websocket_manager.py` — orjson 快速序列化路径，broadcast 只 encode 一次
- `core/event_bus.py` — handler 缓存 tuple + 10ms 轮询 + 延迟日志格式化
- `database/backends/postgres_backend.py` — _DictRow __slots__ + tuple columns 缓存 + tuple(values)
- `api/query_cache.py` — _inflight_lock 独立锁，缓存读写与 inflight 管理互不阻塞

**v4.3.0 关键改动：**
- `api/routers/aggregate.py` — correlation-context N+1 查询（18次 DB）合并为单次全量查询 + 内存分组
- `logic_layer/cross_asset_analysis/service.py` — run_all() 预加载共享数据，消除 3 次重复 DB 调用
- `logic_layer/technical_indicators/repository.py` — open_time 向量化预转换替代逐行 pd.Timestamp()
- `main.py` — shutdown 信号前置检查，避免无效子进程轮询
- `config/symbols.py` — ALL_SECTOR_SYMBOLS frozenset 预计算
- `api/routers/prediction_market.py` / `liquidation_cascade.py` — SELECT * 全部改为列投影
- `logic_layer/result_cache.py` — 短 key (≤128) 跳过 SHA-256 直接用原始字符串
- `logic_layer/technical_indicators/service.py` — loguru import 提升至模块级

**v4.4.0 关键改动：**
- `logic_layer/cross_asset_analysis/calculator.py` — compute_correlation_matrix 从 O(n²) 纯 Python 循环改为 numpy corrcoef 一次向量化计算 (10-100×)
- `api/dependencies.py` — 新增 6 个 @lru_cache 服务单例（liquidity_regime/liquidation_cascade/holder_behavior/miner_pressure/flow_decomposition/temporal_pattern）
- `api/routers/` (6 个 context 端点) — 逐请求 Service() + close() 改为单例注入，消除 50-200ms/请求实例化开销
- `logic_layer/cross_asset_analysis/repository.py` — json.dumps/loads 替换为 orjson 快速路径 (3-5× 加速)
- `logic_layer/time_slice/service.py` — 3 次 sum() generator 改为 Counter 单次遍历
- `core/memory_monitor.py` — 缓存 TTL 从固定 1s 改为 MEMORY_CACHE_TTL_SECONDS 环境变量 (默认 5s)
- `api/routers/` (12 个端点) — liquidity_regime/holder_behavior/miner_pressure/orderflow_micro/stablecoin_flow/prediction_market SELECT * → 列投影

**v4.5.0 关键改动：**
- `api/routers/volatility.py` — ranking 端点 N+1 查询合并为单次 IN(...) 批量查询 + 内存分组 (5-10×)
- `api/routers/factor_explorer.py` — 手动 Pearson 循环改为 np.corrcoef() 向量化 (10-50×)
- `logic_layer/news_sentiment/classifier.py` — 逐词 `kw in text` 改为预编译正则 findall 单次扫描 (3-5×)
- `logic_layer/technical_indicators/enricher.py` — groupby sort=False + 辅助 DataFrame 预分组 dict 查找替代 boolean mask
- `api/fair_limiter.py` — metrics() set(list+list) 改为 dict_keys 视图并集
- `api/pagination.py` — cursor 编解码 json.dumps/loads 替换为 orjson 快速路径

**v4.6.0 关键改动：**
- `logic_layer/feature_standardization/service.py` — 跨资产排名 O(n²) 嵌套循环改为预建 feature_name→rows 索引 O(n) + Counter 替代手动 regime 计数 + orjson 序列化
- `logic_layer/portfolio_risk/calculator.py` — O(n²) 协方差矩阵循环改为 numpy `w @ cov @ w` 矩阵乘法 (30-50×)
- `logic_layer/cross_asset_analysis/service.py` — fund_flow 多次 sum(get()) 改为单次遍历 flow_map 预聚合 tier/sector 数组
- `logic_layer/asset_readiness/service.py` — 12 次 set() | set() 改为单个 set 累加器 .update() 链
- `main.py` — 3 次 list comprehension 优先级分组改为单次循环 dict 累加
