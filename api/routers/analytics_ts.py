"""Analytics 路由 — 时序分析（价格变化、波动率趋势、均值回归、动量历史等）。"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_exchange_db
from api.routers._helpers import (
    _compute_volatility,
    _normalize_symbol,
    _risk_level,
    _safe_float,
)
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/price-change/{symbol}")
def price_change(
    symbol: str,
    periods: str = Query("1,7,14,30", description="逗号分隔的天数列表"),
) -> dict[str, Any]:
    """N 日价格变化率对比。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT close, open_time FROM merged_klines
           WHERE symbol = ? AND timeframe = '1d'
           ORDER BY open_time DESC LIMIT 31""",
        (normalized,),
    )
    if len(rows) < 2:
        raise HTTPException(status_code=404, detail="Insufficient kline data.")

    prices = [float(r["close"]) for r in rows]
    # prices[0] is most recent
    period_list = [int(p.strip()) for p in periods.split(",") if p.strip().isdigit()]

    changes: dict[str, float | None] = {}
    for p in period_list:
        if p < len(prices) and prices[p] > 0:
            changes[f"{p}d"] = round((prices[0] - prices[p]) / prices[p], 6)
        else:
            changes[f"{p}d"] = None

    return {
        "symbol": normalized,
        "current_price": prices[0],
        "changes": changes,
    }


@router.get("/volatility-trend/{symbol}")
def volatility_trend(
    symbol: str,
    window: int = Query(24, ge=6, le=168, description="滚动窗口（小时）"),
    limit: int = Query(30, ge=1, le=100, description="返回数据点数"),
) -> dict[str, Any]:
    """波动率趋势（滚动计算）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    total_bars = window + limit
    rows = db.fetch_all(
        """SELECT close, open_time FROM merged_klines
           WHERE symbol = ? AND timeframe = '1h'
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, total_bars),
    )
    if len(rows) < window + 1:
        raise HTTPException(status_code=404, detail="Insufficient data for volatility trend.")

    prices = [float(r["close"]) for r in rows]
    times = [r["open_time"] for r in rows]
    prices.reverse()
    times.reverse()

    trend = []
    for i in range(window, len(prices)):
        segment = prices[i - window: i + 1]
        daily_vol, ann_vol = _compute_volatility(segment)
        trend.append({
            "time": times[i],
            "daily_vol": round(daily_vol, 6),
            "annualized_vol": round(ann_vol, 4),
        })

    return {
        "symbol": normalized,
        "window_hours": window,
        "count": len(trend),
        "trend": trend,
    }


@router.get("/mean-reversion/{symbol}")
def mean_reversion(
    symbol: str,
    window: int = Query(20, ge=5, le=100, description="均值窗口（天）"),
) -> dict[str, Any]:
    """均值回归信号（zscore）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT close, open_time FROM merged_klines
           WHERE symbol = ? AND timeframe = '1d'
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, window + 1),
    )
    if len(rows) < window:
        raise HTTPException(status_code=404, detail="Insufficient data for mean reversion.")

    prices = [float(r["close"]) for r in rows]
    prices.reverse()

    mean_price = sum(prices) / len(prices)
    std_price = math.sqrt(sum((p - mean_price) ** 2 for p in prices) / len(prices))
    current = prices[-1]
    zscore = (current - mean_price) / std_price if std_price > 0 else 0

    if zscore < -2:
        signal = "strong_buy"
    elif zscore < -1:
        signal = "buy"
    elif zscore > 2:
        signal = "strong_sell"
    elif zscore > 1:
        signal = "sell"
    else:
        signal = "neutral"

    return {
        "symbol": normalized,
        "window_days": window,
        "current_price": current,
        "mean_price": round(mean_price, 6),
        "std_price": round(std_price, 6),
        "zscore": round(zscore, 4),
        "signal": signal,
    }


