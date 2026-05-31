"""Orderflow 路由 — 订单流智能分析端点。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db
from api.routers._helpers import (
    _detect_divergence,
    _linear_slope,
    _normalize_symbol,
    _percentile_rank,
    _safe_float,
)
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/orderflow", tags=["orderflow"])


@router.get("/cvd/{symbol}")
def cvd_timeseries(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    limit: int = Query(100, ge=1, le=500, description="数据点数"),
) -> dict[str, Any]:
    """CVD 时序 + 价格背离检测。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT open_time, cvd, net_taker_notional, buy_notional, sell_notional "
        "FROM trade_flow_bars WHERE symbol = ? AND exchange = ? "
        "ORDER BY open_time DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    if not rows:
        return {"symbol": normalized, "exchange": exchange, "data": [], "divergence": None}

    rows.reverse()
    cvd_values = [_safe_float(r["cvd"]) or 0.0 for r in rows]

    # Get price data for divergence detection
    klines = db.fetch_all(
        "SELECT close FROM klines WHERE symbol = ? AND exchange = ? "
        "AND timeframe = '1h' ORDER BY open_time DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    prices = [_safe_float(r["close"]) or 0.0 for r in reversed(klines)] if klines else []
    divergence = _detect_divergence(prices, cvd_values) if len(prices) >= 4 else None

    data = [
        {
            "time": r["open_time"],
            "cvd": _safe_float(r["cvd"]),
            "net_taker": _safe_float(r["net_taker_notional"]),
            "buy_notional": _safe_float(r["buy_notional"]),
            "sell_notional": _safe_float(r["sell_notional"]),
        }
        for r in rows
    ]
    return {
        "symbol": normalized,
        "exchange": exchange,
        "count": len(data),
        "cvd_trend_slope": round(_linear_slope(cvd_values), 6),
        "divergence": divergence,
        "data": data,
    }


@router.get("/aggression/{symbol}")
def aggression(
    symbol: str,
    limit: int = Query(50, ge=1, le=200, description="数据点数"),
) -> dict[str, Any]:
    """多交易所买卖侵略性对比。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT exchange, open_time, aggressive_buy_notional, aggressive_sell_notional, "
        "buy_notional, sell_notional, trade_count "
        "FROM trade_flow_bars WHERE symbol = ? "
        "ORDER BY open_time DESC LIMIT ?",
        (normalized, limit * 3),
    )
    if not rows:
        return {"symbol": normalized, "exchanges": {}}

    by_exchange: dict[str, list] = {}
    for r in rows:
        ex = r["exchange"]
        agg_buy = _safe_float(r["aggressive_buy_notional"]) or 0.0
        agg_sell = _safe_float(r["aggressive_sell_notional"]) or 0.0
        total = agg_buy + agg_sell
        by_exchange.setdefault(ex, []).append({
            "time": r["open_time"],
            "aggressive_buy": agg_buy,
            "aggressive_sell": agg_sell,
            "aggression_ratio": round(agg_buy / total, 4) if total > 0 else 0.5,
            "trade_count": r["trade_count"],
        })

    summary = {}
    for ex, data in by_exchange.items():
        ratios = [d["aggression_ratio"] for d in data]
        summary[ex] = {
            "avg_aggression_ratio": round(sum(ratios) / len(ratios), 4),
            "data_points": len(data),
            "latest": data[0] if data else None,
        }
    return {"symbol": normalized, "exchanges": summary}


@router.get("/whale-trades/{symbol}")
def whale_trades(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    percentile: float = Query(95.0, ge=50, le=99.9, description="大单百分位阈值"),
    limit: int = Query(200, ge=1, le=1000, description="扫描条数"),
) -> dict[str, Any]:
    """大单检测（百分位筛选）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT open_time, largest_trade_notional, avg_trade_notional, trade_count, "
        "buy_notional, sell_notional, net_taker_notional "
        "FROM trade_flow_bars WHERE symbol = ? AND exchange = ? "
        "ORDER BY open_time DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    if not rows:
        return {"symbol": normalized, "exchange": exchange, "whale_trades": [], "threshold": 0}

    largest_values = [_safe_float(r["largest_trade_notional"]) or 0.0 for r in rows]
    threshold = sorted(largest_values)[int(len(largest_values) * percentile / 100)]

    whale_bars = [
        {
            "time": r["open_time"],
            "largest_trade": _safe_float(r["largest_trade_notional"]),
            "avg_trade": _safe_float(r["avg_trade_notional"]),
            "trade_count": r["trade_count"],
            "net_taker": _safe_float(r["net_taker_notional"]),
        }
        for r in rows
        if (_safe_float(r["largest_trade_notional"]) or 0.0) >= threshold
    ]
    return {
        "symbol": normalized,
        "exchange": exchange,
        "percentile": percentile,
        "threshold_notional": round(threshold, 2),
        "whale_trade_count": len(whale_bars),
        "whale_trades": whale_bars[:50],
    }


@router.get("/depth-heatmap/{symbol}")
def depth_heatmap(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    limit: int = Query(20, ge=1, le=100, description="快照数"),
) -> dict[str, Any]:
    """订单簿深度热力图（挂单墙检测）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT timestamp, mid_price, bids_json, asks_json, bid_depth_notional, "
        "ask_depth_notional FROM orderbook_snapshots "
        "WHERE symbol = ? AND exchange = ? ORDER BY timestamp DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    if not rows:
        return {"symbol": normalized, "exchange": exchange, "heatmap": []}

    heatmap = []
    for r in rows:
        mid = _safe_float(r["mid_price"]) or 0.0
        try:
            bids = json.loads(r["bids_json"]) if r["bids_json"] else []
            asks = json.loads(r["asks_json"]) if r["asks_json"] else []
        except (json.JSONDecodeError, TypeError):
            bids, asks = [], []
        # Find walls (levels with > 3x average size)
        bid_sizes = [float(b["amount"]) * float(b["price"]) for b in bids[:20]
                     if isinstance(b, dict) and "price" in b and "amount" in b]
        ask_sizes = [float(a["amount"]) * float(a["price"]) for a in asks[:20]
                     if isinstance(a, dict) and "price" in a and "amount" in a]
        avg_bid = sum(bid_sizes) / len(bid_sizes) if bid_sizes else 1.0
        avg_ask = sum(ask_sizes) / len(ask_sizes) if ask_sizes else 1.0
        bid_walls = [
            {"price": float(b["price"]), "notional": float(b["amount"]) * float(b["price"]),
             "distance_bps": round((mid - float(b["price"])) / mid * 10000, 1) if mid else 0}
            for b in bids[:20]
            if isinstance(b, dict) and "price" in b and "amount" in b
            and float(b["amount"]) * float(b["price"]) > avg_bid * 3
        ]
        ask_walls = [
            {"price": float(a["price"]), "notional": float(a["amount"]) * float(a["price"]),
             "distance_bps": round((float(a["price"]) - mid) / mid * 10000, 1) if mid else 0}
            for a in asks[:20]
            if isinstance(a, dict) and "price" in a and "amount" in a
            and float(a["amount"]) * float(a["price"]) > avg_ask * 3
        ]
        heatmap.append({
            "time": r["timestamp"], "mid_price": mid,
            "bid_depth": _safe_float(r["bid_depth_notional"]),
            "ask_depth": _safe_float(r["ask_depth_notional"]),
            "bid_walls": bid_walls[:5], "ask_walls": ask_walls[:5],
        })
    return {"symbol": normalized, "exchange": exchange, "snapshots": len(heatmap), "heatmap": heatmap}


@router.get("/imbalance-history/{symbol}")
def imbalance_history(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    limit: int = Query(100, ge=1, le=500, description="快照数"),
) -> dict[str, Any]:
    """订单簿失衡时序 + 趋势检测。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT timestamp, depth_imbalance, bid_depth_notional, ask_depth_notional, mid_price "
        "FROM orderbook_snapshots WHERE symbol = ? AND exchange = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (normalized, exchange, limit),
    )
    if not rows:
        return {"symbol": normalized, "exchange": exchange, "data": [], "trend": None}

    rows.reverse()
    imbalances = [_safe_float(r["depth_imbalance"]) or 0.0 for r in rows]
    slope = _linear_slope(imbalances)
    avg_imb = sum(imbalances) / len(imbalances)

    data = [
        {
            "time": r["timestamp"],
            "imbalance": _safe_float(r["depth_imbalance"]),
            "bid_depth": _safe_float(r["bid_depth_notional"]),
            "ask_depth": _safe_float(r["ask_depth_notional"]),
            "mid_price": _safe_float(r["mid_price"]),
        }
        for r in rows
    ]
    trend = "bid_dominant" if slope > 0.001 else "ask_dominant" if slope < -0.001 else "neutral"
    return {
        "symbol": normalized, "exchange": exchange, "count": len(data),
        "avg_imbalance": round(avg_imb, 4), "imbalance_slope": round(slope, 6),
        "trend": trend, "data": data,
    }


