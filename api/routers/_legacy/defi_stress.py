"""DeFi Stress 路由 — DeFi 压力指数端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/defi-stress", tags=["defi-stress"])


@router.get("/state")
def get_defi_stress_state() -> dict[str, Any]:
    """当前 DeFi 压力状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM defi_stress_states ORDER BY ts DESC LIMIT 1",
    )
    return {"state": row}


@router.get("/history")
def get_defi_stress_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史 DeFi 压力数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_stress_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/cascade")
def get_cascade_probability(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """级联清算概率数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, cascade_prob_5pct, cascade_prob_10pct, cascade_prob_20pct "
        "FROM defi_stress_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "cascade": rows}


@router.get("/protocols")
def get_protocol_risk_ranking(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """协议风险排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_stress_states "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "protocols": rows}


@router.get("/context")
def get_defi_stress_context() -> dict[str, Any]:
    """DeFi 压力 AI 上下文 bundle。"""
    from logic_layer.defi_stress.service import DefiStressService
    service = DefiStressService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
