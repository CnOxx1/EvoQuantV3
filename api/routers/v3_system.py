"""v3 System — 系统状态与数据质量统一入口。

端点：
  /system/health         — 健康检查
  /system/status         — 域数据可用性
  /system/data-quality   — 数据质量审计
  /system/domains        — 域列表与新鲜度
  /system/market-structure — 市场结构
  /system/breadth        — 市场广度
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_exchange_db, get_market_db
from core.feature_flags import feature_flags

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health_check() -> dict[str, Any]:
    """基本健康检查。"""
    status = "ok"
    checks = {}

    # DB connectivity
    for name, getter in [("exchange", get_exchange_db), ("market", get_market_db), ("analytics", get_analytics_db)]:
        try:
            db = getter()
            db.fetch_one("SELECT 1", ())
            checks[name] = "ok"
        except Exception as e:
            checks[name] = f"error: {str(e)[:50]}"
            status = "degraded"

    return {"status": status, "databases": checks}


@router.get("/status")
def get_status() -> dict[str, Any]:
    """域数据可用性总览。"""
    domain_checks = {
        "klines": ("exchange", "klines"),
        "market_info": ("exchange", "market_info"),
        "merged_klines": ("analytics", "merged_klines"),
        "technical_indicators": ("analytics", "technical_indicators"),
        "macro": ("market", "macro_timeseries"),
        "news": ("market", "news_articles"),
        "onchain": ("market", "latest_onchain_timeseries"),
        "alternative": ("market", "latest_alternative_timeseries"),
        "governance": ("market", "governance_proposals"),
        "prediction_markets": ("market", "prediction_markets"),
        "cross_chain": ("market", "cross_chain_messages"),
        "mempool": ("market", "mempool_snapshots"),
        "stablecoin_flows": ("market", "stablecoin_chain_flows"),
        "depth": ("market", "depth_snapshots"),
        "announcements": ("market", "exchange_announcements"),
        "correlation": ("analytics", "cross_asset_correlation_snapshots"),
        "portfolio_risk": ("analytics", "portfolio_risk_snapshots"),
        "market_breadth": ("analytics", "market_breadth_snapshots"),
        "defi_stress": ("analytics", "defi_stress_states"),
        "retail_fomo": ("analytics", "retail_fomo_states"),
        "smart_money": ("analytics", "smart_money_conviction_states"),
        "liquidity_regime": ("analytics", "liquidity_regime_states"),
    }

    db_getters = {
        "exchange": get_exchange_db,
        "market": get_market_db,
        "analytics": get_analytics_db,
    }

    results = {}
    active = 0
    empty = 0

    for domain, (db_name, table) in domain_checks.items():
        try:
            db = db_getters[db_name]()
            row = db.fetch_one(f"SELECT 1 FROM {table} LIMIT 1", ())
            has_data = row is not None
        except Exception:
            has_data = False

        if has_data:
            results[domain] = "active"
            active += 1
        else:
            results[domain] = "empty"
            empty += 1

    return {
        "summary": {"active": active, "empty": empty, "total": active + empty},
        "domains": results,
    }


@router.get("/status/disabled")
def get_disabled() -> dict[str, Any]:
    """列出所有被禁用的路由模块。"""
    import pkgutil
    from pathlib import Path
    import api.routers as routers_pkg

    package_dir = Path(routers_pkg.__file__).parent
    scan_dirs = [str(package_dir), str(package_dir / "_legacy")]
    all_modules = []
    for d in scan_dirs:
        if Path(d).is_dir():
            all_modules.extend(
                m.name for m in pkgutil.iter_modules([d])
                if not m.name.startswith("_")
            )

    disabled = [m for m in all_modules if not feature_flags.is_enabled(m)]
    return {
        "disabled_count": len(disabled),
        "disabled_modules": sorted(disabled),
        "hint": "Set FF_{MODULE_UPPER}_ENABLED=1 in .env to re-enable",
    }


@router.get("/data-quality")
def get_data_quality() -> dict[str, Any]:
    """数据质量审计快照。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM data_quality_audit_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No data quality audit.")
    data = dict(row)
    for k in list(data.keys()):
        if k.endswith("_json") and data[k]:
            try:
                data[k[:-5]] = json.loads(data[k])
                del data[k]
            except (json.JSONDecodeError, KeyError):
                pass
    return data


@router.get("/market-structure")
def get_market_structure() -> dict[str, Any]:
    """市场结构快照。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM market_structure_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No market structure data.")
    data = dict(row)
    for k in list(data.keys()):
        if k.endswith("_json") and data[k]:
            try:
                data[k[:-5]] = json.loads(data[k])
                del data[k]
            except (json.JSONDecodeError, KeyError):
                pass
    return data


@router.get("/asset-readiness")
def get_asset_readiness() -> dict[str, Any]:
    """资产数据就绪状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT snapshot_time, scope_kind, market_world_status, "
        "asset_count, ready_asset_count, partial_asset_count, "
        "thin_asset_count, blocked_asset_count, "
        "average_readiness_score, data_quality_flag, bundle_json "
        "FROM asset_readiness_snapshots ORDER BY snapshot_time DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No readiness data.")
    data = dict(row)
    if data.get("bundle_json"):
        try:
            data["bundle"] = json.loads(data["bundle_json"])
            del data["bundle_json"]
        except (json.JSONDecodeError, KeyError):
            pass
    return data
