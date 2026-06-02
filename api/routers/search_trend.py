"""Search Trend 路由 — 搜索趋势数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/search-trend", tags=["search-trend"])


@router.get("/latest")
def get_latest_trends(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """最新搜索趋势分数。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM search_trends ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "trends": rows}


@router.get("/history")
def get_trend_history(
    keyword: str = Query("bitcoin", description="关键词"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """指定关键词的趋势历史。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM trend_history WHERE keyword = ? "
        "ORDER BY ts DESC LIMIT ?",
        (keyword.lower(), limit),
    )
    return {"keyword": keyword.lower(), "count": len(rows), "history": rows}


@router.get("/momentum")
def get_trend_momentum(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """搜索热度变化最大的关键词。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM search_trends "
        "ORDER BY ABS(interest_change_7d) DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "momentum": rows}


@router.get("/top")
def get_top_trending(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """搜索热度最高的关键词排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM search_trends ORDER BY interest_score DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "top": rows}


@router.get("/context")
def get_search_trend_context() -> dict[str, Any]:
    """搜索趋势 AI 上下文 bundle。"""
    from data_layer.search_trend_data.service import SearchTrendDataService
    service = SearchTrendDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
