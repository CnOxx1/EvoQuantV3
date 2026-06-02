"""Smart Money 信念指数计算引擎：conviction index、方向分类、散户背离、PnL 趋势。"""

from __future__ import annotations


class SmartMoneyConvictionCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_conviction_index(
        avg_pnl: float, position_direction: float, consistency: float
    ) -> float:
        """计算 Smart Money 信念指数（0-100）。

        综合考虑平均盈亏、持仓方向一致性、历史一致性。

        Parameters
        ----------
        avg_pnl : float
            聪明钱平均 PnL 百分比（如 0.05 表示 +5%）
        position_direction : float
            持仓方向指标 [-1, 1]，1=全做多, -1=全做空
        consistency : float
            方向一致性（0-1），1=所有聪明钱方向一致

        Returns
        -------
        float
            信念指数 [0, 100]
        """
        # PnL 因子：盈利越高信念越强，归一化到 0-40
        pnl_norm = max(-1.0, min(1.0, avg_pnl / 0.10))
        pnl_score = (pnl_norm + 1.0) / 2.0 * 40.0

        # 方向因子：方向越极端信念越强，归一化到 0-35
        dir_score = abs(position_direction) * 35.0

        # 一致性因子：一致性越高信念越强，归一化到 0-25
        consist_score = max(0.0, min(1.0, consistency)) * 25.0

        score = pnl_score + dir_score + consist_score
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def classify_direction(conviction: float) -> str:
        """根据信念指数分类方向。

        Parameters
        ----------
        conviction : float
            信念指数 [0, 100]

        Returns
        -------
        str
            "strong_bullish"/"bullish"/"neutral"/"bearish"/"strong_bearish"
        """
        if conviction >= 80:
            return "strong_bullish"
        elif conviction >= 60:
            return "bullish"
        elif conviction >= 40:
            return "neutral"
        elif conviction >= 20:
            return "bearish"
        return "strong_bearish"

    @staticmethod
    def compute_retail_divergence(
        smart_money_direction: float, retail_flow: float
    ) -> float:
        """计算散户背离度。

        当散户流向与聪明钱方向相反时产生背离信号。

        Parameters
        ----------
        smart_money_direction : float
            聪明钱方向 [-1, 1]
        retail_flow : float
            散户净流入方向 [-1, 1]，正=买入为主

        Returns
        -------
        float
            背离度 [-1, 1]，正值表示散户看多但聪明钱看空
        """
        # 背离 = 散户方向 - 聪明钱方向的差异
        divergence = retail_flow - smart_money_direction
        # 归一化到 [-1, 1]
        normalized = max(-1.0, min(1.0, divergence / 2.0))
        return round(normalized, 6)

    @staticmethod
    def compute_pnl_trend(pnl_series: list[float]) -> str:
        """根据 PnL 序列判断趋势方向。

        使用线性回归斜率判断 PnL 变化趋势。

        Parameters
        ----------
        pnl_series : list[float]
            PnL 百分比时间序列（从旧到新）

        Returns
        -------
        str
            "improving" / "stable" / "declining"
        """
        if len(pnl_series) < 3:
            return "stable"

        n = len(pnl_series)
        # 简化线性回归斜率
        x_mean = (n - 1) / 2.0
        y_mean = sum(pnl_series) / n

        numerator = sum(
            (i - x_mean) * (pnl_series[i] - y_mean) for i in range(n)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        # 斜率阈值判断
        if slope > 0.005:
            return "improving"
        elif slope < -0.005:
            return "declining"
        return "stable"
