"""volatility_forecast 波动率计算器。"""

import math
import statistics


class VolatilityCalculator:
    """波动率计算与预测。

    方法：
    1. 已实现波动率：Close-to-Close 标准差年化
    2. EWMA 预测：指数加权移动平均波动率
    3. 波动率锥：多窗口历史分位数
    4. RV-IV 价差：已实现 vs 隐含波动率差
    """

    ANNUALIZATION_FACTOR = math.sqrt(365)  # 加密市场 365 天
    EWMA_LAMBDA = 0.94  # RiskMetrics 标准衰减因子

    def compute_realized_vol(self, returns: list[float], window: int = 30) -> float:
        """计算已实现波动率（年化）。"""
        if len(returns) < window:
            return 0.0
        recent = returns[-window:]
        daily_vol = statistics.stdev(recent) if len(recent) > 1 else 0.0
        return round(daily_vol * self.ANNUALIZATION_FACTOR, 6)

    def compute_ewma_forecast(self, returns: list[float], horizon_days: int = 1) -> float:
        """EWMA 波动率预测。"""
        if len(returns) < 10:
            return 0.0

        # 初始化
        variance = sum(r**2 for r in returns[:10]) / 10

        # EWMA 递推
        for r in returns[10:]:
            variance = self.EWMA_LAMBDA * variance + (1 - self.EWMA_LAMBDA) * r**2

        # 多步预测（假设波动率均值回归较慢，短期内近似恒定）
        daily_vol = math.sqrt(variance)
        annualized = daily_vol * self.ANNUALIZATION_FACTOR
        return round(annualized, 6)

    def compute_volatility_cone(self, returns: list[float], window: int = 30) -> dict:
        """计算波动率锥（某窗口的历史分位数）。"""
        if len(returns) < window + 30:
            return {}

        # 滚动计算历史波动率
        rolling_vols = []
        for i in range(window, len(returns)):
            segment = returns[i - window:i]
            vol = statistics.stdev(segment) * self.ANNUALIZATION_FACTOR
            rolling_vols.append(vol)

        if not rolling_vols:
            return {}

        sorted_vols = sorted(rolling_vols)
        n = len(sorted_vols)

        return {
            "window_days": window,
            "current": round(rolling_vols[-1], 6),
            "percentile_25": round(sorted_vols[int(n * 0.25)], 6),
            "percentile_50": round(sorted_vols[int(n * 0.50)], 6),
            "percentile_75": round(sorted_vols[int(n * 0.75)], 6),
            "min_val": round(sorted_vols[0], 6),
            "max_val": round(sorted_vols[-1], 6),
        }

    def compute_vol_percentile(self, returns: list[float], window: int = 30) -> float:
        """计算当前波动率在历史中的百分位。"""
        if len(returns) < window + 30:
            return 50.0

        rolling_vols = []
        for i in range(window, len(returns)):
            segment = returns[i - window:i]
            vol = statistics.stdev(segment) * self.ANNUALIZATION_FACTOR
            rolling_vols.append(vol)

        if not rolling_vols:
            return 50.0

        current = rolling_vols[-1]
        below = sum(1 for v in rolling_vols if v <= current)
        return round(below / len(rolling_vols) * 100, 1)

    def classify_vol_regime(self, annualized_vol: float) -> str:
        """分类波动率状态。"""
        if annualized_vol < 0.3:
            return "low"
        elif annualized_vol < 0.6:
            return "normal"
        elif annualized_vol < 1.0:
            return "high"
        return "extreme"
