"""Strategy 路由 — AI/策略辅助类端点，提供可直接消费的决策信号。"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db
from api.routers._helpers import (
    _compute_volatility,
    _normalize_symbol,
    _percentile_rank,
    _risk_level,
    _safe_float,
    _zscore,
)
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/strategy", tags=["strategy"])


def _get_prices(db, symbol: str, limit: int = 168) -> list[float]:
    """获取价格序列（最新在后）。"""
    rows = db.fetch_all(
        "SELECT close FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT ?",
        (symbol, limit),
    )
    prices = [_safe_float(r["close"]) for r in rows if _safe_float(r["close"])]
    prices.reverse()
    return prices


def _get_volumes(db, symbol: str, limit: int = 168) -> list[float]:
    """获取成交量序列（最新在后）。"""
    rows = db.fetch_all(
        "SELECT volume FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT ?",
        (symbol, limit),
    )
    vols = [_safe_float(r["volume"]) for r in rows if _safe_float(r["volume"])]
    vols.reverse()
    return vols


@router.get("/multi-factor-score/{symbol}")
def multi_factor_score(symbol: str) -> dict[str, Any]:
    """6 维多因子打分（趋势/动量/资金流/情绪/波动/价值）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    analytics_db = get_exchange_db()
    exchange_db = get_exchange_db()
    prices = _get_prices(analytics_db, normalized)
    volumes = _get_volumes(analytics_db, normalized)

    scores = {}

    # Trend score: price vs MA50
    if len(prices) >= 50:
        ma50 = sum(prices[-50:]) / 50
        trend_pct = (prices[-1] - ma50) / ma50 * 100
        scores["trend"] = max(0, min(100, 50 + trend_pct * 5))
    else:
        scores["trend"] = 50.0

    # Momentum score: rate of change 14 periods
    if len(prices) >= 14:
        roc = (prices[-1] - prices[-14]) / prices[-14] * 100
        scores["momentum"] = max(0, min(100, 50 + roc * 3))
    else:
        scores["momentum"] = 50.0

    # Flow score: volume trend
    if len(volumes) >= 20:
        recent_vol = sum(volumes[-5:]) / 5
        avg_vol = sum(volumes[-20:]) / 20
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
        scores["flow"] = max(0, min(100, vol_ratio * 50))
    else:
        scores["flow"] = 50.0

    # Sentiment score: funding rate
    funding = exchange_db.fetch_one(
        "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
        (normalized,),
    )
    rate = _safe_float(funding["funding_rate"]) if funding else 0
    scores["sentiment"] = max(0, min(100, 50 + (rate or 0) * 5000))

    # Volatility score (inverse - low vol = high score)
    daily_vol, annual_vol = _compute_volatility(prices) if prices else (0, 0)
    scores["volatility"] = max(0, min(100, 100 - annual_vol * 30))

    # Value score: distance from 168h high
    if prices:
        high = max(prices)
        drawdown = (prices[-1] - high) / high * 100
        scores["value"] = max(0, min(100, 50 - drawdown * 2))
    else:
        scores["value"] = 50.0

    # Round all scores
    scores = {k: round(v, 1) for k, v in scores.items()}
    composite = round(sum(scores.values()) / len(scores), 1)

    return {
        "symbol": normalized,
        "composite_score": composite,
        "factors": scores,
        "signal": "strong_buy" if composite > 75 else "buy" if composite > 60 else "neutral" if composite > 40 else "sell" if composite > 25 else "strong_sell",
    }


