"""Cross-Asset History 路由 — 跨资产历史序列（相关性趋势、配对相关性、RS排名、板块轮动、资金流、交易所对比）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _normalize_symbol, _safe_float

router = APIRouter(prefix="/cross-asset-history", tags=["cross-asset-history"])


@router.get("/correlation")
def get_correlation_history(
    window_hours: int = Query(168, description="计算窗口（小时）"),
    limit: int = Query(30, ge=1, le=200, description="返回最近 N 个快照"),
) -> dict[str, Any]:
    """相关性矩阵历史趋势。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, window_hours, avg_correlation,
                  max_correlation, min_correlation
           FROM cross_asset_correlation_snapshots
           WHERE window_hours = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (window_hours, limit),
    )
    if not rows:
        rows = db.fetch_all(
            """SELECT snapshot_time, window_hours, avg_correlation,
                      max_correlation, min_correlation
               FROM cross_asset_correlation_snapshots
               ORDER BY snapshot_time DESC LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No correlation history found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {
        "window_hours": window_hours,
        "count": len(records),
        "data": records,
    }


@router.get("/correlation/pair")
def get_pair_correlation_history(
    symbol_a: str = Query(..., description="资产 A"),
    symbol_b: str = Query(..., description="资产 B"),
    limit: int = Query(30, ge=1, le=200, description="返回最近 N 个快照"),
) -> dict[str, Any]:
    """两资产配对相关性历史。"""
    norm_a = _normalize_symbol(symbol_a)
    norm_b = _normalize_symbol(symbol_b)

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, matrix_json, symbols_json
           FROM cross_asset_correlation_snapshots
           ORDER BY snapshot_time DESC LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No correlation data found.")

    history = []
    for r in rows:
        matrix = {}
        symbols = []
        if r["matrix_json"]:
            try:
                matrix = json.loads(r["matrix_json"])
            except json.JSONDecodeError:
                continue
        if r["symbols_json"]:
            try:
                symbols = json.loads(r["symbols_json"])
            except json.JSONDecodeError:
                continue

        # Try to find pair correlation
        pair_key = f"{norm_a}|{norm_b}"
        pair_key_rev = f"{norm_b}|{norm_a}"
        corr = matrix.get(pair_key) or matrix.get(pair_key_rev)

        # Also try index-based lookup
        if corr is None and isinstance(matrix, list) and symbols:
            try:
                idx_a = symbols.index(norm_a)
                idx_b = symbols.index(norm_b)
                corr = matrix[idx_a][idx_b]
            except (ValueError, IndexError):
                pass

        if corr is not None:
            history.append({"snapshot_time": r["snapshot_time"], "correlation": corr})

    history.reverse()
    return {
        "symbol_a": norm_a,
        "symbol_b": norm_b,
        "count": len(history),
        "data": history,
    }


@router.get("/relative-strength/{symbol}")
def get_relative_strength_history(
    symbol: str,
    limit: int = Query(30, ge=1, le=200, description="返回最近 N 个快照"),
) -> dict[str, Any]:
    """单资产 RS 排名历史。"""
    normalized = _normalize_symbol(symbol)

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, rs_vs_btc_7d, rs_vs_btc_3d, rs_vs_btc_1d,
                  rs_rank, rs_momentum, price_change_7d_pct, volume_change_7d_pct
           FROM cross_asset_relative_strength
           WHERE symbol = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (normalized, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No RS data for '{normalized}'.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {
        "symbol": normalized,
        "count": len(records),
        "data": records,
    }


@router.get("/sector-rotation")
def get_sector_rotation_history(
    sector: str | None = Query(None, description="指定板块，不传则返回所有"),
    limit: int = Query(30, ge=1, le=200, description="返回最近 N 个快照"),
) -> dict[str, Any]:
    """板块轮动阶段历史。"""
    db = get_analytics_db()

    if sector:
        rows = db.fetch_all(
            """SELECT snapshot_time, sector, sector_return_7d, sector_volatility_7d,
                      sector_momentum_score, rotation_phase, constituent_count
               FROM cross_asset_sector_rotation
               WHERE sector = ?
               ORDER BY snapshot_time DESC LIMIT ?""",
            (sector, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT snapshot_time, sector, sector_return_7d, sector_volatility_7d,
                      sector_momentum_score, rotation_phase, constituent_count
               FROM cross_asset_sector_rotation
               ORDER BY snapshot_time DESC LIMIT ?""",
            (limit,),
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No sector rotation data found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {"sector": sector, "count": len(records), "data": records}


@router.get("/fund-flow")
def get_fund_flow_history(
    scope: str | None = Query(None, description="范围过滤，如 market / sector_layer1"),
    limit: int = Query(30, ge=1, le=200, description="返回最近 N 个快照"),
) -> dict[str, Any]:
    """资金流历史趋势。"""
    db = get_analytics_db()

    if scope:
        rows = db.fetch_all(
            """SELECT snapshot_time, scope, net_taker_flow_1h, net_taker_flow_24h,
                      oi_change_1h, oi_change_24h, aggressive_buy_share
               FROM cross_asset_fund_flow
               WHERE scope = ?
               ORDER BY snapshot_time DESC LIMIT ?""",
            (scope, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT snapshot_time, scope, net_taker_flow_1h, net_taker_flow_24h,
                      oi_change_1h, oi_change_24h, aggressive_buy_share
               FROM cross_asset_fund_flow
               ORDER BY snapshot_time DESC LIMIT ?""",
            (limit,),
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No fund flow data found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {"scope": scope, "count": len(records), "data": records}


@router.get("/exchange-comparison/{symbol}")
def get_exchange_comparison_history(
    symbol: str,
    limit: int = Query(30, ge=1, le=200, description="返回最近 N 个快照"),
) -> dict[str, Any]:
    """跨交易所对比历史。"""
    normalized = _normalize_symbol(symbol)

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT * FROM exchange_comparison_snapshots
           WHERE symbol = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (normalized, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No exchange comparison data for '{normalized}'.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {"symbol": normalized, "count": len(records), "data": records}
