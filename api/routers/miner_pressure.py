"""Miner Pressure 路由 — 矿工压力分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/miner-pressure", tags=["miner-pressure"])


@router.get("/state")
def get_current_state() -> dict[str, Any]:
    """当前矿工压力状态。"""
    db = get_analytics_db()
    # v4.4.0: SELECT * → column projection
    rows = db.fetch_all(
        "SELECT ts, pressure_score, capitulation_index, puell_zone, hash_ribbon "
        "FROM miner_pressure_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"state": rows[0]}


@router.get("/history")
def get_state_history(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """矿工压力状态历史。"""
    db = get_analytics_db()
    # v4.4.0: SELECT * → column projection
    rows = db.fetch_all(
        "SELECT ts, pressure_score, capitulation_index, puell_zone, hash_ribbon "
        "FROM miner_pressure_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/capitulation")
def get_capitulation_index(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """矿工投降指数历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, capitulation_index, puell_zone, pressure_score "
        "FROM miner_pressure_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "capitulation": rows}


@router.get("/halving")
def get_halving_phase() -> dict[str, Any]:
    """减半周期相位信息。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, halving_days_until_next, halving_cycle_pct "
        "FROM miner_pressure_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"halving": rows[0]}


@router.get("/context")
def get_miner_pressure_context() -> dict[str, Any]:
    """矿工压力 AI 上下文 bundle。"""
    # v4.4.0: 使用单例服务替代逐请求实例化
    from api.dependencies import get_miner_pressure_service
    service = get_miner_pressure_service()
    return service.load_latest_context_bundle()