@router.get("/entry-exit/{symbol}")
def entry_exit(symbol: str) -> dict[str, Any]:
    """入场/出场价位建议（基于 BB/ATR/支撑阻力）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    analytics_db = get_exchange_db()
    prices = _get_prices(analytics_db, normalized)

    if len(prices) < 20:
        return {"symbol": normalized, "note": "Insufficient data"}

    current = prices[-1]

    # Bollinger Bands (20, 2)
    ma20 = sum(prices[-20:]) / 20
    std20 = math.sqrt(sum((p - ma20) ** 2 for p in prices[-20:]) / 20)
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20

    # ATR approximation (using close-to-close)
    trs = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    atr14 = sum(trs[-14:]) / 14 if len(trs) >= 14 else sum(trs) / len(trs) if trs else 0

    # Support/Resistance (recent lows/highs)
    recent = prices[-50:] if len(prices) >= 50 else prices
    support = min(recent)
    resistance = max(recent)

    return {
        "symbol": normalized,
        "current_price": current,
        "entry_zones": {
            "aggressive_long": round(bb_lower, 4),
            "conservative_long": round(ma20 - std20, 4),
            "support": round(support, 4),
        },
        "exit_zones": {
            "take_profit_1": round(current + atr14 * 2, 4),
            "take_profit_2": round(bb_upper, 4),
            "resistance": round(resistance, 4),
        },
        "stop_loss": {
            "tight": round(current - atr14 * 1.5, 4),
            "normal": round(current - atr14 * 2.5, 4),
            "wide": round(bb_lower - atr14, 4),
        },
        "indicators": {
            "bb_upper": round(bb_upper, 4),
            "bb_lower": round(bb_lower, 4),
            "ma20": round(ma20, 4),
            "atr14": round(atr14, 4),
        },
    }


@router.get("/regime-strategy")
def regime_strategy() -> dict[str, Any]:
    """当前体制下的策略推荐（趋势跟踪/均值回归/套利等）。"""
    analytics_db = get_exchange_db()
    exchange_db = get_exchange_db()

    # Determine regime from BTC
    prices = _get_prices(analytics_db, "BTC/USDT")
    regime = "unknown"
    if len(prices) >= 50:
        ma20 = sum(prices[-20:]) / 20
        ma50 = sum(prices[-50:]) / 50
        current = prices[-1]
        trend = (current - ma50) / ma50 * 100

        if trend > 10:
            regime = "euphoria"
        elif trend > 3:
            regime = "trending_up"
        elif trend < -10:
            regime = "panic"
        elif trend < -3:
            regime = "trending_down"
        else:
            regime = "ranging"

    # Strategy recommendations per regime
    strategies = {
        "trending_up": ["trend_following", "momentum", "breakout"],
        "trending_down": ["short_momentum", "hedging", "cash"],
        "ranging": ["mean_reversion", "grid_trading", "funding_arb"],
        "euphoria": ["take_profit", "trailing_stop", "reduce_exposure"],
        "panic": ["dca_accumulation", "volatility_selling", "contrarian"],
        "unknown": ["neutral", "small_positions"],
    }

    # Volatility context
    daily_vol, annual_vol = _compute_volatility(prices) if prices else (0, 0)

    return {
        "regime": regime,
        "recommended_strategies": strategies.get(regime, []),
        "volatility_context": {
            "daily_vol": round(daily_vol, 6),
            "annualized_vol": round(annual_vol, 4),
            "vol_regime": "high" if annual_vol > 1.0 else "medium" if annual_vol > 0.5 else "low",
        },
        "position_sizing": "reduce" if annual_vol > 1.5 else "normal" if annual_vol > 0.5 else "increase",
    }


@router.get("/divergence-scanner")
def divergence_scanner(
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """全市场价格-指标背离扫描。"""
    analytics_db = get_exchange_db()
    exchange_db = get_exchange_db()
    divergences = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(analytics_db, sym)
        volumes = _get_volumes(analytics_db, sym)
        if len(prices) < 20 or len(volumes) < 20:
            continue

        # Price making new highs but volume declining = bearish divergence
        recent_price_high = max(prices[-10:])
        prev_price_high = max(prices[-20:-10])
        recent_vol_avg = sum(volumes[-10:]) / 10
        prev_vol_avg = sum(volumes[-20:-10]) / 10

        div_type = None
        if recent_price_high > prev_price_high and recent_vol_avg < prev_vol_avg * 0.8:
            div_type = "bearish_volume"
        elif recent_price_high < prev_price_high and recent_vol_avg > prev_vol_avg * 1.2:
            div_type = "bullish_volume"

        # Funding divergence
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        rate = _safe_float(funding["funding_rate"]) if funding else None
        price_trend = (prices[-1] - prices[-20]) / prices[-20] * 100

        if rate and rate > 0.001 and price_trend < -2:
            div_type = "bearish_funding"
        elif rate and rate < -0.001 and price_trend > 2:
            div_type = "bullish_funding"

        if div_type:
            divergences.append({
                "symbol": sym,
                "type": div_type,
                "price_change_20h": round(price_trend, 2),
                "funding_rate": rate,
                "severity": "high" if abs(price_trend) > 5 else "medium",
            })

    divergences.sort(key=lambda x: abs(x["price_change_20h"]), reverse=True)
    return {"count": len(divergences[:limit]), "divergences": divergences[:limit]}


@router.get("/funding-arb")
def funding_arb(
    min_rate: float = Query(0.0005, description="最低资金费率阈值"),
) -> dict[str, Any]:
    """资金费率套利机会（做空永续+做多现货）。"""
    exchange_db = get_exchange_db()
    opportunities = []

    for sym in TARGET_SYMBOLS:
        funding = exchange_db.fetch_one(
            "SELECT funding_rate, mark_price FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        if not funding:
            continue
        rate = _safe_float(funding["funding_rate"])
        if rate is None or abs(rate) < min_rate:
            continue

        annualized = rate * 3 * 365
        direction = "short_perp_long_spot" if rate > 0 else "long_perp_short_spot"
        opportunities.append({
            "symbol": sym,
            "funding_rate": rate,
            "annualized_yield": round(annualized, 4),
            "direction": direction,
            "mark_price": _safe_float(funding["mark_price"]),
            "risk": "low" if abs(rate) < 0.001 else "medium" if abs(rate) < 0.003 else "high",
        })

    opportunities.sort(key=lambda x: abs(x["funding_rate"]), reverse=True)
    return {"count": len(opportunities), "opportunities": opportunities}


@router.get("/squeeze-detector")
def squeeze_detector() -> dict[str, Any]:
    """空头/多头挤压检测。"""
    analytics_db = get_exchange_db()
    exchange_db = get_exchange_db()
    squeezes = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(analytics_db, sym)
        if len(prices) < 20:
            continue

        # Bollinger Band width (squeeze = narrow bands)
        ma20 = sum(prices[-20:]) / 20
        std20 = math.sqrt(sum((p - ma20) ** 2 for p in prices[-20:]) / 20)
        bb_width = (std20 * 4) / ma20 * 100 if ma20 > 0 else 0

        # Price momentum
        momentum = (prices[-1] - prices[-10]) / prices[-10] * 100 if prices[-10] > 0 else 0

        # Funding rate for positioning
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        rate = _safe_float(funding["funding_rate"]) if funding else 0

        squeeze_type = None
        # Short squeeze: negative funding + price rising + tight bands
        if rate and rate < -0.0005 and momentum > 3 and bb_width < 5:
            squeeze_type = "short_squeeze"
        # Long squeeze: positive funding + price falling + tight bands
        elif rate and rate > 0.0005 and momentum < -3 and bb_width < 5:
            squeeze_type = "long_squeeze"

        if squeeze_type:
            squeezes.append({
                "symbol": sym,
                "type": squeeze_type,
                "momentum_10h": round(momentum, 2),
                "bb_width_pct": round(bb_width, 2),
                "funding_rate": rate,
                "severity": "high" if abs(momentum) > 5 else "medium",
            })

    squeezes.sort(key=lambda x: abs(x["momentum_10h"]), reverse=True)
    return {"count": len(squeezes), "squeezes": squeezes}


@router.get("/mean-reversion-candidates")
def mean_reversion_candidates(
    zscore_threshold: float = Query(2.0, description="z-score 阈值"),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """统计极端延伸资产（z-score 筛选）。"""
    analytics_db = get_exchange_db()
    candidates = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(analytics_db, sym)
        if len(prices) < 50:
            continue

        current = prices[-1]
        z = _zscore(prices[-50:], current)

        if abs(z) >= zscore_threshold:
            ma50 = sum(prices[-50:]) / 50
            candidates.append({
                "symbol": sym,
                "zscore": round(z, 3),
                "current_price": current,
                "mean_price": round(ma50, 4),
                "deviation_pct": round((current - ma50) / ma50 * 100, 2),
                "direction": "oversold" if z < 0 else "overbought",
                "reversion_target": round(ma50, 4),
            })

    candidates.sort(key=lambda x: abs(x["zscore"]), reverse=True)
    return {"count": len(candidates[:limit]), "candidates": candidates[:limit]}


@router.get("/portfolio-signals")
def portfolio_signals(
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """全市场信号排行（多/空候选 + 组合指标）。"""
    analytics_db = get_exchange_db()
    exchange_db = get_exchange_db()
    signals = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(analytics_db, sym)
        if len(prices) < 20:
            continue

        current = prices[-1]
        ma20 = sum(prices[-20:]) / 20
        trend_score = (current - ma20) / ma20 * 100

        # Momentum
        momentum = (prices[-1] - prices[-10]) / prices[-10] * 100 if len(prices) >= 10 and prices[-10] > 0 else 0

        # Funding
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        rate = _safe_float(funding["funding_rate"]) if funding else 0

        # Composite signal
        composite = trend_score * 0.4 + momentum * 0.4 + (rate or 0) * 2000 * 0.2
        direction = "long" if composite > 0 else "short"

        signals.append({
            "symbol": sym,
            "composite_signal": round(composite, 3),
            "direction": direction,
            "trend_score": round(trend_score, 2),
            "momentum_10h": round(momentum, 2),
            "funding_rate": rate,
        })

    # Split into long/short candidates
    signals.sort(key=lambda x: x["composite_signal"], reverse=True)
    long_candidates = [s for s in signals if s["direction"] == "long"][:limit]
    short_candidates = [s for s in signals if s["direction"] == "short"]
    short_candidates.sort(key=lambda x: x["composite_signal"])
    short_candidates = short_candidates[:limit]

    return {
        "long_candidates": long_candidates,
        "short_candidates": short_candidates,
        "total_scanned": len(signals),
    }