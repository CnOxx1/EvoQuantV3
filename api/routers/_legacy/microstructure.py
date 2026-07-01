"""Microstructure 路由 — 市场微观结构分析（波动率、成交量分布、价差、时段统计、跳空、流动性）。"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/microstructure", tags=["microstructure"])

_VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


@router.get("/volatility-profile/{symbol}")
def get_volatility_profile(
    symbol: str,
    limit: int = Query(500, ge=50, le=2000, description="回溯 K 线数"),
) -> dict[str, Any]:
    """多时间框架波动率结构。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    result = {}

    for tf in ("1h", "4h", "1d"):
        rows = db.fetch_all(
            """SELECT close FROM klines
               WHERE symbol = ? AND timeframe = ?
               ORDER BY open_time DESC LIMIT ?""",
            (normalized, tf, limit),
        )
        if len(rows) < 2:
            result[tf] = {"daily_vol": None, "annualized_vol": None, "sample_size": 0}
            continue

        prices = [_safe_float(r["close"]) for r in reversed(rows) if _safe_float(r["close"])]
        if len(prices) < 2:
            result[tf] = {"daily_vol": None, "annualized_vol": None, "sample_size": 0}
            continue

        log_rets = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]
        if not log_rets:
            result[tf] = {"daily_vol": None, "annualized_vol": None, "sample_size": 0}
            continue

        mean_r = sum(log_rets) / len(log_rets)
        variance = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
        period_vol = math.sqrt(variance)

        # Scale to daily/annual based on timeframe
        if tf == "1h":
            daily_vol = period_vol * math.sqrt(24)
        elif tf == "4h":
            daily_vol = period_vol * math.sqrt(6)
        else:
            daily_vol = period_vol
        annualized_vol = daily_vol * math.sqrt(365)

        result[tf] = {
            "daily_vol": round(daily_vol, 6),
            "annualized_vol": round(annualized_vol, 6),
            "sample_size": len(log_rets),
        }

    return {"symbol": normalized, "volatility_by_timeframe": result}


