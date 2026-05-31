"""Derivatives 路由 — 衍生品复合信号端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db
from api.routers._helpers import (
    _detect_divergence,
    _linear_slope,
    _normalize_symbol,
    _percentile_rank,
    _safe_float,
    _zscore,
)
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/derivatives", tags=["derivatives"])


@router.get("/health/{symbol}")
def derivatives_health(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
) -> dict[str, Any]:
    """统一衍生品健康评分（funding+basis+positioning+OI+liquidation）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    scores = {}
    details = {}

    # Funding
    funding = db.fetch_one(
        "SELECT funding_rate, mark_price FROM latest_funding_rates "
        "WHERE symbol = ? AND exchange = ?", (normalized, exchange),
    )
    if funding:
        rate = _safe_float(funding["funding_rate"]) or 0.0
        ann = rate * 3 * 365
        scores["funding"] = max(0, min(100, 50 + ann * 10))
        details["funding"] = {"rate": rate, "annualized": round(ann, 4)}

    # OI
    oi = db.fetch_one(
        "SELECT open_interest_usd, open_interest_change_24h FROM latest_open_interest_snapshots "
        "WHERE symbol = ? AND exchange = ?", (normalized, exchange),
    )
    if oi:
        change = _safe_float(oi["open_interest_change_24h"]) or 0.0
        scores["oi"] = max(0, min(100, 50 + change * 200))
        details["oi"] = {
            "usd": _safe_float(oi["open_interest_usd"]),
            "change_24h": change,
        }

    # Positioning
    pos = db.fetch_one(
        "SELECT long_short_ratio, long_ratio, short_ratio FROM latest_positioning_snapshots "
        "WHERE symbol = ? AND exchange = ?", (normalized, exchange),
    )
    if pos:
        lsr = _safe_float(pos["long_short_ratio"]) or 1.0
        scores["positioning"] = max(0, min(100, 50 + (lsr - 1.0) * 30))
        details["positioning"] = {
            "long_short_ratio": lsr,
            "long_ratio": _safe_float(pos["long_ratio"]),
            "short_ratio": _safe_float(pos["short_ratio"]),
        }

    # Liquidation
    liq = db.fetch_one(
        "SELECT total_liquidation_notional, long_liquidation_notional, "
        "short_liquidation_notional FROM latest_liquidation_bars "
        "WHERE symbol = ? AND exchange = ?", (normalized, exchange),
    )
    if liq:
        total_liq = _safe_float(liq["total_liquidation_notional"]) or 0.0
        scores["liquidation"] = max(0, min(100, 100 - min(total_liq / 10000, 50)))
        details["liquidation"] = {
            "total": total_liq,
            "long": _safe_float(liq["long_liquidation_notional"]),
            "short": _safe_float(liq["short_liquidation_notional"]),
        }

    # Composite score
    if scores:
        composite = sum(scores.values()) / len(scores)
    else:
        composite = 50.0
    health_label = "healthy" if composite > 65 else "stressed" if composite < 35 else "neutral"

    return {
        "symbol": normalized, "exchange": exchange,
        "composite_score": round(composite, 1), "health_label": health_label,
        "component_scores": scores, "details": details,
    }


@router.get("/leverage-map")
def leverage_map() -> dict[str, Any]:
    """全市场杠杆热力图（哪些资产最拥挤）。"""
    db = get_exchange_db()
    oi_rows = db.fetch_all(
        "SELECT symbol, exchange, open_interest_usd, open_interest_change_24h "
        "FROM latest_open_interest_snapshots",
    )
    pos_rows = db.fetch_all(
        "SELECT symbol, exchange, long_short_ratio FROM latest_positioning_snapshots",
    )
    funding_rows = db.fetch_all(
        "SELECT symbol, exchange, funding_rate FROM latest_funding_rates",
    )

    assets: dict[str, dict] = {}
    for r in oi_rows:
        sym = r["symbol"]
        assets.setdefault(sym, {"symbol": sym})
        assets[sym]["oi_usd"] = _safe_float(r["open_interest_usd"])
        assets[sym]["oi_change_24h"] = _safe_float(r["open_interest_change_24h"])

    for r in pos_rows:
        sym = r["symbol"]
        if sym in assets:
            assets[sym]["long_short_ratio"] = _safe_float(r["long_short_ratio"])

    for r in funding_rows:
        sym = r["symbol"]
        if sym in assets:
            assets[sym]["funding_rate"] = _safe_float(r["funding_rate"])

    # Compute crowding score
    for a in assets.values():
        lsr = a.get("long_short_ratio") or 1.0
        fr = abs(a.get("funding_rate") or 0.0)
        oi_chg = abs(a.get("oi_change_24h") or 0.0)
        a["crowding_score"] = round(abs(lsr - 1.0) * 30 + fr * 5000 + oi_chg * 100, 2)

    ranked = sorted(assets.values(), key=lambda x: x.get("crowding_score", 0), reverse=True)
    return {"count": len(ranked), "assets": ranked[:30]}


