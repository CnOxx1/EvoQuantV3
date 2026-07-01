"""Prediction Market 路由 — 预测市场数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/prediction-market", tags=["prediction-market"])


@router.get("/active")
def get_active_markets(
    category: str | None = Query(None, description="按类别过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """当前活跃的预测市场。"""
    db = get_market_db()
    # v4.3.0: SELECT * → column projection
    sql = ("SELECT market_id, title, category, probability, volume_24h, "
           "liquidity, last_trade_time FROM prediction_markets WHERE 1=1")
    params: list[Any] = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY volume_24h DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "markets": rows}


@router.get("/crypto")
def get_crypto_markets(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """与加密货币相关的预测市场。"""
    db = get_market_db()
    # v4.3.0: SELECT * → column projection
    rows = db.fetch_all(
        "SELECT market_id, title, probability, volume_24h, liquidity, last_trade_time "
        "FROM prediction_markets WHERE category = 'crypto' "
        "ORDER BY volume_24h DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "markets": rows}


@router.get("/history/{market_id}")
def get_market_history(
    market_id: str,
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """单个市场的概率历史。"""
    db = get_market_db()
    # v4.3.0: SELECT * → column projection
    rows = db.fetch_all(
        "SELECT market_id, probability, volume, collected_at "
        "FROM prediction_market_history WHERE market_id = ? "
        "ORDER BY collected_at DESC LIMIT ?",
        (market_id, limit),
    )
    return {"market_id": market_id, "count": len(rows), "history": rows}


@router.get("/movers")
def get_probability_movers(
    min_change: float = Query(0.05, description="最小概率变化阈值"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """概率变化最大的市场。"""
    db = get_market_db()
    # v4.4.0: SELECT m.* → column projection
    rows = db.fetch_all(
        """SELECT m.market_id, m.title, m.category, m.probability, m.volume_24h,
                  h.outcome_yes_price as prev_yes_price
           FROM prediction_markets m
           LEFT JOIN prediction_market_history h ON m.market_id = h.market_id
           ORDER BY m.volume_24h DESC LIMIT ?""",
        (limit,),
    )
    return {"count": len(rows), "movers": rows}


@router.get("/context")
def get_prediction_market_context() -> dict[str, Any]:
    """预测市场 AI 上下文 bundle。"""
    from data_layer.prediction_market_data.service import PredictionMarketDataService
    service = PredictionMarketDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
