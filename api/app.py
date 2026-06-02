"""EvoQuant API — FastAPI 应用入口。

启动方式：
    python -m api.app --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.cache import cache
from api.query_cache import query_cache
from api.models import SymbolInfo, SymbolsResponse
from api.routers.bundle import router as bundle_router
from api.routers.cross_asset import router as cross_asset_router
from api.routers.domains import router as domains_router
from api.routers.exchange import router as exchange_router
from api.routers.health import router as health_router
from api.routers.macro import router as macro_router
from api.routers.onchain import router as onchain_router
from api.routers.risk import router as risk_router
from api.routers.sentiment import router as sentiment_router
from api.routers.signals import router as signals_router
from api.routers.technical import router as technical_router
from api.routers.time_slice import router as time_slice_router
from api.routers.data_quality import router as data_quality_router
from api.routers.features import router as features_router
from api.routers.alternative import router as alternative_router
from api.routers.market_info import router as market_info_router
from api.routers.catalogs import router as catalogs_router
from api.routers.aggregate import router as aggregate_router
from api.routers.strategy import router as strategy_router
from api.routers.monitor import router as monitor_router
from api.routers.orderflow import router as orderflow_router
from api.routers.derivatives import router as derivatives_router
from api.routers.news_intel import router as news_intel_router
from api.routers.ai_context import router as ai_context_router
from api.routers.technical_deep import router as technical_deep_router
from api.routers.portfolio_analytics import router as portfolio_analytics_router
from api.routers.microstructure import router as microstructure_router
from api.routers.cross_asset_history import router as cross_asset_history_router
from api.routers.factor_explorer import router as factor_explorer_router
from api.routers.social_sentiment import router as social_sentiment_router
from api.routers.whale_tracker import router as whale_tracker_router
from api.routers.orderflow_micro import router as orderflow_micro_router
from api.routers.defi import router as defi_router
from api.routers.bridge_flow import router as bridge_flow_router
from api.routers.regulatory import router as regulatory_router
from api.routers.regime import router as regime_router
from api.routers.anomaly import router as anomaly_router
from api.routers.liquidity import router as liquidity_router
from api.routers.volatility import router as volatility_router
from api.routers.etf_flow import router as etf_flow_router
from api.routers.basis_curve import router as basis_curve_router
from api.routers.mev import router as mev_router
from api.routers.cefi_lending import router as cefi_lending_router
from api.routers.temporal_pattern import router as temporal_pattern_router
from api.routers.flow_decomposition import router as flow_decomposition_router
from api.routers.contagion_risk import router as contagion_risk_router
from api.routers.alpha_decay import router as alpha_decay_router
from api.routers.narrative_regime import router as narrative_regime_router
from api.routers.perpetual_dex import router as perpetual_dex_router
from api.routers.onchain_address import router as onchain_address_router
from api.routers.dex_liquidity import router as dex_liquidity_router
from api.routers.gas_network import router as gas_network_router
from api.routers.governance import router as governance_router
from api.routers.liquidation_cascade import router as liquidation_cascade_router
from api.routers.cross_venue_arb import router as cross_venue_arb_router
from api.routers.onchain_lead_lag import router as onchain_lead_lag_router
from api.routers.prediction_market import router as prediction_market_router
from api.routers.onchain_holder import router as onchain_holder_router
from api.routers.liquid_staking import router as liquid_staking_router
from api.routers.mempool import router as mempool_router
from api.routers.funding_round import router as funding_round_router
from api.routers.exchange_reserve import router as exchange_reserve_router
from api.routers.miner import router as miner_router
from api.routers.derivatives_sentiment import router as derivatives_sentiment_router
from api.routers.holder_behavior import router as holder_behavior_router
from api.routers.liquidity_regime import router as liquidity_regime_router
from api.routers.event_probability import router as event_probability_router
from api.routers.miner_pressure import router as miner_pressure_router
from api.routers.sentiment_composite import router as sentiment_composite_router
from api.routers.stablecoin_flow import router as stablecoin_flow_router
from api.routers.token_unlock import router as token_unlock_router
from api.routers.orderbook_depth import router as orderbook_depth_router
from api.routers.whale_pnl import router as whale_pnl_router
from api.routers.nft_market import router as nft_market_router
from api.routers.defi_liquidation import router as defi_liquidation_router
from api.routers.dex_trade_flow import router as dex_trade_flow_router
from api.routers.cross_chain_msg import router as cross_chain_msg_router
from api.routers.lending_utilization import router as lending_utilization_router
from api.routers.search_trend import router as search_trend_router
from api.routers.exchange_announcement import router as exchange_announcement_router
from api.routers.stablecoin_pulse import router as stablecoin_pulse_router
from api.routers.unlock_impact import router as unlock_impact_router
from api.routers.depth_regime import router as depth_regime_router
from api.routers.smart_money_conviction import router as smart_money_conviction_router
from api.routers.defi_stress import router as defi_stress_router
from api.routers.retail_fomo import router as retail_fomo_router
from api.errors import register_error_handlers
from config.symbols import SYMBOL_UNIVERSE

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
    """滑动窗口限流器 — 按 IP 限制请求频率。"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        # 清理过期记录
        timestamps = self._requests[client_ip]
        self._requests[client_ip] = [t for t in timestamps if t > window_start]
        if len(self._requests[client_ip]) >= self.max_requests:
            return False
        self._requests[client_ip].append(now)
        return True

    def remaining(self, client_ip: str) -> int:
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = [t for t in self._requests.get(client_ip, []) if t > window_start]
        return max(0, self.max_requests - len(timestamps))


