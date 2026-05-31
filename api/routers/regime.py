"""Regime 路由 — 市场状态分类端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/regime", tags=["regime"])


@router.get("/current/{symbol}")
def get_current_regime(symbol: str) -> dict[str, Any]:
    """单资产当前 regime 状态。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM regime_states WHERE symbol = ? ORDER BY ts DESC LIMIT 1",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No regime data for {symbol}")
    return {
        "symbol": normalized,
        "ts": row.get("ts"),
        "price_regime": row.get("price_regime"),
        "volatility_regime": row.get("volatility_regime"),
        "correlation_regime": row.get("correlation_regime"),
        "momentum_regime": row.get("momentum_regime"),
        "regime_duration_hours": row.get("regime_duration_hours"),
        "data_source": "regime_detection",
    }


@router.get("/current")
def get_all_regimes() -> dict[str, Any]:
    """全资产当前 regime 快照。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM regime_states WHERE ts = ("
        "SELECT MAX(ts) FROM regime_states AS sub "
        "WHERE sub.symbol = regime_states.symbol) "
        "ORDER BY symbol",
    )
    return {"count": len(rows), "regimes": rows}


@router.get("/history/{symbol}")
def get_regime_history(
    symbol: str,
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """regime 状态历史。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM regime_states WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
        (normalized, limit),
    )
    return {"symbol": normalized, "count": len(rows), "history": rows}


@router.get("/transitions/{symbol}")
def get_regime_transitions(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """regime 转换记录。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM regime_transitions WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
        (normalized, limit),
    )
    return {"symbol": normalized, "count": len(rows), "transitions": rows}
