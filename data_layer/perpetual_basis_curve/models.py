"""perpetual_basis_curve 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FuturesTermStructure:
    """单个合约的期限结构数据点。"""
    ts: str                    # ISO 8601
    symbol: str                # BTCUSDT, ETHUSDT
    exchange: str              # binance, okx, bybit
    contract_type: str         # perp, quarterly, bi_quarterly
    expiry_date: str | None    # 到期日（perp 为 None）
    price: float
    basis_pct: float           # (futures - spot) / spot * 100
    annualized_basis_pct: float


@dataclass(frozen=True)
class BasisCurveSnapshot:
    """期限结构曲线快照。"""
    ts: str
    symbol: str
    curve_slope: float         # 曲线斜率
    contango_backwardation: str  # contango / backwardation / flat
    roll_yield_7d: float       # 7 天滚动收益
    term_premium: float        # 期限溢价
    convexity: float           # 曲线凸度
