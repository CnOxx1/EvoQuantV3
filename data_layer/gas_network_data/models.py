"""gas_network_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GasPrice:
    """当前 Gas 价格数据。"""
    base_fee_gwei: float
    priority_fee_gwei: float
    gas_used_ratio: float
    block_number: int
    timestamp: str              # ISO 8601


@dataclass(frozen=True)
class NetworkCongestion:
    """网络拥堵状态数据。"""
    pending_tx_count: int
    block_utilization_pct: float
    avg_wait_seconds: float
    congestion_level: str       # low / moderate / high / extreme
    timestamp: str              # ISO 8601


@dataclass(frozen=True)
class GasSpike:
    """Gas 价格突增事件。"""
    block_number: int
    base_fee_gwei: float
    spike_ratio: float          # 当前 base fee / 1h 均值
    probable_cause: str         # NFT mint / airdrop / liquidation cascade / unknown
    timestamp: str              # ISO 8601
