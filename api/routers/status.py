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
    # === 交易所核心（免费 API）===
    "exchange": {
        "db": "exchange",
        "table": "latest_tickers",
        "description": "交易所行情 (Binance/OKX/Bybit)",
    },
    "derivatives": {
        "db": "exchange",
        "table": "latest_funding_rates",
        "description": "衍生品 (资金费率/持仓量/清算)",
    },
    "orderflow": {
        "db": "exchange",
        "table": "latest_trade_flow_bars",
        "description": "订单流 (CVD/大单/买卖压力)",
    },
    "orderbook_depth": {
        "db": "exchange",
        "table": "latest_orderbook_snapshots",
        "description": "盘口深度 (5000档)",
    },
    # === 逻辑层 (analytics) ===
    "technical_indicators": {
        "db": "analytics",
        "table": "technical_indicators",
        "description": "技术指标 (228个)",
    },
    "feature_standardization": {
        "db": "analytics",
        "table": "feature_standardization_details",
        "description": "特征标准化 (Z-score/百分位/排名)",
    },
    "cross_asset": {
        "db": "analytics",
        "table": "cross_asset_correlation",
        "description": "跨资产分析 (相关性/板块轮动)",
    },
    "portfolio_risk": {
        "db": "analytics",
        "table": "portfolio_risk_snapshots",
        "description": "组合风险 (VaR/集中度)",
    },
    "regime_detection": {
        "db": "analytics",
        "table": "regime_states",
        "description": "市场状态分类 (trending/ranging/crisis)",
    },
    "anomaly_detection": {
        "db": "analytics",
        "table": "anomaly_events",
        "description": "异常检测 (价格尖刺/量激增)",
    },
    "sentiment_composite": {
        "db": "analytics",
        "table": "composite_sentiment_states",
        "description": "综合情绪评分",
    },
    "liquidity_regime": {
        "db": "analytics",
        "table": "liquidity_regime_states",
        "description": "流动性 Regime 分类",
    },
    # === 外部数据 (market) ===
    "macro": {
        "db": "market",
        "table": "macro_timeseries",
        "description": "宏观数据 (DXY/纳指/黄金/利率)",
    },
    "news": {
        "db": "market",
        "table": "news_articles",
        "description": "新闻情感 (分类/标注)",
    },
    "onchain": {
        "db": "market",
        "table": "latest_onchain_timeseries",
        "description": "链上数据 (TVL/交易所流/质押)",
    },
    "options": {
        "db": "market",
        "table": "latest_options_summary",
        "description": "期权数据 (波动率曲面/Gamma)",
    },
    "defi": {
        "db": "market",
        "table": "defi_tvl",
        "description": "DeFi 协议 (TVL/借贷/DEX)",
    },
    "governance": {
        "db": "market",
        "table": "governance_proposals",
        "description": "治理投票 (Snapshot/Tally)",
    },
    "gas_network": {
        "db": "market",
        "table": "gas_prices",
        "description": "Gas/网络 (Gas价格/拥堵)",
    },
    "etf_flow": {
        "db": "market",
        "table": "etf_flow_daily",
        "description": "ETF 资金流 (净流入/AUM)",
    },
    "mev": {
        "db": "market",
        "table": "mev_metrics",
        "description": "MEV 数据 (三明治/清算MEV)",
    },
    "mempool": {
        "db": "market",
        "table": "mempool_stats",
        "description": "内存池 (压力/Fee趋势)",
    },
    "exchange_reserve": {
        "db": "market",
        "table": "exchange_reserves",
        "description": "交易所储备 (BTC/ETH净流)",
    },
    "miner": {
        "db": "market",
        "table": "miner_metrics",
        "description": "矿工数据 (算力/Puell/收入)",
    },
    "stablecoin_flow": {
        "db": "market",
        "table": "stablecoin_events",
        "description": "稳定币事件流 (mint/burn)",
    },
    "token_unlock": {
        "db": "market",
        "table": "token_unlock_events",
        "description": "代币解锁 (排程/卖压)",
    },
    # === 需付费 / 数据源不可用（默认禁用）===
    "whale_tracker": {
        "db": "market",
        "table": "whale_transactions",
        "description": "巨鲸追踪 [需付费: Arkham+Nansen]",
    },
    "whale_pnl": {
        "db": "market",
        "table": "whale_portfolios",
        "description": "巨鲸 PnL [需付费: DeBank Pro]",
    },
    "social_sentiment": {
        "db": "market",
        "table": "social_sentiment_agg",
        "description": "社交情绪 [需付费: LunarCrush+Santiment]",
    },
    "nft_market": {
        "db": "market",
        "table": "nft_collection_stats",
        "description": "NFT 市场 [API 已失效: Reservoir]",
    },
    "dex_trade_flow": {
        "db": "market",
        "table": "dex_large_trades",
        "description": "DEX 交易流 [API 不存在: 0x]",
    },
    "regulatory": {
        "db": "market",
        "table": "regulatory_events",
        "description": "监管动态 [采集未实现]",
    },
    "onchain_address": {
        "db": "market",
        "table": "whale_moves",
        "description": "链上地址画像 [需付费: Arkham]",
    },
    "derivatives_sentiment": {
        "db": "market",
        "table": "derivatives_sentiment",
        "description": "衍生品情绪 [数据源缺失]",
    },
    "onchain_holder": {
        "db": "market",
        "table": "holder_distribution",
        "description": "链上持有者 [数据源缺失/付费]",
    },
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
