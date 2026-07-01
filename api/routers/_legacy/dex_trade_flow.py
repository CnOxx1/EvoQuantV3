"""DEX Trade Flow 路由 — DEX 大额交易流端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/dex-trade-flow", tags=["dex-trade-flow"])


@router.get("/recent")
def get_recent_large_trades(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近大额 DEX 交易列表。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM dex_large_trades ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "trades": rows}


@router.get("/routers")
def get_router_volume_stats(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """DEX Router 成交量排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM dex_router_stats ORDER BY volume_24h_usd DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "routers": rows}


@router.get("/mev-victims")
def get_mev_victim_trades(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """被 MEV 攻击的交易列表。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM dex_large_trades WHERE is_mev_victim = 1 "
        "ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "mev_victims": rows}


@router.get("/by-token")
def get_trades_by_token(
    token: str = Query(..., description="代币符号"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """按代币筛选 DEX 大额交易。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM dex_large_trades WHERE token = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (token.upper(), limit),
    )
    return {"token": token.upper(), "count": len(rows), "trades": rows}


@router.get("/context")
def get_dex_trade_flow_context() -> dict[str, Any]:
    """DEX 交易流 AI 上下文 bundle。"""
    from data_layer.dex_trade_flow.service import DexTradeFlowService
    service = DexTradeFlowService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
