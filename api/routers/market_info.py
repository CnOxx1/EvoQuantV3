"""Market Info 路由 — 交易对元数据（费率、精度、合约信息）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db

router = APIRouter(prefix="/market-info", tags=["market-info"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/")
def get_all_market_info(
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(500, ge=1, le=5000, description="返回条数"),
) -> dict[str, Any]:
    """返回所有交易对的市场元数据（费率、精度、合约信息）。"""
    db = get_exchange_db()
    if exchange:
        rows = db.fetch_all(
            """SELECT symbol, exchange, base, quote, market_type, status,
                      is_spot, is_swap, is_linear, price_precision,
                      amount_precision, min_amount, maker_fee, taker_fee,
                      contract_size
               FROM market_info
               WHERE exchange = ?
               ORDER BY symbol
               LIMIT ?""",
            (exchange, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT symbol, exchange, base, quote, market_type, status,
                      is_spot, is_swap, is_linear, price_precision,
                      amount_precision, min_amount, maker_fee, taker_fee,
                      contract_size
               FROM market_info
               ORDER BY symbol
               LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No market info found.")
    return {"count": len(rows), "markets": [dict(r) for r in rows]}


@router.get("/{symbol}")
def get_symbol_market_info(symbol: str) -> dict[str, Any]:
    """返回指定资产在各交易所的市场元数据。"""
    normalized = _normalize_symbol(symbol)
    db = get_exchange_db()
    rows = db.fetch_all(
        """SELECT symbol, exchange, base, quote, market_type, status,
                  is_spot, is_swap, is_linear, price_precision,
                  amount_precision, min_amount, maker_fee, taker_fee,
                  contract_size
           FROM market_info
           WHERE symbol = ?
           ORDER BY exchange""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No market info for '{normalized}'.")
    return {"symbol": normalized, "count": len(rows), "exchanges": [dict(r) for r in rows]}
