"""News Intel 路由 — 新闻情报端点。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/news-intel", tags=["news-intel"])


def _parse_relevance_symbols(raw: str | None) -> list[str]:
    """Parse relevance_symbols field (may be JSON array or comma-separated)."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [s.strip().upper() for s in parsed if isinstance(s, str) and s.strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@router.get("/signal")
def news_signal(
    hours: int = Query(24, ge=1, le=168, description="回溯小时数"),
) -> dict[str, Any]:
    """新闻驱动交易信号（加权情感动量）。"""
    market_db = get_market_db()
    analytics_db = get_analytics_db()

    articles = market_db.fetch_all(
        "SELECT id, title, sentiment_label, relevance_symbols, published_at "
        "FROM news_articles WHERE published_at >= datetime('now', ?) "
        "ORDER BY published_at DESC",
        (f"-{hours} hours",),
    )
    # Get sentiment labels from analytics
    labels = analytics_db.fetch_all(
        "SELECT url_hash, sentiment, confidence, event_type, impact_scope "
        "FROM news_sentiment_labels",
    )
    label_map = {l["url_hash"]: l for l in labels} if labels else {}

    sentiment_scores = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}
    symbol_signals: dict[str, dict] = {}

    for art in articles:
        symbols_str = art["relevance_symbols"] or ""
        sentiment = (art["sentiment_label"] or "neutral").lower()
        score = sentiment_scores.get(sentiment, 0.0)

        for sym in _parse_relevance_symbols(symbols_str):
            if not sym:
                continue
            entry = symbol_signals.setdefault(sym, {"scores": [], "count": 0})
            entry["scores"].append(score)
            entry["count"] += 1

    # Compute signals
    signals = []
    for sym, data in symbol_signals.items():
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0.0
        momentum = avg_score * data["count"]  # weighted by volume
        signal = "bullish" if avg_score > 0.3 else "bearish" if avg_score < -0.3 else "neutral"
        signals.append({
            "symbol": sym, "article_count": data["count"],
            "avg_sentiment": round(avg_score, 3),
            "momentum": round(momentum, 3), "signal": signal,
        })

    signals.sort(key=lambda x: abs(x["momentum"]), reverse=True)
    return {
        "hours": hours, "total_articles": len(articles),
        "symbols_with_signal": len(signals), "signals": signals[:30],
    }


@router.get("/events/upcoming")
def upcoming_events(
    days: int = Query(7, ge=1, le=30, description="未来天数"),
) -> dict[str, Any]:
    """即将到来的市场事件（解锁、日历）。"""
    market_db = get_market_db()

    unlocks = market_db.fetch_all(
        "SELECT asset, event_type, scheduled_at, unlock_amount, unlock_value_usd, "
        "unlock_pct_float, beneficiary_group, status FROM token_unlock_events "
        "WHERE scheduled_at >= datetime('now') AND scheduled_at <= datetime('now', ?) "
        "ORDER BY scheduled_at ASC",
        (f"+{days} days",),
    )
    calendar = market_db.fetch_all(
        "SELECT event_type, title, symbol, scheduled_at, importance_score, status "
        "FROM event_calendar_events "
        "WHERE scheduled_at >= datetime('now') AND scheduled_at <= datetime('now', ?) "
        "ORDER BY scheduled_at ASC",
        (f"+{days} days",),
    )

    unlock_data = [
        {
            "asset": r["asset"], "type": r["event_type"],
            "scheduled_at": r["scheduled_at"],
            "value_usd": _safe_float(r["unlock_value_usd"]),
            "pct_float": _safe_float(r["unlock_pct_float"]),
            "beneficiary": r["beneficiary_group"],
        }
        for r in unlocks
    ]
    calendar_data = [
        {
            "title": r["title"], "type": r["event_type"],
            "symbol": r["symbol"], "scheduled_at": r["scheduled_at"],
            "importance": _safe_float(r["importance_score"]),
        }
        for r in calendar
    ]
    return {
        "days_ahead": days,
        "unlock_events": len(unlock_data), "calendar_events": len(calendar_data),
        "unlocks": unlock_data, "calendar": calendar_data,
    }


