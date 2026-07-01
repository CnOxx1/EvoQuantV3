"""Technical Deep 路由 — 技术指标深度分析（时序提取、极端检测、背离、体制分类、扫描）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import (
    _detect_divergence,
    _linear_slope,
    _normalize_symbol,
    _percentile_rank,
    _safe_float,
    _zscore,
)
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/technical-deep", tags=["technical-deep"])

_VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


@router.get("/available-fields")
def get_available_fields() -> dict[str, Any]:
    """列出 technical_indicators 表所有可用指标字段。"""
    db = get_analytics_db()
    rows = db.fetch_all("PRAGMA table_info(technical_indicators)", ())
    if not rows:
        raise HTTPException(status_code=404, detail="Table not found.")

    meta_cols = {"symbol", "timeframe", "open_time", "id"}
    fields = [
        {"name": r["name"], "type": r["type"]}
        for r in rows
        if r["name"] not in meta_cols
    ]
    return {"field_count": len(fields), "fields": fields}


@router.get("/indicator/{symbol}")
def get_single_indicator(
    symbol: str,
    indicator: str = Query(..., description="指标字段名，如 rsi_14, macd_line"),
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(100, ge=1, le=1000, description="返回最近 N 条"),
) -> dict[str, Any]:
    """单指标时序提取。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TIMEFRAMES}")

    db = get_analytics_db()
    # Validate field exists
    cols = db.fetch_all("PRAGMA table_info(technical_indicators)", ())
    col_names = {r["name"] for r in cols}
    if indicator not in col_names:
        raise HTTPException(status_code=400, detail=f"Unknown indicator '{indicator}'. Use /available-fields.")

    rows = db.fetch_all(
        f"SELECT open_time, {indicator} FROM technical_indicators "
        f"WHERE symbol = ? AND timeframe = ? ORDER BY open_time DESC LIMIT ?",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data found.")

    records = [{"open_time": r["open_time"], "value": _safe_float(r[indicator])} for r in rows]
    records.reverse()
    return {"symbol": normalized, "indicator": indicator, "timeframe": timeframe, "count": len(records), "data": records}


@router.get("/multi/{symbol}")
def get_multi_indicators(
    symbol: str,
    indicators: str = Query(..., description="逗号分隔的指标字段名，如 rsi_14,macd_line,bb_upper"),
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(100, ge=1, le=1000, description="返回最近 N 条"),
) -> dict[str, Any]:
    """多指标批量提取。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TIMEFRAMES}")

    db = get_analytics_db()
    cols = db.fetch_all("PRAGMA table_info(technical_indicators)", ())
    col_names = {r["name"] for r in cols}
    requested = [i.strip() for i in indicators.split(",") if i.strip()]
    invalid = [i for i in requested if i not in col_names]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown indicators: {invalid}")

    select_cols = ", ".join(requested)
    rows = db.fetch_all(
        f"SELECT open_time, {select_cols} FROM technical_indicators "
        f"WHERE symbol = ? AND timeframe = ? ORDER BY open_time DESC LIMIT ?",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "indicators": requested, "timeframe": timeframe, "count": len(records), "data": records}


@router.get("/extremes/{symbol}")
def get_extremes(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(200, ge=10, le=1000, description="回溯条数"),
) -> dict[str, Any]:
    """极端读数检测（超买/超卖/BB突破）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Valid: {_VALID_TIMEFRAMES}")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT open_time, close, rsi_14, macd_hist, bb_upper, bb_lower,
                  stoch_k, stoch_d, cci_20
           FROM technical_indicators
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data found.")

    signals = []
    latest = dict(rows[0])
    rsi = _safe_float(latest.get("rsi_14"))
    close = _safe_float(latest.get("close"))
    bb_upper = _safe_float(latest.get("bb_upper"))
    bb_lower = _safe_float(latest.get("bb_lower"))
    stoch_k = _safe_float(latest.get("stoch_k"))
    cci = _safe_float(latest.get("cci_20"))

    if rsi is not None:
        if rsi > 70:
            signals.append({"indicator": "rsi_14", "condition": "overbought", "value": rsi})
        elif rsi < 30:
            signals.append({"indicator": "rsi_14", "condition": "oversold", "value": rsi})
    if close is not None and bb_upper is not None and close > bb_upper:
        signals.append({"indicator": "bb_upper", "condition": "breakout_above", "value": close})
    if close is not None and bb_lower is not None and close < bb_lower:
        signals.append({"indicator": "bb_lower", "condition": "breakout_below", "value": close})
    if stoch_k is not None:
        if stoch_k > 80:
            signals.append({"indicator": "stoch_k", "condition": "overbought", "value": stoch_k})
        elif stoch_k < 20:
            signals.append({"indicator": "stoch_k", "condition": "oversold", "value": stoch_k})
    if cci is not None:
        if cci > 100:
            signals.append({"indicator": "cci_20", "condition": "overbought", "value": cci})
        elif cci < -100:
            signals.append({"indicator": "cci_20", "condition": "oversold", "value": cci})

    # Percentile context
    rsi_values = [_safe_float(r["rsi_14"]) for r in rows if _safe_float(r["rsi_14"]) is not None]
    rsi_pct = _percentile_rank(rsi_values, rsi) if rsi and rsi_values else None

    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "lookback": len(rows),
        "extreme_count": len(signals),
        "signals": signals,
        "context": {"rsi_percentile": rsi_pct, "latest_rsi": rsi, "latest_close": close},
    }


