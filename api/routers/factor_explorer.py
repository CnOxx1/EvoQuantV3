"""Factor Explorer 路由 — 因子探索（搜索、时序、相关性、概览、域列表）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/factors", tags=["factors"])

_FACTOR_DOMAINS = {
    "options": {"catalog": "options_factor_catalog", "timeseries": "options_timeseries"},
    "tokenomics": {"catalog": "tokenomics_factor_catalog", "timeseries": "tokenomics_timeseries"},
    "onchain": {"catalog": "onchain_factor_catalog", "timeseries": "onchain_timeseries"},
    "alternative": {"catalog": "alternative_factor_catalog", "timeseries": "alternative_timeseries"},
    "macro": {"catalog": "macro_factor_catalog", "timeseries": "macro_timeseries"},
}


@router.get("/domains")
def get_factor_domains() -> dict[str, Any]:
    """列出所有因子域及其 catalog。"""
    db = get_market_db()
    domains = []
    for domain, tables in _FACTOR_DOMAINS.items():
        count = 0
        try:
            row = db.fetch_one(f"SELECT COUNT(*) as cnt FROM {tables['catalog']}", ())
            if row:
                count = row["cnt"]
        except Exception:
            pass  # table may not exist yet
        domains.append({"domain": domain, "catalog_table": tables["catalog"], "factor_count": count})

    return {"domain_count": len(domains), "domains": domains}


@router.get("/search")
def search_factors(
    q: str = Query(..., min_length=1, description="搜索关键字"),
    domain: str | None = Query(None, description="限定域: options/tokenomics/onchain/alternative/macro"),
) -> dict[str, Any]:
    """全域因子搜索（关键字）。"""
    db = get_market_db()
    results = []

    search_domains = {domain: _FACTOR_DOMAINS[domain]} if domain and domain in _FACTOR_DOMAINS else _FACTOR_DOMAINS

    for dom, tables in search_domains.items():
        try:
            rows = db.fetch_all(
                f"""SELECT factor_id, name, category, description
                    FROM {tables['catalog']}
                    WHERE name LIKE ? OR description LIKE ? OR category LIKE ?""",
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            )
            for r in rows:
                entry = dict(r)
                entry["domain"] = dom
                results.append(entry)
        except Exception:
            continue  # table may not exist yet

    return {"query": q, "domain": domain, "result_count": len(results), "results": results}


@router.get("/timeseries/{domain}/{factor_id}")
def get_factor_timeseries(
    domain: str,
    factor_id: str,
    entity_key: str | None = Query(None, description="实体键，如 BTC/USDT"),
    limit: int = Query(100, ge=1, le=1000, description="返回最近 N 条"),
) -> dict[str, Any]:
    """统一因子时序获取。"""
    if domain not in _FACTOR_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'. Valid: {list(_FACTOR_DOMAINS.keys())}")

    db = get_market_db()
    table = _FACTOR_DOMAINS[domain]["timeseries"]

    if entity_key:
        rows = db.fetch_all(
            f"""SELECT observation_time, value, entity_type, entity_key
                FROM {table}
                WHERE factor_id = ? AND entity_key = ?
                ORDER BY observation_time DESC LIMIT ?""",
            (factor_id, entity_key, limit),
        )
    else:
        rows = db.fetch_all(
            f"""SELECT observation_time, value, entity_type, entity_key
                FROM {table}
                WHERE factor_id = ?
                ORDER BY observation_time DESC LIMIT ?""",
            (factor_id, limit),
        )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No timeseries data for factor '{factor_id}' in domain '{domain}'.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {
        "domain": domain,
        "factor_id": factor_id,
        "entity_key": entity_key,
        "count": len(records),
        "data": records,
    }


@router.get("/correlation")
def get_factor_correlation(
    domain_a: str = Query(..., description="因子 A 所属域"),
    factor_a: str = Query(..., description="因子 A ID"),
    domain_b: str = Query(..., description="因子 B 所属域"),
    factor_b: str = Query(..., description="因子 B ID"),
    entity_key: str | None = Query(None, description="实体键"),
    limit: int = Query(100, ge=10, le=1000, description="用于计算的数据点数"),
) -> dict[str, Any]:
    """任意两因子相关性计算。"""
    for d in (domain_a, domain_b):
        if d not in _FACTOR_DOMAINS:
            raise HTTPException(status_code=400, detail=f"Unknown domain '{d}'.")

    db = get_market_db()

    def _fetch_values(domain: str, factor_id: str) -> list[tuple[str, float]]:
        table = _FACTOR_DOMAINS[domain]["timeseries"]
        if entity_key:
            rows = db.fetch_all(
                f"""SELECT observation_time, value FROM {table}
                    WHERE factor_id = ? AND entity_key = ?
                    ORDER BY observation_time DESC LIMIT ?""",
                (factor_id, entity_key, limit),
            )
        else:
            rows = db.fetch_all(
                f"""SELECT observation_time, value FROM {table}
                    WHERE factor_id = ?
                    ORDER BY observation_time DESC LIMIT ?""",
                (factor_id, limit),
            )
        return [(r["observation_time"], _safe_float(r["value"])) for r in rows if _safe_float(r["value"]) is not None]

    series_a = _fetch_values(domain_a, factor_a)
    series_b = _fetch_values(domain_b, factor_b)

    if not series_a or not series_b:
        raise HTTPException(status_code=404, detail="Insufficient data for correlation.")

    # Align by time
    times_a = {t: v for t, v in series_a}
    times_b = {t: v for t, v in series_b}
    common_times = sorted(times_a.keys() & times_b.keys())

    if len(common_times) < 5:
        raise HTTPException(status_code=404, detail="Insufficient overlapping data points.")

    vals_a = [times_a[t] for t in common_times]
    vals_b = [times_b[t] for t in common_times]

    # v4.5.0: numpy vectorized Pearson correlation
    import numpy as np
    arr_a = np.array(vals_a, dtype=np.float64)
    arr_b = np.array(vals_b, dtype=np.float64)
    corr_matrix = np.corrcoef(arr_a, arr_b)
    correlation = float(np.nan_to_num(corr_matrix[0, 1], nan=0.0))
    n = len(vals_a)

    return {
        "factor_a": {"domain": domain_a, "factor_id": factor_a},
        "factor_b": {"domain": domain_b, "factor_id": factor_b},
        "correlation": round(correlation, 6),
        "data_points": n,
        "interpretation": "strong_positive" if correlation > 0.7
            else "moderate_positive" if correlation > 0.3
            else "weak" if correlation > -0.3
            else "moderate_negative" if correlation > -0.7
            else "strong_negative",
    }


@router.get("/summary")
def get_factor_summary() -> dict[str, Any]:
    """全域因子概览（数量/新鲜度/覆盖率）。"""
    db = get_market_db()
    summary = []

    for domain, tables in _FACTOR_DOMAINS.items():
        info: dict[str, Any] = {"domain": domain, "factor_count": 0, "timeseries_rows": 0, "latest_observation": None}
        try:
            cat_row = db.fetch_one(f"SELECT COUNT(*) as cnt FROM {tables['catalog']}", ())
            if cat_row:
                info["factor_count"] = cat_row["cnt"]
        except Exception:
            pass  # table may not exist yet
        try:
            ts_row = db.fetch_one(f"SELECT COUNT(*) as cnt FROM {tables['timeseries']}", ())
            if ts_row:
                info["timeseries_rows"] = ts_row["cnt"]
        except Exception:
            pass  # table may not exist yet
        try:
            latest_row = db.fetch_one(
                f"SELECT MAX(observation_time) as latest FROM {tables['timeseries']}", ()
            )
            if latest_row:
                info["latest_observation"] = latest_row["latest"]
        except Exception:
            pass
        summary.append(info)

    total_factors = sum(s["factor_count"] for s in summary)
    total_rows = sum(s["timeseries_rows"] for s in summary)

    return {
        "total_factors": total_factors,
        "total_timeseries_rows": total_rows,
        "domain_count": len(summary),
        "domains": summary,
    }
