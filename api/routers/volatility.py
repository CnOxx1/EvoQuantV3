"""Volatility 路由 — 波动率预测端点。"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/volatility", tags=["volatility"])

_LAMBDA = 0.94  # RiskMetrics EWMA decay


@router.get("/forecast/{symbol}")
def get_volatility_forecast(symbol: str) -> dict[str, Any]:
    """EWMA 波动率预测 + regime 分类。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT close FROM merged_klines WHERE symbol = ? "
        "ORDER BY open_time DESC LIMIT 31",
        (normalized,),
    )
    if len(rows) < 10:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
    closes = [_safe_float(r.get("close")) or 0 for r in reversed(rows)]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    if not returns:
        raise HTTPException(status_code=404, detail="Cannot compute returns")
    variance = returns[0] ** 2
    for r in returns[1:]:
        variance = _LAMBDA * variance + (1 - _LAMBDA) * r ** 2
    ewma_daily = math.sqrt(variance)
    ewma_annual = ewma_daily * math.sqrt(365)
    realized_vol = (sum(r ** 2 for r in returns) / len(returns)) ** 0.5 * math.sqrt(365)
    if ewma_annual < 0.3:
        regime = "low"
    elif ewma_annual < 0.6:
        regime = "normal"
    elif ewma_annual < 1.0:
        regime = "high"
    else:
        regime = "extreme"
    return {
        "symbol": normalized,
        "ewma_daily_vol": round(ewma_daily, 6),
        "ewma_annual_vol": round(ewma_annual, 4),
        "realized_vol_annual": round(realized_vol, 4),
        "vol_regime": regime,
        "data_source": "merged_klines",
    }


@router.get("/cone/{symbol}")
def get_volatility_cone(symbol: str) -> dict[str, Any]:
    """波动率锥（历史分位）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT close FROM merged_klines WHERE symbol = ? ORDER BY open_time DESC LIMIT 180",
        (normalized,),
    )
    if len(rows) < 30:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
    closes = [_safe_float(r.get("close")) or 0 for r in reversed(rows)]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    windows = [7, 14, 30, 60, 90]
    cone = {}
    for w in windows:
        if len(returns) < w:
            continue
        vols = []
        for i in range(len(returns) - w + 1):
            chunk = returns[i:i + w]
            vol = (sum(r ** 2 for r in chunk) / len(chunk)) ** 0.5 * math.sqrt(365)
            vols.append(vol)
        vols.sort()
        cone[f"{w}d"] = {
            "min": round(vols[0], 4),
            "p25": round(vols[len(vols) // 4], 4),
            "median": round(vols[len(vols) // 2], 4),
            "p75": round(vols[3 * len(vols) // 4], 4),
            "max": round(vols[-1], 4),
            "current": round(vols[-1], 4),
        }
    return {"symbol": normalized, "cone": cone, "data_source": "merged_klines"}


@router.get("/ranking")
def get_volatility_ranking() -> dict[str, Any]:
    """全资产波动率排名。"""
    db = get_market_db()
    # v4.5.0: 单次批量查询所有符号替代 N+1 逐符号查询
    placeholders = ",".join("?" * len(TARGET_SYMBOLS))
    all_rows = db.fetch_all(
        f"SELECT symbol, close FROM merged_klines "
        f"WHERE symbol IN ({placeholders}) "
        f"ORDER BY symbol, open_time DESC",
        tuple(TARGET_SYMBOLS),
    )
    # 按 symbol 分组，每个最多取 31 根
    from collections import defaultdict
    series: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for row in all_rows:
        sym = row["symbol"]
        if counts[sym] >= 31:
            continue
        val = _safe_float(row.get("close"))
        if val:
            series[sym].append(val)
            counts[sym] += 1

    results = []
    for sym in TARGET_SYMBOLS:
        closes = list(reversed(series.get(sym, [])))
        if len(closes) < 10:
            continue
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
        if not returns:
            continue
        vol = (sum(r ** 2 for r in returns) / len(returns)) ** 0.5 * math.sqrt(365)
        results.append({"symbol": sym, "annual_vol": round(vol, 4)})
    results.sort(key=lambda x: x["annual_vol"], reverse=True)
    return {"count": len(results), "ranking": results}


@router.get("/rv-iv-spread/{symbol}")
def get_rv_iv_spread(symbol: str) -> dict[str, Any]:
    """RV-IV 价差。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT close FROM merged_klines WHERE symbol = ? ORDER BY open_time DESC LIMIT 31",
        (normalized,),
    )
    if len(rows) < 10:
        raise HTTPException(status_code=404, detail=f"Insufficient price data for {symbol}")
    closes = [_safe_float(r.get("close")) or 0 for r in reversed(rows)]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    rv = (sum(r ** 2 for r in returns) / len(returns)) ** 0.5 * math.sqrt(365) if returns else 0
    iv_row = db.fetch_one(
        "SELECT value FROM options_timeseries WHERE entity_key = ? "
        "AND factor_id = 'atm_iv_30d' ORDER BY observation_time DESC LIMIT 1",
        (normalized,),
    )
    iv = _safe_float(iv_row.get("value")) if iv_row else None
    spread = round(rv - iv, 4) if iv is not None else None
    signal = None
    if spread is not None:
        signal = "iv_cheap" if spread > 0.05 else ("iv_rich" if spread < -0.05 else "fair")
    return {
        "symbol": normalized,
        "realized_vol_30d": round(rv, 4),
        "implied_vol_30d": round(iv, 4) if iv is not None else None,
        "rv_iv_spread": spread,
        "signal": signal,
        "data_source": "merged_klines + options_timeseries",
    }
