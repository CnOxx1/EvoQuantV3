"""Onchain 路由 — 链上数据查询（交易所净流量、鲸鱼活动、稳定币、TVL 等）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/onchain", tags=["onchain"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


def _get_latest_factors(db, factor_ids: list[str], entity_key: str | None = None) -> dict[str, Any]:
    """从 latest_onchain_timeseries 读取指定因子的最新值。"""
    placeholders = ",".join("?" * len(factor_ids))
    params: list[Any] = list(factor_ids)

    if entity_key:
        rows = db.fetch_all(
            f"""SELECT factor_id, entity_key, value, timestamp
                FROM latest_onchain_timeseries
                WHERE factor_id IN ({placeholders}) AND entity_key = ?
                ORDER BY factor_id""",
            (*params, entity_key),
        )
    else:
        rows = db.fetch_all(
            f"""SELECT factor_id, entity_key, value, timestamp
                FROM latest_onchain_timeseries
                WHERE factor_id IN ({placeholders})
                ORDER BY factor_id, entity_key""",
            params,
        )

    result: dict[str, Any] = {}
    for row in rows:
        fid = row["factor_id"]
        if entity_key:
            result[fid] = {"value": row["value"], "timestamp": row["timestamp"]}
        else:
            result.setdefault(fid, {})[row["entity_key"]] = {
                "value": row["value"],
                "timestamp": row["timestamp"],
            }
    return result


@router.get("/exchange-flow/{symbol}")
def get_exchange_flow(symbol: str) -> dict[str, Any]:
    """返回指定资产的交易所净流量（鲸鱼充提行为）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_market_db()
    base = symbol.upper().replace("/USDT", "").replace("-USDT", "")

    factors = _get_latest_factors(
        db,
        ["exchange_netflow_24h", "exchange_inflow_24h", "exchange_outflow_24h",
         "exchange_reserve", "large_tx_count_24h"],
        entity_key=base,
    )

    if not factors:
        raise HTTPException(status_code=404, detail="No exchange flow data found.")

    netflow = factors.get("exchange_netflow_24h", {}).get("value")
    inflow = factors.get("exchange_inflow_24h", {}).get("value")
    outflow = factors.get("exchange_outflow_24h", {}).get("value")

    signal = "neutral"
    if netflow is not None:
        if netflow < -1e6:
            signal = "bullish_outflow"
        elif netflow > 1e6:
            signal = "bearish_inflow"

    return {
        "symbol": normalized,
        "signal": signal,
        "exchange_netflow_24h": netflow,
        "exchange_inflow_24h": inflow,
        "exchange_outflow_24h": outflow,
        "exchange_reserve": factors.get("exchange_reserve", {}).get("value"),
        "large_tx_count_24h": factors.get("large_tx_count_24h", {}).get("value"),
    }


