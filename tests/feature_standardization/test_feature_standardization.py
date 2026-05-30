"""特征标准化模块单元测试。"""

import numpy as np
import pandas as pd
import pytest

from logic_layer.feature_standardization.calculator import FeatureStandardizationCalculator


class TestRollingZscore:
    def test_basic_zscore(self):
        calc = FeatureStandardizationCalculator()
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = calc.rolling_zscore(series, window=5)
        # 最后一个值 10，窗口 [6,7,8,9,10]，mean=8, std~1.41
        assert not pd.isna(result.iloc[-1])
        assert result.iloc[-1] > 0  # 10 > mean(6..10)

    def test_constant_series_returns_nan(self):
        calc = FeatureStandardizationCalculator()
        series = pd.Series([5.0] * 20)
        result = calc.rolling_zscore(series, window=10)
        # std=0 → NaN
        assert pd.isna(result.iloc[-1])

    def test_nan_handling(self):
        calc = FeatureStandardizationCalculator()
        series = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0])
        result = calc.rolling_zscore(series, window=3)
        assert len(result) == 5


class TestRollingPercentileRank:
    def test_highest_value_gets_100(self):
        calc = FeatureStandardizationCalculator()
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = calc.rolling_percentile_rank(series, window=10)
        # 10 is highest in [1..10] → 100%
        assert result.iloc[-1] == 100.0

    def test_lowest_value_gets_0(self):
        calc = FeatureStandardizationCalculator()
        series = pd.Series([10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
        result = calc.rolling_percentile_rank(series, window=10)
        # 1 is lowest in [10..1] → 0%
        assert result.iloc[-1] == 0.0
