"""exchange_reserve_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExchangeReserve:
    """交易所储备数据。"""
    exchange: str              # 交易所名称
    asset: str                 # 资产类型 (BTC/ETH/USDT)
    reserve_balance: float     # 储备余额
    collected_at: str          # ISO 8601


@dataclass(frozen=True)
class ReserveChange:
    """储备变动数据。"""
    exchange: str              # 交易所名称
    asset: str                 # 资产类型
    change_24h: float          # 24小时变动
    change_7d: float           # 7天变动
    netflow_24h: float         # 24小时净流入/流出
    collected_at: str          # ISO 8601
