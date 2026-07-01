"""Smart Money Conviction 路由 — 聪明钱信念端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/smart-money-conviction", tags=["smart-money-conviction"])


@router.get("/state")
def get_conviction_state() -> dict[str, Any]:
    """当前聪明钱信念状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM smart_money_conviction_states ORDER BY ts DESC LIMIT 1",
    )
    return {"state": row}


@router.get("/history")
def get_conviction_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史聪明钱信念数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM smart_money_conviction_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/divergence")
def get_retail_divergence(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """散户分歧数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM smart_money_conviction_states "
        "WHERE retail_divergence IS NOT NULL "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "divergence": rows}


@router.get("/direction")
def get_direction_signal() -> dict[str, Any]:
    """当前方向信号。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM smart_money_conviction_states ORDER BY ts DESC LIMIT 1",
    )
    return {"direction": row}


@router.get("/context")
def get_smart_money_conviction_context() -> dict[str, Any]:
    """聪明钱信念 AI 上下文 bundle。"""
    from logic_layer.smart_money_conviction.service import SmartMoneyConvictionService
    service = SmartMoneyConvictionService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
