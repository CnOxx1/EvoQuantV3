"""v3 Risk — 风险与组合分析统一入口。

端点：
  /risk/portfolio       — 组合风险快照
  /risk/correlation     — 相关性矩阵
  /risk/relative-strength — 相对强弱
  /risk/sector-rotation — 板块轮动
  /risk/fund-flow       — 资金流向
  /risk/liquidity-regime — 流动性状态
  /risk/summary         — 跨资产摘要
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/risk", tags=["risk"])


def _norm(symbol: str) -> str:
    s = symbol.upper().replace("-", "/")
    if not s.endswith("/USDT"):
        s = f"{s}/USDT"
    return s


@router.get("/portfolio")
def get_portfolio() -> dict[str, Any]:
    """组合风险快照（VaR/集中度/分散化）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM portfolio_risk_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No portfolio risk data.")
    data = dict(row)
    for k in list(data.keys()):
        if k.endswith("_json") and data[k]:
            try:
                data[k[:-5]] = json.loads(data[k])
                del data[k]
            except (json.JSONDecodeError, KeyError):
                pass
    return data


@router.get("/correlation")
def get_correlation(
    window_hours: int = Query(168, description="窗口（小时），默认7天"),
) -> dict[str, Any]:
    """跨资产相关性矩阵。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM cross_asset_correlation_snapshots "
        "WHERE window_hours = ? ORDER BY snapshot_time DESC LIMIT 1",
        (window_hours,),
    )
    if not row:
        row = db.fetch_one(
            "SELECT * FROM cross_asset_correlation_snapshots "
            "ORDER BY snapshot_time DESC LIMIT 1", ()
        )
    if not row:
        raise HTTPException(status_code=404, detail="No correlation data.")
    data = dict(row)
    for field in ("matrix_json", "symbols_json"):
        if data.get(field):
            try:
                data[field[:-5]] = json.loads(data[field])
                del data[field]
            except json.JSONDecodeError:
                pass
    return data


@router.get("/relative-strength")
def get_relative_strength(
    symbol: str | None = Query(None, description="指定资产"),
) -> dict[str, Any]:
    """相对强弱排名。"""
    db = get_analytics_db()
    if symbol:
        normalized = _norm(symbol)
        rows = db.fetch_all(
            "SELECT * FROM cross_asset_relative_strength "
            "WHERE symbol = ? AND snapshot_time = ("
            "SELECT MAX(snapshot_time) FROM cross_asset_relative_strength WHERE symbol = ?)",
            (normalized, normalized),
        )
    else:
        rows = db.fetch_all(
            "SELECT crs.* FROM cross_asset_relative_strength crs "
            "INNER JOIN (SELECT symbol, MAX(snapshot_time) AS max_ts "
            "FROM cross_asset_relative_strength GROUP BY symbol) "
            "latest ON crs.symbol = latest.symbol AND crs.snapshot_time = latest.max_ts "
            "ORDER BY crs.rs_rank ASC", ()
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No relative strength data.")
    records = [dict(r) for r in rows]
    if symbol:
        return {"symbol": _norm(symbol), "data": records[0]}
    return {"symbol_count": len(records), "data": records}


@router.get("/sector-rotation")
def get_sector_rotation() -> dict[str, Any]:
    """板块轮动状态。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT csr.* FROM cross_asset_sector_rotation csr "
        "INNER JOIN (SELECT sector, MAX(snapshot_time) AS max_ts "
        "FROM cross_asset_sector_rotation GROUP BY sector) "
        "latest ON csr.sector = latest.sector AND csr.snapshot_time = latest.max_ts "
        "ORDER BY csr.sector_return_7d DESC", ()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No sector rotation data.")
    records = [dict(r) for r in rows]
    return {"sector_count": len(records), "sectors": records}


@router.get("/fund-flow")
def get_fund_flow(
    scope: str | None = Query(None, description="范围: market/sector_*"),
) -> dict[str, Any]:
    """资金流向。"""
    db = get_analytics_db()
    if scope:
        rows = db.fetch_all(
            "SELECT * FROM cross_asset_fund_flow "
            "WHERE scope = ? ORDER BY snapshot_time DESC LIMIT 1",
            (scope,),
        )
    else:
        rows = db.fetch_all(
            "SELECT cff.* FROM cross_asset_fund_flow cff "
            "INNER JOIN (SELECT scope, MAX(snapshot_time) AS max_ts "
            "FROM cross_asset_fund_flow GROUP BY scope) "
            "latest ON cff.scope = latest.scope AND cff.snapshot_time = latest.max_ts "
            "ORDER BY cff.scope", ()
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No fund flow data.")
    records = [dict(r) for r in rows]
    return {"count": len(records), "data": records if not scope else records[0]}


@router.get("/liquidity-regime")
def get_liquidity_regime() -> dict[str, Any]:
    """流动性 Regime 状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM liquidity_regime_states ORDER BY ts DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No liquidity regime data.")
    return dict(row)


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    """跨资产分析摘要。"""
    db = get_analytics_db()
    corr = db.fetch_one(
        "SELECT avg_correlation, max_correlation, min_correlation, snapshot_time "
        "FROM cross_asset_correlation_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    rs_rows = db.fetch_all(
        "SELECT symbol, rs_rank, rs_vs_btc_7d FROM cross_asset_relative_strength "
        "WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM cross_asset_relative_strength) "
        "ORDER BY rs_rank ASC LIMIT 5", ()
    )
    sectors = db.fetch_all(
        "SELECT sector, rotation_phase, sector_return_7d FROM cross_asset_sector_rotation "
        "WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM cross_asset_sector_rotation) "
        "ORDER BY sector_return_7d DESC", ()
    )
    return {
        "correlation": dict(corr) if corr else None,
        "top5_relative_strength": [dict(r) for r in rs_rows],
        "sector_rotation": [dict(r) for r in sectors],
    }
