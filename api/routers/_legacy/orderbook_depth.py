"""Orderbook Depth 路由 — 订单簿深度与买卖墙分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/orderbook-depth", tags=["orderbook-depth"])


@router.get("/latest")
def get_latest_depth(
    symbol: str = Query("BTCUSDT", description="交易对"),
) -> dict[str, Any]:
    """指定交易对最新深度快照。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM depth_snapshots WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
        (symbol,),
    )
    if not rows:
        return {"status": "no_data", "symbol": symbol}
    return {"symbol": symbol, "snapshot": rows[0]}


@router.get("/history")
def get_history(
    symbol: str = Query("BTCUSDT", description="交易对"),
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史深度快照。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM depth_snapshots WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
        (symbol, limit),
    )
    return {"symbol": symbol, "count": len(rows), "history": rows}


@router.get("/imbalance")
def get_imbalance(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """深度不平衡数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT symbol, timestamp, depth_imbalance_1pct, depth_imbalance_5pct "
        "FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "imbalance": rows}


@router.get("/walls")
def get_walls(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """买卖墙数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT symbol, buy_wall_price, buy_wall_size, sell_wall_price, sell_wall_size "
        "FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "walls": rows}


@router.get("/context")
def get_orderbook_depth_context() -> dict[str, Any]:
    """订单簿深度 AI 上下文 bundle。"""
    from data_layer.cex_orderbook_depth.service import CexOrderbookDepthService
    service = CexOrderbookDepthService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
