"""regime_detection 状态分类器。"""

import math
import statistics
from dataclasses import dataclass


@dataclass
class RegimeFeatures:
    """用于状态分类的特征集。"""
    returns: list[float]       # 收益率序列
    volatility: list[float]    # 波动率序列
    volume_ratio: float        # 当前成交量/均值
    rsi: float                 # RSI 值
    adx: float                 # ADX 值（趋势强度）
    correlation_to_btc: float  # 与 BTC 相关性


class RegimeClassifier:
    """基于多因子的市场状态分类器。

    分类维度：
    1. 价格状态：trending_up, trending_down, ranging, crisis
    2. 波动率状态：low, normal, high, extreme
    3. 相关性状态：high_corr, moderate_corr, decorrelated
    4. 动量状态：strong_up, weak_up, neutral, weak_down, strong_down
    """

    # 波动率阈值（年化）
    VOL_THRESHOLDS = {"low": 0.3, "normal": 0.6, "high": 1.0}  # > 1.0 = extreme
    # ADX 阈值
    ADX_TRENDING = 25.0
    ADX_STRONG_TREND = 40.0
    # RSI 阈值
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    # 危机检测：最大回撤阈值
    CRISIS_DRAWDOWN = -0.15  # 15% 回撤触发危机模式

    def classify_price_regime(self, features: RegimeFeatures) -> tuple[str, float]:
        """分类价格状态。返回 (regime, confidence)。"""
        if not features.returns:
            return "ranging", 0.5

        # 计算关键指标
        cumulative_return = sum(features.returns)
        max_drawdown = self._max_drawdown(features.returns)

        # 危机检测（优先级最高）
        if max_drawdown <= self.CRISIS_DRAWDOWN:
            confidence = min(1.0, abs(max_drawdown) / 0.3)
            return "crisis", confidence

        # 趋势检测
        if features.adx >= self.ADX_TRENDING:
            if cumulative_return > 0:
                confidence = min(1.0, features.adx / 50.0)
                return "trending_up", confidence
            else:
                confidence = min(1.0, features.adx / 50.0)
                return "trending_down", confidence

        # 默认：震荡
        confidence = 1.0 - (features.adx / self.ADX_TRENDING)
        return "ranging", max(0.3, confidence)

    def classify_volatility_regime(self, features: RegimeFeatures) -> str:
        """分类波动率状态。"""
        if not features.volatility:
            return "normal"

        current_vol = features.volatility[-1] if features.volatility else 0
        # 年化波动率
        annualized = current_vol * math.sqrt(365)

        if annualized < self.VOL_THRESHOLDS["low"]:
            return "low"
        elif annualized < self.VOL_THRESHOLDS["normal"]:
            return "normal"
        elif annualized < self.VOL_THRESHOLDS["high"]:
            return "high"
        return "extreme"

    def classify_correlation_regime(self, correlation: float) -> str:
        """分类相关性状态。"""
        if abs(correlation) >= 0.7:
            return "high_corr"
        elif abs(correlation) >= 0.4:
            return "moderate_corr"
        return "decorrelated"

    def classify_momentum_regime(self, features: RegimeFeatures) -> str:
        """分类动量状态。"""
        rsi = features.rsi
        if rsi >= 70:
            return "strong_up"
        elif rsi >= 55:
            return "weak_up"
        elif rsi >= 45:
            return "neutral"
        elif rsi >= 30:
            return "weak_down"
        return "strong_down"

    @staticmethod
    def _max_drawdown(returns: list[float]) -> float:
        """计算最大回撤。"""
        if not returns:
            return 0.0
        peak = 0.0
        cumulative = 0.0
        max_dd = 0.0
        for r in returns:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = cumulative - peak
            if dd < max_dd:
                max_dd = dd
        return max_dd

    def compute_transition_probability(
        self, current_regime: str, history: list[str]
    ) -> dict[str, float]:
        """基于历史状态序列计算转换概率。"""
        if not history:
            return {}

        transitions = {}
        total = 0
        for i in range(len(history) - 1):
            if history[i] == current_regime:
                next_state = history[i + 1]
                transitions[next_state] = transitions.get(next_state, 0) + 1
                total += 1

        if total == 0:
            return {}

        return {k: round(v / total, 4) for k, v in transitions.items()}
