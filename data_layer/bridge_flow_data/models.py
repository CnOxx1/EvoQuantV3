"""bridge_flow_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeFlow:
    """单条跨链桥资金流记录。"""
    bridge_name: str       # stargate, wormhole, across, layerzero
    source_chain: str      # ethereum, arbitrum, optimism
    dest_chain: str
    token: str             # USDC, ETH, USDT
    volume_usd: float
    tx_count: int
    avg_time_seconds: int  # 平均跨链时间
    snapshot_time: str     # ISO 8601


@dataclass(frozen=True)
class ChainNetFlow:
    """某链在某时间窗口的净流入/流出。"""
    chain: str
    interval: str          # 1h, 4h, 1d
    window_start: str
    window_end: str
    inflow_usd: float      # 流入该链
    outflow_usd: float     # 流出该链
    net_flow_usd: float    # inflow - outflow（正=净流入）
    top_source_chain: str  # 最大流入来源链
    top_dest_chain: str    # 最大流出目标链
    dominant_token: str    # 主要跨链代币