@router.get("/narrative/{symbol}")
def narrative(
    symbol: str,
    hours: int = Query(72, ge=1, le=336, description="回溯小时数"),
) -> dict[str, Any]:
    """单资产主导叙事提取。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    market_db = get_market_db()
    # Search by symbol in relevance_symbols
    base = normalized.split("/")[0]  # BTC from BTC/USDT
    articles = market_db.fetch_all(
        "SELECT title, summary, category, sentiment_label, tags, published_at "
        "FROM news_articles WHERE relevance_symbols LIKE ? "
        "AND published_at >= datetime('now', ?) ORDER BY published_at DESC LIMIT 50",
        (f"%{base}%", f"-{hours} hours"),
    )
    if not articles:
        return {"symbol": normalized, "hours": hours, "articles": 0, "narratives": []}

    # Extract dominant themes from categories/tags
    theme_counts: dict[str, int] = {}
    sentiments: list[str] = []
    for art in articles:
        cat = art["category"] or "general"
        theme_counts[cat] = theme_counts.get(cat, 0) + 1
        tags = art["tags"] or ""
        for tag in tags.split(","):
            tag = tag.strip().lower()
            if tag:
                theme_counts[tag] = theme_counts.get(tag, 0) + 1
        sentiments.append((art["sentiment_label"] or "neutral").lower())

    top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    bullish_pct = sentiments.count("bullish") / len(sentiments) * 100 if sentiments else 0
    bearish_pct = sentiments.count("bearish") / len(sentiments) * 100 if sentiments else 0

    return {
        "symbol": normalized, "hours": hours, "article_count": len(articles),
        "bullish_pct": round(bullish_pct, 1), "bearish_pct": round(bearish_pct, 1),
        "dominant_themes": [{"theme": t[0], "count": t[1]} for t in top_themes],
        "recent_titles": [a["title"] for a in articles[:10]],
    }


@router.get("/cross-asset-sentiment")
def cross_asset_sentiment(
    hours: int = Query(24, ge=1, le=168, description="回溯小时数"),
) -> dict[str, Any]:
    """全资产情感热力图。"""
    market_db = get_market_db()

    articles = market_db.fetch_all(
        "SELECT sentiment_label, relevance_symbols FROM news_articles "
        "WHERE published_at >= datetime('now', ?) ORDER BY published_at DESC",
        (f"-{hours} hours",),
    )
    if not articles:
        return {"hours": hours, "assets": []}

    sentiment_scores = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}
    asset_sentiments: dict[str, list[float]] = {}

    for art in articles:
        symbols_str = art["relevance_symbols"] or ""
        sentiment = (art["sentiment_label"] or "neutral").lower()
        score = sentiment_scores.get(sentiment, 0.0)
        for sym in _parse_relevance_symbols(symbols_str):
            if sym:
                asset_sentiments.setdefault(sym, []).append(score)

    assets = []
    for sym, scores in asset_sentiments.items():
        avg = sum(scores) / len(scores)
        assets.append({
            "symbol": sym, "article_count": len(scores),
            "avg_sentiment": round(avg, 3),
            "bullish_ratio": round(sum(1 for s in scores if s > 0) / len(scores), 3),
            "bearish_ratio": round(sum(1 for s in scores if s < 0) / len(scores), 3),
        })

    assets.sort(key=lambda x: x["article_count"], reverse=True)
    return {"hours": hours, "total_articles": len(articles), "assets": assets[:30]}


@router.get("/regulatory-radar")
def regulatory_radar(
    hours: int = Query(72, ge=1, le=336, description="回溯小时数"),
) -> dict[str, Any]:
    """监管新闻过滤（突发风险）。"""
    market_db = get_market_db()

    regulatory_keywords = ["regulat", "SEC", "CFTC", "ban", "compliance", "enforcement",
                           "lawsuit", "sanction", "policy", "legislation", "legal"]
    # Use LIKE for basic keyword matching
    conditions = " OR ".join(
        f"(title LIKE '%{kw}%' OR summary LIKE '%{kw}%')" for kw in regulatory_keywords
    )
    articles = market_db.fetch_all(
        f"SELECT title, summary, source, sentiment_label, published_at, url, "
        f"relevance_symbols FROM news_articles "
        f"WHERE published_at >= datetime('now', ?) AND ({conditions}) "
        f"ORDER BY published_at DESC LIMIT 50",
        (f"-{hours} hours",),
    )

    results = [
        {
            "title": a["title"],
            "source": a["source"],
            "sentiment": a["sentiment_label"],
            "published_at": a["published_at"],
            "affected_symbols": a["relevance_symbols"],
            "summary": (a["summary"] or "")[:200],
        }
        for a in articles
    ]
    return {"hours": hours, "regulatory_articles": len(results), "articles": results}


@router.get("/source-reliability")
def source_reliability() -> dict[str, Any]:
    """新闻源可靠性统计。"""
    market_db = get_market_db()

    rows = market_db.fetch_all(
        "SELECT source, COUNT(*) as article_count, "
        "SUM(CASE WHEN sentiment_label = 'bullish' THEN 1 ELSE 0 END) as bullish_count, "
        "SUM(CASE WHEN sentiment_label = 'bearish' THEN 1 ELSE 0 END) as bearish_count, "
        "SUM(CASE WHEN sentiment_label = 'neutral' THEN 1 ELSE 0 END) as neutral_count, "
        "MIN(published_at) as first_article, MAX(published_at) as last_article "
        "FROM news_articles GROUP BY source ORDER BY article_count DESC",
    )
    if not rows:
        return {"sources": []}

    sources = []
    for r in rows:
        total = r["article_count"] or 1
        sources.append({
            "source": r["source"],
            "article_count": total,
            "bullish_pct": round((r["bullish_count"] or 0) / total * 100, 1),
            "bearish_pct": round((r["bearish_count"] or 0) / total * 100, 1),
            "neutral_pct": round((r["neutral_count"] or 0) / total * 100, 1),
            "first_article": r["first_article"],
            "last_article": r["last_article"],
            "bias_score": round(abs((r["bullish_count"] or 0) - (r["bearish_count"] or 0)) / total, 3),
        })
    return {"source_count": len(sources), "sources": sources}