@router.get("/whale-activity/{symbol}")
def get_whale_activity(symbol: str) -> dict[str, Any]:
    """返回指定资产的鲸鱼活动（大额转账、鲸鱼积累/派发）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_market_db()
    base = symbol.upper().replace("/USDT", "").replace("-USDT", "")

    factors = _get_latest_factors(
        db,
        ["whale_tx_count_24h", "whale_volume_24h", "whale_net_accumulation_7d",
         "top100_holders_pct"],
        entity_key=base,
    )

    if not factors:
        raise HTTPException(status_code=404, detail="No whale activity data found.")

    accumulation = factors.get("whale_net_accumulation_7d", {}).get("value")
    signal = "neutral"
    if accumulation is not None:
        signal = "accumulating" if accumulation > 0 else "distributing"

    return {
        "symbol": normalized,
        "whale_signal": signal,
        "whale_tx_count_24h": factors.get("whale_tx_count_24h", {}).get("value"),
        "whale_volume_24h": factors.get("whale_volume_24h", {}).get("value"),
        "whale_net_accumulation_7d": accumulation,
        "top100_holders_pct": factors.get("top100_holders_pct", {}).get("value"),
    }


@router.get("/stablecoin")
def get_stablecoin_supply() -> dict[str, Any]:
    """返回稳定币供应量与流动性指标（USDT、USDC 等）。"""
    db = get_market_db()
    rows = db.fetch_all(
        """SELECT lot.factor_id, lot.entity_key, lot.value, lot.timestamp
           FROM latest_onchain_timeseries lot
           WHERE lot.factor_id IN (
               'stablecoin_total_supply', 'stablecoin_supply_change_7d',
               'stablecoin_mint_24h', 'stablecoin_burn_24h'
           )
           ORDER BY lot.factor_id, lot.entity_key""",
        (),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No stablecoin data found.")

    result: dict[str, Any] = {}
    for row in rows:
        fid = row["factor_id"]
        ek = row["entity_key"]
        result.setdefault(fid, {})[ek] = {
            "value": row["value"],
            "timestamp": row["timestamp"],
        }

    return {"stablecoin_data": result}


@router.get("/protocol-tvl")
def get_protocol_tvl(
    protocol: str | None = Query(None, description="指定协议名称"),
    limit: int = Query(20, ge=1, le=100, description="返回 top N 协议"),
) -> dict[str, Any]:
    """返回 DeFi 协议 TVL 数据。"""
    db = get_market_db()

    if protocol:
        rows = db.fetch_all(
            """SELECT factor_id, entity_key, value, timestamp
               FROM latest_onchain_timeseries
               WHERE factor_id = 'protocol_tvl' AND entity_key = ?""",
            (protocol,),
        )
    else:
        rows = db.fetch_all(
            """SELECT factor_id, entity_key, value, timestamp
               FROM latest_onchain_timeseries
               WHERE factor_id = 'protocol_tvl'
               ORDER BY CAST(value AS REAL) DESC
               LIMIT ?""",
            (limit,),
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No TVL data found.")

    records = [{"protocol": r["entity_key"], "tvl_usd": r["value"], "timestamp": r["timestamp"]} for r in rows]
    total_tvl = sum(float(r["tvl_usd"]) for r in records if r["tvl_usd"] is not None)

    return {
        "protocol_count": len(records),
        "total_tvl_usd": total_tvl,
        "protocols": records,
    }


@router.get("/network/{symbol}")
def get_network_usage(symbol: str) -> dict[str, Any]:
    """返回指定链的网络使用状况（活跃地址、交易量、费用）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_market_db()
    base = symbol.upper().replace("/USDT", "").replace("-USDT", "")

    factors = _get_latest_factors(
        db,
        ["active_addresses_24h", "transaction_count_24h",
         "avg_fee_usd", "network_hash_rate"],
        entity_key=base,
    )

    if not factors:
        raise HTTPException(status_code=404, detail="No network usage data found.")

    return {
        "symbol": normalized,
        "active_addresses_24h": factors.get("active_addresses_24h", {}).get("value"),
        "transaction_count_24h": factors.get("transaction_count_24h", {}).get("value"),
        "avg_fee_usd": factors.get("avg_fee_usd", {}).get("value"),
        "network_hash_rate": factors.get("network_hash_rate", {}).get("value"),
    }


@router.get("/summary")
def get_onchain_summary() -> dict[str, Any]:
    """返回链上数据全局摘要（供 Dashboard 使用）。"""
    db = get_market_db()

    rows = db.fetch_all(
        """SELECT factor_id, entity_key, value, timestamp
           FROM latest_onchain_timeseries
           WHERE factor_id IN (
               'exchange_netflow_24h', 'stablecoin_total_supply',
               'protocol_tvl', 'active_addresses_24h'
           )
           ORDER BY factor_id, entity_key""",
        (),
    )

    summary: dict[str, Any] = {}
    for row in rows:
        fid = row["factor_id"]
        summary.setdefault(fid, {})[row["entity_key"]] = row["value"]

    return {"onchain_summary": summary}
