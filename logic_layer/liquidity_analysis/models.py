"""liquidity_analysis 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LiquidityProfile:
    """某标的的流动性画像。"""
    entity_key: str
    exchange: str
    bid_depth_usd: float       # 买盘深度（距中间价 2% 内）
    ask_depth_usd: float       # 卖盘深度（距中间价 2% 内）
    spread_bps: float          # bid-ask spread (basis points)
    slippage_10k_bps: float    # $10K 订单预估滑点
    slippage_100k_bps: float   # $100K 订单预估滑点
    slippage_1m_bps: float     # $1M 订单预估滑点
    liquidity_score: float     # 0~100 综合流动性评分
    as_of: str


@dataclass(frozen=True)
class LiquidityAlert:
    """流动性预警。"""
    entity_key: str
    alert_type: str            # thin_book, spread_blow, depth_drop, imbalance
    severity: str              # critical, warning
    current_value: float
    normal_value: float
    description: str
    detected_at: str
