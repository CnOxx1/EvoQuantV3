"""Catalogs 路由 — 因子目录（alternative, onchain, options, tokenomics, macro）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/catalogs", tags=["catalogs"])


@router.get("/alternative")
def get_alternative_catalog(
    category: str | None = Query(None, description="按类别过滤"),
    limit: int = Query(500, ge=1, le=2000, description="返回条数"),
) -> dict[str, Any]:
    """返回所有另类因子定义。"""
    db = get_market_db()
    if category:
        rows = db.fetch_all(
            """SELECT factor_id, name, category, factor_type, entity_scope,
                      entity_type, description, unit, source_name, enabled
               FROM alternative_factor_catalog
               WHERE category = ?
               ORDER BY factor_id
               LIMIT ?""",
            (category, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT factor_id, name, category, factor_type, entity_scope,
                      entity_type, description, unit, source_name, enabled
               FROM alternative_factor_catalog
               ORDER BY factor_id
               LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No alternative factors found.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}


@router.get("/onchain")
def get_onchain_catalog(
    category: str | None = Query(None, description="按类别过滤"),
    limit: int = Query(500, ge=1, le=2000, description="返回条数"),
) -> dict[str, Any]:
    """返回所有链上因子定义。"""
    db = get_market_db()
    if category:
        rows = db.fetch_all(
            """SELECT factor_id, name, category, factor_type, entity_scope,
                      entity_type, description, unit, source_name, enabled
               FROM onchain_factor_catalog
               WHERE category = ?
               ORDER BY factor_id
               LIMIT ?""",
            (category, limit),
        )
    else:
        rows = db.fetch_all(
            """SELECT factor_id, name, category, factor_type, entity_scope,
                      entity_type, description, unit, source_name, enabled
               FROM onchain_factor_catalog
               ORDER BY factor_id
               LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No onchain factors found.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}


@router.get("/options")
def get_options_catalog(
    limit: int = Query(500, ge=1, le=2000, description="返回条数"),
) -> dict[str, Any]:
    """返回所有期权因子定义。"""
    db = get_market_db()
    rows = db.fetch_all(
        """SELECT factor_id, name, category, factor_type, entity_scope,
                  entity_type, description, unit, source_name, enabled
           FROM options_factor_catalog
           ORDER BY factor_id
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No options factors found.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}


@router.get("/tokenomics")
def get_tokenomics_catalog(
    limit: int = Query(500, ge=1, le=2000, description="返回条数"),
) -> dict[str, Any]:
    """返回所有代币经济学因子定义。"""
    db = get_market_db()
    rows = db.fetch_all(
        """SELECT factor_id, name, category, factor_type, entity_scope,
                  entity_type, description, unit, source_name, enabled
           FROM tokenomics_factor_catalog
           ORDER BY factor_id
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No tokenomics factors found.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}


@router.get("/macro")
def get_macro_catalog(
    limit: int = Query(500, ge=1, le=2000, description="返回条数"),
) -> dict[str, Any]:
    """返回所有宏观因子定义。"""
    db = get_market_db()
    rows = db.fetch_all(
        """SELECT factor_id, name, category, factor_type,
                  description, unit, source_name, enabled
           FROM macro_factor_catalog
           ORDER BY factor_id
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No macro factors found.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}
