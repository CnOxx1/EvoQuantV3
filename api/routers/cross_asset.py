"""Cross-Asset 路由 — 跨资产分析（相关性矩阵、相对强弱、板块轮动、资金流向）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/cross-asset", tags=["cross-asset"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/correlation")
def get_correlation_matrix(
    window_hours: int = Query(168, description="计算窗口（小时），默认 168h = 7 天"),
) -> dict[str, Any]:
    """返回最新跨资产相关性矩阵。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM cross_asset_correlation_snapshots
           WHERE window_hours = ?
           ORDER BY snapshot_time DESC LIMIT 1""",
        (window_hours,),
    )
    if not row:
        row = db.fetch_one(
            """SELECT * FROM cross_asset_correlation_snapshots
               ORDER BY snapshot_time DESC LIMIT 1""",
            (),
        )
    if not row:
        raise HTTPException(status_code=404, detail="No correlation data found. Run logic_pipeline first.")

    data = dict(row)
    if data.get("matrix_json"):
        try:
            data["matrix"] = json.loads(data["matrix_json"])
            del data["matrix_json"]
        except json.JSONDecodeError:
            pass
    if data.get("symbols_json"):
        try:
            data["symbols"] = json.loads(data["symbols_json"])
            del data["symbols_json"]
        except json.JSONDecodeError:
            pass

    return data


@router.get("/relative-strength")
def get_relative_strength(
    symbol: str | None = Query(None, description="指定资产，不传则返回全部"),
) -> dict[str, Any]:
    """返回各资产相对 BTC 强弱排名与动量。"""
    db = get_analytics_db()

    if symbol:
        normalized = _normalize_symbol(symbol)
        rows = db.fetch_all(
            """SELECT * FROM cross_asset_relative_strength
               WHERE symbol = ?
               AND snapshot_time = (
                   SELECT MAX(snapshot_time) FROM cross_asset_relative_strength
                   WHERE symbol = ?
               )""",
            (normalized, normalized),
        )
    else:
        rows = db.fetch_all(
            """SELECT crs.*
               FROM cross_asset_relative_strength crs
               INNER JOIN (
                   SELECT symbol, MAX(snapshot_time) AS max_ts
                   FROM cross_asset_relative_strength
                   GROUP BY symbol
               ) latest ON crs.symbol = latest.symbol AND crs.snapshot_time = latest.max_ts
               ORDER BY crs.rs_rank ASC""",
            (),
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No relative strength data found.")

    records = [dict(r) for r in rows]

    if symbol:
        return {"symbol": _normalize_symbol(symbol), "data": records[0] if records else {}}

    return {
        "symbol_count": len(records),
        "ranked_by": "rs_vs_btc_7d",
        "data": records,
    }


@router.get("/sector-rotation")
def get_sector_rotation() -> dict[str, Any]:
    """返回最新板块轮动状态（收益率、动量、资金流向、轮动阶段）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT csr.*
           FROM cross_asset_sector_rotation csr
           INNER JOIN (
               SELECT sector, MAX(snapshot_time) AS max_ts
               FROM cross_asset_sector_rotation
               GROUP BY sector
           ) latest ON csr.sector = latest.sector AND csr.snapshot_time = latest.max_ts
           ORDER BY csr.sector_return_7d DESC""",
        (),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No sector rotation data found.")

    records = [dict(r) for r in rows]
    leading = [r["sector"] for r in records if r.get("rotation_phase") == "leading"]
    lagging = [r["sector"] for r in records if r.get("rotation_phase") == "lagging"]

    return {
        "sector_count": len(records),
        "leading_sectors": leading,
        "lagging_sectors": lagging,
        "sectors": records,
    }


@router.get("/fund-flow")
def get_fund_flow(
    scope: str | None = Query(None, description="范围过滤，如 market / sector_layer1 等"),
) -> dict[str, Any]:
    """返回最新资金流向数据（净主动买卖、OI 变化）。"""
    db = get_analytics_db()

    if scope:
        rows = db.fetch_all(
            """SELECT * FROM cross_asset_fund_flow
               WHERE scope = ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (scope,),
        )
    else:
        rows = db.fetch_all(
            """SELECT cff.*
               FROM cross_asset_fund_flow cff
               INNER JOIN (
                   SELECT scope, MAX(snapshot_time) AS max_ts
                   FROM cross_asset_fund_flow
                   GROUP BY scope
               ) latest ON cff.scope = latest.scope AND cff.snapshot_time = latest.max_ts
               ORDER BY cff.scope""",
            (),
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No fund flow data found.")

    records = [dict(r) for r in rows]
    return {
        "scope_count": len(records),
        "data": records if not scope else records[0],
    }


@router.get("/summary")
def get_cross_asset_summary() -> dict[str, Any]:
    """返回跨资产分析摘要（供 Dashboard 和 Bridge 快速消费）。"""
    db = get_analytics_db()

    corr_row = db.fetch_one(
        """SELECT avg_correlation, max_correlation, min_correlation, snapshot_time
           FROM cross_asset_correlation_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )

    rs_rows = db.fetch_all(
        """SELECT symbol, rs_rank, rs_vs_btc_7d, rs_momentum
           FROM cross_asset_relative_strength
           WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM cross_asset_relative_strength)
           ORDER BY rs_rank ASC LIMIT 5""",
        (),
    )

    sector_rows = db.fetch_all(
        """SELECT sector, rotation_phase, sector_return_7d
           FROM cross_asset_sector_rotation
           WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM cross_asset_sector_rotation)
           ORDER BY sector_return_7d DESC""",
        (),
    )

    return {
        "correlation": dict(corr_row) if corr_row else None,
        "top5_relative_strength": [dict(r) for r in rs_rows],
        "sector_rotation": [dict(r) for r in sector_rows],
    }
