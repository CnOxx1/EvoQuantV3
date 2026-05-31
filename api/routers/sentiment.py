"""Sentiment 路由 — 新闻情感分析与市场广度查询。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/news/latest")
def get_latest_news(
    symbol: str | None = Query(None, description="按资产过滤（如 BTC）"),
    sentiment: str | None = Query(None, description="按情感过滤: positive/negative/neutral"),
    limit: int = Query(20, ge=1, le=100, description="返回最近 N 条新闻"),
) -> dict[str, Any]:
    """返回最新新闻及情感标注结果。"""
    db = get_market_db()

    conditions = ["1=1"]
    params: list[Any] = []

    if symbol:
        base = symbol.upper().replace("/USDT", "").replace("-USDT", "")
        conditions.append("(title LIKE ? OR summary LIKE ?)")
        params.extend([f"%{base}%", f"%{base}%"])

    if sentiment:
        conditions.append("sentiment_label = ?")
        params.append(sentiment)

    where_clause = " AND ".join(conditions)
    params.append(limit)

    rows = db.fetch_all(
        f"""SELECT id, title, summary, source, published_at,
                   sentiment_label, category, url
            FROM news_articles
            WHERE {where_clause}
            ORDER BY published_at DESC
            LIMIT ?""",
        params,
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No news articles found.")

    records = [dict(r) for r in rows]

    label_counts: dict[str, int] = {}
    for r in records:
        label = r.get("sentiment_label") or "unlabeled"
        label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "count": len(records),
        "sentiment_distribution": label_counts,
        "articles": records,
    }


@router.get("/news/score/{symbol}")
def get_news_sentiment_score(symbol: str) -> dict[str, Any]:
    """返回指定资产近期新闻情感评分（-1 极负 ~ +1 极正）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    base = symbol.upper().replace("/USDT", "").replace("-USDT", "")
    db = get_market_db()

    rows = db.fetch_all(
        """SELECT sentiment_label, COUNT(*) AS cnt
           FROM news_articles
           WHERE (title LIKE ? OR summary LIKE ?)
             AND published_at >= datetime('now', '-3 days')
           GROUP BY sentiment_label""",
        (f"%{base}%", f"%{base}%"),
    )

    if not rows:
        return {
            "symbol": normalized,
            "sentiment_score": None,
            "sentiment_label": "no_data",
            "article_count": 0,
            "distribution": {},
        }

    dist: dict[str, int] = {r["sentiment_label"] or "unlabeled": r["cnt"] for r in rows}
    total = sum(dist.values())

    pos = dist.get("positive", 0)
    neg = dist.get("negative", 0)
    score = (pos - neg) / total if total > 0 else 0.0

    if score > 0.3:
        label = "positive"
    elif score < -0.3:
        label = "negative"
    else:
        label = "neutral"

    return {
        "symbol": normalized,
        "sentiment_score": round(score, 3),
        "sentiment_label": label,
        "article_count": total,
        "distribution": dist,
        "window": "3d",
    }


@router.get("/market-breadth")
def get_market_breadth() -> dict[str, Any]:
    """返回最新市场广度快照（多空比、价格广度、新闻广度等）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM market_breadth_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No market breadth data found. Run logic_pipeline first.",
        )
    return dict(row)


@router.get("/market-breadth/history")
def get_market_breadth_history(
    limit: int = Query(48, ge=1, le=500, description="返回最近 N 条广度快照"),
) -> dict[str, Any]:
    """返回市场广度历史序列。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, breadth_status, asset_count,
                  ai_ready_asset_count, breadth_score, data_quality_flag
           FROM market_breadth_snapshots
           ORDER BY snapshot_time DESC
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No market breadth history found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {"count": len(records), "history": records}


@router.get("/summary")
def get_sentiment_summary() -> dict[str, Any]:
    """返回整体情感摘要（供 Bridge 和 Dashboard 使用）。"""
    db_market = get_market_db()
    db_analytics = get_analytics_db()

    rows = db_market.fetch_all(
        """SELECT sentiment_label, COUNT(*) AS cnt
           FROM news_articles
           WHERE published_at >= datetime('now', '-1 day')
           GROUP BY sentiment_label""",
        (),
    )
    dist: dict[str, int] = {r["sentiment_label"] or "unlabeled": r["cnt"] for r in rows}
    total = sum(dist.values())
    pos = dist.get("positive", 0)
    neg = dist.get("negative", 0)
    overall_score = round((pos - neg) / total, 3) if total > 0 else 0.0
    overall_label = "positive" if overall_score > 0.2 else "negative" if overall_score < -0.2 else "neutral"

    breadth_row = db_analytics.fetch_one(
        """SELECT breadth_status, breadth_score, asset_count, ai_ready_asset_count
           FROM market_breadth_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )

    return {
        "news_sentiment_24h": {
            "score": overall_score,
            "label": overall_label,
            "article_count": total,
            "distribution": dist,
        },
        "market_breadth": dict(breadth_row) if breadth_row else None,
    }


@router.get("/labels")
def get_sentiment_labels(
    symbol: str | None = Query(None, description="按资产过滤（如 BTC）"),
    sentiment: str | None = Query(None, description="按情感过滤: positive/negative/neutral"),
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """返回 AI 情感标注结果（含置信度和影响评估）。"""
    db = get_analytics_db()

    conditions = ["1=1"]
    params: list[Any] = []

    if symbol:
        base = symbol.upper().replace("/USDT", "").replace("-USDT", "")
        conditions.append("title LIKE ?")
        params.append(f"%{base}%")

    if sentiment:
        conditions.append("sentiment = ?")
        params.append(sentiment)

    where_clause = " AND ".join(conditions)
    params.append(limit)

    rows = db.fetch_all(
        f"""SELECT article_id, url_hash, title, sentiment, confidence,
                   event_type, impact_scope, impact_duration, labeled_at
            FROM news_sentiment_labels
            WHERE {where_clause}
            ORDER BY labeled_at DESC
            LIMIT ?""",
        params,
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No sentiment labels found.")
    return {"count": len(rows), "labels": [dict(r) for r in rows]}


@router.get("/signal/{symbol}")
def get_sentiment_signal(symbol: str) -> dict[str, Any]:
    """情绪-价格信号（reversal/confirmation/divergence）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM sentiment_signals WHERE symbol = ? ORDER BY ts DESC LIMIT 5",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No sentiment signal for {symbol}")
    latest = rows[0]
    return {
        "symbol": normalized,
        "ts": latest.get("ts"),
        "signal_type": latest.get("signal_type"),
        "confidence": latest.get("confidence"),
        "description": latest.get("description"),
        "recent_signals": rows,
        "data_source": "sentiment_signal",
    }


@router.get("/causality/{symbol}")
def get_causality(symbol: str) -> dict[str, Any]:
    """Granger 因果检验结果（情绪是否领先价格）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM sentiment_causality WHERE symbol = ? ORDER BY ts DESC LIMIT 1",
        (normalized,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No causality data for {symbol}")
    return {
        "symbol": normalized,
        "ts": row.get("ts"),
        "sentiment_leads_price": row.get("sentiment_leads_price"),
        "correlation": row.get("correlation"),
        "lag_periods": row.get("lag_periods"),
        "data_source": "sentiment_signal",
    }