@router.get("/divergences/{symbol}")
def get_divergences(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(100, ge=20, le=500, description="回溯条数"),
) -> dict[str, Any]:
    """价格 vs 指标背离检测。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe.")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT open_time, close, rsi_14, macd_hist, obv
           FROM technical_indicators
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data found.")

    rows_asc = list(reversed(rows))
    prices = [_safe_float(r["close"]) or 0 for r in rows_asc]
    rsi_vals = [_safe_float(r["rsi_14"]) or 50 for r in rows_asc]
    macd_vals = [_safe_float(r["macd_hist"]) or 0 for r in rows_asc]
    obv_vals = [_safe_float(r["obv"]) or 0 for r in rows_asc]

    divergences = {
        "price_vs_rsi": _detect_divergence(prices, rsi_vals),
        "price_vs_macd": _detect_divergence(prices, macd_vals),
        "price_vs_obv": _detect_divergence(prices, obv_vals),
    }

    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "lookback": len(rows),
        "divergences": divergences,
    }


@router.get("/regime/{symbol}")
def get_regime(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(100, ge=20, le=500, description="回溯条数"),
) -> dict[str, Any]:
    """技术体制分类（趋势/震荡/高波动）基于 ADX + ATR% + BB width。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe.")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT open_time, close, adx_14, atr_14, bb_upper, bb_lower, bb_middle
           FROM technical_indicators
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data found.")

    latest = dict(rows[0])
    adx = _safe_float(latest.get("adx_14"))
    atr = _safe_float(latest.get("atr_14"))
    close = _safe_float(latest.get("close"))
    bb_upper = _safe_float(latest.get("bb_upper"))
    bb_lower = _safe_float(latest.get("bb_lower"))

    # BB width as % of price
    bb_width_pct = None
    if bb_upper and bb_lower and close and close > 0:
        bb_width_pct = (bb_upper - bb_lower) / close * 100

    # ATR as % of price
    atr_pct = (atr / close * 100) if atr and close and close > 0 else None

    # Regime classification
    if adx is not None and adx > 25:
        regime = "trending"
    elif bb_width_pct is not None and bb_width_pct > 8:
        regime = "high_volatility"
    elif adx is not None and adx < 20:
        regime = "ranging"
    else:
        regime = "transitional"

    # Trend of ADX (strengthening or weakening)
    adx_values = [_safe_float(r["adx_14"]) for r in rows if _safe_float(r["adx_14"]) is not None]
    adx_slope = _linear_slope(list(reversed(adx_values[-20:]))) if len(adx_values) >= 5 else 0

    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "regime": regime,
        "metrics": {
            "adx": adx,
            "atr_pct": round(atr_pct, 4) if atr_pct else None,
            "bb_width_pct": round(bb_width_pct, 4) if bb_width_pct else None,
            "adx_slope": round(adx_slope, 6),
        },
        "interpretation": {
            "trending": adx is not None and adx > 25,
            "ranging": adx is not None and adx < 20,
            "high_volatility": bb_width_pct is not None and bb_width_pct > 8,
            "trend_strengthening": adx_slope > 0,
        },
    }


