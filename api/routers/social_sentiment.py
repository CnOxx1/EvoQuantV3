"""Social Sentiment 路由 — 社交媒体情绪分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/social-sentiment", tags=["social-sentiment"])


@router.get("/score/{symbol}")
def get_sentiment_score(symbol: str) -> dict[str, Any]:
    """单资产社交情绪评分。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    row = db.fetch_one(
        "SELECT * FROM social_sentiment_agg WHERE entity_key = ? ORDER BY ts DESC LIMIT 1",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No sentiment data for {symbol}")
    return {
        "symbol": normalized,
        "ts": row.get("ts"),
        "avg_sentiment": _safe_float(row.get("avg_sentiment")),
        "weighted_sentiment": _safe_float(row.get("weighted_sentiment")),
        "bullish_ratio": _safe_float(row.get("bullish_ratio")),
        "bearish_ratio": _safe_float(row.get("bearish_ratio")),
        "mention_count": row.get("mention_count"),
        "kol_sentiment": _safe_float(row.get("kol_sentiment")),
        "volume_zscore": _safe_float(row.get("volume_zscore")),
        "data_source": "social_sentiment_data",
    }


@router.get("/history/{symbol}")
def get_sentiment_history(
    symbol: str,
    limit: int = Query(50, ge=1, le=500, description="返回最近 N 条记录"),
) -> dict[str, Any]:
    """单资产社交情绪时序。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT ts, avg_sentiment, weighted_sentiment, bullish_ratio, bearish_ratio, "
        "mention_count, volume_zscore FROM social_sentiment_agg "
        "WHERE entity_key = ? ORDER BY ts DESC LIMIT ?",
        (normalized, limit),
    )
    return {"symbol": normalized, "count": len(rows), "history": rows}


@router.get("/ranking")
def get_sentiment_ranking() -> dict[str, Any]:
    """全资产社交情绪排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT entity_key, weighted_sentiment, mention_count, bullish_ratio, "
        "volume_zscore, ts FROM social_sentiment_agg "
        "WHERE ts = (SELECT MAX(ts) FROM social_sentiment_agg AS sub "
        "WHERE sub.entity_key = social_sentiment_agg.entity_key) "
        "ORDER BY weighted_sentiment DESC",
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/summary")
def get_sentiment_summary() -> dict[str, Any]:
    """市场整体社交情绪概览。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT entity_key, avg_sentiment, weighted_sentiment, bullish_ratio, "
        "bearish_ratio, mention_count, volume_zscore FROM social_sentiment_agg "
        "WHERE ts = (SELECT MAX(ts) FROM social_sentiment_agg AS sub "
        "WHERE sub.entity_key = social_sentiment_agg.entity_key)",
    )
    if not rows:
        return {"status": "no_data", "assets_covered": 0}
    total_mentions = sum(r.get("mention_count", 0) or 0 for r in rows)
    avg_weighted = sum(_safe_float(r.get("weighted_sentiment")) or 0 for r in rows) / len(rows)
    bullish_count = sum(1 for r in rows if (_safe_float(r.get("bullish_ratio")) or 0) > 0.6)
    bearish_count = sum(1 for r in rows if (_safe_float(r.get("bearish_ratio")) or 0) > 0.6)
    return {
        "assets_covered": len(rows),
        "total_mentions": total_mentions,
        "market_avg_sentiment": round(avg_weighted, 4),
        "bullish_assets": bullish_count,
        "bearish_assets": bearish_count,
        "neutral_assets": len(rows) - bullish_count - bearish_count,
        "market_mood": "bullish" if avg_weighted > 0.2 else ("bearish" if avg_weighted < -0.2 else "neutral"),
        "data_source": "social_sentiment_data",
    }
