"""mempool_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MempoolSnapshot:
    """内存池快照数据。"""
    timestamp: str              # ISO 8601
    pending_count: int          # 待确认交易数量
    pending_vsize_mb: float     # 待确认交易总虚拟大小 (MB)
    fee_rate_fastest: float     # 最快确认费率 (sat/vB)
    fee_rate_median: float      # 中等优先级费率 (sat/vB)
    fee_rate_slow: float        # 低优先级费率 (sat/vB)
    large_tx_count: int         # 大额交易数量
    large_tx_total_value: float # 大额交易总价值 (BTC)


@dataclass(frozen=True)
class PendingLargeTx:
    """内存池中的大额待确认交易。"""
    txid: str                   # 交易 ID
    value_btc: float            # 交易价值 (BTC)
    fee_rate: float             # 费率 (sat/vB)
    vsize: int                  # 虚拟大小 (vBytes)
    timestamp: str              # ISO 8601