@router.get("/momentum-history/{symbol}")
def momentum_history(
    symbol: str,
    limit: int = Query(30, ge=1, le=200, description="返回数据点数"),
) -> dict[str, Any]:
    """RSI/MACD 历史 + 交叉事件检测。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT open_time, rsi_14, macd, macd_signal, macd_histogram
           FROM technical_indicators
           WHERE symbol = ? AND timeframe = '1h'
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No technical indicator data found.")

    records = [dict(r) for r in rows]
    records.reverse()

    # Detect crossover events
    crossovers = []
    for i in range(1, len(records)):
        prev_macd = _safe_float(records[i - 1].get("macd"))
        prev_sig = _safe_float(records[i - 1].get("macd_signal"))
        curr_macd = _safe_float(records[i].get("macd"))
        curr_sig = _safe_float(records[i].get("macd_signal"))
        if None in (prev_macd, prev_sig, curr_macd, curr_sig):
            continue
        if prev_macd <= prev_sig and curr_macd > curr_sig:
            crossovers.append({"time": records[i]["open_time"], "type": "bullish_cross"})
        elif prev_macd >= prev_sig and curr_macd < curr_sig:
            crossovers.append({"time": records[i]["open_time"], "type": "bearish_cross"})

    return {
        "symbol": normalized,
        "count": len(records),
        "crossovers": crossovers,
        "history": records,
    }


@router.get("/funding-trend/{symbol}")
def funding_trend(
    symbol: str,
    limit: int = Query(30, ge=1, le=200, description="返回数据点数"),
) -> dict[str, Any]:
    """资金费率趋势分析。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT funding_rate, timestamp FROM funding_rates
           WHERE symbol = ? AND exchange = 'binance'
           ORDER BY timestamp DESC LIMIT ?""",
        (normalized, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No funding rate history found.")

    records = [{"time": r["timestamp"], "rate": _safe_float(r["funding_rate"])} for r in rows]
    records.reverse()

    rates = [r["rate"] for r in records if r["rate"] is not None]
    avg_rate = sum(rates) / len(rates) if rates else 0
    max_rate = max(rates) if rates else 0
    min_rate = min(rates) if rates else 0

    # Trend direction
    if len(rates) >= 3:
        recent = sum(rates[-3:]) / 3
        older = sum(rates[:3]) / 3
        trend = "rising" if recent > older + 0.0001 else "falling" if recent < older - 0.0001 else "flat"
    else:
        trend = "insufficient_data"

    return {
        "symbol": normalized,
        "count": len(records),
        "avg_rate": round(avg_rate, 6),
        "max_rate": round(max_rate, 6),
        "min_rate": round(min_rate, 6),
        "trend": trend,
        "history": records,
    }


@router.get("/multi-timeframe/{symbol}")
def multi_timeframe(
    symbol: str,
) -> dict[str, Any]:
    """多周期技术信号对齐分析。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    timeframes = ["5m", "15m", "1h", "4h", "1d"]
    signals: dict[str, dict[str, Any]] = {}

    for tf in timeframes:
        row = db.fetch_one(
            """SELECT rsi_14, macd, macd_signal, bb_upper, bb_lower, close
               FROM technical_indicators
               WHERE symbol = ? AND timeframe = ?
               ORDER BY open_time DESC LIMIT 1""",
            (normalized, tf),
        )
        if not row:
            signals[tf] = {"available": False}
            continue

        rsi = _safe_float(row["rsi_14"])
        macd = _safe_float(row["macd"])
        macd_sig = _safe_float(row["macd_signal"])
        bb_upper = _safe_float(row["bb_upper"])
        bb_lower = _safe_float(row["bb_lower"])
        close = _safe_float(row["close"])

        # Determine signal per timeframe
        if rsi is not None:
            if rsi > 70:
                rsi_signal = "overbought"
            elif rsi < 30:
                rsi_signal = "oversold"
            else:
                rsi_signal = "neutral"
        else:
            rsi_signal = "unknown"

        macd_bullish = macd > macd_sig if macd is not None and macd_sig is not None else None

        bb_signal = "neutral"
        if close and bb_upper and bb_lower:
            if close > bb_upper:
                bb_signal = "above_upper"
            elif close < bb_lower:
                bb_signal = "below_lower"

        signals[tf] = {
            "available": True,
            "rsi_14": round(rsi, 2) if rsi else None,
            "rsi_signal": rsi_signal,
            "macd_bullish": macd_bullish,
            "bb_signal": bb_signal,
        }

    # Alignment score
    bullish_count = sum(
        1 for s in signals.values()
        if s.get("available") and s.get("rsi_signal") == "oversold"
    )
    bearish_count = sum(
        1 for s in signals.values()
        if s.get("available") and s.get("rsi_signal") == "overbought"
    )
    available_count = sum(1 for s in signals.values() if s.get("available"))
    alignment = "neutral"
    if available_count > 0:
        if bullish_count >= available_count * 0.6:
            alignment = "bullish_aligned"
        elif bearish_count >= available_count * 0.6:
            alignment = "bearish_aligned"

    return {
        "symbol": normalized,
        "alignment": alignment,
        "timeframes": signals,
    }
