"""特征标准化纯计算引擎：Z-score、百分位、跨资产排名、regime 分类。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from logic_layer.feature_standardization.registry import (
    CONFIDENCE_THRESHOLD_HIGH,
    CONFIDENCE_THRESHOLD_MEDIUM,
)


class FeatureStandardizationCalculator:
    """无状态计算器，所有方法为 staticmethod 或 classmethod。"""

    REGIME_THRESHOLDS = (
        ("extreme_high", 2.0),
        ("elevated", 1.0),
        ("normal", -1.0),
        ("depressed", -2.0),
    )

    @staticmethod
    def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
        """滚动 Z-score: (x - rolling_mean) / rolling_std。"""
        rolling_mean = series.rolling(window, min_periods=max(1, window // 4)).mean()
        rolling_std = series.rolling(window, min_periods=max(1, window // 4)).std(ddof=0)
        result = (series - rolling_mean) / rolling_std.replace(0, np.nan)
        return result

    @staticmethod
    def rolling_percentile_rank(series: pd.Series, window: int) -> pd.Series:
        """滚动百分位排名 (0-100)。"""
        def _pct_rank(arr: np.ndarray) -> float:
            if len(arr) < 2:
                return np.nan
            current = arr[-1]
            if np.isnan(current):
                return np.nan
            valid = arr[~np.isnan(arr)]
            if len(valid) < 2:
                return np.nan
            return float((valid < current).sum() / (len(valid) - 1) * 100)

        return series.rolling(window, min_periods=max(1, window // 4)).apply(
            _pct_rank, raw=True
        )

    @staticmethod
    def cross_asset_rank(
        feature_values: dict[str, float | None],
        ascending: bool = False,
    ) -> dict[str, int | None]:
        """跨资产排名。rank 1 = 最强/最极端。"""
        valid = {
            s: v for s, v in feature_values.items()
            if v is not None and not (isinstance(v, float) and np.isnan(v))
        }
        if not valid:
            return {s: None for s in feature_values}
        sorted_symbols = sorted(
            valid.keys(), key=lambda s: valid[s], reverse=not ascending
        )
        ranks = {s: rank for rank, s in enumerate(sorted_symbols, 1)}
        return {s: ranks.get(s) for s in feature_values}

    @classmethod
    def classify_regime(cls, zscore: float | None) -> str:
        """将 Z-score 映射为语义标签。"""
        if zscore is None or (isinstance(zscore, float) and np.isnan(zscore)):
            return "unknown"
        for label, threshold in cls.REGIME_THRESHOLDS:
            if zscore >= threshold:
                return label
        return "extreme_low"

    @staticmethod
    def compute_confidence(available_count: int, required_count: int) -> str:
        """根据数据充足度判断置信度。"""
        if required_count <= 0:
            return "low"
        ratio = available_count / required_count
        if ratio >= CONFIDENCE_THRESHOLD_HIGH:
            return "high"
        if ratio >= CONFIDENCE_THRESHOLD_MEDIUM:
            return "medium"
        return "low"

    @staticmethod
    def compute_composite(values: dict[str, float | None]) -> float | None:
        """计算复合信号：非空组件的均值。"""
        valid = [
            v for v in values.values()
            if v is not None and not (isinstance(v, float) and np.isnan(v))
        ]
        if not valid:
            return None
        return float(np.mean(valid))
