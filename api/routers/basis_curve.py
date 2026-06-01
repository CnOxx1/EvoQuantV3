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


@router.get("/context")
def get_basis_curve_context() -> dict[str, Any]:
    """期限结构 AI 上下文 bundle。"""
    from data_layer.perpetual_basis_curve.service import PerpetualBasisCurveService
    service = PerpetualBasisCurveService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
