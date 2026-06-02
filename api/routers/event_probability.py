"""Event Probability 路由 — 事件概率分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/event-probability", tags=["event-probability"])


@router.get("/events")
def get_tracked_events(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """追踪的高影响事件。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM event_probability_states "
        "WHERE ts = (SELECT MAX(ts) FROM event_probability_states) "
        "ORDER BY impact_score DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "events": rows}


@router.get("/jumps")
def get_probability_jumps(
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
) -> dict[str, Any]:
    """概率跳变事件。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM event_probability_states WHERE is_jump = 1 "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "jumps": rows}


@router.get("/by-asset")
def get_events_by_asset(
    asset: str = Query("BTC", description="资产符号"),
) -> dict[str, Any]:
    """影响指定资产的事件。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM event_probability_states "
        "WHERE affected_assets LIKE ? "
        "AND ts = (SELECT MAX(ts) FROM event_probability_states) "
        "ORDER BY impact_score DESC",
        (f"%{asset.upper()}%",),
    )
    return {"asset": asset.upper(), "count": len(rows), "events": rows}


@router.get("/history/{market_id}")
def get_event_history(
    market_id: str,
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """单事件概率历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, probability, prob_change_24h, impact_score "
        "FROM event_probability_states WHERE market_id = ? "
        "ORDER BY ts DESC LIMIT ?",
        (market_id, limit),
    )
    return {"market_id": market_id, "count": len(rows), "history": rows}


@router.get("/context")
def get_event_probability_context() -> dict[str, Any]:
    """事件概率 AI 上下文 bundle。"""
    from logic_layer.event_probability.service import EventProbabilityService
    service = EventProbabilityService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
