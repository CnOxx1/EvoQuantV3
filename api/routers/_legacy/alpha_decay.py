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


@router.get("/half-life/{signal_name}")
def get_signal_half_life(
    signal_name: str,
    limit: int = Query(30, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """单信号半衰期历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM signal_decay WHERE signal_name = ? "
        "ORDER BY ts DESC LIMIT ?",
        (signal_name, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No decay data for signal {signal_name}")
    return {"signal_name": signal_name, "count": len(rows), "half_life_history": rows}


@router.get("/signal-ranking")
def get_signal_ranking() -> dict[str, Any]:
    """按衰减速率排名信号。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT signal_name, half_life, decay_rate, ts FROM signal_decay "
        "WHERE ts = (SELECT MAX(ts) FROM signal_decay AS sub "
        "WHERE sub.signal_name = signal_decay.signal_name) "
        "ORDER BY decay_rate DESC",
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/divergence")
def get_signal_divergence() -> dict[str, Any]:
    """跨信号背离检测。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM signal_divergence ORDER BY ts DESC LIMIT 20",
    )
    return {"count": len(rows), "divergences": rows}


@router.get("/crowding-history")
def get_crowding_history(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """拥挤度历史趋势。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM crowding_index ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "crowding_history": rows}


@router.get("/context")
def get_alpha_decay_context() -> dict[str, Any]:
    """信号衰减 AI 上下文 bundle。"""
    from logic_layer.alpha_decay.service import AlphaDecayService
    service = AlphaDecayService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
