"""Features 路由 — 特征标准化复合分数与明细。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/features", tags=["features"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/composites/{symbol}")
def get_composites_by_symbol(symbol: str) -> dict[str, Any]:
    """返回指定资产的所有复合分数。"""
    normalized = _normalize_symbol(symbol)
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, symbol, composite_name, composite_zscore,
                  composite_percentile, cross_asset_rank,
                  cross_asset_rank_total, regime_label,
                  confidence, component_count
           FROM feature_standardization_composites
           WHERE symbol = ?
           ORDER BY snapshot_time DESC""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No composite data found.")
    return {"symbol": normalized, "count": len(rows), "composites": [dict(r) for r in rows]}


@router.get("/composites")
def get_composites_by_name(
    name: str = Query(..., description="复合分数名称，如 momentum"),
) -> dict[str, Any]:
    """返回指定复合分数的跨资产排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, symbol, composite_name, composite_zscore,
                  composite_percentile, cross_asset_rank,
                  cross_asset_rank_total, regime_label, confidence
           FROM feature_standardization_composites
           WHERE composite_name = ?
           ORDER BY cross_asset_rank ASC""",
        (name,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No composite data for '{name}'.")
    return {"composite_name": name, "count": len(rows), "ranking": [dict(r) for r in rows]}


@router.get("/details/{symbol}")
def get_details_by_symbol(symbol: str) -> dict[str, Any]:
    """返回指定资产的所有标准化特征明细。"""
    normalized = _normalize_symbol(symbol)
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, symbol, feature_name, raw_value,
                  zscore_7d, zscore_30d, percentile_30d,
                  cross_asset_rank, cross_asset_rank_total,
                  regime_label, confidence
           FROM feature_standardization_details
           WHERE symbol = ?
           ORDER BY feature_name""",
        (normalized,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No feature details found.")
    return {"symbol": normalized, "count": len(rows), "features": [dict(r) for r in rows]}


@router.get("/ranking")
def get_feature_ranking(
    feature: str = Query(..., description="特征名称，如 rsi_14"),
) -> dict[str, Any]:
    """返回指定特征的跨资产排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, symbol, feature_name, raw_value,
                  zscore_7d, zscore_30d, percentile_30d,
                  cross_asset_rank, cross_asset_rank_total,
                  regime_label, confidence
           FROM feature_standardization_details
           WHERE feature_name = ?
           ORDER BY cross_asset_rank ASC""",
        (feature,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for feature '{feature}'.")
    return {"feature_name": feature, "count": len(rows), "ranking": [dict(r) for r in rows]}
