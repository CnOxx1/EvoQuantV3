"""v3 Onchain — 链上数据统一入口。

端点：
  /onchain/metrics/{symbol}    — 链上指标
  /onchain/alternative         — 另类因子最新值
  /onchain/stablecoin/flows    — 稳定币链间流
  /onchain/stablecoin/pulse    — 稳定币脉冲信号
  /onchain/cross-chain         — 跨链消息统计
  /onchain/mempool             — 内存池状态
  /onchain/mempool/large-txs   — 大额待确认交易
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/onchain", tags=["onchain"])


@router.get("/metrics/{symbol}")
def get_metrics(
    symbol: str,
    limit: int = Query(10, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """指定资产链上指标（来自 onchain_timeseries）。"""
    base = symbol.upper().replace("/USDT", "").replace("-USDT", "")
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT factor_id, value, observation_time "
        "FROM latest_onchain_timeseries WHERE entity_key = ? "
        "ORDER BY factor_id",
        (base,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No onchain data for {base}.")
    return {"asset": base, "count": len(rows), "metrics": [dict(r) for r in rows]}


@router.get("/alternative")
def get_alternative(
    entity: str | None = Query(None, description="实体键，如 BTC"),
    limit: int = Query(50, ge=1, le=200, description="条数"),
) -> dict[str, Any]:
    """另类因子最新值。"""
    db = get_market_db()
    if entity:
        rows = db.fetch_all(
            "SELECT factor_id, entity_key, value, observation_time "
            "FROM latest_alternative_timeseries WHERE entity_key = ? "
            "ORDER BY factor_id LIMIT ?",
            (entity.upper(), limit),
        )
    else:
        rows = db.fetch_all(
            "SELECT factor_id, entity_key, value, observation_time "
            "FROM latest_alternative_timeseries ORDER BY factor_id LIMIT ?",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No alternative data.")
    return {"count": len(rows), "factors": [dict(r) for r in rows]}


@router.get("/stablecoin/flows")
def get_stablecoin_flows(
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """稳定币链间净流。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT chain, net_flow, inflow, outflow, timestamp "
        "FROM stablecoin_chain_flows ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No stablecoin flow data.")
    return {"count": len(rows), "flows": [dict(r) for r in rows]}


@router.get("/stablecoin/pulse")
def get_stablecoin_pulse() -> dict[str, Any]:
    """稳定币脉冲信号（expansion/contraction）。"""
    from api.dependencies import get_analytics_db
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM stablecoin_pulse_states ORDER BY ts DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No stablecoin pulse data.")
    return dict(row)


@router.get("/cross-chain")
def get_cross_chain(
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """跨链消息统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT protocol, source_chain, dest_chain, message_count, volume_usd, timestamp "
        "FROM cross_chain_messages ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No cross-chain data.")
    return {"count": len(rows), "messages": [dict(r) for r in rows]}


@router.get("/mempool")
def get_mempool() -> dict[str, Any]:
    """BTC 内存池状态。"""
    db = get_market_db()
    row = db.fetch_one(
        "SELECT * FROM mempool_snapshots ORDER BY timestamp DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No mempool data.")
    return dict(row)


@router.get("/mempool/large-txs")
def get_large_txs(
    limit: int = Query(10, ge=1, le=50, description="条数"),
) -> dict[str, Any]:
    """大额待确认交易。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT txid, value_btc, fee_rate, size_vbytes, first_seen "
        "FROM pending_large_txs ORDER BY value_btc DESC LIMIT ?",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No large pending txs.")
    return {"count": len(rows), "transactions": [dict(r) for r in rows]}
