"""代币解锁冲击计算引擎：卖压比率、冲击评分、价格影响预估、流动性吸收容量。"""

from __future__ import annotations


class UnlockImpactCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_sell_pressure_ratio(
        unlock_amount: float, daily_volume: float
    ) -> float:
        """计算解锁卖压比率（解锁量 / 日均成交量）。

        Parameters
        ----------
        unlock_amount : float
            解锁代币的 USD 价值
        daily_volume : float
            该代币近期日均成交量（USD）

        Returns
        -------
        float
            卖压比率，>1 表示解锁量超过日均成交量
        """
        if daily_volume <= 0:
            return 0.0
        ratio = unlock_amount / daily_volume
        return round(ratio, 6)

    @staticmethod
    def compute_impact_score(
        sell_pressure: float, historical_reaction: float
    ) -> float:
        """计算综合冲击评分（0-100）。

        综合考虑卖压比率和历史反应幅度。

        Parameters
        ----------
        sell_pressure : float
            卖压比率（compute_sell_pressure_ratio 输出）
        historical_reaction : float
            历史解锁后平均价格跌幅（如 0.05 表示 5%）

        Returns
        -------
        float
            冲击评分 [0, 100]
        """
        # 卖压因子：卖压比率映射到 0-50 分（>2 为满分）
        pressure_score = min(50.0, sell_pressure / 2.0 * 50.0)

        # 历史反应因子：跌幅映射到 0-50 分（>10% 为满分）
        reaction_score = min(50.0, abs(historical_reaction) / 0.10 * 50.0)

        score = pressure_score + reaction_score
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def estimate_price_impact(
        sell_pressure: float, depth_factor: float
    ) -> float:
        """预估解锁导致的价格影响百分比。

        基于卖压和盘口深度因子的简化冲击模型。

        Parameters
        ----------
        sell_pressure : float
            卖压比率
        depth_factor : float
            深度因子（1% 深度 / 日均成交量），越大表示盘口越薄

        Returns
        -------
        float
            预期价格影响百分比（如 3.5 表示 -3.5%）
        """
        if sell_pressure <= 0:
            return 0.0

        # 简化平方根冲击模型：impact = k * sqrt(sell_pressure) * depth_factor
        k = 2.0
        depth_mult = max(0.5, min(3.0, depth_factor))
        impact = k * (sell_pressure ** 0.5) * depth_mult
        return round(max(0.0, min(50.0, impact)), 4)

    @staticmethod
    def compute_liquidity_absorption(
        daily_volume: float, depth_1pct: float
    ) -> float:
        """计算流动性吸收容量。

        衡量市场能在多少时间内消化解锁量而不引起剧烈波动。

        Parameters
        ----------
        daily_volume : float
            日均成交量（USD）
        depth_1pct : float
            ±1% 价格范围内的盘口深度（USD）

        Returns
        -------
        float
            吸收容量得分 [0, 1]，1 表示流动性充裕
        """
        if daily_volume <= 0 and depth_1pct <= 0:
            return 0.0

        # 综合深度和成交量，归一化
        # 假设 depth_1pct > 5M 且 daily_volume > 100M 为充裕
        depth_norm = min(1.0, depth_1pct / 5_000_000.0) if depth_1pct > 0 else 0.0
        volume_norm = min(1.0, daily_volume / 100_000_000.0) if daily_volume > 0 else 0.0

        absorption = depth_norm * 0.4 + volume_norm * 0.6
        return round(absorption, 6)
