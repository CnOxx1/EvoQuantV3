"""Orderflow Micro 路由 — 微观订单流分析端点（基于 orderflow_data 模块）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/orderflow-micro", tags=["orderflow-micro"])


@router.get("/pressure/{symbol}")
def get_pressure(
    symbol: str,
    exchange: str | None = Query(None, description="交易所过滤"),
    limit: int = Query(24, ge=1, le=200, description="最近 N 条聚合记录"),
) -> dict[str, Any]:
    """买卖压力分析（CVD + aggression_ratio）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    sql = ("SELECT * FROM orderflow_agg WHERE symbol = ?"
           + (" AND exchange = ?" if exchange else "")
           + " ORDER BY ts DESC LIMIT ?")
    params: tuple = (normalized, exchange, limit) if exchange else (normalized, limit)
    rows = db.fetch_all(sql, params)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No orderflow data for {symbol}")
    latest = rows[0]
    return {
        "symbol": normalized,
        "exchange": exchange or "all",
        "latest": {
            "ts": latest.get("ts"),
            "cvd": _safe_float(latest.get("cvd")),
            "buy_volume": _safe_float(latest.get("buy_volume")),
            "sell_volume": _safe_float(latest.get("sell_volume")),
            "aggression_ratio": _safe_float(latest.get("aggression_ratio")),
            "trade_count": latest.get("trade_count"),
        },
        "history_count": len(rows),
        "history": rows,
    }


@router.get("/large-trades/{symbol}")
def get_large_trades(
    symbol: str,
    limit: int = Query(24, ge=1, le=200, description="最近 N 条聚合记录"),
) -> dict[str, Any]:
    """大单统计。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT ts, exchange, large_buy_count, large_sell_count, "
        "large_buy_volume, large_sell_volume, vwap FROM orderflow_agg "
        "WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
        (normalized, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No large trade data for {symbol}")
    return {"symbol": normalized, "count": len(rows), "large_trades": rows}


@router.get("/cross-exchange/{symbol}")
def get_cross_exchange(symbol: str) -> dict[str, Any]:
    """跨交易所订单流对比。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT exchange, cvd, buy_volume, sell_volume, aggression_ratio, "
        "trade_count, ts FROM orderflow_agg WHERE symbol = ? "
        "AND ts = (SELECT MAX(ts) FROM orderflow_agg AS sub "
        "WHERE sub.symbol = ? AND sub.exchange = orderflow_agg.exchange)",
        (normalized, normalized),
    )
    return {"symbol": normalized, "exchanges": rows}


@router.get("/summary")
def get_orderflow_summary() -> dict[str, Any]:
    """全市场订单流概览。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT symbol, SUM(buy_volume) as total_buy, SUM(sell_volume) as total_sell, "
        "SUM(cvd) as total_cvd, SUM(large_buy_count) as large_buys, "
        "SUM(large_sell_count) as large_sells FROM orderflow_agg "
        "WHERE ts >= datetime('now', '-1 hour') GROUP BY symbol "
        "ORDER BY total_cvd DESC",
    )
    return {"period": "1h", "count": len(rows), "assets": rows}