_rate_limiter = _RateLimiter(_RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW_SECONDS)


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """管理 API 生命周期：启动缓存清理线程，关闭时停止。"""
    cache.start()
    query_cache.start()
    yield
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


# ---------------------------------------------------------------------------
# 中间件（注册顺序：后注册的先执行）
# ---------------------------------------------------------------------------

# Gzip 压缩 — 响应体超过 1KB 时自动压缩（减少 60-80% 传输体积）
from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

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
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """按 IP 限流 — 超限返回 429。"""
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        logger.warning("rate limit exceeded for {}: {}", client_ip, request.url.path)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(_RATE_LIMIT_WINDOW_SECONDS)},
        )
    response: Response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(_rate_limiter.remaining(client_ip))
    return response


# ---------------------------------------------------------------------------
# 全局异常处理 — 标准化错误响应
# ---------------------------------------------------------------------------

register_error_handlers(app)


# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------

app.include_router(bundle_router)
app.include_router(domains_router)
app.include_router(health_router)
app.include_router(time_slice_router)
app.include_router(signals_router)
app.include_router(technical_router)
app.include_router(risk_router)
app.include_router(exchange_router)
app.include_router(macro_router)
app.include_router(cross_asset_router)
app.include_router(onchain_router)
app.include_router(sentiment_router)
app.include_router(data_quality_router)
app.include_router(features_router)
app.include_router(alternative_router)
app.include_router(market_info_router)
app.include_router(catalogs_router)
app.include_router(aggregate_router)
app.include_router(strategy_router)
app.include_router(monitor_router)
app.include_router(orderflow_router)
app.include_router(derivatives_router)
app.include_router(news_intel_router)
app.include_router(ai_context_router)
app.include_router(technical_deep_router)
app.include_router(portfolio_analytics_router)
app.include_router(microstructure_router)
app.include_router(cross_asset_history_router)
app.include_router(factor_explorer_router)
app.include_router(social_sentiment_router)
app.include_router(whale_tracker_router)
app.include_router(orderflow_micro_router)
app.include_router(defi_router)
app.include_router(bridge_flow_router)
app.include_router(regulatory_router)
app.include_router(regime_router)
app.include_router(anomaly_router)
app.include_router(liquidity_router)
app.include_router(volatility_router)
app.include_router(etf_flow_router)
app.include_router(basis_curve_router)
app.include_router(mev_router)
app.include_router(cefi_lending_router)
app.include_router(temporal_pattern_router)
app.include_router(flow_decomposition_router)
app.include_router(contagion_risk_router)
app.include_router(alpha_decay_router)
app.include_router(narrative_regime_router)
app.include_router(perpetual_dex_router)
app.include_router(onchain_address_router)
app.include_router(dex_liquidity_router)
app.include_router(gas_network_router)
app.include_router(governance_router)
app.include_router(liquidation_cascade_router)
app.include_router(cross_venue_arb_router)
app.include_router(onchain_lead_lag_router)
app.include_router(prediction_market_router)
app.include_router(onchain_holder_router)
app.include_router(liquid_staking_router)
app.include_router(mempool_router)
app.include_router(funding_round_router)
app.include_router(exchange_reserve_router)
app.include_router(miner_router)
app.include_router(derivatives_sentiment_router)
app.include_router(holder_behavior_router)
app.include_router(liquidity_regime_router)
app.include_router(event_probability_router)
app.include_router(miner_pressure_router)
app.include_router(sentiment_composite_router)
app.include_router(stablecoin_flow_router)
app.include_router(token_unlock_router)
app.include_router(orderbook_depth_router)
app.include_router(whale_pnl_router)
app.include_router(nft_market_router)
app.include_router(defi_liquidation_router)
app.include_router(dex_trade_flow_router)
app.include_router(cross_chain_msg_router)
app.include_router(lending_utilization_router)
app.include_router(search_trend_router)
app.include_router(exchange_announcement_router)
app.include_router(stablecoin_pulse_router)
app.include_router(unlock_impact_router)
app.include_router(depth_regime_router)
app.include_router(smart_money_conviction_router)
app.include_router(defi_stress_router)
app.include_router(retail_fomo_router)


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
