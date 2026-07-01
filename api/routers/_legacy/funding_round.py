"""Funding Round 路由 — VC 融资数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/funding-round", tags=["funding-round"])


@router.get("/recent")
def get_recent_rounds(
    days: int = Query(30, ge=1, le=90, description="回溯天数"),
    category: str | None = Query(None, description="按类别过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """近期融资轮次。"""
    db = get_market_db()
    sql = "SELECT * FROM funding_rounds WHERE 1=1"
    params: list[Any] = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY amount_usd DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "rounds": rows}


@router.get("/top-investors")
def get_top_investors(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """活跃投资方排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM investor_activity "
        "WHERE collected_at = (SELECT MAX(collected_at) FROM investor_activity) "
        "ORDER BY total_invested_usd DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "investors": rows}


@router.get("/by-category")
def get_rounds_by_category() -> dict[str, Any]:
    """按赛道聚合融资数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT category, COUNT(*) as count, SUM(amount_usd) as total_usd "
        "FROM funding_rounds GROUP BY category ORDER BY total_usd DESC",
        (),
    )
    return {"count": len(rows), "categories": rows}


@router.get("/by-chain")
def get_rounds_by_chain() -> dict[str, Any]:
    """按链聚合融资数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT chain, COUNT(*) as count, SUM(amount_usd) as total_usd "
        "FROM funding_rounds WHERE chain != '' GROUP BY chain ORDER BY total_usd DESC",
        (),
    )
    return {"count": len(rows), "chains": rows}


@router.get("/context")
def get_funding_round_context() -> dict[str, Any]:
    """VC 融资 AI 上下文 bundle。"""
    from data_layer.funding_round_data.service import FundingRoundDataService
    service = FundingRoundDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
