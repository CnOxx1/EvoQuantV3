"""Temporal Pattern 路由 — 时间模式识别端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _normalize_symbol

router = APIRouter(prefix="/temporal-pattern", tags=["temporal-pattern"])


@router.get("/patterns")
def get_temporal_patterns(
    symbol: str = Query("BTC/USDT", description="交易对"),
    pattern_type: str | None = Query(None, description="模式类型过滤"),
) -> dict[str, Any]:
    """最新时间模式检测结果。"""
    db = get_analytics_db()
    sql = "SELECT * FROM temporal_patterns WHERE symbol = ?"
    params: list[Any] = [_normalize_symbol(symbol)]
    if pattern_type:
        sql += " AND pattern_type = ?"
        params.append(pattern_type)
    sql += " ORDER BY ts DESC LIMIT 20"
    rows = db.fetch_all(sql, tuple(params))
    return {"symbol": symbol, "count": len(rows), "patterns": rows}


@router.get("/seasonal/{symbol}")
def get_seasonal_profile(symbol: str) -> dict[str, Any]:
    """获取季节性统计画像。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM seasonal_profiles WHERE symbol = ? "
        "ORDER BY dimension, hour_of_day, day_of_week",
        (_normalize_symbol(symbol),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No seasonal data for {symbol}")
    return {"symbol": symbol, "count": len(rows), "profiles": rows}


@router.get("/hourly/{symbol}")
def get_hourly_pattern(symbol: str) -> dict[str, Any]:
    """小时级季节性效应。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM seasonal_profiles WHERE symbol = ? AND dimension = 'hourly' "
        "ORDER BY hour_of_day",
        (_normalize_symbol(symbol),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No hourly pattern for {symbol}")
    return {"symbol": symbol, "count": len(rows), "hourly_pattern": rows}


@router.get("/day-of-week/{symbol}")
def get_day_of_week_pattern(symbol: str) -> dict[str, Any]:
    """星期效应。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM seasonal_profiles WHERE symbol = ? AND dimension = 'day_of_week' "
        "ORDER BY day_of_week",
        (_normalize_symbol(symbol),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No day-of-week data for {symbol}")
    return {"symbol": symbol, "count": len(rows), "day_of_week_pattern": rows}


@router.get("/halving-cycle")
def get_halving_cycle() -> dict[str, Any]:
    """减半周期相位。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM halving_cycle_phase ORDER BY ts DESC LIMIT 1",
    )
    if not row:
        raise HTTPException(status_code=404, detail="No halving cycle data")
    return dict(row)


@router.get("/funding-cycle/{symbol}")
def get_funding_cycle(
    symbol: str,
    limit: int = Query(24, ge=1, le=168, description="返回条数"),
) -> dict[str, Any]:
    """Funding 8h 周期模式。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM funding_cycle_patterns WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT ?",
        (_normalize_symbol(symbol), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No funding cycle data for {symbol}")
    return {"symbol": symbol, "count": len(rows), "funding_cycles": rows}


@router.get("/context")
def get_temporal_context() -> dict[str, Any]:
    """时间模式 AI 上下文 bundle。"""
    from logic_layer.temporal_pattern.service import TemporalPatternService
    service = TemporalPatternService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
