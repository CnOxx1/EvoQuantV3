"""Holder Behavior 路由 — 持有者行为分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/holder-behavior", tags=["holder-behavior"])


@router.get("/state")
def get_current_state() -> dict[str, Any]:
    """当前持有者行为状态。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM holder_behavior_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"state": rows[0]}


@router.get("/history")
def get_state_history(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """持有者行为状态历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM holder_behavior_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/phase")
def get_market_phase() -> dict[str, Any]:
    """当前市场阶段判断。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, market_phase, mvrv_percentile, sopr_state "
        "FROM holder_behavior_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"phase": rows[0]}


@router.get("/signals")
def get_behavior_signals(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """持有者行为信号序列。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, sopr_state, supply_shock_prob, market_phase "
        "FROM holder_behavior_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "signals": rows}


@router.get("/context")
def get_holder_behavior_context() -> dict[str, Any]:
    """持有者行为 AI 上下文 bundle。"""
    from logic_layer.holder_behavior_analysis.service import HolderBehaviorService
    service = HolderBehaviorService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