@router.get("/volume-profile/{symbol}")
def get_volume_profile(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(200, ge=20, le=2000, description="回溯 K 线数"),
    bins: int = Query(20, ge=5, le=50, description="价格分 bin 数"),
) -> dict[str, Any]:
    """成交量分布（VPOC/VAH/VAL）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT high, low, close, volume FROM klines
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data found.")

    # Build volume profile bins
    all_highs = [_safe_float(r["high"]) for r in rows if _safe_float(r["high"])]
    all_lows = [_safe_float(r["low"]) for r in rows if _safe_float(r["low"])]
    if not all_highs or not all_lows:
        raise HTTPException(status_code=404, detail="Insufficient price data.")

    price_min = min(all_lows)
    price_max = max(all_highs)
    bin_size = (price_max - price_min) / bins if price_max > price_min else 1

    volume_bins = [0.0] * bins
    for r in rows:
        h = _safe_float(r["high"]) or 0
        l = _safe_float(r["low"]) or 0
        v = _safe_float(r["volume"]) or 0
        mid = (h + l) / 2
        idx = int((mid - price_min) / bin_size) if bin_size > 0 else 0
        idx = min(idx, bins - 1)
        volume_bins[idx] += v

    # VPOC = price of max volume bin
    max_vol_idx = volume_bins.index(max(volume_bins))
    vpoc = price_min + (max_vol_idx + 0.5) * bin_size

    # Value Area (70% of volume)
    total_vol = sum(volume_bins)
    target_vol = total_vol * 0.7
    sorted_indices = sorted(range(bins), key=lambda i: volume_bins[i], reverse=True)
    accum = 0.0
    va_indices = []
    for idx in sorted_indices:
        accum += volume_bins[idx]
        va_indices.append(idx)
        if accum >= target_vol:
            break

    vah = price_min + (max(va_indices) + 1) * bin_size
    val_ = price_min + min(va_indices) * bin_size

    profile = [
        {"price_low": round(price_min + i * bin_size, 4),
         "price_high": round(price_min + (i + 1) * bin_size, 4),
         "volume": round(volume_bins[i], 2)}
        for i in range(bins)
    ]

    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "bars_analyzed": len(rows),
        "vpoc": round(vpoc, 4),
        "value_area_high": round(vah, 4),
        "value_area_low": round(val_, 4),
        "profile": profile,
    }


@router.get("/spread-history/{symbol}")
def get_spread_history(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000, description="返回最近 N 条"),
) -> dict[str, Any]:
    """历史买卖价差演变。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, best_bid, best_ask, mid_price, spread_bps
           FROM orderbook_snapshots
           WHERE symbol = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (normalized, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No orderbook data found.")

    records = [dict(r) for r in rows]
    records.reverse()
    spreads = [_safe_float(r.get("spread_bps")) or 0 for r in records]
    avg_spread = sum(spreads) / len(spreads) if spreads else 0

    return {
        "symbol": normalized,
        "count": len(records),
        "avg_spread_bps": round(avg_spread, 4),
        "min_spread_bps": round(min(spreads), 4) if spreads else None,
        "max_spread_bps": round(max(spreads), 4) if spreads else None,
        "data": records,
    }


@router.get("/session-stats/{symbol}")
def get_session_stats(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(500, ge=50, le=2000, description="回溯 K 线数"),
) -> dict[str, Any]:
    """日内时段统计（亚洲/欧洲/美洲）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT open_time, open, high, low, close, volume FROM klines
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data found.")

    # Classify by session: Asia 0-8 UTC, Europe 8-16 UTC, Americas 16-24 UTC
    sessions: dict[str, list] = {"asia": [], "europe": [], "americas": []}
    for r in rows:
        ot = r["open_time"] or ""
        # Extract hour from ISO timestamp or unix
        hour = None
        if "T" in str(ot):
            try:
                hour = int(str(ot).split("T")[1][:2])
            except (IndexError, ValueError):
                pass
        if hour is None:
            continue
        vol = _safe_float(r["volume"]) or 0
        h = _safe_float(r["high"]) or 0
        l = _safe_float(r["low"]) or 0
        rng = (h - l) / l * 100 if l > 0 else 0
        entry = {"volume": vol, "range_pct": rng}
        if 0 <= hour < 8:
            sessions["asia"].append(entry)
        elif 8 <= hour < 16:
            sessions["europe"].append(entry)
        else:
            sessions["americas"].append(entry)

    stats = {}
    for session, entries in sessions.items():
        if not entries:
            stats[session] = {"avg_volume": 0, "avg_range_pct": 0, "bar_count": 0}
            continue
        stats[session] = {
            "avg_volume": round(sum(e["volume"] for e in entries) / len(entries), 2),
            "avg_range_pct": round(sum(e["range_pct"] for e in entries) / len(entries), 4),
            "bar_count": len(entries),
        }

    return {"symbol": normalized, "timeframe": timeframe, "sessions": stats}


@router.get("/gap-analysis/{symbol}")
def get_gap_analysis(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(500, ge=50, le=2000, description="回溯 K 线数"),
    min_gap_pct: float = Query(0.1, description="最小跳空百分比阈值"),
) -> dict[str, Any]:
    """价格跳空分析。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT open_time, open, close FROM klines
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if len(rows) < 2:
        raise HTTPException(status_code=404, detail="Insufficient kline data.")

    rows_asc = list(reversed(rows))
    gaps = []
    for i in range(1, len(rows_asc)):
        prev_close = _safe_float(rows_asc[i - 1]["close"]) or 0
        curr_open = _safe_float(rows_asc[i]["open"]) or 0
        if prev_close == 0:
            continue
        gap_pct = (curr_open - prev_close) / prev_close * 100
        if abs(gap_pct) >= min_gap_pct:
            gaps.append({
                "time": rows_asc[i]["open_time"],
                "prev_close": prev_close,
                "open": curr_open,
                "gap_pct": round(gap_pct, 4),
                "direction": "up" if gap_pct > 0 else "down",
            })

    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "bars_analyzed": len(rows_asc),
        "min_gap_pct": min_gap_pct,
        "gap_count": len(gaps),
        "gaps": gaps[-50:],  # Return last 50 gaps
    }


@router.get("/liquidity-heatmap/{symbol}")
def get_liquidity_heatmap(
    symbol: str,
    timeframe: str = Query("1h", description="K 线周期"),
    limit: int = Query(1000, ge=100, le=5000, description="回溯 K 线数"),
) -> dict[str, Any]:
    """按小时/星期聚合流动性热力图。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT open_time, volume FROM klines
           WHERE symbol = ? AND timeframe = ?
           ORDER BY open_time DESC LIMIT ?""",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data found.")

    # Aggregate by hour of day and day of week
    hour_vol: dict[int, list] = {h: [] for h in range(24)}
    dow_vol: dict[int, list] = {d: [] for d in range(7)}

    for r in rows:
        ot = str(r["open_time"] or "")
        vol = _safe_float(r["volume"]) or 0
        if "T" not in ot:
            continue
        try:
            date_part, time_part = ot.split("T")
            hour = int(time_part[:2])
            # Simple day-of-week from date (ISO format YYYY-MM-DD)
            parts = date_part.split("-")
            if len(parts) == 3:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                # Zeller-like day of week
                import datetime
                dow = datetime.date(y, m, d).weekday()
                dow_vol[dow].append(vol)
            hour_vol[hour].append(vol)
        except (ValueError, IndexError):
            continue

    hour_avg = {
        h: round(sum(vols) / len(vols), 2) if vols else 0
        for h, vols in hour_vol.items()
    }
    dow_avg = {
        d: round(sum(vols) / len(vols), 2) if vols else 0
        for d, vols in dow_vol.items()
    }
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    return {
        "symbol": normalized,
        "timeframe": timeframe,
        "bars_analyzed": len(rows),
        "by_hour": hour_avg,
        "by_day_of_week": {dow_names[d]: v for d, v in dow_avg.items()},
    }
