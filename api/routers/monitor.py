"""Monitor 路由 — 实时监控类端点，提供告警和异常检测。"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_exchange_db
from api.routers._helpers import (
    _compute_volatility,
    _normalize_symbol,
    _percentile_rank,
    _safe_float,
    _zscore,
)
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/monitor", tags=["monitor"])


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


@router.get("/alerts")
def alerts(
    severity: str = Query("all", description="all / high / medium / low"),
) -> dict[str, Any]:
    """主告警端点（汇总所有类型告警，按严重度排序）。"""
    exchange_db = get_exchange_db()
    all_alerts: list[dict] = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(exchange_db, sym)
        volumes = _get_volumes(exchange_db, sym)

        # Price breakout check
        if len(prices) >= 20:
            ma20 = sum(prices[-20:]) / 20
            std20 = math.sqrt(sum((p - ma20) ** 2 for p in prices[-20:]) / 20)
            bb_upper = ma20 + 2 * std20
            bb_lower = ma20 - 2 * std20
            current = prices[-1]
            if current > bb_upper:
                all_alerts.append({
                    "symbol": sym, "type": "price_breakout_up",
                    "severity": "medium", "detail": f"Price above BB upper ({current:.4f} > {bb_upper:.4f})",
                })
            elif current < bb_lower:
                all_alerts.append({
                    "symbol": sym, "type": "price_breakout_down",
                    "severity": "medium", "detail": f"Price below BB lower ({current:.4f} < {bb_lower:.4f})",
                })

        # Volume spike check
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            if volumes[-1] > avg_vol * 3:
                all_alerts.append({
                    "symbol": sym, "type": "volume_spike",
                    "severity": "high", "detail": f"Volume {volumes[-1]:.0f} is {volumes[-1]/avg_vol:.1f}x average",
                })

        # Funding anomaly check
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        rate = _safe_float(funding["funding_rate"]) if funding else None
        if rate and abs(rate) > 0.003:
            all_alerts.append({
                "symbol": sym, "type": "funding_anomaly",
                "severity": "high", "detail": f"Extreme funding rate: {rate:.6f}",
            })
        elif rate and abs(rate) > 0.001:
            all_alerts.append({
                "symbol": sym, "type": "funding_elevated",
                "severity": "low", "detail": f"Elevated funding rate: {rate:.6f}",
            })

    # Filter by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    if severity != "all":
        all_alerts = [a for a in all_alerts if a["severity"] == severity]
    all_alerts.sort(key=lambda x: severity_order.get(x["severity"], 99))

    return {"count": len(all_alerts), "alerts": all_alerts}


@router.get("/price-breakouts")
def price_breakouts() -> dict[str, Any]:
    """价格突破检测（BB/EMA 突破）。"""
    exchange_db = get_exchange_db()
    breakouts = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(exchange_db, sym)
        if len(prices) < 20:
            continue

        current = prices[-1]
        ma20 = sum(prices[-20:]) / 20
        std20 = math.sqrt(sum((p - ma20) ** 2 for p in prices[-20:]) / 20)
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20

        # EMA20 approximation
        ema = prices[0]
        multiplier = 2 / (20 + 1)
        for p in prices[1:]:
            ema = (p - ema) * multiplier + ema

        breakout_type = None
        if current > bb_upper:
            breakout_type = "bb_upper_break"
        elif current < bb_lower:
            breakout_type = "bb_lower_break"
        elif current > ema * 1.03:
            breakout_type = "ema_break_up"
        elif current < ema * 0.97:
            breakout_type = "ema_break_down"

        if breakout_type:
            breakouts.append({
                "symbol": sym,
                "type": breakout_type,
                "current_price": current,
                "bb_upper": round(bb_upper, 4),
                "bb_lower": round(bb_lower, 4),
                "ema20": round(ema, 4),
                "deviation_pct": round((current - ma20) / ma20 * 100, 2),
            })

    breakouts.sort(key=lambda x: abs(x["deviation_pct"]), reverse=True)
    return {"count": len(breakouts), "breakouts": breakouts}


@router.get("/funding-anomalies")
def funding_anomalies(
    threshold: float = Query(0.001, description="异常阈值（绝对值）"),
) -> dict[str, Any]:
    """资金费率异常告警。"""
    exchange_db = get_exchange_db()
    anomalies = []

    for sym in TARGET_SYMBOLS:
        funding = exchange_db.fetch_one(
            "SELECT funding_rate, mark_price, timestamp FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        if not funding:
            continue
        rate = _safe_float(funding["funding_rate"])
        if rate is None or abs(rate) < threshold:
            continue

        anomalies.append({
            "symbol": sym,
            "funding_rate": rate,
            "annualized": round(rate * 3 * 365, 4),
            "direction": "long_paying" if rate > 0 else "short_paying",
            "severity": "high" if abs(rate) > 0.003 else "medium" if abs(rate) > 0.001 else "low",
            "mark_price": _safe_float(funding["mark_price"]),
        })

    anomalies.sort(key=lambda x: abs(x["funding_rate"]), reverse=True)
    return {"count": len(anomalies), "anomalies": anomalies}


@router.get("/liquidation-surges")
def liquidation_surges() -> dict[str, Any]:
    """清算激增检测。"""
    exchange_db = get_exchange_db()
    surges = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(exchange_db, sym)
        if len(prices) < 5:
            continue

        # Detect rapid price moves (proxy for liquidation cascades)
        current = prices[-1]
        price_5h_ago = prices[-5] if len(prices) >= 5 else prices[0]
        move_pct = (current - price_5h_ago) / price_5h_ago * 100

        # Large moves suggest liquidation cascades
        if abs(move_pct) > 5:
            oi_row = exchange_db.fetch_one(
                "SELECT open_interest_contracts FROM latest_open_interest_snapshots WHERE symbol = ? AND exchange = 'binance'",
                (sym,),
            )
            surges.append({
                "symbol": sym,
                "price_move_5h_pct": round(move_pct, 2),
                "direction": "long_liquidations" if move_pct < 0 else "short_liquidations",
                "severity": "high" if abs(move_pct) > 10 else "medium",
                "current_oi": _safe_float(oi_row["open_interest_contracts"]) if oi_row else None,
            })

    surges.sort(key=lambda x: abs(x["price_move_5h_pct"]), reverse=True)
    return {"count": len(surges), "surges": surges}


@router.get("/volume-spikes")
def volume_spikes(
    multiplier: float = Query(2.5, description="相对均值的倍数阈值"),
) -> dict[str, Any]:
    """成交量异常放大检测。"""
    exchange_db = get_exchange_db()
    spikes = []

    for sym in TARGET_SYMBOLS:
        volumes = _get_volumes(exchange_db, sym)
        if len(volumes) < 20:
            continue

        current_vol = volumes[-1]
        avg_vol = sum(volumes[-20:]) / 20
        if avg_vol <= 0:
            continue

        ratio = current_vol / avg_vol
        if ratio >= multiplier:
            prices = _get_prices(exchange_db, sym)
            price_change = None
            if len(prices) >= 2:
                price_change = round((prices[-1] - prices[-2]) / prices[-2] * 100, 2)

            spikes.append({
                "symbol": sym,
                "current_volume": current_vol,
                "avg_volume_20h": round(avg_vol, 2),
                "volume_ratio": round(ratio, 2),
                "price_change_1h": price_change,
                "interpretation": "accumulation" if (price_change and price_change > 0) else "distribution" if (price_change and price_change < 0) else "neutral",
            })

    spikes.sort(key=lambda x: x["volume_ratio"], reverse=True)
    return {"count": len(spikes), "spikes": spikes}


@router.get("/positioning-extremes")
def positioning_extremes() -> dict[str, Any]:
    """持仓极端告警（拥挤度）。"""
    exchange_db = get_exchange_db()
    extremes = []

    # Collect all funding rates to determine percentile
    all_rates: list[float] = []
    sym_data: list[dict] = []
    for sym in TARGET_SYMBOLS:
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        oi_row = exchange_db.fetch_one(
            "SELECT open_interest_contracts FROM latest_open_interest_snapshots WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        rate = _safe_float(funding["funding_rate"]) if funding else None
        oi = _safe_float(oi_row["open_interest_contracts"]) if oi_row else None
        if rate is not None:
            all_rates.append(rate)
        sym_data.append({"symbol": sym, "funding_rate": rate, "open_interest_contracts": oi})

    for item in sym_data:
        rate = item["funding_rate"]
        if rate is None:
            continue
        pct = _percentile_rank(all_rates, rate)
        if pct > 90 or pct < 10:
            extremes.append({
                "symbol": item["symbol"],
                "funding_rate": rate,
                "percentile": round(pct, 1),
                "open_interest_contracts": item["open_interest_contracts"],
                "crowding": "extremely_long" if pct > 90 else "extremely_short",
                "severity": "high" if (pct > 95 or pct < 5) else "medium",
            })

    extremes.sort(key=lambda x: abs(x["percentile"] - 50), reverse=True)
    return {"count": len(extremes), "extremes": extremes}


@router.get("/oi-divergence")
def oi_divergence() -> dict[str, Any]:
    """OI 与价格背离检测。"""
    exchange_db = get_exchange_db()
    divergences = []

    for sym in TARGET_SYMBOLS:
        prices = _get_prices(exchange_db, sym)
        if len(prices) < 10:
            continue

        # Price trend
        price_change = (prices[-1] - prices[-10]) / prices[-10] * 100 if prices[-10] > 0 else 0

        # OI data (current snapshot - compare with funding rate as proxy)
        oi_row = exchange_db.fetch_one(
            "SELECT open_interest_contracts FROM latest_open_interest_snapshots WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        oi = _safe_float(oi_row["open_interest_contracts"]) if oi_row else None
        rate = _safe_float(funding["funding_rate"]) if funding else None

        if oi is None or rate is None:
            continue

        # Divergence: price falling but OI rising (indicated by positive funding)
        # or price rising but OI sentiment bearish (negative funding)
        div_type = None
        if price_change > 3 and rate < -0.0005:
            div_type = "price_up_oi_bearish"
        elif price_change < -3 and rate > 0.0005:
            div_type = "price_down_oi_bullish"

        if div_type:
            divergences.append({
                "symbol": sym,
                "type": div_type,
                "price_change_10h": round(price_change, 2),
                "funding_rate": rate,
                "open_interest_contracts": oi,
                "severity": "high" if abs(price_change) > 5 else "medium",
            })

    divergences.sort(key=lambda x: abs(x["price_change_10h"]), reverse=True)
    return {"count": len(divergences), "divergences": divergences}