"""Perpetual Basis Curve 路由 — 期货期限结构端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/basis-curve", tags=["basis-curve"])


@router.get("/term-structure")
def get_term_structure(
    symbol: str = Query("BTCUSDT", description="合约标的"),
    exchange: str | None = Query(None, description="交易所过滤"),
) -> dict[str, Any]:
    """最新期限结构数据。"""
    db = get_market_db()
    sql = "SELECT * FROM futures_term_structure WHERE symbol = ?"
    params: list[Any] = [symbol.upper()]
    if exchange:
        sql += " AND exchange = ?"
        params.append(exchange.lower())
    sql += " ORDER BY ts DESC LIMIT 20"
    rows = db.fetch_all(sql, tuple(params))
    return {"symbol": symbol.upper(), "count": len(rows), "term_structure": rows}


@router.get("/snapshot")
def get_basis_snapshot(
    symbol: str = Query("BTCUSDT", description="合约标的"),
) -> dict[str, Any]:
    """最新曲线快照（contango/backwardation 判定）。"""
    db = get_market_db()
    row = db.fetch_one(
        "SELECT * FROM basis_curve_snapshot WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT 1",
        (symbol.upper(),),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No basis curve data for {symbol}")
    return dict(row)


@router.get("/roll-yield/{symbol}")
def get_roll_yield(
    symbol: str,
    days: int = Query(7, ge=1, le=30, description="分析天数"),
) -> dict[str, Any]:
    """7 日 roll yield 分析。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM basis_roll_yield WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT ?",
        (symbol.upper(), days),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No roll yield data for {symbol}")
    return {"symbol": symbol.upper(), "days": days, "count": len(rows), "roll_yield": rows}


@router.get("/slope-history/{symbol}")
def get_slope_history(
    symbol: str,
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """曲线斜率历史趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM basis_slope_history WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "slope_history": rows}


@router.get("/exchange-comparison/{symbol}")
def get_exchange_comparison(symbol: str) -> dict[str, Any]:
    """跨交易所 basis 对比。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM basis_exchange_comparison WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT 20",
        (symbol.upper(),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No exchange comparison for {symbol}")
    return {"symbol": symbol.upper(), "count": len(rows), "comparisons": rows}


@router.get("/anomalies")
def get_basis_anomalies(
    symbol: str = Query("BTCUSDT", description="合约标的"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """期限溢价/凸度异常检测。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM basis_anomalies WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "anomalies": rows}


@router.get("/context")
def get_basis_curve_context() -> dict[str, Any]:
    """期限结构 AI 上下文 bundle。"""
    from data_layer.perpetual_basis_curve.service import PerpetualBasisCurveService
    service = PerpetualBasisCurveService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
