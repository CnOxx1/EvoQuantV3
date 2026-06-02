"""Derivatives Sentiment 路由 — 衍生品情绪数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/derivatives-sentiment", tags=["derivatives-sentiment"])


@router.get("/fear-greed")
def get_fear_greed(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """恐惧贪婪指数历史。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM sentiment_index ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "fear_greed": rows}


@router.get("/fear-greed/latest")
def get_latest_fear_greed() -> dict[str, Any]:
    """最新恐惧贪婪指数。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM sentiment_index ORDER BY collected_at DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"latest": rows[0]}


@router.get("/long-short")
def get_long_short_ratios(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """多空比历史数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT btc_long_short_ratio, eth_long_short_ratio, collected_at "
        "FROM derivatives_sentiment ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "ratios": rows}


@router.get("/open-interest")
def get_open_interest(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """全市场未平仓合约。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT total_open_interest_usd, oi_change_24h, estimated_leverage_ratio, collected_at "
        "FROM derivatives_sentiment ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "open_interest": rows}


@router.get("/context")
def get_derivatives_sentiment_context() -> dict[str, Any]:
    """衍生品情绪 AI 上下文 bundle。"""
    from data_layer.derivatives_sentiment_data.service import DerivativesSentimentDataService
    service = DerivativesSentimentDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
