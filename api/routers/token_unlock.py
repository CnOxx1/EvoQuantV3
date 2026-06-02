"""Token Unlock 路由 — 代币解锁计划与事件分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/token-unlock", tags=["token-unlock"])


@router.get("/upcoming")
def get_upcoming_unlocks(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """即将到来的代币解锁事件（按天数排序）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM upcoming_unlocks ORDER BY days_until ASC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "upcoming": rows}


@router.get("/history")
def get_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史解锁事件。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM unlock_events ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/by-token")
def get_by_token(
    token: str = Query(..., description="代币名称"),
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """指定代币的解锁记录。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM upcoming_unlocks WHERE token = ? ORDER BY days_until ASC LIMIT ?",
        (token, limit),
    )
    return {"token": token, "count": len(rows), "unlocks": rows}


@router.get("/high-impact")
def get_high_impact(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """高影响解锁事件（按流通占比排序）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM upcoming_unlocks ORDER BY pct_of_supply DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "high_impact": rows}


@router.get("/context")
def get_token_unlock_context() -> dict[str, Any]:
    """代币解锁 AI 上下文 bundle。"""
    from data_layer.token_unlock_realtime.service import TokenUnlockRealtimeService
    service = TokenUnlockRealtimeService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
