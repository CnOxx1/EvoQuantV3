"""v3 Market — 行情与交易所统一入口。

端点：
  /market/tickers          — 最新报价
  /market/klines/{symbol}  — K线
  /market/funding-rates    — 资金费率
  /market/open-interest    — 持仓量
  /market/depth/{symbol}   — 深度盘口
  /market/info             — 资产元数据
  /market/announcements    — 交易所公告
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_exchange_db, get_market_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/market", tags=["market"])


def _norm(symbol: str) -> str:
    s = symbol.upper().replace("-", "/")
    if not s.endswith("/USDT"):
        s = f"{s}/USDT"
    return s


@router.get("/tickers")
def get_tickers(
    symbol: str | None = Query(None, description="指定资产"),
) -> dict[str, Any]:
    """最新 Ticker 快照。"""
    db = get_exchange_db()
    if symbol:
        normalized = _norm(symbol)
        rows = db.fetch_all(
            "SELECT symbol, exchange, price, volume_24h, change_pct_24h, timestamp "
            "FROM latest_tickers WHERE symbol = ? ORDER BY exchange",
            (normalized,),
        )
    else:
        rows = db.fetch_all(
            "SELECT symbol, exchange, price, volume_24h, change_pct_24h, timestamp "
            "FROM latest_tickers ORDER BY symbol, exchange",
            (),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No ticker data.")
    return {"count": len(rows), "tickers": [dict(r) for r in rows]}


@router.get("/klines/{symbol}")
def get_klines(
    symbol: str,
    timeframe: str = Query("1h", description="周期: 1m/5m/15m/1h/4h/1d"),
    limit: int = Query(100, ge=1, le=1000, description="K线数量"),
) -> dict[str, Any]:
    """合并 K 线（多交易所聚合）。"""
    normalized = _norm(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT open_time, open, high, low, close, volume, exchange_count "
        "FROM merged_klines WHERE symbol = ? AND timeframe = ? "
        "ORDER BY open_time DESC LIMIT ?",
        (normalized, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "timeframe": timeframe, "count": len(records), "klines": records}


@router.get("/funding-rates")
def get_funding_rates(
    symbol: str | None = Query(None, description="指定资产"),
) -> dict[str, Any]:
    """最新资金费率。"""
    db = get_exchange_db()
    if symbol:
        normalized = _norm(symbol)
        rows = db.fetch_all(
            "SELECT symbol, exchange, funding_rate, mark_price, timestamp "
            "FROM latest_funding_rates WHERE symbol = ? ORDER BY exchange",
            (normalized,),
        )
    else:
        rows = db.fetch_all(
            "SELECT symbol, exchange, funding_rate, mark_price, timestamp "
            "FROM latest_funding_rates ORDER BY symbol, exchange",
            (),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No funding rate data.")
    return {"count": len(rows), "funding_rates": [dict(r) for r in rows]}


@router.get("/open-interest")
def get_open_interest(
    symbol: str | None = Query(None, description="指定资产"),
) -> dict[str, Any]:
    """最新持仓量。"""
    db = get_exchange_db()
    if symbol:
        normalized = _norm(symbol)
        rows = db.fetch_all(
            "SELECT symbol, exchange, open_interest, open_interest_usd, timestamp "
            "FROM latest_open_interest_snapshots WHERE symbol = ? ORDER BY exchange",
            (normalized,),
        )
    else:
        rows = db.fetch_all(
            "SELECT symbol, exchange, open_interest, open_interest_usd, timestamp "
            "FROM latest_open_interest_snapshots ORDER BY symbol",
            (),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No open interest data.")
    return {"count": len(rows), "open_interest": [dict(r) for r in rows]}


@router.get("/depth/{symbol}")
def get_depth(
    symbol: str,
    levels: int = Query(20, ge=1, le=100, description="档位数"),
) -> dict[str, Any]:
    """深度盘口快照。"""
    normalized = _norm(symbol)
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT side, price, quantity, cumulative_qty "
        "FROM depth_levels WHERE symbol = ? ORDER BY side, price LIMIT ?",
        (normalized, levels * 2),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No depth data.")
    bids = [dict(r) for r in rows if r["side"] == "bid"]
    asks = [dict(r) for r in rows if r["side"] == "ask"]
    return {"symbol": normalized, "bids": bids[:levels], "asks": asks[:levels]}


@router.get("/info")
def get_market_info() -> dict[str, Any]:
    """资产元数据。"""
    db = get_exchange_db()
    rows = db.fetch_all("SELECT * FROM market_info ORDER BY symbol", ())
    return {"count": len(rows), "assets": [dict(r) for r in rows]}


@router.get("/announcements")
def get_announcements(
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """最新交易所公告。"""
    db = get_market_db()
    if exchange:
        rows = db.fetch_all(
            "SELECT title, exchange, category, url, published_at "
            "FROM exchange_announcements WHERE exchange = ? "
            "ORDER BY published_at DESC LIMIT ?",
            (exchange, limit),
        )
    else:
        rows = db.fetch_all(
            "SELECT title, exchange, category, url, published_at "
            "FROM exchange_announcements ORDER BY published_at DESC LIMIT ?",
            (limit,),
        )
    return {"count": len(rows), "announcements": [dict(r) for r in rows]}


@router.get("/announcements/listings")
def get_listings(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """上币/下币事件。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT token, exchange, event_type, effective_at, announced_at "
        "FROM listing_events ORDER BY announced_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "listings": [dict(r) for r in rows]}
