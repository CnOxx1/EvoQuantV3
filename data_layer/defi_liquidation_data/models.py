"""defi_liquidation_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DefiLiquidation:
    """单条 DeFi 清算事件。"""
    protocol: str
    timestamp: str
    liquidator: str
    borrower: str
    collateral_asset: str
    debt_asset: str
    debt_repaid_usd: float
    collateral_seized_usd: float
    health_factor_before: float
    tx_hash: str
    block_number: int


@dataclass(frozen=True)
class HealthFactorDistribution:
    """健康因子分布。"""
    protocol: str
    timestamp: str
    hf_bucket: str
    position_count: int
    total_collateral_usd: float
