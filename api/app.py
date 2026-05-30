"""EvoQuant API — FastAPI 应用入口。

启动方式：
    python -m api.app --port 8000
"""

from __future__ import annotations

import argparse
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from config.symbols import SYMBOL_UNIVERSE

app = FastAPI(
    title="EvoQuant Data API",
    description="AI 市场数据供给层对外接口 — 提供结构化、质量自知的市场信息",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# 原有路由
app.include_router(bundle_router)
app.include_router(domains_router)
app.include_router(health_router)
app.include_router(time_slice_router)

# 新增路由
app.include_router(signals_router)
app.include_router(technical_router)
app.include_router(risk_router)
app.include_router(exchange_router)
app.include_router(macro_router)
app.include_router(cross_asset_router)
app.include_router(onchain_router)
app.include_router(sentiment_router)


@app.get("/symbols", response_model=SymbolsResponse, tags=["symbols"])
def get_symbols() -> SymbolsResponse:
    """返回资产宇宙列表（含 tier 和 sector）。"""
    items = [
        SymbolInfo(symbol=s["symbol"], tier=s["tier"], sector=s["sector"])
        for s in SYMBOL_UNIVERSE
    ]
    return SymbolsResponse(count=len(items), symbols=items)


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
