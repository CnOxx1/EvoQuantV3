"""perpetual_dex_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PerpDexPosition:
    """永续合约 DEX 持仓数据。"""
    exchange: str              # 交易所名称 (dydx/hyperliquid/gmx)
    symbol: str                # 交易对
    side: str                  # long/short
    size_usd: float            # 仓位规模 (USD)
    leverage: float            # 杠杆倍数
    entry_price: float         # 开仓价格
    mark_price: float          # 标记价格
    pnl_pct: float             # 盈亏百分比
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class PerpDexFunding:
    """永续合约 DEX 资金费率数据。"""
    exchange: str              # 交易所名称
    symbol: str                # 交易对
    funding_rate: float        # 资金费率
    next_funding_ts: str       # 下次结算时间
    open_interest_usd: float   # 未平仓合约 (USD)
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class PerpDexVolume:
    """永续合约 DEX 交易量数据。"""
    exchange: str              # 交易所名称
    symbol: str                # 交易对
    volume_24h_usd: float      # 24h 交易量 (USD)
    trades_24h: int            # 24h 交易笔数
    timestamp: str             # ISO 8601
