"""采集层级配置：定义每个层级的采集间隔。

层级由 config.symbols.SymbolTier 定义，本文件只负责映射间隔参数。
"""

import os

from config.symbols import SymbolTier

# 每层级的采集间隔（秒）
TIER_INTERVALS: dict[SymbolTier, dict[str, int]] = {
    SymbolTier.CORE: {
        "orderbook_interval": int(
            os.getenv("TIER_CORE_ORDERBOOK_INTERVAL", "3")
        ),
        "derivatives_interval": int(
            os.getenv("TIER_CORE_DERIVATIVES_INTERVAL", "60")
        ),
    },
    SymbolTier.ACTIVE: {
        "orderbook_interval": int(
            os.getenv("TIER_ACTIVE_ORDERBOOK_INTERVAL", "10")
        ),
        "derivatives_interval": int(
            os.getenv("TIER_ACTIVE_DERIVATIVES_INTERVAL", "300")
        ),
    },
    SymbolTier.MONITOR: {
        "orderbook_interval": int(
            os.getenv("TIER_MONITOR_ORDERBOOK_INTERVAL", "30")
        ),
        "derivatives_interval": int(
            os.getenv("TIER_MONITOR_DERIVATIVES_INTERVAL", "900")
        ),
    },
}


def get_orderbook_interval(tier: SymbolTier) -> int:
    """获取指定层级的 orderbook 采集间隔（秒）。"""
    return TIER_INTERVALS[tier]["orderbook_interval"]


def get_derivatives_interval(tier: SymbolTier) -> int:
    """获取指定层级的衍生品采集间隔（秒）。"""
    return TIER_INTERVALS[tier]["derivatives_interval"]
