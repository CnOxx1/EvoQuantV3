"""lending_utilization 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LendingPool:
    """借贷协议池信息快照。"""
    protocol: str           # aave, compound, morpho
    asset: str              # USDC, ETH, WBTC
    total_supply_usd: float
    total_borrow_usd: float
    utilization_rate: float  # 0~1
    supply_apy: float
    borrow_apy: float
    kink_utilization: float  # 拐点利用率
    kink_rate: float         # 拐点利率
    optimal_rate: float      # 最优利率
    timestamp: str           # ISO 8601


@dataclass(frozen=True)
class UtilizationSnapshot:
    """利用率时间序列快照。"""
    protocol: str
    asset: str
    utilization_rate: float
    supply_apy: float
    borrow_apy: float
    timestamp: str           # ISO 8601
