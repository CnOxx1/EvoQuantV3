"""Aggregate 路由 — 聚合查询类端点，减少调用方请求次数。"""

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
from config.symbols import (
    SECTOR_DEFINITIONS,
    SYMBOL_UNIVERSE,
    TARGET_SYMBOLS,
)

router = APIRouter(prefix="/aggregate", tags=["aggregate"])


@router.get("/asset-profile/{symbol}")
def asset_profile(symbol: str) -> dict[str, Any]:
    """单资产全维度画像（价格+衍生品+技术+风险+因子）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    exchange_db = get_exchange_db()

    # Price data
    ticker = exchange_db.fetch_one(
        "SELECT * FROM latest_tickers WHERE symbol = ? AND exchange = 'binance'",
        (normalized,),
    )
    price_info = {}
    if ticker:
        price_info = {
            "price": _safe_float(ticker["last_price"]),
            "change_24h": _safe_float(ticker["change_24h"]),
            "volume_24h": _safe_float(ticker["quote_volume_24h"]),
        }

    # Derivatives data
    funding = exchange_db.fetch_one(
        "SELECT * FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
        (normalized,),
    )
    derivatives_info = {}
    if funding:
        rate = _safe_float(funding["funding_rate"])
        derivatives_info = {
            "funding_rate": rate,
            "annualized_funding": round(rate * 3 * 365, 4) if rate else None,
            "mark_price": _safe_float(funding["mark_price"]),
        }

    # OI data
    oi_row = exchange_db.fetch_one(
        "SELECT open_interest_contracts, open_interest_usd, open_interest_change_24h FROM latest_open_interest_snapshots WHERE symbol = ? AND exchange = 'binance'",
        (normalized,),
    )
    if oi_row:
        derivatives_info["open_interest_contracts"] = _safe_float(oi_row["open_interest_contracts"])
        derivatives_info["open_interest_usd"] = _safe_float(oi_row["open_interest_usd"])
        derivatives_info["open_interest_change_24h"] = _safe_float(oi_row["open_interest_change_24h"])

    # Volatility / Risk
    klines = exchange_db.fetch_all(
        "SELECT close FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 168",
        (normalized,),
    )
    prices = [_safe_float(r["close"]) for r in klines if _safe_float(r["close"])]
    prices.reverse()
    daily_vol, annual_vol = _compute_volatility(prices) if prices else (0.0, 0.0)
    risk_score, risk_label = _risk_level(annual_vol)

    # Sector info
    sector = None
    tier = None
    for entry in SYMBOL_UNIVERSE:
        if entry["symbol"] == normalized:
            sector = entry["sector"]
            tier = entry["tier"]
            break

    return {
        "symbol": normalized,
        "sector": sector,
        "tier": tier,
        "price": price_info,
        "derivatives": derivatives_info,
        "risk": {
            "daily_volatility": round(daily_vol, 6),
            "annualized_volatility": round(annual_vol, 4),
            "risk_score": risk_score,
            "risk_level": risk_label,
        },
    }


@router.get("/multi-asset-compare")
def multi_asset_compare(
    symbols: str = Query(..., description="逗号分隔的 2-5 个符号"),
) -> dict[str, Any]:
    """2-5 资产横向对比 + 排名 + 分歧检测。"""
    sym_list = [_normalize_symbol(s.strip()) for s in symbols.split(",")]
    if len(sym_list) < 2 or len(sym_list) > 5:
        raise HTTPException(status_code=400, detail="需要 2-5 个符号")

    exchange_db = get_exchange_db()
    results = []
    for sym in sym_list:
        ticker = exchange_db.fetch_one(
            "SELECT * FROM latest_tickers WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        results.append({
            "symbol": sym,
            "price": _safe_float(ticker["last_price"]) if ticker else None,
            "change_24h": _safe_float(ticker["change_24h"]) if ticker else None,
            "volume_24h": _safe_float(ticker["quote_volume_24h"]) if ticker else None,
            "funding_rate": _safe_float(funding["funding_rate"]) if funding else None,
        })

    # Rank by change_24h
    valid = [r for r in results if r["change_24h"] is not None]
    valid.sort(key=lambda x: x["change_24h"], reverse=True)
    for i, r in enumerate(valid):
        r["rank_by_change"] = i + 1

    # Divergence detection
    changes = [r["change_24h"] for r in results if r["change_24h"] is not None]
    divergence = (max(changes) - min(changes)) if len(changes) >= 2 else 0

    return {
        "count": len(results),
        "assets": results,
        "divergence_spread": round(divergence, 4),
        "has_divergence": divergence > 5.0,
    }


@router.get("/sector-snapshot")
def sector_snapshot() -> dict[str, Any]:
    """板块聚合视图（领涨/领跌、板块统计、轮动阶段）。"""
    exchange_db = get_exchange_db()
    sectors: dict[str, list[dict]] = {}

    for sector_name, syms in SECTOR_DEFINITIONS.items():
        sector_assets = []
        for sym in syms:
            ticker = exchange_db.fetch_one(
                "SELECT last_price, change_24h, quote_volume_24h FROM latest_tickers WHERE symbol = ? AND exchange = 'binance'",
                (sym,),
            )
            if ticker:
                sector_assets.append({
                    "symbol": sym,
                    "change_24h": _safe_float(ticker["change_24h"]),
                    "volume_24h": _safe_float(ticker["quote_volume_24h"]),
                })
        sectors[sector_name] = sector_assets

    sector_stats = []
    for sector_name, assets in sectors.items():
        changes = [a["change_24h"] for a in assets if a["change_24h"] is not None]
        avg_change = sum(changes) / len(changes) if changes else 0
        sector_stats.append({
            "sector": sector_name,
            "avg_change_24h": round(avg_change, 4),
            "asset_count": len(assets),
            "leader": max(assets, key=lambda x: x["change_24h"] or -999)["symbol"] if assets else None,
            "laggard": min(assets, key=lambda x: x["change_24h"] or 999)["symbol"] if assets else None,
        })

    sector_stats.sort(key=lambda x: x["avg_change_24h"], reverse=True)

    return {
        "sector_count": len(sector_stats),
        "sectors": sector_stats,
        "top_sector": sector_stats[0]["sector"] if sector_stats else None,
        "bottom_sector": sector_stats[-1]["sector"] if sector_stats else None,
    }


@router.get("/derivatives-heatmap")
def derivatives_heatmap() -> dict[str, Any]:
    """全市场衍生品热力图（资金费率/OI/基差）。"""
    exchange_db = get_exchange_db()
    items = []

    for sym in TARGET_SYMBOLS:
        funding = exchange_db.fetch_one(
            "SELECT funding_rate, mark_price, index_price FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        oi_row = exchange_db.fetch_one(
            "SELECT open_interest_contracts FROM latest_open_interest_snapshots WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        rate = _safe_float(funding["funding_rate"]) if funding else None
        mark = _safe_float(funding["mark_price"]) if funding else None
        index_p = _safe_float(funding["index_price"]) if funding else None
        basis = round((mark - index_p) / index_p * 100, 4) if (mark and index_p and index_p > 0) else None

        items.append({
            "symbol": sym,
            "funding_rate": rate,
            "annualized_funding": round(rate * 3 * 365, 4) if rate else None,
            "open_interest_contracts": _safe_float(oi_row["open_interest_contracts"]) if oi_row else None,
            "basis_pct": basis,
            "sentiment": "bullish" if (rate and rate > 0.0001) else "bearish" if (rate and rate < -0.0001) else "neutral",
        })

    items.sort(key=lambda x: abs(x["funding_rate"] or 0), reverse=True)
    return {"count": len(items), "assets": items}


@router.get("/market-regime")
def market_regime() -> dict[str, Any]:
    """市场体制判断（趋势/震荡/恐慌/狂热）。"""
    exchange_db = get_exchange_db()

    # Gather BTC as market proxy
    btc_klines = exchange_db.fetch_all(
        "SELECT close FROM klines WHERE symbol = 'BTC/USDT' AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 168",
        (),
    )
    prices = [_safe_float(r["close"]) for r in btc_klines if _safe_float(r["close"])]
    prices.reverse()

    # Calculate trend via simple MA comparison
    regime = "unknown"
    trend_strength = 0.0
    if len(prices) >= 50:
        ma20 = sum(prices[-20:]) / 20
        ma50 = sum(prices[-50:]) / 50
        current = prices[-1]
        trend_strength = (current - ma50) / ma50 * 100 if ma50 else 0

        if trend_strength > 10:
            regime = "euphoria"
        elif trend_strength > 3:
            regime = "trending_up"
        elif trend_strength < -10:
            regime = "panic"
        elif trend_strength < -3:
            regime = "trending_down"
        else:
            regime = "ranging"

    # Aggregate funding sentiment
    fundings = exchange_db.fetch_all(
        "SELECT funding_rate FROM latest_funding_rates WHERE exchange = 'binance'",
        (),
    )
    rates = [_safe_float(r["funding_rate"]) for r in fundings if _safe_float(r["funding_rate"]) is not None]
    avg_funding = sum(rates) / len(rates) if rates else 0
    positive_pct = sum(1 for r in rates if r > 0) / len(rates) * 100 if rates else 50

    return {
        "regime": regime,
        "trend_strength": round(trend_strength, 2),
        "btc_proxy": {
            "price": prices[-1] if prices else None,
            "ma20": round(sum(prices[-20:]) / 20, 2) if len(prices) >= 20 else None,
            "ma50": round(sum(prices[-50:]) / 50, 2) if len(prices) >= 50 else None,
        },
        "funding_sentiment": {
            "avg_funding_rate": round(avg_funding, 6),
            "positive_pct": round(positive_pct, 1),
        },
    }


@router.get("/correlation-context/{symbol}")
def correlation_context(symbol: str) -> dict[str, Any]:
    """单资产相关性上下文（Beta、最相关/最不相关）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    analytics_db = get_exchange_db()

    # Get target prices
    target_rows = analytics_db.fetch_all(
        "SELECT close FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 168",
        (normalized,),
    )
    target_prices = [_safe_float(r["close"]) for r in target_rows if _safe_float(r["close"])]
    target_prices.reverse()

    if len(target_prices) < 10:
        return {"symbol": normalized, "correlations": [], "note": "Insufficient data"}

    # Calculate returns for target
    target_rets = [
        (target_prices[i] - target_prices[i - 1]) / target_prices[i - 1]
        for i in range(1, len(target_prices))
        if target_prices[i - 1] != 0
    ]

    correlations = []
    for sym in TARGET_SYMBOLS:
        if sym == normalized:
            continue
        rows = analytics_db.fetch_all(
            "SELECT close FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 168",
            (sym,),
        )
        prices = [_safe_float(r["close"]) for r in rows if _safe_float(r["close"])]
        prices.reverse()
        if len(prices) < 10:
            continue
        rets = [
            (prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
            if prices[i - 1] != 0
        ]
        # Align lengths
        n = min(len(target_rets), len(rets))
        if n < 5:
            continue
        tr = target_rets[:n]
        sr = rets[:n]
        # Pearson correlation
        mean_t = sum(tr) / n
        mean_s = sum(sr) / n
        cov = sum((tr[i] - mean_t) * (sr[i] - mean_s) for i in range(n)) / n
        std_t = math.sqrt(sum((x - mean_t) ** 2 for x in tr) / n)
        std_s = math.sqrt(sum((x - mean_s) ** 2 for x in sr) / n)
        corr = cov / (std_t * std_s) if (std_t > 0 and std_s > 0) else 0
        correlations.append({"symbol": sym, "correlation": round(corr, 4)})

    correlations.sort(key=lambda x: x["correlation"], reverse=True)
    most_correlated = correlations[:3] if correlations else []
    least_correlated = correlations[-3:] if correlations else []

    # Beta vs BTC
    btc_rows = analytics_db.fetch_all(
        "SELECT close FROM klines WHERE symbol = 'BTC/USDT' AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 168",
        (),
    )
    btc_prices = [_safe_float(r["close"]) for r in btc_rows if _safe_float(r["close"])]
    btc_prices.reverse()
    beta = None
    if len(btc_prices) >= 10 and normalized != "BTC/USDT":
        btc_rets = [
            (btc_prices[i] - btc_prices[i - 1]) / btc_prices[i - 1]
            for i in range(1, len(btc_prices))
            if btc_prices[i - 1] != 0
        ]
        n = min(len(target_rets), len(btc_rets))
        if n >= 5:
            mean_b = sum(btc_rets[:n]) / n
            mean_t = sum(target_rets[:n]) / n
            cov = sum((target_rets[i] - mean_t) * (btc_rets[i] - mean_b) for i in range(n)) / n
            var_b = sum((btc_rets[i] - mean_b) ** 2 for i in range(n)) / n
            beta = round(cov / var_b, 4) if var_b > 0 else None

    return {
        "symbol": normalized,
        "beta_vs_btc": beta,
        "most_correlated": most_correlated,
        "least_correlated": least_correlated,
        "total_pairs": len(correlations),
    }


@router.get("/watchlist")
def watchlist(
    symbols: str = Query(..., description="逗号分隔的符号列表"),
) -> dict[str, Any]:
    """自定义观察列表批量查询。"""
    sym_list = [_normalize_symbol(s.strip()) for s in symbols.split(",")]
    exchange_db = get_exchange_db()

    items = []
    for sym in sym_list:
        ticker = exchange_db.fetch_one(
            "SELECT last_price, change_24h, quote_volume_24h FROM latest_tickers WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        funding = exchange_db.fetch_one(
            "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
            (sym,),
        )
        items.append({
            "symbol": sym,
            "price": _safe_float(ticker["last_price"]) if ticker else None,
            "change_24h": _safe_float(ticker["change_24h"]) if ticker else None,
            "volume_24h": _safe_float(ticker["quote_volume_24h"]) if ticker else None,
            "funding_rate": _safe_float(funding["funding_rate"]) if funding else None,
            "in_universe": sym in TARGET_SYMBOLS,
        })

    return {"count": len(items), "assets": items}
