"""EvoQuant API — FastAPI 应用入口。

启动方式：
    python -m api.app --port 8000
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.cache import cache
from api.query_cache import query_cache
from api.models import SymbolInfo, SymbolsResponse
from api.router_registry import discover_routers
from api.errors import register_error_handlers
from api.versioning import CURRENT_API_VERSION, SUPPORTED_VERSIONS
from config.symbols import SYMBOL_UNIVERSE
from core.structured_logging import set_correlation_id, get_correlation_id

# Prometheus 监控（优雅降级：未安装 prometheus_client 时跳过）
try:
    from monitoring.middleware import PrometheusMiddleware
    from monitoring.exporters.prometheus_endpoint import metrics_router
    _MONITORING_AVAILABLE = True
except ImportError:
    _MONITORING_AVAILABLE = False

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# CORS 允许的来源列表，通过环境变量配置，默认仅允许本地开发
_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("API_CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")
    if o.strip()
]

# 限流配置：每个 IP 在窗口期内最大请求数
_RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("API_RATE_LIMIT_MAX_REQUESTS", "200"))
_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("API_RATE_LIMIT_WINDOW_SECONDS", "60"))


# ---------------------------------------------------------------------------
# 限流器（轻量级内存实现，适合单实例部署）
# ---------------------------------------------------------------------------

class _RateLimiter:
    """滑动窗口限流器 — 按 IP 限制请求频率。

    优化 #7: 使用 deque 替代 list，O(1) 弹出过期时间戳。
    优化 #8: LRU 淘汰超过 MAX_TRACKED_IPS 的旧条目。
    """

    MAX_TRACKED_IPS = int(os.environ.get("RATE_LIMIT_MAX_IPS", "10000"))

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque] = {}
        self._access_order: deque = deque()  # LRU 追踪

    def _evict_if_needed(self) -> None:
        """当 IP 追踪数超上限时，淘汰最旧的条目。"""
        while len(self._requests) > self.MAX_TRACKED_IPS:
            old_ip = self._access_order.popleft()
            self._requests.pop(old_ip, None)

    def is_allowed(self, client_ip: str, weight: int = 1) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds

        if client_ip not in self._requests:
            self._requests[client_ip] = deque()
            self._access_order.append(client_ip)
            self._evict_if_needed()

        timestamps = self._requests[client_ip]
        # O(1) 弹出过期时间戳（deque 头部是最旧的）
        while timestamps and timestamps[0] <= window_start:
            timestamps.popleft()

        if len(timestamps) + weight > self.max_requests:
            return False
        for _ in range(weight):
            timestamps.append(now)
        return True

    def remaining(self, client_ip: str) -> int:
        """O(1) 剩余配额计算 — 直接用 deque 长度减去已弹出的过期项。"""
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = self._requests.get(client_ip)
        if not timestamps:
            return self.max_requests
        # 先弹出过期项（维护 deque 干净）
        while timestamps and timestamps[0] <= window_start:
            timestamps.popleft()
        # O(1): deque 当前长度即为有效请求数
        return max(0, self.max_requests - len(timestamps))


_rate_limiter = _RateLimiter(_RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW_SECONDS)


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """管理 API 生命周期：启动缓存清理线程，关闭时停止。"""
    # 优化 #14: GC 阈值调优 — 减少 full GC 频率，降低尾延迟
    gc.set_threshold(50000, 20, 10)
    # 结构化日志初始化
    from core.structured_logging import configure_structured_logging
    configure_structured_logging()
    # 事件总线启动
    from core.event_bus import event_bus
    event_bus.start()
    # 查询预取器启动
    from api.prefetch import query_prefetcher
    query_prefetcher.start()
    cache.start()
    query_cache.start()
    # 热数据预加载：将高频查询表缓存到 QueryCache 消除冷启动延迟
    from api.preloader import preload_hot_data
    await preload_hot_data()
    yield
    query_prefetcher.stop()
    event_bus.stop()
    query_cache.stop()
    cache.stop()


# ---------------------------------------------------------------------------
# 应用实例
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EvoQuant Data API",
    description="AI 市场数据供给层对外接口 — 提供结构化、质量自知的市场信息",
    version="2.1.0",
    lifespan=_lifespan,
)

# 使用 orjson 加速 JSON 序列化（减少 20-30% 序列化开销）
try:
    from fastapi.responses import ORJSONResponse
    app.router.default_response_class = ORJSONResponse
except ImportError:
    pass

# OpenTelemetry 分布式追踪（可选启用，通过 OTEL_ENABLED=true 开启）
from core.tracing import init_tracing
init_tracing(app=app)


# ---------------------------------------------------------------------------
# 中间件（注册顺序：后注册的先执行）
# ---------------------------------------------------------------------------

# 压缩中间件 — 优化 #9: 优先 Brotli（比 Gzip 高 15-25% 压缩率），降级 Gzip
try:
    from starlette_compress import CompressMiddleware
    app.add_middleware(CompressMiddleware, minimum_size=1000)
    _COMPRESSION_TYPE = "brotli+gzip"
except ImportError:
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    _COMPRESSION_TYPE = "gzip"

# ETag 条件请求 — 减少未变更响应的带宽消耗
from api.etag_middleware import ETagMiddleware

app.add_middleware(ETagMiddleware)

# Prometheus HTTP 指标中间件
if _MONITORING_AVAILABLE:
    app.add_middleware(PrometheusMiddleware)

# CORS — 限制允许的来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """注入 X-Request-ID，用于分布式追踪和日志关联。"""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    # 设置结构化日志关联 ID
    set_correlation_id(request_id)
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-API-Version"] = CURRENT_API_VERSION
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """按 IP + 端点权重限流 — 昂贵端点消耗更多配额，超限返回 429。"""
    client_ip = request.client.host if request.client else "unknown"
    # 差异化权重：昂贵端点消耗更多配额
    path = request.url.path
    weight = 1
    if path.startswith("/aggregate/"):
        weight = 5
    elif path.startswith("/health/external"):
        weight = 3
    elif path.startswith("/ai-context/"):
        weight = 3

    if not _rate_limiter.is_allowed(client_ip, weight=weight):
        logger.warning("rate limit exceeded for {}: {}", client_ip, path)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(_RATE_LIMIT_WINDOW_SECONDS)},
        )
    response: Response = await call_next(request)
    remaining = _rate_limiter.remaining(client_ip)
    response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT_MAX_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


# ---------------------------------------------------------------------------
# 全局异常处理 — 标准化错误响应
# ---------------------------------------------------------------------------

register_error_handlers(app)


# ---------------------------------------------------------------------------
# 路由注册 — 自动发现
# ---------------------------------------------------------------------------

for _router in discover_routers():
    app.include_router(_router)

# Prometheus 指标端点
if _MONITORING_AVAILABLE:
    app.include_router(metrics_router)


# ---------------------------------------------------------------------------
# 根端点
# ---------------------------------------------------------------------------

@app.get("/symbols", response_model=SymbolsResponse, tags=["symbols"])
def get_symbols() -> SymbolsResponse:
    """返回资产宇宙列表（含 tier 和 sector）。"""
    items = [
        SymbolInfo(symbol=s["symbol"], tier=s["tier"], sector=s["sector"])
        for s in SYMBOL_UNIVERSE
    ]
    return SymbolsResponse(count=len(items), symbols=items)


@app.get("/metrics", tags=["ops"])
def get_metrics():
    """运维指标端点 — 暴露缓存命中率、限流状态等内部指标。"""
    return {
        "cache": cache.metrics,
        "query_cache": query_cache.metrics,
        "rate_limiter": {
            "max_requests": _RATE_LIMIT_MAX_REQUESTS,
            "window_seconds": _RATE_LIMIT_WINDOW_SECONDS,
            "tracked_ips": len(_rate_limiter._requests),
        },
    }


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="EvoQuant API Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