@router.get("/market-impact/{symbol}")
def market_impact(
    symbol: str,
    trade_size_usd: float = Query(100000, ge=1000, description="模拟交易金额 (USD)"),
) -> dict[str, Any]:
    """滑点估算 + 最优执行交易所。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT exchange, mid_price, spread_bps, bid_depth_notional, ask_depth_notional, "
        "bids_json, asks_json FROM latest_orderbook_snapshots WHERE symbol = ?",
        (normalized,),
    )
    if not rows:
        return {"symbol": normalized, "trade_size_usd": trade_size_usd, "exchanges": []}

    results = []
    for r in rows:
        mid = _safe_float(r["mid_price"]) or 0.0
        spread_bps = _safe_float(r["spread_bps"]) or 0.0
        bid_depth = _safe_float(r["bid_depth_notional"]) or 0.0
        ask_depth = _safe_float(r["ask_depth_notional"]) or 0.0
        # Estimate slippage: simple model based on depth
        buy_slippage_bps = (trade_size_usd / (ask_depth + 1)) * 100
        sell_slippage_bps = (trade_size_usd / (bid_depth + 1)) * 100
        total_cost_buy_bps = spread_bps / 2 + buy_slippage_bps
        total_cost_sell_bps = spread_bps / 2 + sell_slippage_bps
        results.append({
            "exchange": r["exchange"],
            "mid_price": mid,
            "spread_bps": round(spread_bps, 2),
            "bid_depth_usd": round(bid_depth, 0),
            "ask_depth_usd": round(ask_depth, 0),
            "estimated_buy_slippage_bps": round(buy_slippage_bps, 2),
            "estimated_sell_slippage_bps": round(sell_slippage_bps, 2),
            "total_cost_buy_bps": round(total_cost_buy_bps, 2),
            "total_cost_sell_bps": round(total_cost_sell_bps, 2),
        })
    results.sort(key=lambda x: x["total_cost_buy_bps"])
    best_buy = results[0]["exchange"] if results else None
    results.sort(key=lambda x: x["total_cost_sell_bps"])
    best_sell = results[0]["exchange"] if results else None
    return {
        "symbol": normalized, "trade_size_usd": trade_size_usd,
        "best_buy_exchange": best_buy, "best_sell_exchange": best_sell,
        "exchanges": results,
    }


@router.get("/summary")
def orderflow_summary() -> dict[str, Any]:
    """全市场订单流摘要排名。"""
    db = get_exchange_db()
    flow_rows = db.fetch_all(
        "SELECT symbol, exchange, cvd, net_taker_notional, aggressive_buy_notional, "
        "aggressive_sell_notional, trade_count FROM latest_trade_flow_bars",
    )
    ob_rows = db.fetch_all(
        "SELECT symbol, exchange, depth_imbalance, spread_bps, bid_depth_notional, "
        "ask_depth_notional FROM latest_orderbook_snapshots",
    )

    # Merge by symbol
    symbols: dict[str, dict] = {}
    for r in flow_rows:
        sym = r["symbol"]
        symbols.setdefault(sym, {"symbol": sym, "exchanges": []})
        agg_buy = _safe_float(r["aggressive_buy_notional"]) or 0.0
        agg_sell = _safe_float(r["aggressive_sell_notional"]) or 0.0
        symbols[sym]["cvd"] = _safe_float(r["cvd"])
        symbols[sym]["net_taker"] = _safe_float(r["net_taker_notional"])
        symbols[sym]["aggression_ratio"] = round(agg_buy / (agg_buy + agg_sell), 4) if (agg_buy + agg_sell) > 0 else 0.5

    for r in ob_rows:
        sym = r["symbol"]
        if sym in symbols:
            symbols[sym]["depth_imbalance"] = _safe_float(r["depth_imbalance"])
            symbols[sym]["spread_bps"] = _safe_float(r["spread_bps"])

    # Rank by absolute CVD
    ranked = sorted(symbols.values(), key=lambda x: abs(x.get("cvd") or 0), reverse=True)
    return {"count": len(ranked), "assets": ranked[:30]}
