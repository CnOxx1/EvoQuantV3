"""Status 路由 — API 数据域可用性总览。

提供每个数据域的启用/禁用状态和数据存在性检查，
让用户和 AI 提前知道哪些域有数据、哪些为空、哪些被禁用。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from loguru import logger

from core.feature_flags import feature_flags

router = APIRouter(prefix="/status", tags=["status"])

# 域 → 主表映射（用于 EXISTS 检查）
DOMAIN_REGISTRY: dict[str, dict[str, str]] = {
    "exchange": {"db": "exchange", "table": "latest_tickers", "description": "OKX 市场行情"},
    "derivatives": {"db": "exchange", "table": "latest_funding_rates", "description": "公开资金费率与持仓数据"},
    "orderflow": {"db": "exchange", "table": "latest_trade_flow_bars", "description": "成交与订单流原始聚合"},
    "orderbook_depth": {"db": "exchange", "table": "latest_orderbook_snapshots", "description": "订单簿深度快照"},
    "macro": {"db": "market", "table": "macro_timeseries", "description": "公开宏观时间序列"},
    "news": {"db": "market", "table": "news_articles", "description": "公开新闻原文与元数据"},
    "onchain": {"db": "market", "table": "latest_onchain_timeseries", "description": "公开链上与 DeFi 指标"},
    "options": {"db": "market", "table": "latest_options_timeseries", "description": "Deribit 公开期权数据"},
    "defi": {"db": "market", "table": "defi_tvl", "description": "DeFi 协议 TVL 数据"},
    "governance": {"db": "market", "table": "governance_proposals", "description": "Snapshot 公共治理提案"},
    "gas_network": {"db": "market", "table": "gas_prices", "description": "公开 Gas 与网络状态"},
    "mev": {"db": "market", "table": "mev_blocks", "description": "Flashbots 公开 MEV 区块"},
    "mempool": {"db": "market", "table": "mempool_snapshots", "description": "Bitcoin Mempool 快照"},
    "exchange_reserve": {"db": "market", "table": "exchange_reserves", "description": "OKX 官方 PoR 报告快照"},
    "miner": {"db": "market", "table": "miner_metrics", "description": "公开矿工网络指标"},
    "stablecoin_flow": {"db": "market", "table": "stablecoin_chain_flows", "description": "稳定币供应与链分布快照"},
    "onchain_address": {"db": "market", "table": "address_labels", "description": "公开已知地址标签"},
    "asset_metadata": {"db": "market", "table": "asset_metadata_snapshots", "description": "CoinGecko 公开资产元数据与当前供应快照"},
    "bitcoin_onchain_history": {"db": "market", "table": "bitcoin_onchain_history", "description": "Bitcoin 公开交易、活跃地址与手续费日频历史"},
    "ethereum_network": {"db": "market", "table": "ethereum_network_snapshots", "description": "Ethereum 公开交易、区块与手续费网络快照"},
    "okx_derivatives_history": {"db": "exchange", "table": "okx_derivatives_raw", "description": "OKX 公开 OI、资金费率、清算与基差原始记录"},
    "okx_market_history": {"db": "exchange", "table": "okx_market_candle_history_raw", "description": "OKX BTC/ETH 现货与永续小时 K 线原始历史"},
    "okx_funding_history": {"db": "exchange", "table": "okx_funding_history_raw", "description": "OKX BTC/ETH 永续资金费率原始历史"},
    "deribit_funding_history": {"db": "exchange", "table": "deribit_funding_history_raw", "description": "Deribit BTC/ETH 永续小时资金费率原始历史"},
    "multi_exchange_quotes": {"db": "exchange", "table": "public_exchange_quote_snapshots", "description": "Kraken 与 Coinbase 公开跨交易所报价原始快照"},
}


def _get_db(db_type: str):
    """按类型获取数据库连接。"""
    from api.dependencies import get_analytics_db, get_exchange_db, get_market_db

    if db_type == "analytics":
        return get_analytics_db()
    elif db_type == "exchange":
        return get_exchange_db()
    else:
        return get_market_db()


@router.get("/")
def api_status() -> dict[str, Any]:
    """API 数据域可用性总览。

    返回每个域的状态：
    - active: 域已启用且有数据
    - empty: 域已启用但表为空
    - disabled: 域被 feature flag 禁用
    - error: 查询出错（表可能不存在）
    """
    results: dict[str, dict[str, Any]] = {}

    for domain, cfg in DOMAIN_REGISTRY.items():
        enabled = feature_flags.is_enabled(domain)
        if not enabled:
            results[domain] = {
                "status": "disabled",
                "description": cfg["description"],
            }
            continue

        try:
            db = _get_db(cfg["db"])
            row = db.fetch_one(
                f"SELECT 1 FROM {cfg['table']} LIMIT 1"
            )
            has_data = row is not None
            results[domain] = {
                "status": "active" if has_data else "empty",
                "description": cfg["description"],
            }
        except Exception as exc:
            logger.debug("status check for {} failed: {}", domain, exc)
            results[domain] = {
                "status": "error",
                "description": cfg["description"],
            }

    # 汇总
    active_count = sum(1 for d in results.values() if d["status"] == "active")
    empty_count = sum(1 for d in results.values() if d["status"] == "empty")
    disabled_count = sum(1 for d in results.values() if d["status"] == "disabled")
    error_count = sum(1 for d in results.values() if d["status"] == "error")

    return {
        "summary": {
            "total_domains": len(results),
            "active": active_count,
            "empty": empty_count,
            "disabled": disabled_count,
            "error": error_count,
        },
        "domains": results,
    }


@router.get("/disabled")
def list_disabled_routers() -> dict[str, Any]:
    """列出所有被禁用的路由及其原因。"""
    disabled = {}
    for domain, cfg in DOMAIN_REGISTRY.items():
        if not feature_flags.is_enabled(domain):
            disabled[domain] = cfg["description"]
    return {
        "disabled_count": len(disabled),
        "routers": disabled,
        "hint": "设置 FF_{DOMAIN_UPPER}_ENABLED=1 可重新启用对应路由",
    }
