"""Alpha Decay 路由 — 信号衰减与拥挤度端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/alpha-decay", tags=["alpha-decay"])


@router.get("/decay")
def get_signal_decay(
    signal_name: str | None = Query(None, description="按信号名过滤"),
) -> dict[str, Any]:
    """信号衰减分析结果。"""
    db = get_analytics_db()
    if signal_name:
        rows = db.fetch_all(
            "SELECT * FROM signal_decay WHERE signal_name = ? "
            "ORDER BY ts DESC LIMIT 20",
            (signal_name,),
        )
    else:
        rows = db.fetch_all(
            "SELECT * FROM signal_decay ORDER BY ts DESC LIMIT 50",
        )
    return {"count": len(rows), "signal_decay": rows}


@router.get("/crowding")
def get_crowding_index() -> dict[str, Any]:
    """最新信号拥挤度指数。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM crowding_index ORDER BY ts DESC LIMIT 1",
    )
    if not row:
        raise HTTPException(status_code=404, detail="No crowding data available")
    return dict(row)


@router.get("/context")
def get_alpha_decay_context() -> dict[str, Any]:
    """信号衰减 AI 上下文 bundle。"""
    from logic_layer.alpha_decay.service import AlphaDecayService
    service = AlphaDecayService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
