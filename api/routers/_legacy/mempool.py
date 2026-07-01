"""Mempool 路由 — 内存池数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/mempool", tags=["mempool"])


@router.get("/snapshots")
def get_mempool_snapshots(
    limit: int = Query(60, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """内存池快照历史。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM mempool_snapshots ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "snapshots": rows}


@router.get("/fees")
def get_fee_trends(
    limit: int = Query(60, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """手续费趋势数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT fee_rate_fastest, fee_rate_median, fee_rate_slow, collected_at "
        "FROM mempool_snapshots ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "fees": rows}


@router.get("/large-txs")
def get_large_transactions(
    min_value: float = Query(10.0, description="最小 BTC 价值"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """大额待确认交易。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM pending_large_txs WHERE value_btc >= ? "
        "ORDER BY value_btc DESC LIMIT ?",
        (min_value, limit),
    )
    return {"count": len(rows), "transactions": rows}


@router.get("/pressure")
def get_mempool_pressure() -> dict[str, Any]:
    """内存池压力指数（最新快照）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM mempool_snapshots ORDER BY collected_at DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    latest = rows[0]
    pending = _safe_float(latest.get("pending_count")) or 0
    vsize = _safe_float(latest.get("pending_vsize_mb")) or 0
    # Pressure index: 0-100 based on vsize (300MB = extreme)
    pressure = min(100.0, (vsize / 300.0) * 100.0)
    return {
        "pressure_index": round(pressure, 1),
        "pending_count": int(pending),
        "pending_vsize_mb": round(vsize, 2),
        "snapshot": latest,
    }


@router.get("/context")
def get_mempool_context() -> dict[str, Any]:
    """内存池 AI 上下文 bundle。"""
    from data_layer.mempool_data.service import MempoolDataService
    service = MempoolDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
