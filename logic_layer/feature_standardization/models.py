"""特征标准化数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StandardizedFeature:
    """单个特征在单个资产上的标准化结果。"""

    symbol: str
    feature_name: str
    raw_value: float | None
    zscore_7d: float | None
    zscore_30d: float | None
    percentile_30d: float | None
    cross_asset_rank: int | None
    cross_asset_rank_total: int
    regime_label: str
    confidence: str


@dataclass
class CompositeSignal:
    """维度级复合信号。"""

    symbol: str
    composite_name: str
    composite_zscore: float | None
    composite_percentile: float | None
    cross_asset_rank: int | None
    cross_asset_rank_total: int
    regime_label: str
    confidence: str
    component_count: int
    component_names: list[str]
