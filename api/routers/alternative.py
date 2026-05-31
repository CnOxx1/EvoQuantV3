"""Alternative 路由 — 另类数据（开发者活动、稳定币流动、因子探索）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/alternative", tags=["alternative"])



@router.get("/developer/{symbol}")
def get_developer_activity(symbol: str) -> dict[str, Any]:
    """返回指定资产的 GitHub 开发者活动指标。"""
    entity_key = symbol.upper().replace("/USDT", "").replace("-", "")
    db = get_market_db()
    rows = db.fetch_all(
        """SELECT factor_id, category, factor_type, entity_type,
                  entity_key, observation_time, value, unit, source_name
           FROM latest_alternative_timeseries
           WHERE category = 'developer_activity' AND entity_key = ?
           ORDER BY observation_time DESC""",
        (entity_key,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No developer data found.")
    return {"symbol": entity_key, "count": len(rows), "metrics": [dict(r) for r in rows]}


@router.get("/stablecoin-flows")
def get_stablecoin_flows(
    entity: str | None = Query(None, description="实体过滤，如 USDT, USDC"),
) -> dict[str, Any]:
    """返回稳定币供应/流动数据。"""
    db = get_market_db()
    if entity:
        rows = db.fetch_all(
            """SELECT factor_id, category, factor_type, entity_type,
                      entity_key, observation_time, value, unit, source_name
               FROM latest_alternative_timeseries
               WHERE category = 'stablecoin_liquidity' AND entity_key = ?
               ORDER BY observation_time DESC""",
            (entity,),
        )
    else:
        rows = db.fetch_all(
            """SELECT factor_id, category, factor_type, entity_type,
                      entity_key, observation_time, value, unit, source_name
               FROM latest_alternative_timeseries
               WHERE category = 'stablecoin_liquidity'
               ORDER BY observation_time DESC""",
            (),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No stablecoin flow data found.")
    return {"count": len(rows), "flows": [dict(r) for r in rows]}


@router.get("/factors")
def get_factors(
    category: str | None = Query(None, description="因子类别过滤"),
    limit: int = Query(100, ge=1, le=500, description="返回最近 N 条"),
) -> dict[str, Any]:
    """通用因子探索接口。"""
    db = get_market_db()
    if category:
        rows = db.fetch_all(
            """SELECT factor_id, category, factor_type, entity_type,
                      entity_key, observation_time, value, unit, source_name
               FROM latest_alternative_timeseries
               WHERE category = ?
               ORDER BY observation_time DESC
               LIMIT ?""",
            (category, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT factor_id, category, factor_type, entity_type,
                      entity_key, observation_time, value, unit, source_name
               FROM latest_alternative_timeseries
               ORDER BY observation_time DESC
               LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No factor data found.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}
