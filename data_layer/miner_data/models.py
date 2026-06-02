"""miner_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MinerMetrics:
    """矿工指标数据。"""
    hashrate: float                # 全网算力 (TH/s)
    difficulty: float              # 当前难度
    block_reward: float            # 区块奖励 (BTC)
    miner_revenue_24h: float       # 24h 矿工收入 (USD)
    miner_outflow_24h: float       # 24h 矿工流出 (BTC)
    hash_price: float              # 算力价格 (USD/TH/s/day)
    difficulty_adjustment_pct: float  # 下次难度调整预估 (%)
    puell_multiple: float          # Puell Multiple
    collected_at: str              # ISO 8601


@dataclass(frozen=True)
class HashrateHistory:
    """算力历史数据。"""
    hashrate: float                # 算力 (TH/s)
    difficulty: float              # 难度
    timestamp: str                 # ISO 8601
    collected_at: str              # ISO 8601
