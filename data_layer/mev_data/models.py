"""mev_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MevBlock:
    """单个区块的 MEV 数据。"""
    block_number: int
    timestamp: str             # ISO 8601
    mev_reward_eth: float
    mev_reward_usd: float
    sandwich_count: int
    arb_count: int
    liquidation_count: int
    builder: str               # block builder 名称


@dataclass(frozen=True)
class MevAggregation:
    """MEV 聚合数据（按时间窗口）。"""
    ts: str
    interval: str              # 1h
    total_mev_usd: float
    sandwich_volume_usd: float
    arb_volume_usd: float
    liquidation_mev_usd: float
    avg_mev_per_block: float
    builder_hhi: float         # Builder 集中度 (HHI)
