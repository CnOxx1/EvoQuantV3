"""Depth Regime 路由 — 深度流动性状态端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/depth-regime", tags=["depth-regime"])


@router.get("/state")
def get_depth_regime_state() -> dict[str, Any]:
    """当前深度流动性状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM depth_regime_states ORDER BY ts DESC LIMIT 1",
    )
    return {"state": row}


@router.get("/history")
def get_depth_regime_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史深度状态数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM depth_regime_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/slippage")
def get_slippage_estimates(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """滑点估算数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT symbol, ts, slippage_10k, slippage_100k, slippage_1m "
        "FROM depth_regime_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "slippage": rows}


@router.get("/walls")
def get_wall_strength(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """买卖挂单墙强度数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT symbol, ts, bid_wall_strength, ask_wall_strength "
        "FROM depth_regime_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "walls": rows}


@router.get("/context")
def get_depth_regime_context() -> dict[str, Any]:
    """深度流动性 AI 上下文 bundle。"""
    from logic_layer.depth_regime.service import DepthRegimeService
    service = DepthRegimeService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
