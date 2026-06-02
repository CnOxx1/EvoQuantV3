"""Stablecoin Pulse 路由 — 稳定币脉冲状态端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/stablecoin-pulse", tags=["stablecoin-pulse"])


@router.get("/state")
def get_current_pulse_state() -> dict[str, Any]:
    """当前稳定币脉冲状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM stablecoin_pulse_states ORDER BY ts DESC LIMIT 1",
    )
    if not row:
        return {"status": "no_data", "state": None}
    return {"state": dict(row)}


@router.get("/history")
def get_pulse_history(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """稳定币脉冲历史状态。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM stablecoin_pulse_states "
        "WHERE ts >= datetime('now', '-' || ? || ' days') "
        "ORDER BY ts DESC LIMIT ?",
        (days, limit),
    )
    return {"days": days, "count": len(rows), "history": rows}


@router.get("/signal")
def get_expansion_signal() -> dict[str, Any]:
    """稳定币扩张/收缩信号。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT ts, signal, net_mint_7d, expansion_rate "
        "FROM stablecoin_pulse_states ORDER BY ts DESC LIMIT 1",
    )
    if not row:
        return {"status": "no_data", "signal": None}
    return {"signal": dict(row)}


@router.get("/correlation")
def get_btc_correlation(
    days: int = Query(30, ge=1, le=90, description="统计天数"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """稳定币脉冲与 BTC 相关性数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, btc_correlation, net_mint_7d, btc_return_7d "
        "FROM stablecoin_pulse_states "
        "WHERE ts >= datetime('now', '-' || ? || ' days') "
        "ORDER BY ts DESC LIMIT ?",
        (days, limit),
    )
    return {"days": days, "count": len(rows), "correlation": rows}


@router.get("/context")
def get_stablecoin_pulse_context() -> dict[str, Any]:
    """稳定币脉冲 AI 上下文 bundle。"""
    from logic_layer.stablecoin_pulse.service import StablecoinPulseService
    service = StablecoinPulseService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
