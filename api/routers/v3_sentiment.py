"""v3 Sentiment — 情绪与新闻统一入口。

端点：
  /sentiment/news            — 最新新闻
  /sentiment/news/{symbol}   — 资产相关新闻
  /sentiment/composite       — 综合情绪评分
  /sentiment/retail-fomo     — FOMO/FUD 指数
  /sentiment/prediction-markets — 预测市场
  /sentiment/movers          — 概率变动
  /sentiment/breadth         — 市场广度
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/news")
def get_news(
    sentiment: str | None = Query(None, description="过滤: positive/negative/neutral"),
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """最新新闻及情感标注。"""
    db = get_market_db()
    params: list[Any] = []
    where = "1=1"
    if sentiment:
        where += " AND sentiment_label = ?"
        params.append(sentiment)
    params.append(limit)
    rows = db.fetch_all(
        f"SELECT id, title, summary, source, published_at, sentiment_label, category "
        f"FROM news_articles WHERE {where} ORDER BY published_at DESC LIMIT ?",
        params,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No news found.")
    return {"count": len(rows), "news": [dict(r) for r in rows]}


@router.get("/news/{symbol}")
def get_news_by_asset(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """指定资产相关新闻。"""
    base = symbol.upper().replace("/USDT", "").replace("-USDT", "")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT id, title, summary, source, published_at, sentiment_label, category "
        "FROM news_articles WHERE (title LIKE ? OR summary LIKE ?) "
        "ORDER BY published_at DESC LIMIT ?",
        (f"%{base}%", f"%{base}%", limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No news for {base}.")
    return {"asset": base, "count": len(rows), "news": [dict(r) for r in rows]}


@router.get("/composite")
def get_composite() -> dict[str, Any]:
    """综合情绪评分（恐惧贪婪指数）。"""
    db = get_market_db()
    row = db.fetch_one(
        "SELECT fear_greed_index, fear_greed_class, collected_at "
        "FROM sentiment_index ORDER BY collected_at DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No composite sentiment data.")
    return dict(row)


@router.get("/retail-fomo")
def get_retail_fomo() -> dict[str, Any]:
    """散户 FOMO/FUD 指数。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM retail_fomo_states ORDER BY ts DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No retail FOMO data.")
    return dict(row)


@router.get("/prediction-markets")
def get_prediction_markets(
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """活跃预测市场。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT market_id, question, probability, volume_usd, category, updated_at "
        "FROM prediction_markets ORDER BY volume_usd DESC LIMIT ?",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No prediction market data.")
    return {"count": len(rows), "markets": [dict(r) for r in rows]}


@router.get("/movers")
def get_probability_movers(
    limit: int = Query(10, ge=1, le=50, description="条数"),
) -> dict[str, Any]:
    """预测市场概率变动 Top N。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT m.market_id, m.question, m.probability, "
        "h.probability AS prev_probability, m.category "
        "FROM prediction_markets m "
        "LEFT JOIN prediction_market_history h ON m.market_id = h.market_id "
        "ORDER BY ABS(m.probability - COALESCE(h.probability, m.probability)) DESC "
        "LIMIT ?",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No movers data.")
    return {"count": len(rows), "movers": [dict(r) for r in rows]}


@router.get("/breadth")
def get_market_breadth() -> dict[str, Any]:
    """市场广度快照。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM market_breadth_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No breadth data.")
    return dict(row)
