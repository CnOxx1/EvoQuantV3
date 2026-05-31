"""Screener 路由 — 筛选排名（涨跌幅、成交量、资金费率、风险、动量、异常、机会）。"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db, get_exchange_db
from api.routers._helpers import (
    _compute_volatility,
    _normalize_symbol,
    _risk_level,
    _safe_float,
)
from config.symbols import SYMBOL_UNIVERSE, TARGET_SYMBOLS

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("/top-movers")
def top_movers(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
    direction: str = Query("both", description="gainers / losers / both"),
) -> dict[str, Any]:
    """涨跌幅排行榜。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, last_price, change_24h, quote_volume_24h
           FROM latest_tickers WHERE exchange = 'binance'
           ORDER BY symbol""",
        (),
    )

    items = []
    for r in rows:
        change = _safe_float(r["change_24h"])
        if change is None:
            continue
        items.append({
            "symbol": r["symbol"],
            "price": _safe_float(r["last_price"]),
            "change_24h": change,
            "volume_24h": _safe_float(r["quote_volume_24h"]),
        })

    if direction == "gainers":
        items.sort(key=lambda x: x["change_24h"], reverse=True)
    elif direction == "losers":
        items.sort(key=lambda x: x["change_24h"])
    else:
        items.sort(key=lambda x: abs(x["change_24h"]), reverse=True)

    return {"direction": direction, "count": min(limit, len(items)), "assets": items[:limit]}


@router.get("/volume-leaders")
def volume_leaders(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
) -> dict[str, Any]:
    """成交量排行。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, last_price, quote_volume_24h, change_24h
           FROM latest_tickers WHERE exchange = 'binance'
           ORDER BY symbol""",
        (),
    )

    items = []
    for r in rows:
        vol = _safe_float(r["quote_volume_24h"])
        if vol is None:
            continue
        items.append({
            "symbol": r["symbol"],
            "price": _safe_float(r["last_price"]),
            "volume_24h": vol,
            "change_24h": _safe_float(r["change_24h"]),
        })

    items.sort(key=lambda x: x["volume_24h"], reverse=True)
    return {"count": min(limit, len(items)), "assets": items[:limit]}


@router.get("/funding-extremes")
def funding_extremes(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
    threshold: float = Query(0.0005, description="异常阈值（绝对值）"),
) -> dict[str, Any]:
    """资金费率异常资产。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, funding_rate, mark_price
           FROM latest_funding_rates ORDER BY symbol""",
        (),
    )

    # Average by symbol
    sym_rates: dict[str, list[float]] = {}
    for r in rows:
        rate = _safe_float(r["funding_rate"])
        if rate is not None:
            sym_rates.setdefault(r["symbol"], []).append(rate)

    items = []
    for sym, rates in sym_rates.items():
        avg = sum(rates) / len(rates)
        if abs(avg) >= threshold:
            items.append({
                "symbol": sym,
                "avg_funding_rate": round(avg, 6),
                "annualized_rate": round(avg * 3 * 365, 4),
                "direction": "long_pays" if avg > 0 else "short_pays",
            })

    items.sort(key=lambda x: abs(x["avg_funding_rate"]), reverse=True)
    return {"threshold": threshold, "count": min(limit, len(items)), "assets": items[:limit]}


@router.get("/risk-ranking")
def risk_ranking(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
) -> dict[str, Any]:
    """风险评分排名（基于年化波动率）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT symbol, close FROM merged_klines
           WHERE timeframe = '1h'
           ORDER BY symbol, open_time DESC""",
        (),
    )

    price_series: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for r in rows:
        sym = r["symbol"]
        if counts.get(sym, 0) >= 168:
            continue
        price_series.setdefault(sym, []).append(float(r["close"]))
        counts[sym] = counts.get(sym, 0) + 1

    items = []
    for sym, prices in price_series.items():
        prices.reverse()
        daily_vol, ann_vol = _compute_volatility(prices)
        if ann_vol == 0:
            continue
        score, level = _risk_level(ann_vol)
        items.append({
            "symbol": sym,
            "risk_score": score,
            "risk_level": level,
            "annualized_vol": round(ann_vol, 4),
            "daily_vol": round(daily_vol, 6),
        })

    items.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"count": min(limit, len(items)), "assets": items[:limit]}


@router.get("/momentum-ranking")
def momentum_ranking(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
) -> dict[str, Any]:
    """动量/RSI 排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT ti.*
           FROM technical_indicators ti
           INNER JOIN (
               SELECT symbol, MAX(open_time) AS max_time
               FROM technical_indicators
               WHERE timeframe = '1h'
               GROUP BY symbol
           ) latest ON ti.symbol = latest.symbol AND ti.open_time = latest.max_time
           WHERE ti.timeframe = '1h'""",
        (),
    )

    items = []
    for r in rows:
        d = dict(r)
        rsi = _safe_float(d.get("rsi_14"))
        macd = _safe_float(d.get("macd"))
        macd_signal = _safe_float(d.get("macd_signal"))
        items.append({
            "symbol": d["symbol"],
            "rsi_14": round(rsi, 2) if rsi is not None else None,
            "macd": round(macd, 6) if macd is not None else None,
            "macd_signal": round(macd_signal, 6) if macd_signal is not None else None,
            "macd_bullish": macd > macd_signal if macd is not None and macd_signal is not None else None,
            "momentum_score": rsi if rsi is not None else 50.0,
        })

    items.sort(key=lambda x: x["momentum_score"], reverse=True)
    return {"count": min(limit, len(items)), "assets": items[:limit]}


@router.get("/anomalies")
def anomalies(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
) -> dict[str, Any]:
    """异常检测（量价异动、OI 突变、清算激增）。"""
    exchange_db = get_exchange_db()
    analytics_db = get_analytics_db()

    # Volume anomaly: compare latest volume to 7d average
    ticker_rows = exchange_db.fetch_all(
        """SELECT symbol, quote_volume_24h, change_24h
           FROM latest_tickers WHERE exchange = 'binance'""",
        (),
    )

    # OI changes
    oi_rows = exchange_db.fetch_all(
        """SELECT symbol, open_interest_value FROM latest_open_interest_snapshots""",
        (),
    )
    oi_by_sym: dict[str, float] = {}
    for r in oi_rows:
        sym = r["symbol"]
        oi_by_sym[sym] = oi_by_sym.get(sym, 0) + (_safe_float(r["open_interest_value"]) or 0)

    # Liquidations
    liq_rows = exchange_db.fetch_all(
        """SELECT symbol, total_liq_value FROM latest_liquidation_bars""",
        (),
    )
    liq_by_sym: dict[str, float] = {}
    for r in liq_rows:
        sym = r["symbol"]
        liq_by_sym[sym] = liq_by_sym.get(sym, 0) + (_safe_float(r["total_liq_value"]) or 0)

    items = []
    for r in ticker_rows:
        sym = r["symbol"]
        vol = _safe_float(r["quote_volume_24h"]) or 0
        change = _safe_float(r["change_24h"]) or 0
        liq = liq_by_sym.get(sym, 0)

        # Anomaly score: weighted combination of abs(change), liq magnitude
        anomaly_score = abs(change) * 40 + (liq / max(vol, 1)) * 30
        flags = []
        if abs(change) > 0.05:
            flags.append("price_spike")
        if liq > vol * 0.01:
            flags.append("liquidation_surge")

        if flags or anomaly_score > 3:
            items.append({
                "symbol": sym,
                "anomaly_score": round(anomaly_score, 2),
                "flags": flags,
                "change_24h": round(change, 4),
                "volume_24h": round(vol, 2),
                "liquidations_usd": round(liq, 2),
                "oi_usd": round(oi_by_sym.get(sym, 0), 2),
            })

    items.sort(key=lambda x: x["anomaly_score"], reverse=True)
    return {"count": min(limit, len(items)), "assets": items[:limit]}


@router.get("/opportunities")
def opportunities(
    limit: int = Query(10, ge=1, le=50, description="返回前 N 名"),
) -> dict[str, Any]:
    """多因子综合机会评分（动量 + 资金费率 + 波动率 + 成交量）。"""
    exchange_db = get_exchange_db()
    analytics_db = get_analytics_db()

    # Tickers
    ticker_rows = exchange_db.fetch_all(
        """SELECT symbol, last_price, quote_volume_24h, change_24h
           FROM latest_tickers WHERE exchange = 'binance'""",
        (),
    )
    ticker_map: dict[str, dict] = {}
    for r in ticker_rows:
        ticker_map[r["symbol"]] = {
            "price": _safe_float(r["last_price"]),
            "volume": _safe_float(r["quote_volume_24h"]) or 0,
            "change": _safe_float(r["change_24h"]) or 0,
        }

    # Funding rates
    fr_rows = exchange_db.fetch_all(
        """SELECT symbol, funding_rate FROM latest_funding_rates
           WHERE exchange = 'binance'""",
        (),
    )
    fr_map: dict[str, float] = {}
    for r in fr_rows:
        rate = _safe_float(r["funding_rate"])
        if rate is not None:
            fr_map[r["symbol"]] = rate

    # Technical indicators (RSI)
    ti_rows = analytics_db.fetch_all(
        """SELECT ti.symbol, ti.rsi_14
           FROM technical_indicators ti
           INNER JOIN (
               SELECT symbol, MAX(open_time) AS max_time
               FROM technical_indicators WHERE timeframe = '1h'
               GROUP BY symbol
           ) latest ON ti.symbol = latest.symbol AND ti.open_time = latest.max_time
           WHERE ti.timeframe = '1h'""",
        (),
    )
    rsi_map: dict[str, float] = {}
    for r in ti_rows:
        rsi = _safe_float(r["rsi_14"])
        if rsi is not None:
            rsi_map[r["symbol"]] = rsi

    items = []
    for sym in TARGET_SYMBOLS:
        t = ticker_map.get(sym)
        if not t:
            continue
        rsi = rsi_map.get(sym, 50.0)
        fr = fr_map.get(sym, 0.0)

        # Opportunity score: oversold + negative funding = potential long
        # Overbought + positive funding = potential short
        momentum_factor = (50 - rsi) / 50  # positive when oversold
        funding_factor = -fr * 1000  # positive when shorts pay
        volume_factor = min(t["volume"] / 1e8, 1.0)  # normalized

        opp_score = round(
            momentum_factor * 40 + funding_factor * 30 + volume_factor * 30, 2
        )

        items.append({
            "symbol": sym,
            "opportunity_score": opp_score,
            "direction": "long" if opp_score > 0 else "short",
            "rsi_14": round(rsi, 2),
            "funding_rate": round(fr, 6),
            "change_24h": round(t["change"], 4),
            "volume_24h": round(t["volume"], 2),
        })

    items.sort(key=lambda x: abs(x["opportunity_score"]), reverse=True)
    return {"count": min(limit, len(items)), "assets": items[:limit]}
