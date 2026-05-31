"""Liquidity 路由 — 流动性分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/liquidity", tags=["liquidity"])


@router.get("/score/{symbol}")
def get_liquidity_score(symbol: str) -> dict[str, Any]:
    """流动性评分（0-100）+ 组成分解。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_exchange_db()
    row = db.fetch_one(
        "SELECT * FROM latest_orderbook_snapshots WHERE symbol = ? "
        "ORDER BY timestamp DESC LIMIT 1",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No orderbook data for {symbol}")
    best_bid = _safe_float(row.get("bid_price")) or 0
    best_ask = _safe_float(row.get("ask_price")) or 0
    bid_depth = _safe_float(row.get("bid_depth_usd")) or 0
    ask_depth = _safe_float(row.get("ask_depth_usd")) or 0
    spread_bps = ((best_ask - best_bid) / best_bid * 10000) if best_bid > 0 else 999
    total_depth = bid_depth + ask_depth
    balance = min(bid_depth, ask_depth) / max(bid_depth, ask_depth) if max(bid_depth, ask_depth) > 0 else 0
    spread_score = max(0, min(100, 100 - spread_bps * 5))
    depth_score = min(100, total_depth / 10000)
    balance_score = balance * 100
    composite = spread_score * 0.3 + depth_score * 0.4 + balance_score * 0.3
    return {
        "symbol": normalized,
        "liquidity_score": round(composite, 1),
        "spread_bps": round(spread_bps, 2),
        "spread_score": round(spread_score, 1),
        "depth_score": round(depth_score, 1),
        "balance_score": round(balance_score, 1),
        "total_depth_usd": round(total_depth, 2),
        "data_source": "exchange_data",
    }


@router.get("/slippage/{symbol}")
def get_slippage(symbol: str) -> dict[str, Any]:
    """滑点估算（10K/100K/1M USD）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_exchange_db()
    row = db.fetch_one(
        "SELECT * FROM latest_orderbook_snapshots WHERE symbol = ? "
        "ORDER BY timestamp DESC LIMIT 1",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No orderbook data for {symbol}")
    bid_depth = _safe_float(row.get("bid_depth_usd")) or 1
    ask_depth = _safe_float(row.get("ask_depth_usd")) or 1
    best_bid = _safe_float(row.get("bid_price")) or 0
    best_ask = _safe_float(row.get("ask_price")) or 0
    spread_bps = ((best_ask - best_bid) / best_bid * 10000) if best_bid > 0 else 0
    slippage_10k = spread_bps / 2 + (10000 / ask_depth) * 5
    slippage_100k = spread_bps / 2 + (100000 / ask_depth) * 5
    slippage_1m = spread_bps / 2 + (1000000 / ask_depth) * 5
    return {
        "symbol": normalized,
        "spread_bps": round(spread_bps, 2),
        "slippage_10k_bps": round(slippage_10k, 2),
        "slippage_100k_bps": round(slippage_100k, 2),
        "slippage_1m_bps": round(slippage_1m, 2),
        "bid_depth_usd": round(bid_depth, 2),
        "ask_depth_usd": round(ask_depth, 2),
        "data_source": "exchange_data",
    }


@router.get("/alerts")
def get_liquidity_alerts() -> dict[str, Any]:
    """流动性预警列表。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT symbol, bid_price, ask_price, bid_depth_usd, ask_depth_usd, timestamp "
        "FROM latest_orderbook_snapshots",
    )
    alerts = []
    for r in rows:
        bid = _safe_float(r.get("bid_price")) or 0
        ask = _safe_float(r.get("ask_price")) or 0
        bid_d = _safe_float(r.get("bid_depth_usd")) or 0
        ask_d = _safe_float(r.get("ask_depth_usd")) or 0
        spread = ((ask - bid) / bid * 10000) if bid > 0 else 999
        total_depth = bid_d + ask_d
        if spread > 20:
            alerts.append({"symbol": r.get("symbol"), "type": "wide_spread", "spread_bps": round(spread, 2)})
        if total_depth < 100000:
            alerts.append({"symbol": r.get("symbol"), "type": "thin_book", "depth_usd": round(total_depth, 2)})
    return {"alert_count": len(alerts), "alerts": alerts}


@router.get("/ranking")
def get_liquidity_ranking() -> dict[str, Any]:
    """全资产流动性排名。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        "SELECT symbol, bid_price, ask_price, bid_depth_usd, ask_depth_usd "
        "FROM latest_orderbook_snapshots",
    )
    scored = []
    for r in rows:
        bid = _safe_float(r.get("bid_price")) or 0
        ask = _safe_float(r.get("ask_price")) or 0
        bid_d = _safe_float(r.get("bid_depth_usd")) or 0
        ask_d = _safe_float(r.get("ask_depth_usd")) or 0
        spread_bps = ((ask - bid) / bid * 10000) if bid > 0 else 999
        total_depth = bid_d + ask_d
        balance = min(bid_d, ask_d) / max(bid_d, ask_d) if max(bid_d, ask_d) > 0 else 0
        score = max(0, min(100, 100 - spread_bps * 5)) * 0.3 + min(100, total_depth / 10000) * 0.4 + balance * 100 * 0.3
        scored.append({"symbol": r.get("symbol"), "liquidity_score": round(score, 1), "spread_bps": round(spread_bps, 2), "depth_usd": round(total_depth, 2)})
    scored.sort(key=lambda x: x["liquidity_score"], reverse=True)
    return {"count": len(scored), "ranking": scored}
