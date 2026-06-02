"""cross_chain_messaging 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CrossChainMessage:
    """单条跨链消息协议数据。"""
    protocol: str
    src_chain: str
    dst_chain: str
    message_count: int
    value_transferred_usd: float
    timestamp: str
    avg_latency_seconds: float
    failure_rate: float


@dataclass(frozen=True)
class MessagingMetrics:
    """跨链消息协议整体指标。"""
    protocol: str
    total_messages_24h: int
    total_value_24h_usd: float
    unique_chains: int
    avg_latency: float
    timestamp: str
