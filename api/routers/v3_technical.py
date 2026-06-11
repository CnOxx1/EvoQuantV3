"""v3 Technical — 技术分析统一入口。

端点：
  /technical/indicators/{symbol}  — 最新指标
  /technical/indicators          — 全资产指标快照
  /technical/klines/{symbol}     — 合并K线
  /technical/history/{symbol}    — 指标历史
  /technical/extremes/{symbol}   — 极值检测
  /technical/divergences/{symbol} — 背离
  /technical/multi-tf/{symbol}   — 多周期
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/technical", tags=["technical"])

_VALID_TF = {"1m", "5m", "15m", "1h", "4h", "1d"}


def _norm(symbol: str) -> str:
    s = symbol.upper().replace("-", "/")
    if not s.endswith("/USDT"):
        s = f"{s}/USDT"
    return s


def _check_tf(tf: str) -> None:
    if tf not in _VALID_TF:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TF}")


@router.get("/indicators/{symbol}")
def get_indicators(
    symbol: str,
    timeframe: str = Query("1h", description="周期"),
    limit: int = Query(1, ge=1, le=500, description="条数"),
) -> dict[str, Any]:
    """指定资产最新技术指标。"""
    normalized = _norm(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    _check_tf(timeframe)
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM technical_indicators "
        "WHERE symbol = ? AND timeframe = ? ORDER BY open_time DESC LIMIT ?",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No indicator data.")
    records = [dict(r) for r in rows]
    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "count": len(records),
        "data": records if limit > 1 else records[0],
    }


@router.get("/indicators")
def get_all_indicators(
    timeframe: str = Query("1h", description="周期"),
) -> dict[str, Any]:
    """全资产最新指标快照。"""
    _check_tf(timeframe)
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ti.* FROM technical_indicators ti "
        "INNER JOIN (SELECT symbol, MAX(open_time) AS max_time "
        "FROM technical_indicators WHERE timeframe = ? GROUP BY symbol) "
        "latest ON ti.symbol = latest.symbol AND ti.open_time = latest.max_time "
        "WHERE ti.timeframe = ? ORDER BY ti.symbol",
        (timeframe, timeframe),
    )
    result = {}
    for row in rows:
        d = dict(row)
        result[d["symbol"]] = d
    return {"timeframe": timeframe, "symbol_count": len(result), "data": result}


@router.get("/klines/{symbol}")
def get_klines(
    symbol: str,
    timeframe: str = Query("1h", description="周期"),
    limit: int = Query(100, ge=1, le=1000, description="K线数量"),
) -> dict[str, Any]:
    """合并 K 线。"""
    normalized = _norm(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    _check_tf(timeframe)
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT open_time, open, high, low, close, volume, exchange_count "
        "FROM merged_klines WHERE symbol = ? AND timeframe = ? "
        "ORDER BY open_time DESC LIMIT ?",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "timeframe": timeframe, "count": len(records), "klines": records}


@router.get("/history/{symbol}")
def get_history(
    symbol: str,
    timeframe: str = Query("1h", description="周期"),
    limit: int = Query(50, ge=1, le=500, description="条数"),
) -> dict[str, Any]:
    """技术指标历史序列。"""
    normalized = _norm(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    _check_tf(timeframe)
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT open_time, rsi_14, macd, macd_signal, bb_upper, bb_lower, atr_14 "
        "FROM technical_indicators WHERE symbol = ? AND timeframe = ? "
        "ORDER BY open_time DESC LIMIT ?",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No history data.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "timeframe": timeframe, "count": len(records), "history": records}


@router.get("/extremes/{symbol}")
def get_extremes(
    symbol: str,
    timeframe: str = Query("1h", description="周期"),
) -> dict[str, Any]:
    """极值检测（RSI/BB 突破）。"""
    normalized = _norm(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    _check_tf(timeframe)
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM technical_indicators "
        "WHERE symbol = ? AND timeframe = ? ORDER BY open_time DESC LIMIT 1",
        (normalized, timeframe),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No data.")
    d = dict(row)
    extremes = []
    if d.get("rsi_14") and d["rsi_14"] > 70:
        extremes.append({"indicator": "rsi_14", "value": d["rsi_14"], "signal": "overbought"})
    if d.get("rsi_14") and d["rsi_14"] < 30:
        extremes.append({"indicator": "rsi_14", "value": d["rsi_14"], "signal": "oversold"})
    if d.get("close") and d.get("bb_upper") and d["close"] > d["bb_upper"]:
        extremes.append({"indicator": "bb_upper", "value": d["close"], "signal": "above_upper_band"})
    if d.get("close") and d.get("bb_lower") and d["close"] < d["bb_lower"]:
        extremes.append({"indicator": "bb_lower", "value": d["close"], "signal": "below_lower_band"})
    return {"symbol": normalized, "timeframe": timeframe, "extremes": extremes, "latest": d}


@router.get("/multi-tf/{symbol}")
def get_multi_timeframe(
    symbol: str,
) -> dict[str, Any]:
    """多周期指标对比。"""
    normalized = _norm(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    db = get_analytics_db()
    result = {}
    for tf in ("15m", "1h", "4h", "1d"):
        row = db.fetch_one(
            "SELECT open_time, close, rsi_14, macd, macd_signal, bb_upper, bb_lower, atr_14 "
            "FROM technical_indicators "
            "WHERE symbol = ? AND timeframe = ? ORDER BY open_time DESC LIMIT 1",
            (normalized, tf),
        )
        if row:
            result[tf] = dict(row)
    if not result:
        raise HTTPException(status_code=404, detail="No multi-tf data.")
    return {"symbol": normalized, "timeframes": result}
