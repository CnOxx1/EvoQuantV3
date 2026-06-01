"""cefi_lending_rate 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CefiLendingRate:
    """单平台单资产借贷利率。"""
    ts: str                    # ISO 8601
    platform: str              # binance, okx, bybit
    asset: str                 # BTC, ETH, USDT, USDC
    product_type: str          # flexible, fixed
    supply_apy: float          # 存款年化
    borrow_apy: float          # 借款年化
    utilization_pct: float     # 资金利用率
    min_amount: float          # 最低金额


@dataclass(frozen=True)
class LendingRateSpread:
    """CeFi vs DeFi 利率价差。"""
    ts: str
    asset: str
    cefi_avg_supply: float
    defi_avg_supply: float
    cefi_avg_borrow: float
    defi_avg_borrow: float
    supply_spread: float       # cefi - defi
    borrow_spread: float       # cefi - defi
    spread_signal: str         # normal / inverted / compressed
