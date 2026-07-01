"""Exchange 路由 — 交易所数据（资金费率、订单簿、Ticker、交易所对比快照）。"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.dependencies import get_analytics_db, get_exchange_db
from api.pagination import CursorParams, build_keyset_query, paginated_response
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


@router.get("/funding-rates/paginated/{symbol}")
def get_funding_rates_paginated(
    symbol: str,
    cursor: Optional[str] = Query(None, description="分页游标"),
    limit: int = Query(50, ge=1, le=1000, description="每页条数"),
) -> dict[str, Any]:
    """资金费率历史（游标分页）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    params = CursorParams(cursor=cursor, limit=limit)
    sql, sql_params = build_keyset_query(
        base_sql="SELECT rowid, exchange, funding_rate, mark_price, timestamp FROM funding_rates WHERE symbol = ?",
        base_params=(normalized,),
        cursor_params=params,
        timestamp_col="timestamp",
        id_col="rowid",
    )
    rows = db.fetch_all(sql, sql_params)
    return paginated_response(rows, params, timestamp_col="timestamp", id_col="rowid")


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

    # Compute averages using SQL aggregation for better performance
    agg_rows = db.fetch_all(
        """SELECT symbol, AVG(funding_rate) as avg_rate, COUNT(*) as cnt
           FROM latest_funding_rates
           WHERE funding_rate IS NOT NULL
           GROUP BY symbol""",
        (),
    )
    for agg in agg_rows:
        sym = agg["symbol"]
        if sym in result and agg["avg_rate"] is not None:
            avg = agg["avg_rate"]
            result[sym]["avg_rate"] = round(avg, 6)
            result[sym]["annualized_rate"] = round(avg * 3 * 365, 4)
            result[sym]["is_elevated"] = abs(avg) > 0.001

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
        """SELECT exchange, open_interest_contracts, open_interest_usd,
                  open_interest_change_5m, open_interest_change_1h,
                  open_interest_change_24h, timestamp
           FROM latest_open_interest_snapshots
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No open interest data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    total_oi_value = sum(
        r["open_interest_usd"]
        for r in rows
        if r["open_interest_usd"] is not None
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


@router.get("/trade-flow/{symbol}")
def get_trade_flow(symbol: str) -> dict[str, Any]:
    """返回指定资产的买卖压力（按交易所）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, market_type, interval, open_time,
                  trade_count, buy_notional, sell_notional,
                  net_taker_notional, cvd,
                  aggressive_buy_notional, aggressive_sell_notional
           FROM latest_trade_flow_bars
           WHERE symbol = ?
           ORDER BY open_time DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No trade flow data found.")

    by_exchange = {}
    for r in rows:
        ex = r["exchange"]
        if ex not in by_exchange:
            by_exchange[ex] = []
        by_exchange[ex].append(dict(r))

    return {"symbol": normalized, "exchange_count": len(by_exchange), "by_exchange": by_exchange}


@router.get("/basis/{symbol}")
def get_basis(symbol: str) -> dict[str, Any]:
    """返回指定资产的现货-期货基差（按交易所）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, timestamp, spot_price, mark_price,
                  index_price, basis_bps, annualized_basis_bps, funding_rate
           FROM latest_basis_snapshots
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No basis data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    basis_values = [r["basis_bps"] for r in rows if r["basis_bps"] is not None]
    avg_basis = sum(basis_values) / len(basis_values) if basis_values else None

    return {
        "symbol": normalized,
        "avg_basis_bps": round(avg_basis, 2) if avg_basis else None,
        "by_exchange": by_exchange,
    }


@router.get("/positioning/{symbol}")
def get_positioning(symbol: str) -> dict[str, Any]:
    """返回指定资产的多空比（按交易所）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, timestamp, long_ratio, short_ratio,
                  long_short_ratio, top_trader_long_ratio,
                  top_trader_short_ratio
           FROM latest_positioning_snapshots
           WHERE symbol = ?
           ORDER BY timestamp DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No positioning data found.")

    by_exchange = {r["exchange"]: dict(r) for r in rows}
    ls_ratios = [r["long_short_ratio"] for r in rows if r["long_short_ratio"] is not None]
    avg_ls = sum(ls_ratios) / len(ls_ratios) if ls_ratios else None

    return {
        "symbol": normalized,
        "avg_long_short_ratio": round(avg_ls, 4) if avg_ls else None,
        "by_exchange": by_exchange,
    }


