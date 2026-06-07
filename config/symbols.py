"""资产宇宙定义：符号、层级、板块分组。

层级决定采集频率：
- CORE: 最高频（orderbook 3s, derivatives 60s）
- ACTIVE: 中频（orderbook 10s, derivatives 300s）
- MONITOR: 低频（orderbook 30s, derivatives 900s）

Ticker 和 Kline 对所有层级统一频率（batch 采集无限速压力）。
"""

from enum import Enum
from typing import TypedDict


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

# 向后兼容：扁平符号列表（现有代码无需修改）
TARGET_SYMBOLS: list[str] = [e["symbol"] for e in SYMBOL_UNIVERSE]

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


# 目标交易所（与 settings.EXCHANGE_CONFIG 中的 key 对应）
TARGET_EXCHANGES = [
    "binance",
    "okx",
    "bybit",
]

# K线采集周期
KLINE_TIMEFRAMES = [
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
]

# K线历史回填天数
KLINE_BACKFILL_DAYS = 30

# 深度数据采集档位数
ORDERBOOK_DEPTH = 20