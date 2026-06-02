"""Onchain Holder 路由 — 链上持有者数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/onchain-holder", tags=["onchain-holder"])


@router.get("/distribution")
def get_holder_distribution(
    symbol: str = Query("BTC", description="资产符号"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """持有者分布数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM holder_distribution WHERE symbol = ? "
        "ORDER BY collected_at DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "distribution": rows}


@router.get("/metrics")
def get_holder_metrics(
    symbol: str = Query("BTC", description="资产符号"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """链上指标（MVRV/SOPR/NUPL）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM holder_metrics WHERE symbol = ? "
        "ORDER BY collected_at DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "metrics": rows}


@router.get("/metrics/latest")
def get_latest_metrics(
    symbol: str = Query("BTC", description="资产符号"),
) -> dict[str, Any]:
    """最新链上指标快照。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM holder_metrics WHERE symbol = ? "
        "ORDER BY collected_at DESC LIMIT 1",
        (symbol.upper(),),
    )
    if not rows:
        return {"symbol": symbol.upper(), "status": "no_data"}
    return {"symbol": symbol.upper(), "latest": rows[0]}


@router.get("/structure-change")
def get_structure_change(
    symbol: str = Query("BTC", description="资产符号"),
    hours: int = Query(24, ge=1, le=168, description="回溯小时数"),
) -> dict[str, Any]:
    """持有者结构变化趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT holder_category, supply_pct, collected_at FROM holder_distribution "
        "WHERE symbol = ? ORDER BY collected_at DESC LIMIT ?",
        (symbol.upper(), hours * 3),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "changes": rows}


@router.get("/context")
def get_onchain_holder_context() -> dict[str, Any]:
    """链上持有者 AI 上下文 bundle。"""
    from data_layer.onchain_holder_data.service import OnchainHolderDataService
    service = OnchainHolderDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
