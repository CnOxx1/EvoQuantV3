"""funding_rate_model 计算器。"""

import math
import statistics


class FundingRateCalculator:
    """资金费率与基差计算器。

    核心功能：
    1. Funding rate 预测：基于历史均值回归 + 动量
    2. 基差分析：期现价差的状态分类和均值回归信号
    3. 拥挤度检测：判断多空拥挤程度
    """

    # 阈值
    FUNDING_NEUTRAL_BAND = 0.0001  # ±0.01% 视为中性
    FUNDING_EXTREME = 0.0005       # ±0.05% 视为极端
    BASIS_FLAT_BAND = 0.1          # ±0.1% 视为平坦

    def predict_next_funding(self, rates: list[float]) -> float:
        """预测下一期 funding rate。

        方法：均值回归模型 + 短期动量加权
        predicted = alpha * mean + (1-alpha) * latest_momentum
        """
        if len(rates) < 10:
            return rates[-1] if rates else 0.0

        # 长期均值
        long_mean = statistics.mean(rates)
        # 短期动量（最近 3 期均值）
        short_momentum = statistics.mean(rates[-3:])
        # 均值回归强度（越偏离均值，回归力越强）
        alpha = 0.3  # 均值回归权重

        predicted = alpha * long_mean + (1 - alpha) * short_momentum
        return round(predicted, 8)

    def compute_rate_zscore(self, rates: list[float]) -> float:
        """计算当前 funding rate 的 z-score。"""
        if len(rates) < 10:
            return 0.0
        mean = statistics.mean(rates[:-1])
        std = statistics.stdev(rates[:-1]) if len(rates) > 2 else 0.0001
        if std == 0:
            std = 0.0001
        return round((rates[-1] - mean) / std, 4)

    def compute_rate_percentile(self, rates: list[float]) -> float:
        """计算当前 funding rate 在历史中的百分位。"""
        if len(rates) < 10:
            return 50.0
        current = rates[-1]
        below = sum(1 for r in rates[:-1] if r <= current)
        return round(below / (len(rates) - 1) * 100, 1)

    def compute_cumulative_funding(self, rates: list[float], periods: int = 21) -> float:
        """计算累积 funding（默认 7 天 = 21 期 × 8h）。"""
        if len(rates) < periods:
            return sum(rates)
        return round(sum(rates[-periods:]), 8)

    def classify_direction_bias(self, rate: float) -> str:
        """判断多空拥挤方向。"""
        if rate > self.FUNDING_EXTREME:
            return "long_crowded"
        elif rate < -self.FUNDING_EXTREME:
            return "short_crowded"
        elif rate > self.FUNDING_NEUTRAL_BAND:
            return "slight_long"
        elif rate < -self.FUNDING_NEUTRAL_BAND:
            return "slight_short"
        return "neutral"

    def compute_mean_reversion_signal(self, rates: list[float]) -> float:
        """计算均值回归信号。

        返回 -1~1：
        - 正值：预期 funding 下降（做空 funding 的机会）
        - 负值：预期 funding 上升（做多 funding 的机会）
        """
        if len(rates) < 10:
            return 0.0

        zscore = self.compute_rate_zscore(rates)
        # 信号强度与偏离程度成正比，方向相反（均值回归）
        signal = -zscore / 4.0  # 归一化到 -1~1
        return round(max(-1.0, min(1.0, signal)), 4)

    def compute_basis(self, spot: float, futures: float) -> float:
        """计算基差百分比。"""
        if spot <= 0:
            return 0.0
        return round((futures - spot) / spot * 100, 6)

    def compute_annualized_basis(self, basis_pct: float, days_to_expiry: int = 90) -> float:
        """计算年化基差收益。"""
        if days_to_expiry <= 0:
            return 0.0
        return round(basis_pct * 365 / days_to_expiry, 4)

    def classify_basis_regime(self, basis_pct: float) -> str:
        """分类基差状态。"""
        if basis_pct > self.BASIS_FLAT_BAND:
            return "contango"
        elif basis_pct < -self.BASIS_FLAT_BAND:
            return "backwardation"
        return "flat"

    def compute_basis_mean_reversion(self, basis_history: list[float]) -> float:
        """计算基差均值回归信号。"""
        if len(basis_history) < 10:
            return 0.0
        mean = statistics.mean(basis_history)
        std = statistics.stdev(basis_history) if len(basis_history) > 2 else 0.01
        if std == 0:
            std = 0.01
        zscore = (basis_history[-1] - mean) / std
        signal = -zscore / 3.0
        return round(max(-1.0, min(1.0, signal)), 4)
