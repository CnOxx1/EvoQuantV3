"""Overview 路由 — 聚合概览仪表盘（一次请求获取全局市场状态）。"""

from __future__ import annotations

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

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/market-dashboard")
def market_dashboard() -> dict[str, Any]:
    """全市场仪表盘：价格、成交量、涨跌幅、风险等级。"""
    exchange_db = get_exchange_db()
    analytics_db = get_analytics_db()

    # 最新 ticker
    tickers = exchange_db.fetch_all(
        """SELECT symbol, last_price, quote_volume_24h, change_24h, timestamp
           FROM latest_tickers
           WHERE exchange = 'binance'
           ORDER BY symbol""",
        (),
    )

    # 1h klines for volatility
    kline_rows = analytics_db.fetch_all(
        """SELECT symbol, close FROM merged_klines
           WHERE timeframe = '1h'
           ORDER BY symbol, open_time DESC""",
        (),
    )
    # Build price series per symbol (max 168 bars = 7d)
    price_series: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for r in kline_rows:
        sym = r["symbol"]
        if counts.get(sym, 0) >= 168:
            continue
        price_series.setdefault(sym, []).append(float(r["close"]))
        counts[sym] = counts.get(sym, 0) + 1

    assets: list[dict[str, Any]] = []
    for row in tickers:
        sym = row["symbol"]
        prices = price_series.get(sym, [])
        prices_rev = list(reversed(prices))
        daily_vol, ann_vol = _compute_volatility(prices_rev)
        risk_score, risk_lvl = _risk_level(ann_vol) if ann_vol else (0, "unknown")
        assets.append({
            "symbol": sym,
            "price": _safe_float(row["last_price"]),
            "volume_24h": _safe_float(row["quote_volume_24h"]),
            "change_24h": _safe_float(row["change_24h"]),
            "annualized_vol": round(ann_vol, 4),
            "risk_score": risk_score,
            "risk_level": risk_lvl,
        })

    total_vol = sum(a["volume_24h"] or 0 for a in assets)
    gainers = sum(1 for a in assets if (a["change_24h"] or 0) > 0)
    losers = sum(1 for a in assets if (a["change_24h"] or 0) < 0)

    return {
        "asset_count": len(assets),
        "total_volume_24h": round(total_vol, 2),
        "gainers": gainers,
        "losers": losers,
        "assets": assets,
    }


@router.get("/derivatives-dashboard")
def derivatives_dashboard() -> dict[str, Any]:
    """衍生品总览：资金费率、OI、基差、清算。"""
    db = get_exchange_db()

    funding_rows = db.fetch_all(
        """SELECT symbol, exchange, funding_rate FROM latest_funding_rates
           ORDER BY symbol""",
        (),
    )
    oi_rows = db.fetch_all(
        """SELECT symbol, open_interest_value FROM latest_open_interest_snapshots
           ORDER BY symbol""",
        (),
    )
    basis_rows = db.fetch_all(
        """SELECT symbol, basis_bps, annualized_basis_bps
           FROM latest_basis_snapshots ORDER BY symbol""",
        (),
    )
    liq_rows = db.fetch_all(
        """SELECT symbol, total_liq_value FROM latest_liquidation_bars
           ORDER BY symbol""",
        (),
    )

    # Aggregate by symbol
    symbols_data: dict[str, dict[str, Any]] = {}
    for r in funding_rows:
        sym = r["symbol"]
        symbols_data.setdefault(sym, {})
        symbols_data[sym].setdefault("funding_rates", [])
        if r["funding_rate"] is not None:
            symbols_data[sym]["funding_rates"].append(float(r["funding_rate"]))

    for r in oi_rows:
        sym = r["symbol"]
        symbols_data.setdefault(sym, {})
        symbols_data[sym]["oi_value"] = (
            symbols_data[sym].get("oi_value", 0) + (_safe_float(r["open_interest_value"]) or 0)
        )

    for r in basis_rows:
        sym = r["symbol"]
        symbols_data.setdefault(sym, {})
        symbols_data[sym].setdefault("basis_bps_list", [])
        if r["basis_bps"] is not None:
            symbols_data[sym]["basis_bps_list"].append(float(r["basis_bps"]))

    for r in liq_rows:
        sym = r["symbol"]
        symbols_data.setdefault(sym, {})
        symbols_data[sym]["liq_value"] = (
            symbols_data[sym].get("liq_value", 0) + (_safe_float(r["total_liq_value"]) or 0)
        )

    assets: list[dict[str, Any]] = []
    for sym, d in sorted(symbols_data.items()):
        rates = d.get("funding_rates", [])
        avg_fr = sum(rates) / len(rates) if rates else None
        basis_list = d.get("basis_bps_list", [])
        avg_basis = sum(basis_list) / len(basis_list) if basis_list else None
        assets.append({
            "symbol": sym,
            "avg_funding_rate": round(avg_fr, 6) if avg_fr is not None else None,
            "annualized_funding": round(avg_fr * 3 * 365, 4) if avg_fr is not None else None,
            "total_oi_usd": round(d.get("oi_value", 0), 2),
            "avg_basis_bps": round(avg_basis, 2) if avg_basis is not None else None,
            "total_liquidations_usd": round(d.get("liq_value", 0), 2),
        })

    total_oi = sum(a["total_oi_usd"] for a in assets)
    total_liq = sum(a["total_liquidations_usd"] for a in assets)

    return {
        "asset_count": len(assets),
        "total_open_interest_usd": round(total_oi, 2),
        "total_liquidations_usd": round(total_liq, 2),
        "assets": assets,
    }