@router.get("/funding-curve/{symbol}")
def funding_curve(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    limit: int = Query(168, ge=1, le=500, description="数据点数"),
) -> dict[str, Any]:
    """资金费率历史 + 体制检测 + 均值回归信号。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT timestamp, funding_rate, mark_price FROM funding_rates "
        "WHERE symbol = ? AND exchange = ? ORDER BY timestamp DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    if not rows:
        return {"symbol": normalized, "exchange": exchange, "data": [], "regime": None}

    rows.reverse()
    rates = [_safe_float(r["funding_rate"]) or 0.0 for r in rows]
    avg_rate = sum(rates) / len(rates)
    current_rate = rates[-1]
    z = _zscore(rates, current_rate)
    slope = _linear_slope(rates)

    # Regime detection
    if avg_rate > 0.0003:
        regime = "contango_strong"
    elif avg_rate > 0.0001:
        regime = "contango_mild"
    elif avg_rate < -0.0003:
        regime = "backwardation_strong"
    elif avg_rate < -0.0001:
        regime = "backwardation_mild"
    else:
        regime = "neutral"

    # Mean reversion signal
    if abs(z) > 2.0:
        mr_signal = "short_funding" if z > 0 else "long_funding"
    else:
        mr_signal = "none"

    data = [{"time": r["timestamp"], "rate": _safe_float(r["funding_rate"]),
             "mark_price": _safe_float(r["mark_price"])} for r in rows]
    return {
        "symbol": normalized, "exchange": exchange, "count": len(data),
        "current_rate": current_rate, "avg_rate": round(avg_rate, 6),
        "zscore": round(z, 2), "slope": round(slope, 8),
        "regime": regime, "mean_reversion_signal": mr_signal, "data": data,
    }


@router.get("/oi-divergence/{symbol}")
def oi_divergence(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    limit: int = Query(100, ge=1, le=500, description="数据点数"),
) -> dict[str, Any]:
    """OI vs 价格背离（挤压风险检测）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    oi_rows = db.fetch_all(
        "SELECT timestamp, open_interest_usd FROM open_interest_snapshots "
        "WHERE symbol = ? AND exchange = ? ORDER BY timestamp DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    klines = db.fetch_all(
        "SELECT open_time, close FROM klines WHERE symbol = ? AND exchange = ? "
        "AND timeframe = '1h' ORDER BY open_time DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    if not oi_rows or not klines:
        return {"symbol": normalized, "exchange": exchange, "divergence": None, "data": []}

    oi_rows.reverse()
    klines.reverse()
    oi_values = [_safe_float(r["open_interest_usd"]) or 0.0 for r in oi_rows]
    prices = [_safe_float(r["close"]) or 0.0 for r in klines]

    divergence = _detect_divergence(prices, oi_values)
    oi_slope = _linear_slope(oi_values)
    price_slope = _linear_slope(prices)

    # Squeeze risk: OI rising + price flat = potential squeeze
    squeeze_risk = "high" if oi_slope > 0 and abs(price_slope) < 0.01 else \
                   "medium" if oi_slope > 0 else "low"

    data = [{"time": r["timestamp"], "oi_usd": _safe_float(r["open_interest_usd"])}
            for r in oi_rows[-20:]]
    return {
        "symbol": normalized, "exchange": exchange,
        "divergence": divergence, "squeeze_risk": squeeze_risk,
        "oi_slope": round(oi_slope, 4), "price_slope": round(price_slope, 6),
        "data": data,
    }


@router.get("/liquidation-levels/{symbol}")
def liquidation_levels(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    limit: int = Query(100, ge=1, le=500, description="数据点数"),
) -> dict[str, Any]:
    """清算集中区域估算。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    liq_rows = db.fetch_all(
        "SELECT open_time, long_liquidation_notional, short_liquidation_notional, "
        "long_liquidation_count, short_liquidation_count, total_liquidation_notional, "
        "max_single_liquidation_notional FROM liquidation_bars "
        "WHERE symbol = ? AND exchange = ? ORDER BY open_time DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    pos_rows = db.fetch_all(
        "SELECT timestamp, long_ratio, short_ratio, long_short_ratio "
        "FROM positioning_snapshots WHERE symbol = ? AND exchange = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (normalized, exchange, 20),
    )
    if not liq_rows:
        return {"symbol": normalized, "exchange": exchange, "data": [], "concentration": None}

    total_long_liq = sum(_safe_float(r["long_liquidation_notional"]) or 0.0 for r in liq_rows)
    total_short_liq = sum(_safe_float(r["short_liquidation_notional"]) or 0.0 for r in liq_rows)
    dominant_side = "long" if total_long_liq > total_short_liq else "short"

    # Positioning context
    pos_context = None
    if pos_rows:
        latest_pos = pos_rows[0]
        pos_context = {
            "long_ratio": _safe_float(latest_pos["long_ratio"]),
            "short_ratio": _safe_float(latest_pos["short_ratio"]),
            "long_short_ratio": _safe_float(latest_pos["long_short_ratio"]),
        }

    data = [
        {
            "time": r["open_time"],
            "long_liq": _safe_float(r["long_liquidation_notional"]),
            "short_liq": _safe_float(r["short_liquidation_notional"]),
            "total": _safe_float(r["total_liquidation_notional"]),
            "max_single": _safe_float(r["max_single_liquidation_notional"]),
        }
        for r in liq_rows[:50]
    ]
    return {
        "symbol": normalized, "exchange": exchange,
        "total_long_liquidated": round(total_long_liq, 2),
        "total_short_liquidated": round(total_short_liq, 2),
        "dominant_liquidation_side": dominant_side,
        "positioning": pos_context, "data": data,
    }


@router.get("/positioning-extremes")
def positioning_extremes(
    threshold: float = Query(1.5, ge=1.0, le=5.0, description="极端阈值（long_short_ratio 偏离）"),
) -> dict[str, Any]:
    """全市场持仓极端筛选（拥挤交易=反转风险）。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT symbol, exchange, long_short_ratio, long_ratio, short_ratio, "
        "top_trader_long_ratio, top_trader_short_ratio "
        "FROM latest_positioning_snapshots",
    )
    if not rows:
        return {"threshold": threshold, "extremes": []}

    extremes = []
    for r in rows:
        lsr = _safe_float(r["long_short_ratio"]) or 1.0
        if abs(lsr - 1.0) >= (threshold - 1.0):
            side = "extreme_long" if lsr > threshold else "extreme_short" if lsr < (1.0 / threshold) else "moderate"
            extremes.append({
                "symbol": r["symbol"],
                "exchange": r["exchange"],
                "long_short_ratio": lsr,
                "long_ratio": _safe_float(r["long_ratio"]),
                "short_ratio": _safe_float(r["short_ratio"]),
                "top_trader_long": _safe_float(r["top_trader_long_ratio"]),
                "top_trader_short": _safe_float(r["top_trader_short_ratio"]),
                "extreme_side": side,
                "reversal_risk": round(abs(lsr - 1.0) / threshold * 100, 1),
            })

    extremes.sort(key=lambda x: x["reversal_risk"], reverse=True)
    return {"threshold": threshold, "count": len(extremes), "extremes": extremes[:30]}


