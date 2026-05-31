"""whale_tracker_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WhaleTransaction:
    """单笔巨鲸交易记录。"""
    tx_hash: str
    chain: str             # ethereum, bitcoin, solana
    entity_key: str        # BTC, ETH, etc.
    from_address: str
    to_address: str
    from_label: str        # exchange, whale, fund, unknown
    to_label: str
    amount_usd: float
    amount_native: float
    tx_time: str           # ISO 8601
    tx_type: str           # transfer, deposit, withdrawal


@dataclass(frozen=True)
class WhaleAggregation:
    """某实体在某时间窗口的巨鲸活动聚合。"""
    entity_key: str
    interval: str          # 1h, 4h, 1d
    window_start: str
    window_end: str
    total_volume_usd: float
    deposit_volume_usd: float    # 流入交易所
    withdrawal_volume_usd: float # 流出交易所
    net_flow_usd: float          # deposit - withdrawal（正=抛压）
    tx_count: int
    unique_whales: int
    largest_tx_usd: float
    flow_direction: str          # accumulation, distribution, neutral