@router.get("/sector-dashboard")
def sector_dashboard() -> dict[str, Any]:
    """板块聚合：按 sector 分组的表现和成交量。"""
    exchange_db = get_exchange_db()

    tickers = exchange_db.fetch_all(
        """SELECT symbol, last_price, quote_volume_24h, change_24h
           FROM latest_tickers
           WHERE exchange = 'binance'
           ORDER BY symbol""",
        (),
    )

    ticker_map: dict[str, dict[str, Any]] = {}
    for r in tickers:
        ticker_map[r["symbol"]] = {
            "price": _safe_float(r["last_price"]),
            "volume_24h": _safe_float(r["quote_volume_24h"]),
            "change_24h": _safe_float(r["change_24h"]),
        }

    # Group by sector
    sectors: dict[str, list[dict[str, Any]]] = {}
    for entry in SYMBOL_UNIVERSE:
        sym = entry["symbol"]
        sector = entry["sector"]
        t = ticker_map.get(sym, {})
        sectors.setdefault(sector, []).append({
            "symbol": sym,
            "price": t.get("price"),
            "volume_24h": t.get("volume_24h"),
            "change_24h": t.get("change_24h"),
        })

    result: list[dict[str, Any]] = []
    for sector, assets_list in sorted(sectors.items()):
        changes = [a["change_24h"] for a in assets_list if a["change_24h"] is not None]
        volumes = [a["volume_24h"] for a in assets_list if a["volume_24h"] is not None]
        avg_change = sum(changes) / len(changes) if changes else None
        total_volume = sum(volumes) if volumes else 0
        result.append({
            "sector": sector,
            "asset_count": len(assets_list),
            "avg_change_24h": round(avg_change, 4) if avg_change is not None else None,
            "total_volume_24h": round(total_volume, 2),
            "assets": assets_list,
        })

    return {"sector_count": len(result), "sectors": result}


@router.get("/quick-stats")
def quick_stats() -> dict[str, Any]:
    """极简市场统计：一个请求获取市场情绪概要。"""
    exchange_db = get_exchange_db()

    tickers = exchange_db.fetch_all(
        """SELECT symbol, last_price, quote_volume_24h, change_24h
           FROM latest_tickers WHERE exchange = 'binance'""",
        (),
    )

    funding = exchange_db.fetch_all(
        """SELECT symbol, funding_rate FROM latest_funding_rates
           WHERE exchange = 'binance'""",
        (),
    )

    changes = [_safe_float(r["change_24h"]) for r in tickers if r["change_24h"] is not None]
    volumes = [_safe_float(r["quote_volume_24h"]) for r in tickers if r["quote_volume_24h"] is not None]
    rates = [_safe_float(r["funding_rate"]) for r in funding if r["funding_rate"] is not None]

    gainers = sum(1 for c in changes if c and c > 0)
    losers = sum(1 for c in changes if c and c < 0)
    avg_change = sum(c for c in changes if c) / len(changes) if changes else None
    avg_funding = sum(r for r in rates if r) / len(rates) if rates else None
    total_volume = sum(v for v in volumes if v)

    # Simple sentiment heuristic
    if avg_change and avg_change > 0.02 and avg_funding and avg_funding > 0.0005:
        sentiment = "bullish"
    elif avg_change and avg_change < -0.02 and avg_funding and avg_funding < -0.0005:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "asset_count": len(tickers),
        "gainers": gainers,
        "losers": losers,
        "avg_change_24h": round(avg_change, 4) if avg_change is not None else None,
        "total_volume_24h": round(total_volume, 2),
        "avg_funding_rate": round(avg_funding, 6) if avg_funding is not None else None,
        "market_sentiment": sentiment,
    }
