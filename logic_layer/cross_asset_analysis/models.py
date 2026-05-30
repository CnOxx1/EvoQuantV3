"""跨资产分析数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CorrelationSnapshot:
    snapshot_time: str
    window_hours: int
    matrix: dict[str, dict[str, float]]
    symbols: list[str]
    avg_correlation: float
    max_correlation: float
    min_correlation: float


@dataclass
class RelativeStrengthEntry:
    snapshot_time: str
    symbol: str
    asset: str
    sector: str | None
    tier: str | None
    rs_vs_btc_7d: float | None
    rs_vs_btc_3d: float | None
    rs_vs_btc_1d: float | None
    rs_rank: int
    rs_momentum: str  # rising / falling / stable
    price_change_7d_pct: float | None
    volume_change_7d_pct: float | None


@dataclass
class SectorRotationEntry:
    snapshot_time: str
    sector: str
    sector_return_7d: float | None
    sector_volatility_7d: float | None
    sector_momentum_score: float | None
    sector_net_flow_24h: float | None
    sector_oi_change_24h: float | None
    constituent_count: int
    rotation_phase: str  # leading / weakening / lagging / improving


@dataclass
class FundFlowEntry:
    snapshot_time: str
    scope: str  # total / tier:core / sector:defi etc.
    net_taker_flow_1h: float | None
    net_taker_flow_24h: float | None
    oi_change_1h: float | None
    oi_change_24h: float | None
    aggressive_buy_share: float | None