@router.get("/scanner")
def scan_indicators(
    indicator: str = Query(..., description="指标字段名"),
    condition: str = Query(..., description="条件: gt, lt, cross_above, cross_below"),
    threshold: float = Query(..., description="阈值"),
    timeframe: str = Query("1h", description="K 线周期"),
) -> dict[str, Any]:
    """全市场指标条件扫描。"""
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe.")
    if condition not in ("gt", "lt", "cross_above", "cross_below"):
        raise HTTPException(status_code=400, detail="condition must be gt/lt/cross_above/cross_below")

    db = get_analytics_db()
    cols = db.fetch_all("PRAGMA table_info(technical_indicators)", ())
    col_names = {r["name"] for r in cols}
    if indicator not in col_names:
        raise HTTPException(status_code=400, detail=f"Unknown indicator '{indicator}'.")

    if condition == "gt":
        rows = db.fetch_all(
            f"""SELECT ti.symbol, ti.open_time, ti.{indicator} AS value
                FROM technical_indicators ti
                INNER JOIN (
                    SELECT symbol, MAX(open_time) AS max_time
                    FROM technical_indicators WHERE timeframe = ?
                    GROUP BY symbol
                ) latest ON ti.symbol = latest.symbol AND ti.open_time = latest.max_time
                WHERE ti.timeframe = ? AND ti.{indicator} > ?
                ORDER BY ti.{indicator} DESC""",
            (timeframe, timeframe, threshold),
        )
    elif condition == "lt":
        rows = db.fetch_all(
            f"""SELECT ti.symbol, ti.open_time, ti.{indicator} AS value
                FROM technical_indicators ti
                INNER JOIN (
                    SELECT symbol, MAX(open_time) AS max_time
                    FROM technical_indicators WHERE timeframe = ?
                    GROUP BY symbol
                ) latest ON ti.symbol = latest.symbol AND ti.open_time = latest.max_time
                WHERE ti.timeframe = ? AND ti.{indicator} < ?
                ORDER BY ti.{indicator} ASC""",
            (timeframe, timeframe, threshold),
        )
    else:
        # cross_above / cross_below: need last 2 bars
        results = []
        for sym in TARGET_SYMBOLS:
            last2 = db.fetch_all(
                f"""SELECT {indicator} FROM technical_indicators
                    WHERE symbol = ? AND timeframe = ?
                    ORDER BY open_time DESC LIMIT 2""",
                (sym, timeframe),
            )
            if len(last2) < 2:
                continue
            curr = _safe_float(last2[0][indicator])
            prev = _safe_float(last2[1][indicator])
            if curr is None or prev is None:
                continue
            if condition == "cross_above" and prev <= threshold < curr:
                results.append({"symbol": sym, "value": curr, "prev_value": prev})
            elif condition == "cross_below" and prev >= threshold > curr:
                results.append({"symbol": sym, "value": curr, "prev_value": prev})
        return {
            "indicator": indicator,
            "condition": condition,
            "threshold": threshold,
            "timeframe": timeframe,
            "match_count": len(results),
            "matches": results,
        }

    records = [dict(r) for r in rows]
    return {
        "indicator": indicator,
        "condition": condition,
        "threshold": threshold,
        "timeframe": timeframe,
        "match_count": len(records),
        "matches": records,
    }
