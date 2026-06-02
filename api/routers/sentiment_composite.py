"""Sentiment Composite 路由 — 综合情绪分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/sentiment-composite", tags=["sentiment-composite"])


@router.get("/state")
def get_current_state() -> dict[str, Any]:
    """当前综合情绪状态。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM composite_sentiment_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"state": rows[0]}


@router.get("/history")
def get_state_history(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """综合情绪历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM composite_sentiment_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/score")
def get_composite_score() -> dict[str, Any]:
    """当前综合情绪评分。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, composite_score, extreme_label, funding_consistency "
        "FROM composite_sentiment_states ORDER BY ts DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"score": rows[0]}


@router.get("/divergence")
def get_divergence_signals(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """情绪-价格背离信号。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT ts, divergence_type, divergence_strength, reversal_probability "
        "FROM composite_sentiment_states WHERE divergence_type != 'none' "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "divergences": rows}


@router.get("/context")
def get_sentiment_composite_context() -> dict[str, Any]:
    """综合情绪 AI 上下文 bundle。"""
    from logic_layer.market_sentiment_composite.service import MarketSentimentCompositeService
    service = MarketSentimentCompositeService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
