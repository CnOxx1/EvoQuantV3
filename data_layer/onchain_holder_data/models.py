"""onchain_holder_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HolderDistribution:
    """链上持仓分布数据。"""
    symbol: str                # 代币符号 (BTC)
    holder_category: str       # short_term/long_term/whale
    count: int                 # 持有者数量
    supply_pct: float          # 占总供应量百分比
    avg_cost_basis: float      # 平均持仓成本
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class HolderMetrics:
    """链上持仓指标数据。"""
    symbol: str                # 代币符号 (BTC)
    mvrv_ratio: float          # 市场价值/已实现价值比率
    sopr: float                # 已花费输出利润率
    nupl: float                # 净未实现盈亏
    supply_in_profit_pct: float  # 盈利中的供应量百分比
    timestamp: str             # ISO 8601
