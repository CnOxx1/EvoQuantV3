"""Onchain 路由 — 链上数据查询（交易所净流量、鲸鱼活动、稳定币、TVL 等）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_exchange_db, get_market_db
from api.routers._helpers import _safe_float
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
            f"""SELECT factor_id, entity_key, value, observation_time
                FROM latest_onchain_timeseries
                WHERE factor_id IN ({placeholders}) AND entity_key = ?
                ORDER BY factor_id""",
            (*params, entity_key),
        )
    else:
        rows = db.fetch_all(
            f"""SELECT factor_id, entity_key, value, observation_time
                FROM latest_onchain_timeseries
                WHERE factor_id IN ({placeholders})
                ORDER BY factor_id, entity_key""",
            params,
        )

    result: dict[str, Any] = {}
    for row in rows:
        fid = row["factor_id"]
        if entity_key:
            result[fid] = {"value": row["value"], "timestamp": row["observation_time"]}
        else:
            result.setdefault(fid, {})[row["entity_key"]] = {
                "value": row["value"],
                "timestamp": row["observation_time"],
            }
    return result


@router.get("/exchange-flow/{symbol}")
def get_exchange_flow(symbol: str) -> dict[str, Any]:
    """返回指定资产的交易所资金流向信号。

    基于 OI 变化 + 资金费率合成：
    - OI 增加 + 资金费率上升 → 资金流入做多
    - OI 减少 + 资金费率下降 → 资金流出
    - 同时查询链上数据（如有）
    """
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    exchange_db = get_exchange_db()
    base = normalized.split("/")[0]

    # OI change data
    oi_row = exchange_db.fetch_one(
        """SELECT open_interest_contracts, open_interest_change_1h, open_interest_change_24h
           FROM latest_open_interest_snapshots
           WHERE symbol = ? AND exchange = 'binance'""",
        (normalized,),
    )

    # Funding rate
    funding = exchange_db.fetch_one(
        "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
        (normalized,),
    )

    # Volume trend (recent vs average)
    volumes = exchange_db.fetch_all(
        "SELECT volume FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 24",
        (normalized,),
    )
    vol_list = [_safe_float(r["volume"]) for r in volumes if _safe_float(r["volume"])]

    oi_change_1h = _safe_float(oi_row["open_interest_change_1h"]) if oi_row else None
    oi_change_24h = _safe_float(oi_row["open_interest_change_24h"]) if oi_row else None
    oi_contracts = _safe_float(oi_row["open_interest_contracts"]) if oi_row else None
    rate = _safe_float(funding["funding_rate"]) if funding else None

    # Synthesize flow signal
    signal = "neutral"
    flow_score = 0.0
    if oi_change_24h is not None and rate is not None:
        # OI increasing + positive funding = net long inflow
        if oi_change_24h > 0 and rate > 0.0003:
            signal = "net_inflow_long"
            flow_score = min(100, oi_change_24h / 100 + rate * 10000)
        # OI increasing + negative funding = net short inflow
        elif oi_change_24h > 0 and rate < -0.0003:
            signal = "net_inflow_short"
            flow_score = min(100, oi_change_24h / 100 + abs(rate) * 10000)
        # OI decreasing = position closing / outflow
        elif oi_change_24h < -500:
            signal = "net_outflow"
            flow_score = min(100, abs(oi_change_24h) / 100)

    # Volume context
    vol_ratio = None
    if len(vol_list) >= 6:
        recent_avg = sum(vol_list[:3]) / 3
        older_avg = sum(vol_list[3:]) / len(vol_list[3:])
        vol_ratio = round(recent_avg / older_avg, 2) if older_avg > 0 else None

    # Also try onchain data if available
    onchain_netflow = None
    try:
        mdb = get_market_db()
        onchain_row = mdb.fetch_one(
            """SELECT value, observation_time FROM latest_onchain_timeseries
               WHERE category = 'exchange_flow' AND entity_key = ?""",
            (base,),
        )
        if onchain_row:
            onchain_netflow = _safe_float(onchain_row["value"])
    except Exception:
        pass

    return {
        "symbol": normalized,
        "signal": signal,
        "flow_score": round(flow_score, 1),
        "open_interest_contracts": oi_contracts,
        "oi_change_1h": oi_change_1h,
        "oi_change_24h": oi_change_24h,
        "funding_rate": rate,
        "volume_ratio_3h_vs_avg": vol_ratio,
        "onchain_netflow_usd": onchain_netflow,
        "data_source": "synthetic_from_derivatives" if onchain_netflow is None else "hybrid",
    }


@router.get("/whale-activity/{symbol}")
def get_whale_activity(symbol: str) -> dict[str, Any]:
    """返回指定资产的鲸鱼/大户活动信号。

    基于成交量异常 + 价格大幅波动 + OI 变化合成：
    - 成交量 > 3x 均值 + 价格上涨 → 大户积累
    - 成交量 > 3x 均值 + 价格下跌 → 大户派发
    - 同时查询链上数据（如有）
    """
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    exchange_db = get_exchange_db()
    base = normalized.split("/")[0]

    # Volume analysis (detect abnormal activity)
    volumes = exchange_db.fetch_all(
        "SELECT volume FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 48",
        (normalized,),
    )
    vol_list = [_safe_float(r["volume"]) for r in volumes if _safe_float(r["volume"])]

    # Price movement
    prices = exchange_db.fetch_all(
        "SELECT close FROM klines WHERE symbol = ? AND exchange = 'binance' AND timeframe = '1h' ORDER BY open_time DESC LIMIT 24",
        (normalized,),
    )
    price_list = [_safe_float(r["close"]) for r in prices if _safe_float(r["close"])]

    # OI change (proxy for large position changes)
    oi_row = exchange_db.fetch_one(
        """SELECT open_interest_contracts, open_interest_change_1h, open_interest_change_24h
           FROM latest_open_interest_snapshots
           WHERE symbol = ? AND exchange = 'binance'""",
        (normalized,),
    )

    # Funding rate
    funding = exchange_db.fetch_one(
        "SELECT funding_rate FROM latest_funding_rates WHERE symbol = ? AND exchange = 'binance'",
        (normalized,),
    )

    # Calculate whale signal
    signal = "low_activity"
    activity_score = 0.0
    vol_spike = False
    price_move_pct = 0.0

    if len(vol_list) >= 24:
        recent_vol = vol_list[0]
        avg_vol = sum(vol_list[6:]) / len(vol_list[6:])
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
        vol_spike = vol_ratio > 2.5
        activity_score += min(40, vol_ratio * 10)

    if len(price_list) >= 6:
        price_move_pct = (price_list[0] - price_list[5]) / price_list[5] * 100 if price_list[5] > 0 else 0
        activity_score += min(30, abs(price_move_pct) * 5)

    oi_change_24h = _safe_float(oi_row["open_interest_change_24h"]) if oi_row else None
    if oi_change_24h and abs(oi_change_24h) > 1000:
        activity_score += min(30, abs(oi_change_24h) / 100)

    # Determine signal
    if activity_score > 60:
        if price_move_pct > 0:
            signal = "whale_accumulation"
        else:
            signal = "whale_distribution"
    elif activity_score > 35:
        signal = "moderate_activity"

    # Also try onchain data if available
    onchain_whale_count = None
    try:
        mdb = get_market_db()
        onchain_row = mdb.fetch_one(
            """SELECT value, observation_time FROM latest_onchain_timeseries
               WHERE category = 'whale_activity' AND entity_key = ?""",
            (base,),
        )
        if onchain_row:
            onchain_whale_count = _safe_float(onchain_row["value"])
    except Exception:
        pass

    rate = _safe_float(funding["funding_rate"]) if funding else None

    return {
        "symbol": normalized,
        "whale_signal": signal,
        "activity_score": round(activity_score, 1),
        "volume_spike": vol_spike,
        "price_move_6h_pct": round(price_move_pct, 2),
        "oi_change_24h": oi_change_24h,
        "funding_rate": rate,
        "onchain_whale_transfer_count": onchain_whale_count,
        "data_source": "synthetic_from_derivatives" if onchain_whale_count is None else "hybrid",
    }


@router.get("/stablecoin")
def get_stablecoin_supply() -> dict[str, Any]:
    """返回稳定币供应量与流动性指标（USDT、USDC 等）。"""
    db = get_market_db()
    rows = db.fetch_all(
        """SELECT lot.factor_id, lot.entity_key, lot.value, lot.observation_time
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
            "timestamp": row["observation_time"],
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
            """SELECT factor_id, entity_key, value, observation_time
               FROM latest_onchain_timeseries
               WHERE factor_id = 'protocol_tvl' AND entity_key = ?""",
            (protocol,),
        )
    else:
        rows = db.fetch_all(
            """SELECT factor_id, entity_key, value, observation_time
               FROM latest_onchain_timeseries
               WHERE factor_id = 'protocol_tvl'
               ORDER BY CAST(value AS REAL) DESC
               LIMIT ?""",
            (limit,),
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No TVL data found.")

    records = [{"protocol": r["entity_key"], "tvl_usd": r["value"], "timestamp": r["observation_time"]} for r in rows]
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
        """SELECT factor_id, entity_key, value, observation_time
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
