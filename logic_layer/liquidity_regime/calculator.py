"""流动性状态计算引擎：流动性评分、状态分类、DeFi-CeFi 利差、稳定币脉冲、质押流影响。"""

from __future__ import annotations


class LiquidityRegimeCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_liquidity_score(
        staking_tvl_change: float,
        reserve_change: float,
        stablecoin_supply_change: float,
    ) -> float:
        """计算综合流动性评分（0-100）。

        Parameters
        ----------
        staking_tvl_change : float
            质押 TVL 变化率（如 0.05 表示 +5%）
        reserve_change : float
            交易所储备变化率（如 -0.03 表示 -3%）
        stablecoin_supply_change : float
            稳定币供应变化率（如 0.02 表示 +2%）

        Returns
        -------
        float
            流动性综合评分 [0, 100]
        """
        # 各因子归一化到 [-1, 1] 范围，假设 ±20% 为极端
        norm_staking = max(-1.0, min(1.0, staking_tvl_change / 0.2))
        norm_reserve = max(-1.0, min(1.0, reserve_change / 0.2))
        norm_stable = max(-1.0, min(1.0, stablecoin_supply_change / 0.2))

        # 加权聚合：质押 30%，储备 40%，稳定币 30%
        raw = norm_staking * 0.3 + norm_reserve * 0.4 + norm_stable * 0.3

        # 映射到 0-100（raw 范围 [-1, 1] -> [0, 100]）
        score = (raw + 1.0) / 2.0 * 100.0
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def classify_regime(score: float) -> str:
        """根据流动性评分分类市场流动性状态。

        Parameters
        ----------
        score : float
            流动性评分 [0, 100]

        Returns
        -------
        str
            "expansion" / "neutral" / "contraction" / "crisis"
        """
        if score >= 70:
            return "expansion"
        elif score >= 45:
            return "neutral"
        elif score >= 20:
            return "contraction"
        else:
            return "crisis"

    @staticmethod
    def compute_defi_cefi_spread(defi_rate: float, cefi_rate: float) -> float:
        """计算 DeFi-CeFi 利差方向（套利信号）。

        Parameters
        ----------
        defi_rate : float
            DeFi 协议借贷利率
        cefi_rate : float
            CeFi 借贷利率

        Returns
        -------
        float
            利差（正值表示 DeFi > CeFi，套利方向为 CeFi -> DeFi）
        """
        return round(defi_rate - cefi_rate, 6)

    @staticmethod
    def compute_stablecoin_pulse(supply_changes: list[float]) -> float:
        """计算稳定币供应脉冲（M2 加密代理）。

        使用指数加权移动平均，近期变化权重更高。

        Parameters
        ----------
        supply_changes : list[float]
            稳定币供应变化率序列（从旧到新）

        Returns
        -------
        float
            稳定币脉冲值（正值表示扩张，负值表示收缩）
        """
        if not supply_changes:
            return 0.0

        n = len(supply_changes)
        if n == 1:
            return round(supply_changes[0], 6)

        # 指数加权：alpha = 2/(n+1)
        alpha = 2.0 / (n + 1)
        ema = supply_changes[0]
        for i in range(1, n):
            ema = alpha * supply_changes[i] + (1 - alpha) * ema

        return round(ema, 6)

    @staticmethod
    def compute_staking_flow_impact(net_staked: float, total_supply: float) -> float:
        """计算质押/解质押净流对流动性的影响。

        Parameters
        ----------
        net_staked : float
            净质押量（正值表示净质押，负值表示净解质押）
        total_supply : float
            总供应量

        Returns
        -------
        float
            质押流影响因子（正值表示流动性收紧，负值表示流动性释放）
        """
        if total_supply <= 0:
            return 0.0

        # 净质押占总供应的比例，质押锁定流动性（正值 = 收紧）
        impact = net_staked / total_supply
        return round(impact, 6)