@router.get("/funding-prediction/{symbol}")
def funding_prediction(symbol: str) -> dict[str, Any]:
    """下期资金费率预测（均值回归 + 动量模型）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT funding_rate, timestamp FROM latest_funding_rates "
        "WHERE symbol = ? ORDER BY timestamp DESC LIMIT 21",
        (normalized,),
    )
    if len(rows) < 5:
        raise HTTPException(status_code=404, detail=f"Insufficient funding data for {symbol}")
    rates = [_safe_float(r.get("funding_rate")) or 0 for r in reversed(rows)]
    mean_rate = sum(rates) / len(rates)
    current = rates[-1]
    momentum = (rates[-1] - rates[-3]) / 3 if len(rates) >= 3 else 0
    alpha = 0.3
    predicted = alpha * mean_rate + (1 - alpha) * (current + momentum)
    zscore = _zscore(rates, current)
    if abs(zscore) > 2:
        direction_bias = "long_crowded" if zscore > 0 else "short_crowded"
    elif abs(zscore) > 1:
        direction_bias = "slight_long" if zscore > 0 else "slight_short"
    else:
        direction_bias = "neutral"
    return {
        "symbol": normalized,
        "current_rate": round(current, 6),
        "predicted_next": round(predicted, 6),
        "mean_rate_21": round(mean_rate, 6),
        "zscore": round(zscore, 3),
        "direction_bias": direction_bias,
        "cumulative_7d": round(sum(rates[-21:]) if len(rates) >= 21 else sum(rates), 6),
        "data_source": "latest_funding_rates",
    }


@router.get("/basis-signal/{symbol}")
def basis_signal(symbol: str) -> dict[str, Any]:
    """基差均值回归信号。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT spot_price, futures_price, timestamp FROM latest_funding_rates "
        "WHERE symbol = ? AND spot_price IS NOT NULL AND futures_price IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT 30",
        (normalized,),
    )
    if len(rows) < 5:
        raise HTTPException(status_code=404, detail=f"Insufficient basis data for {symbol}")
    bases = []
    for r in reversed(rows):
        spot = _safe_float(r.get("spot_price")) or 0
        fut = _safe_float(r.get("futures_price")) or 0
        if spot > 0:
            bases.append((fut - spot) / spot)
    if not bases:
        raise HTTPException(status_code=404, detail="Cannot compute basis")
    current_basis = bases[-1]
    mean_basis = sum(bases) / len(bases)
    zscore = _zscore(bases, current_basis)
    regime = "contango" if current_basis > 0.0005 else ("backwardation" if current_basis < -0.0005 else "flat")
    signal_strength = max(-1.0, min(1.0, -zscore * 0.5))
    return {
        "symbol": normalized,
        "current_basis_pct": round(current_basis * 100, 4),
        "mean_basis_pct": round(mean_basis * 100, 4),
        "basis_zscore": round(zscore, 3),
        "regime": regime,
        "mean_reversion_signal": round(signal_strength, 3),
        "data_source": "latest_funding_rates",
    }
