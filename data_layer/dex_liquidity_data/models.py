"""DEX 流动性数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LiquidityPool:
    """DEX 流动性池快照。"""
    protocol: str              # uniswap_v3 / curve
    pool_address: str
    token0: str
    token1: str
    tvl_usd: float
    volume_24h_usd: float
    fee_tier: float
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class TickLiquidity:
    """Uniswap V3 Tick 级别流动性分布。"""
    pool_address: str
    tick_lower: int
    tick_upper: int
    liquidity_usd: float
    price_range_low: float
    price_range_high: float


@dataclass(frozen=True)
class LiquidityEvent:
    """流动性添加/移除事件。"""
    protocol: str
    pool_address: str
    event_type: str            # mint / burn / swap
    amount_usd: float
    sender: str
    timestamp: str
    tx_hash: str
