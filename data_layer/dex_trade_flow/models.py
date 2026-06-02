"""dex_trade_flow 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DexLargeTrade:
    """单条 DEX 大额交易记录。"""
    timestamp: str
    token_in: str
    token_out: str
    amount_usd: float
    router: str
    dex_venue: str
    tx_hash: str
    trader_address: str
    is_mev_victim: bool
    trade_type: str


@dataclass(frozen=True)
class DexRouterStats:
    """DEX 路由器统计。"""
    router: str
    volume_24h_usd: float
    trade_count: int
    avg_trade_size: float
    timestamp: str
