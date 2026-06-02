"""散户 FOMO/FUD 复合指数计算引擎：FOMO 指数、FUD 指数、逆向信号强度、反转概率。"""

from __future__ import annotations


class RetailFomoIndexCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_fomo_index(
        search_score: float,
        social_zscore: float,
        listing_heat: float,
        fear_greed: float,
    ) -> float:
        """计算散户 FOMO 指数（0-100）。

        综合搜索热度、社交量 Z-score、上币热度和恐贪指数。

        Parameters
        ----------
        search_score : float
            搜索热度归一化分数（0-100）
        social_zscore : float
            社交量 Z-score（标准差倍数）
        listing_heat : float
            新币上线热度指标（0-100）
        fear_greed : float
            恐贪指数（0-100），越高越贪婪

        Returns
        -------
        float
            FOMO 指数 [0, 100]
        """
        # 搜索热度因子：30% 权重
        search_factor = max(0.0, min(100.0, search_score)) * 0.30

        # 社交量因子：Z-score > 2 为异常活跃，映射到 25% 权重
        social_factor = min(25.0, max(0.0, social_zscore / 3.0) * 25.0)

        # 上币热度因子：20% 权重
        listing_factor = max(0.0, min(100.0, listing_heat)) * 0.20

        # 恐贪指数因子：25% 权重，只有贪婪端（>50）贡献
        greed_factor = max(0.0, (fear_greed - 50.0) / 50.0) * 25.0

        fomo = search_factor + social_factor + listing_factor + greed_factor
        return round(max(0.0, min(100.0, fomo)), 2)

    @staticmethod
    def compute_fud_index(
        search_decline: float,
        social_negativity: float,
        fear_greed: float,
    ) -> float:
        """计算散户 FUD 指数（0-100）。

        综合搜索热度下降、社交负面情绪、恐贪指数恐惧端。

        Parameters
        ----------
        search_decline : float
            搜索热度下降幅度（0-100），越高表示关注度下降越快
        social_negativity : float
            社交负面情绪比例（0-1）
        fear_greed : float
            恐贪指数（0-100），越低越恐惧

        Returns
        -------
        float
            FUD 指数 [0, 100]
        """
        # 搜索下降因子：35% 权重
        search_factor = max(0.0, min(100.0, search_decline)) * 0.35

        # 社交负面因子：35% 权重
        neg_factor = max(0.0, min(1.0, social_negativity)) * 35.0

        # 恐贪恐惧端因子：30% 权重，只有恐惧端（<50）贡献
        fear_factor = max(0.0, (50.0 - fear_greed) / 50.0) * 30.0

        fud = search_factor + neg_factor + fear_factor
        return round(max(0.0, min(100.0, fud)), 2)

    @staticmethod
    def compute_contrarian_strength(fomo: float, fud: float) -> float:
        """计算逆向信号强度。

        当 FOMO 或 FUD 达到极端时产生逆向交易信号。

        Parameters
        ----------
        fomo : float
            FOMO 指数 [0, 100]
        fud : float
            FUD 指数 [0, 100]

        Returns
        -------
        float
            逆向信号强度 [0, 1]，越高表示逆向信号越强
        """
        # 取 FOMO 和 FUD 中更极端的一个
        extreme = max(fomo, fud)

        # 只有超过 70 才开始产生逆向信号
        if extreme < 70:
            return 0.0

        # 70-100 映射到 0-1
        strength = (extreme - 70.0) / 30.0
        return round(max(0.0, min(1.0, strength)), 6)

    @staticmethod
    def estimate_reversal_probability(
        extreme_score: float, historical_reversals: list[float]
    ) -> float:
        """预估在当前极端情绪下的反转概率。

        基于历史极端情绪后的反转频率估算。

        Parameters
        ----------
        extreme_score : float
            当前极端情绪分数（FOMO 或 FUD 的最大值）
        historical_reversals : list[float]
            历史极端事件后的反转幅度列表（百分比）

        Returns
        -------
        float
            反转概率 [0, 1]
        """
        if extreme_score < 60:
            return 0.0

        # 基础概率：极端程度越高基础概率越大
        base_prob = (extreme_score - 60.0) / 40.0 * 0.5

        # 历史验证调整
        if historical_reversals:
            # 历史反转比例（反转定义为 >2% 的反向运动）
            reversal_count = sum(1 for r in historical_reversals if abs(r) > 2.0)
            hist_ratio = reversal_count / len(historical_reversals)
            # 历史验证加权 50%
            adjusted = base_prob * 0.5 + hist_ratio * 0.5
        else:
            adjusted = base_prob

        return round(max(0.0, min(1.0, adjusted)), 6)
