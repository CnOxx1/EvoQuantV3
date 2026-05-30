"""Technical 路由 — 技术指标与合并 K 线查询。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/technical", tags=["technical"])

_VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/indicators/{symbol}")
def get_indicators(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期，如 1m/5m/15m/1h/4h/1d"),
    limit: int = Query(1, ge=1, le=500, description="返回最近 N 条记录"),
) -> dict[str, Any]:
    """返回指定资产的最新技术指标（RSI、MACD、布林带、ATR 等）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TIMEFRAMES}")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT * FROM technical_indicators
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC
           LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No indicator data found.")

    records = [dict(r) for r in rows]
    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "count": len(records),
        "data": records if limit > 1 else records[0],
    }


@router.get("/indicators")
def get_all_indicators(
    timeframe: str = Query("1h", description="K 线周期"),
) -> dict[str, Any]:
    """返回所有资产的最新技术指标快照。"""
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TIMEFRAMES}")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT ti.*
           FROM technical_indicators ti
           INNER JOIN (
               SELECT symbol, MAX(open_time) AS max_time
               FROM technical_indicators
               WHERE timeframe = ?
               GROUP BY symbol
           ) latest ON ti.symbol = latest.symbol AND ti.open_time = latest.max_time
           WHERE ti.timeframe = ?
           ORDER BY ti.symbol""",
        (timeframe, timeframe),
    )

    result: dict[str, Any] = {}
    for row in rows:
        d = dict(row)
        result[d["symbol"]] = d

    return {
        "timeframe": timeframe,
        "symbol_count": len(result),
        "data": result,
    }


@router.get("/klines/{symbol}")
def get_klines(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(100, ge=1, le=1000, description="返回最近 N 根 K 线"),
) -> dict[str, Any]:
    """返回指定资产的合并 K 线（多交易所聚合后的标准 OHLCV）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TIMEFRAMES}")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT open_time, open, high, low, close, volume, quote_volume,
                  exchange_count, source_exchanges
           FROM merged_klines
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC
           LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "count": len(records),
        "klines": records,
    }
