"""Exchange 路由 — 交易所数据（资金费率、订单簿、Ticker、交易所对比快照）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_exchange_db
from config.symbols import TARGET_EXCHANGES, TARGET_SYMBOLS

router = APIRouter(prefix="/exchange", tags=["exchange"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/funding/{symbol}")
def get_funding_rates(
    symbol: str,
    limit: int = Query(1, ge=1, le=200, description="返回最近 N 条资金费率"),
) -> dict[str, Any]:
    """返回指定资产的资金费率（含各交易所对比）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()

    if limit == 1:
        rows = db.fetch_all(
            """SELECT exchange, funding_rate, mark_price, index_price, timestamp
               FROM latest_funding_rates
               WHERE symbol = ?
               ORDER BY timestamp DESC""",
            (normalized,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="No funding rate data found.")

        by_exchange = {r["exchange"]: dict(r) for r in rows}
        rates = [r["funding_rate"] for r in rows if r["funding_rate"] is not None]
        avg_rate = sum(rates) / len(rates) if rates else None
        return {
            "symbol": normalized,
            "average_funding_rate": round(avg_rate, 6) if avg_rate else None,
            "annualized_rate": round(avg_rate * 3 * 365, 4) if avg_rate else None,
            "is_elevated": abs(avg_rate) > 0.001 if avg_rate else False,
            "by_exchange": by_exchange,
        }
    else:
        rows = db.fetch_all(
            """SELECT exchange, funding_rate, mark_price, timestamp
               FROM funding_rates
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, limit),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="No funding rate history found.")
        records = [dict(r) for r in rows]
        records.reverse()
        return {
            "symbol": normalized,
            "count": len(records),
            "history": records,
        }


@router.get("/funding")
def get_all_funding_rates() -> dict[str, Any]:
    """返回所有资产的最新资金费率摘要。"""
    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, funding_rate, mark_price, timestamp
           FROM latest_funding_rates
           ORDER BY symbol, exchange""",
        (),
    )

    result: dict[str, Any] = {}
    for row in rows:
        sym = row["symbol"]
        if sym not in result:
            result[sym] = {"rates": {}, "avg_rate": None}
        result[sym]["rates"][row["exchange"]] = {
            "funding_rate": row["funding_rate"],
            "mark_price": row["mark_price"],
            "timestamp": row["timestamp"],
        }

    for sym, data in result.items():
        rates = [v["funding_rate"] for v in data["rates"].values() if v["funding_rate"] is not None]
        if rates:
            avg = sum(rates) / len(rates)
            data["avg_rate"] = round(avg, 6)
            data["annualized_rate"] = round(avg * 3 * 365, 4)
            data["is_elevated"] = abs(avg) > 0.001

    return {
        "symbol_count": len(result),
        "funding_rates": result,
    }


@router.get("/orderbook/{symbol}")
def get_orderbook(symbol: str) -> dict[str, Any]:
    """返回指定资产的最新订单簿快照（多交易所）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT exchange, mid_price, spread_bps, bid_depth_notional,
                  ask_depth_notional, depth_imbalance, timestamp
           FROM latest_orderbook_snapshots
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No orderbook data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    spreads = [r["spread_bps"] for r in rows if r["spread_bps"] is not None]
    imbalances = [r["depth_imbalance"] for r in rows if r["depth_imbalance"] is not None]

    return {
        "symbol": normalized,
        "avg_spread_bps": round(sum(spreads) / len(spreads), 3) if spreads else None,
        "avg_depth_imbalance": round(sum(imbalances) / len(imbalances), 4) if imbalances else None,
        "by_exchange": by_exchange,
    }


@router.get("/ticker/{symbol}")
def get_ticker(symbol: str) -> dict[str, Any]:
    """返回指定资产的最新 Ticker（价格、成交量、涨跌幅）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT exchange, last_price, mid_price, spread_bps,
                  quote_volume_24h, change_24h, vwap_24h, timestamp
           FROM latest_tickers
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No ticker data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    prices = [r["last_price"] for r in rows if r["last_price"] is not None]
    volumes = [r["quote_volume_24h"] for r in rows if r["quote_volume_24h"] is not None]
    changes = [r["change_24h"] for r in rows if r["change_24h"] is not None]

    return {
        "symbol": normalized,
        "avg_price": round(sum(prices) / len(prices), 6) if prices else None,
        "total_volume_24h": sum(volumes) if volumes else None,
        "avg_change_24h": round(sum(changes) / len(changes), 4) if changes else None,
        "by_exchange": by_exchange,
    }


@router.get("/comparison/{symbol}")
def get_exchange_comparison(symbol: str) -> dict[str, Any]:
    """返回指定资产的跨交易所对比快照（价差、执行偏好、流动性语境）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM exchange_comparison_snapshots
           WHERE symbol = ?
           ORDER BY snapshot_time DESC LIMIT 1""",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No exchange comparison data found.")

    data = dict(row)
    for field in ("exchange_details_json", "execution_preference_json"):
        if data.get(field):
            try:
                key = field.replace("_json", "")
                data[key] = json.loads(data[field])
                del data[field]
            except (json.JSONDecodeError, KeyError):
                pass

    return data


@router.get("/open-interest/{symbol}")
def get_open_interest(symbol: str) -> dict[str, Any]:
    """返回指定资产的持仓量快照。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT exchange, open_interest, open_interest_value, timestamp
           FROM latest_open_interest_snapshots
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No open interest data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    total_oi_value = sum(
        r["open_interest_value"]
        for r in rows
        if r["open_interest_value"] is not None
    )

    return {
        "symbol": normalized,
        "total_oi_value_usd": total_oi_value,
        "by_exchange": by_exchange,
    }


@router.get("/liquidations/{symbol}")
def get_liquidations(symbol: str) -> dict[str, Any]:
    """返回指定资产的最新清算数据。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT exchange, long_liq_value, short_liq_value,
                  net_liq_value, total_liq_value, timestamp
           FROM latest_liquidation_bars
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No liquidation data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    total_liq = sum(r["total_liq_value"] for r in rows if r["total_liq_value"] is not None)

    return {
        "symbol": normalized,
        "total_liquidation_value_usd": total_liq,
        "by_exchange": by_exchange,
    }
