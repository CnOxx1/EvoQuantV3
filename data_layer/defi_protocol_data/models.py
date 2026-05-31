"""defi_protocol_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolTVL:
    """协议 TVL 快照。"""
    protocol: str          # aave, uniswap, lido
    chain: str             # ethereum, arbitrum, optimism
    tvl_usd: float
    tvl_change_1d_pct: float
    tvl_change_7d_pct: float
    snapshot_time: str     # ISO 8601


@dataclass(frozen=True)
class LendingRate:
    """借贷协议利率快照。"""
    protocol: str          # aave, compound
    chain: str
    asset: str             # USDC, ETH, WBTC
    supply_apy: float      # 存款年化
    borrow_apy: float      # 借款年化
    utilization: float     # 资金利用率 0~1
    total_supply_usd: float
    total_borrow_usd: float
    snapshot_time: str


@dataclass(frozen=True)
class DexVolume:
    """DEX 交易量快照。"""
    protocol: str          # uniswap, curve, sushiswap
    chain: str
    volume_24h_usd: float
    trades_24h: int
    unique_traders_24h: int
    fees_24h_usd: float
    snapshot_time: str


@dataclass(frozen=True)
class DefiLiquidation:
    """DeFi 清算事件。"""
    protocol: str
    chain: str
    asset_liquidated: str
    collateral_asset: str
    amount_usd: float
    liquidation_time: str
    tx_hash: str