@router.get("/klines/{symbol}")
def get_klines(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
    timeframe: str = Query("1h", description="K线周期"),
    limit: int = Query(500, ge=1, le=2000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的原始 OHLCV K线数据。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, timeframe, open_time,
                  open, high, low, close, volume
           FROM klines
           WHERE symbol = ? AND exchange = ? AND timeframe = ?
           ORDER BY open_time DESC
           LIMIT ?""",
        (normalized, exchange, timeframe, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No kline data found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "exchange": exchange, "timeframe": timeframe, "count": len(records), "klines": records}


@router.get("/tickers/history/{symbol}")
def get_ticker_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史 Ticker 快照。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, last_price, high_24h, low_24h,
                      vwap_24h, volume_24h, quote_volume_24h,
                      change_24h, spread_bps, timestamp
               FROM tickers
               WHERE symbol = ? AND exchange = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, last_price, high_24h, low_24h,
                      vwap_24h, volume_24h, quote_volume_24h,
                      change_24h, spread_bps, timestamp
               FROM tickers
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No ticker history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}


@router.get("/orderbook/history/{symbol}")
def get_orderbook_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史订单簿深度快照。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, mid_price, spread_bps,
                      bid_depth_notional, ask_depth_notional,
                      depth_imbalance, timestamp
               FROM orderbook_snapshots
               WHERE symbol = ? AND exchange = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, mid_price, spread_bps,
                      bid_depth_notional, ask_depth_notional,
                      depth_imbalance, timestamp
               FROM orderbook_snapshots
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No orderbook history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}


@router.get("/open-interest/history/{symbol}")
def get_open_interest_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史持仓量快照。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, timestamp, open_interest_contracts,
                      open_interest_usd, open_interest_change_5m,
                      open_interest_change_1h, open_interest_change_24h
               FROM open_interest_snapshots
               WHERE symbol = ? AND exchange = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, timestamp, open_interest_contracts,
                      open_interest_usd, open_interest_change_5m,
                      open_interest_change_1h, open_interest_change_24h
               FROM open_interest_snapshots
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No open interest history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}


@router.get("/positioning/history/{symbol}")
def get_positioning_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史多空比快照。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, timestamp, long_ratio, short_ratio,
                      long_short_ratio, top_trader_long_ratio,
                      top_trader_short_ratio
               FROM positioning_snapshots
               WHERE symbol = ? AND exchange = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, timestamp, long_ratio, short_ratio,
                      long_short_ratio, top_trader_long_ratio,
                      top_trader_short_ratio
               FROM positioning_snapshots
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No positioning history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}


@router.get("/basis/history/{symbol}")
def get_basis_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史基差快照。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, timestamp, spot_price, mark_price,
                      index_price, basis_bps, annualized_basis_bps,
                      funding_rate
               FROM basis_snapshots
               WHERE symbol = ? AND exchange = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, timestamp, spot_price, mark_price,
                      index_price, basis_bps, annualized_basis_bps,
                      funding_rate
               FROM basis_snapshots
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No basis history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}


@router.get("/trade-flow/history/{symbol}")
def get_trade_flow_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史交易流数据。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, market_type, interval, open_time,
                      trade_count, buy_notional, sell_notional,
                      net_taker_notional, cvd,
                      aggressive_buy_notional, aggressive_sell_notional
               FROM trade_flow_bars
               WHERE symbol = ? AND exchange = ?
               ORDER BY open_time DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, market_type, interval, open_time,
                      trade_count, buy_notional, sell_notional,
                      net_taker_notional, cvd,
                      aggressive_buy_notional, aggressive_sell_notional
               FROM trade_flow_bars
               WHERE symbol = ?
               ORDER BY open_time DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No trade flow history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}


@router.get("/liquidations/history/{symbol}")
def get_liquidations_history(
    symbol: str,
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
) -> dict[str, Any]:
    """返回指定资产的历史清算数据。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, open_time,
                      long_liquidation_notional, short_liquidation_notional,
                      total_liquidation_notional,
                      max_single_liquidation_notional
               FROM liquidation_bars
               WHERE symbol = ? AND exchange = ?
               ORDER BY open_time DESC
               LIMIT ?""",
            (normalized, exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, open_time,
                      long_liquidation_notional, short_liquidation_notional,
                      total_liquidation_notional,
                      max_single_liquidation_notional
               FROM liquidation_bars
               WHERE symbol = ?
               ORDER BY open_time DESC
               LIMIT ?""",
            (normalized, limit),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No liquidation history found.")
    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "history": records}