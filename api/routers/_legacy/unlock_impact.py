"""Unlock Impact 路由 — 解锁冲击评估端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/unlock-impact", tags=["unlock-impact"])


@router.get("/state")
def get_unlock_impact_state() -> dict[str, Any]:
    """当前解锁冲击状态（最新条目）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM unlock_impact_states ORDER BY ts DESC LIMIT 10",
    )
    return {"count": len(rows), "states": rows}


@router.get("/history")
def get_unlock_impact_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史解锁冲击数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM unlock_impact_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/high-impact")
def get_high_impact_tokens(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """高冲击 token 排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM unlock_impact_states ORDER BY impact_score DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "high_impact": rows}


@router.get("/by-token")
def get_impact_by_token(
    token: str = Query(..., description="Token 名称"),
) -> dict[str, Any]:
    """指定 token 的解锁冲击数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM unlock_impact_states WHERE token = ? ORDER BY ts DESC",
        (token,),
    )
    return {"token": token, "count": len(rows), "impacts": rows}


@router.get("/context")
def get_unlock_impact_context() -> dict[str, Any]:
    """解锁冲击 AI 上下文 bundle。"""
    from logic_layer.unlock_impact.service import UnlockImpactService
    service = UnlockImpactService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
