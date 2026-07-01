"""Whale Tracker 路由 — 巨鲸追踪端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/whale-tracker", tags=["whale-tracker"])


@router.get("/recent")
def get_recent_transactions(
    symbol: str | None = Query(None, description="按资产过滤"),
    tx_type: str | None = Query(None, description="按类型过滤: deposit/withdrawal/transfer"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近大额转账列表。"""
    db = get_market_db()
    sql = "SELECT * FROM whale_transactions WHERE 1=1"
    params: list[Any] = []
    if symbol:
        normalized = _normalize_symbol(symbol)
        sql += " AND entity_key = ?"
        params.append(normalized)
    if tx_type:
        sql += " AND tx_type = ?"
        params.append(tx_type)
    sql += " ORDER BY tx_time DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "transactions": rows}


@router.get("/flow/{symbol}")
def get_whale_flow(symbol: str) -> dict[str, Any]:
    """单资产巨鲸净流（deposit vs withdrawal）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    row = db.fetch_one(
        "SELECT * FROM whale_flow_agg WHERE entity_key = ? ORDER BY ts DESC LIMIT 1",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No whale flow data for {symbol}")
    return {
        "symbol": normalized,
        "ts": row.get("ts"),
        "total_volume_usd": _safe_float(row.get("total_volume_usd")),
        "deposit_volume_usd": _safe_float(row.get("deposit_volume_usd")),
        "withdrawal_volume_usd": _safe_float(row.get("withdrawal_volume_usd")),
        "net_flow_usd": _safe_float(row.get("net_flow_usd")),
        "tx_count": row.get("tx_count"),
        "unique_whales": row.get("unique_whales"),
        "largest_tx_usd": _safe_float(row.get("largest_tx_usd")),
        "flow_direction": row.get("flow_direction"),
        "data_source": "whale_tracker_data",
    }


@router.get("/ranking")
def get_whale_ranking() -> dict[str, Any]:
    """按 24h 巨鲸活跃度排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT entity_key, total_volume_usd, tx_count, net_flow_usd, "
        "flow_direction, ts FROM whale_flow_agg "
        "WHERE ts = (SELECT MAX(ts) FROM whale_flow_agg AS sub "
        "WHERE sub.entity_key = whale_flow_agg.entity_key) "
        "ORDER BY total_volume_usd DESC",
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/alerts")
def get_whale_alerts(
    min_usd: float = Query(5_000_000, description="最小金额阈值（USD）"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """异常大额转账预警。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM whale_transactions WHERE amount_usd >= ? "
        "ORDER BY tx_time DESC LIMIT ?",
        (min_usd, limit),
    )
    return {"threshold_usd": min_usd, "count": len(rows), "alerts": rows}
