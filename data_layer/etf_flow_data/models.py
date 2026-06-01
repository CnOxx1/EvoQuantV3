"""etf_flow_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EtfDailyFlow:
    """单只 ETF 单日资金流记录。"""
    date: str              # YYYY-MM-DD
    etf_name: str          # e.g. IBIT, FBTC, ETHA
    asset: str             # BTC / ETH
    issuer: str            # BlackRock, Fidelity, etc.
    net_flow_usd: float
    total_aum_usd: float
    shares_outstanding: float
    price: float
    premium_discount_pct: float


@dataclass(frozen=True)
class EtfFlowSummary:
    """某资产单日 ETF 资金流汇总。"""
    date: str
    asset: str
    total_net_flow_usd: float
    cumulative_net_flow_usd: float
    top_inflow_issuer: str
    top_outflow_issuer: str
