"""Liquidity Regime 路由 — 流动性 regime 分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/liquidity-regime", tags=["liquidity-regime"])


@router.get("/state")
def get_current_state() -> dict[str, Any]:
    """当前流动性 regime 状态。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM liquidity_regime_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"state": rows[0]}


@router.get("/history")
def get_state_history(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """流动性 regime 历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM liquidity_regime_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/score")
def get_liquidity_score() -> dict[str, Any]:
    """当前流动性评分。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, liquidity_score, regime FROM liquidity_regime_states "
        "ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"score": rows[0]}


@router.get("/spread")
def get_defi_cefi_spread(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """DeFi-CeFi 利差历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, defi_cefi_spread, regime FROM liquidity_regime_states "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "spreads": rows}


@router.get("/context")
def get_liquidity_regime_context() -> dict[str, Any]:
    """流动性 regime AI 上下文 bundle。"""
    from logic_layer.liquidity_regime.service import LiquidityRegimeService
    service = LiquidityRegimeService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
