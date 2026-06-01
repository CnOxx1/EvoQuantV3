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


@router.get("/context")
def get_temporal_context() -> dict[str, Any]:
    """时间模式 AI 上下文 bundle。"""
    from logic_layer.temporal_pattern.service import TemporalPatternService
    service = TemporalPatternService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
