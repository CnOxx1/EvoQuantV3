"""v3 Factors — 因子目录与宏观数据统一入口。

端点：
  /factors/catalogs/{domain}  — 因子目录查询
  /factors/macro/latest       — 宏观快照
  /factors/macro/timeseries   — 宏观时序
  /factors/explore            — 因子探索（跨域）
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db

router = APIRouter(prefix="/factors", tags=["factors"])

_CATALOG_TABLES = {
    "alternative": "alternative_factor_catalog",
    "onchain": "onchain_factor_catalog",
    "options": "options_factor_catalog",
    "tokenomics": "tokenomics_factor_catalog",
    "macro": "macro_factor_catalog",
}

_TIMESERIES_TABLES = {
    "alternative": "latest_alternative_timeseries",
    "onchain": "latest_onchain_timeseries",
    "macro": "latest_macro_timeseries",
}


@router.get("/catalogs/{domain}")
def get_catalog(
    domain: str,
    category: str | None = Query(None, description="按类别过滤"),
    limit: int = Query(500, ge=1, le=2000, description="条数"),
) -> dict[str, Any]:
    """指定域的因子目录。域: alternative/onchain/options/tokenomics/macro"""
    if domain not in _CATALOG_TABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid domain. Valid: {list(_CATALOG_TABLES.keys())}",
        )
    table = _CATALOG_TABLES[domain]
    db = get_market_db()

    # macro 表列不含 entity_scope/entity_type
    if domain == "macro":
        cols = "factor_id, name, category, factor_type, description, unit, source_name, enabled"
    else:
        cols = "factor_id, name, category, factor_type, entity_scope, entity_type, description, unit, source_name, enabled"

    if category:
        rows = db.fetch_all(
            f"SELECT {cols} FROM {table} WHERE category = ? ORDER BY factor_id LIMIT ?",
            (category, limit),
        )
    else:
        rows = db.fetch_all(
            f"SELECT {cols} FROM {table} ORDER BY factor_id LIMIT ?",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No {domain} factors found.")
    return {"domain": domain, "count": len(rows), "factors": [dict(r) for r in rows]}


@router.get("/macro/latest")
def get_macro_latest() -> dict[str, Any]:
    """宏观上下文快照（AI 聚合结果）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM macro_context_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No macro data. Run logic_pipeline first.")
    data = dict(row)
    for field in list(data.keys()):
        if field.endswith("_json") and data[field]:
            try:
                data[field[:-5]] = json.loads(data[field])
                del data[field]
            except (json.JSONDecodeError, KeyError):
                pass
    return data


@router.get("/macro/timeseries")
def get_macro_timeseries(
    factor_id: str | None = Query(None, description="因子 ID，如 dxy/sp500/vix"),
    limit: int = Query(50, ge=1, le=500, description="条数"),
) -> dict[str, Any]:
    """宏观因子时序数据。"""
    db = get_market_db()
    if factor_id:
        rows = db.fetch_all(
            "SELECT factor_id, value, observation_time "
            "FROM macro_timeseries WHERE factor_id = ? "
            "ORDER BY observation_time DESC LIMIT ?",
            (factor_id, limit),
        )
    else:
        rows = db.fetch_all(
            "SELECT factor_id, value, observation_time "
            "FROM latest_macro_timeseries ORDER BY factor_id",
            (),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No macro timeseries data.")
    return {"count": len(rows), "data": [dict(r) for r in rows]}


@router.get("/explore")
def explore_factors(
    domain: str = Query("alternative", description="域: alternative/onchain/macro"),
    entity: str | None = Query(None, description="实体键，如 BTC"),
    limit: int = Query(50, ge=1, le=200, description="条数"),
) -> dict[str, Any]:
    """跨域因子探索（最新值）。"""
    if domain not in _TIMESERIES_TABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid domain. Valid: {list(_TIMESERIES_TABLES.keys())}",
        )
    table = _TIMESERIES_TABLES[domain]
    db = get_market_db()

    if entity:
        rows = db.fetch_all(
            f"SELECT factor_id, entity_key, value, observation_time "
            f"FROM {table} WHERE entity_key = ? ORDER BY factor_id LIMIT ?",
            (entity.upper(), limit),
        )
    else:
        rows = db.fetch_all(
            f"SELECT factor_id, entity_key, value, observation_time "
            f"FROM {table} ORDER BY factor_id LIMIT ?",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No factor data.")
    return {"domain": domain, "count": len(rows), "data": [dict(r) for r in rows]}
