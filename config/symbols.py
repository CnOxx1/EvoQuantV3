"""资产宇宙定义：符号、层级、板块分组。

层级决定采集频率：
- CORE: 最高频（orderbook 3s, derivatives 60s）
- ACTIVE: 中频（orderbook 10s, derivatives 300s）
- MONITOR: 低频（orderbook 30s, derivatives 900s）

Ticker 和 Kline 对所有层级统一频率（batch 采集无限速压力）。
"""

import os
from enum import Enum
from typing import Sequence, TypedDict


def _resolve_csv_override(
    env_name: str,
    default: Sequence[str],
    *,
    allowed: Sequence[str],
) -> list[str]:
    """读取逗号分隔的部署覆盖，并拒绝未知配置值。"""
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return list(default)

    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    if not values:
        return list(default)

    unknown_values = [value for value in values if value not in allowed]
    if unknown_values:
        raise ValueError(
            f"{env_name} 包含未支持的值: {', '.join(unknown_values)}；"
            f"允许值: {', '.join(allowed)}"
        )
    return values


class SymbolTier(str, Enum):
    CORE = "core"
    ACTIVE = "active"
    MONITOR = "monitor"


class SymbolConfig(TypedDict):
    symbol: str
    tier: str
    sector: str


SYMBOL_UNIVERSE: list[SymbolConfig] = [
    # T1 - Core（最高流动性、最高关注度）
    {"symbol": "BTC/USDT", "tier": "core", "sector": "store_of_value"},
    {"symbol": "ETH/USDT", "tier": "core", "sector": "smart_contract_l1"},
    # T2 - Active（高流动性、活跃交易）
    {"symbol": "SOL/USDT", "tier": "active", "sector": "smart_contract_l1"},
    {"symbol": "SUI/USDT", "tier": "active", "sector": "smart_contract_l1"},
    {"symbol": "DOGE/USDT", "tier": "active", "sector": "meme"},
    {"symbol": "XRP/USDT", "tier": "active", "sector": "payments"},
    {"symbol": "AVAX/USDT", "tier": "active", "sector": "smart_contract_l1"},
    {"symbol": "LINK/USDT", "tier": "active", "sector": "infrastructure"},
    # T3 - Monitor（中等流动性、覆盖主要板块）
    {"symbol": "ADA/USDT", "tier": "monitor", "sector": "smart_contract_l1"},
    {"symbol": "DOT/USDT", "tier": "monitor", "sector": "interoperability"},
    {"symbol": "POL/USDT", "tier": "monitor", "sector": "l2_scaling"},
    {"symbol": "UNI/USDT", "tier": "monitor", "sector": "defi"},
    {"symbol": "ARB/USDT", "tier": "monitor", "sector": "l2_scaling"},
    {"symbol": "OP/USDT", "tier": "monitor", "sector": "l2_scaling"},
    {"symbol": "NEAR/USDT", "tier": "monitor", "sector": "smart_contract_l1"},
    {"symbol": "ATOM/USDT", "tier": "monitor", "sector": "interoperability"},
    {"symbol": "APT/USDT", "tier": "monitor", "sector": "smart_contract_l1"},
    {"symbol": "TIA/USDT", "tier": "monitor", "sector": "modular"},
]

# 默认仅监控 BTC 与 ETH；完整资产宇宙保留为显式扩展配置的允许集合。
# 部署时可用 EVOQUANT_TARGET_SYMBOLS=BTC/USDT,ETH/USDT 覆盖默认范围。
SUPPORTED_TARGET_SYMBOLS: list[str] = [e["symbol"] for e in SYMBOL_UNIVERSE]
DEFAULT_TARGET_SYMBOLS: list[str] = ["BTC/USDT", "ETH/USDT"]
TARGET_SYMBOLS: list[str] = _resolve_csv_override(
    "EVOQUANT_TARGET_SYMBOLS",
    DEFAULT_TARGET_SYMBOLS,
    allowed=SUPPORTED_TARGET_SYMBOLS,
)
TARGET_ASSET_CODES: list[str] = [symbol.split("/", 1)[0] for symbol in TARGET_SYMBOLS]

# 预建索引：O(1) 查找 symbol → config（替代线性扫描）
_SYMBOL_INDEX: dict[str, dict] = {e["symbol"]: e for e in SYMBOL_UNIVERSE}


def symbols_by_tier(tier: SymbolTier) -> list[str]:
    """返回指定层级的符号列表。"""
    return [e["symbol"] for e in SYMBOL_UNIVERSE if e["tier"] == tier.value]


def symbols_by_sector(sector: str) -> list[str]:
    """返回指定板块的符号列表。"""
    return [e["symbol"] for e in SYMBOL_UNIVERSE if e["sector"] == sector]


def get_symbol_sector(symbol: str) -> str | None:
    """获取符号所属板块。"""
    entry = _SYMBOL_INDEX.get(symbol)
    return entry["sector"] if entry else None


def get_symbol_tier(symbol: str) -> SymbolTier | None:
    """获取符号所属层级。"""
    entry = _SYMBOL_INDEX.get(symbol)
    if entry:
        return SymbolTier(entry["tier"])
    return None


# 板块分组（自动从 SYMBOL_UNIVERSE 生成）
SECTOR_DEFINITIONS: dict[str, list[str]] = {}
for _entry in SYMBOL_UNIVERSE:
    SECTOR_DEFINITIONS.setdefault(_entry["sector"], []).append(_entry["symbol"])

# v4.3.0: 预计算所有板块符号的扁平集合（供 sector_snapshot 等端点 O(1) 判定）
ALL_SECTOR_SYMBOLS: frozenset[str] = frozenset(
    sym for syms in SECTOR_DEFINITIONS.values() for sym in syms
)


# 目标交易所（与 settings.EXCHANGE_CONFIG 中的 key 对应）。
# 部署时可用 EVOQUANT_TARGET_EXCHANGES=okx 避开不可达交易所。
DEFAULT_TARGET_EXCHANGES = [
    "binance",
    "okx",
    "bybit",
]
TARGET_EXCHANGES = _resolve_csv_override(
    "EVOQUANT_TARGET_EXCHANGES",
    DEFAULT_TARGET_EXCHANGES,
    allowed=DEFAULT_TARGET_EXCHANGES,
)

# K线采集周期。部署时可用 EVOQUANT_KLINE_TIMEFRAMES=1m,5m 控制请求预算。
DEFAULT_KLINE_TIMEFRAMES = [
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
]
KLINE_TIMEFRAMES = _resolve_csv_override(
    "EVOQUANT_KLINE_TIMEFRAMES",
    DEFAULT_KLINE_TIMEFRAMES,
    allowed=DEFAULT_KLINE_TIMEFRAMES,
)

# K线历史回填天数
KLINE_BACKFILL_DAYS = 30

# 深度数据采集档位数
ORDERBOOK_DEPTH = 20