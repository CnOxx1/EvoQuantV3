"""市场情绪复合指标计算引擎：复合评分、极端检测、背离分析、反转信号。"""

from __future__ import annotations

import math


class MarketSentimentCompositeCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_composite_score(
        fear_greed: float,
        long_short_ratio: float,
        funding_rate: float,
        social_sentiment: float,
    ) -> float:
        """计算复合情绪评分（0-100，多维加权）。

        Parameters
        ----------
        fear_greed : float
            恐惧贪婪指数 (0-100)
        long_short_ratio : float
            多空比（1.0 = 平衡，>1 偏多，<1 偏空）
        funding_rate : float
            资金费率（正 = 偏多，负 = 偏空）
        social_sentiment : float
            社交媒体情绪 (0-100)

        Returns
        -------
        float
            复合情绪评分 [0, 100]
        """
        # 归一化 fear_greed 已在 0-100
        fg_component = max(0.0, min(100.0, fear_greed))

        # 归一化 long_short_ratio: 转换为 0-100 尺度，1.0 = 50
        # ratio 0.5 -> 25, ratio 1.0 -> 50, ratio 2.0 -> 75
        ls_normalized = 50.0 + (long_short_ratio - 1.0) * 50.0
        ls_component = max(0.0, min(100.0, ls_normalized))

        # 归一化 funding_rate: 转换为 0-100 尺度
        # funding_rate 范围通常 -0.1% ~ +0.1%，映射到 0-100
        fr_normalized = 50.0 + funding_rate * 500.0
        fr_component = max(0.0, min(100.0, fr_normalized))

        # 归一化 social_sentiment 已在 0-100
        ss_component = max(0.0, min(100.0, social_sentiment))

        # 加权聚合
        score = (
            fg_component * 0.35
            + ls_component * 0.25
            + fr_component * 0.20
            + ss_component * 0.20
        )
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def detect_extreme(score: float) -> str:
        """根据复合评分检测极端情绪状态。

        Parameters
        ----------
        score : float
            复合情绪评分 (0-100)

        Returns
        -------
        str
            情绪标签: extreme_fear/fear/neutral/greed/extreme_greed
        """
        if score < 15:
            return "extreme_fear"
        elif score < 30:
            return "fear"
        elif score <= 70:
            return "neutral"
        elif score <= 85:
            return "greed"
        else:
            return "extreme_greed"

    @staticmethod
    def detect_sentiment_price_divergence(
        sentiment_trend: float,
        price_trend: float,
    ) -> dict:
        """检测情绪-价格背离。

        Parameters
        ----------
        sentiment_trend : float
            情绪趋势变化率（正=情绪上升，负=情绪下降）
        price_trend : float
            价格趋势变化率（正=价格上涨，负=价格下跌）

        Returns
        -------
        dict
            {"type": "bullish_divergence"/"bearish_divergence"/"none",
             "strength": float 0-1}
        """
        # 无明显趋势
        if abs(sentiment_trend) < 0.01 and abs(price_trend) < 0.01:
            return {"type": "none", "strength": 0.0}

        # 背离强度 = 方向差异的程度
        # 归一化两个趋势到 [-1, 1]
        max_abs = max(abs(sentiment_trend), abs(price_trend), 0.01)
        norm_sentiment = sentiment_trend / max_abs
        norm_price = price_trend / max_abs

        # 方向相反则存在背离
        if norm_sentiment * norm_price < 0:
            # 背离强度
            strength = abs(norm_sentiment - norm_price) / 2.0
            strength = min(1.0, strength)

            if sentiment_trend > 0 and price_trend < 0:
                divergence_type = "bullish_divergence"
            else:
                divergence_type = "bearish_divergence"

            return {
                "type": divergence_type,
                "strength": round(strength, 4),
            }

        return {"type": "none", "strength": 0.0}

    @staticmethod
    def compute_reversal_probability(
        extreme_level: str,
        divergence_strength: float,
        duration_hours: float,
    ) -> float:
        """计算反转信号概率。

        Parameters
        ----------
        extreme_level : str
            极端情绪标签 (extreme_fear/fear/neutral/greed/extreme_greed)
        divergence_strength : float
            背离强度 (0-1)
        duration_hours : float
            极端状态持续时长（小时）

        Returns
        -------
        float
            反转概率 [0, 1]
        """
        # 基础概率：极端程度越高，反转概率越高
        base_prob_map = {
            "extreme_fear": 0.35,
            "fear": 0.15,
            "neutral": 0.05,
            "greed": 0.15,
            "extreme_greed": 0.35,
        }
        base_prob = base_prob_map.get(extreme_level, 0.05)

        # 背离加成：背离越强，反转概率越高
        divergence_bonus = divergence_strength * 0.30

        # 持续时间加成：极端状态持续越久，反转越可能
        # 使用对数衰减：12h 开始有意义，72h 趋近上限
        if duration_hours > 0:
            duration_bonus = min(
                0.25, 0.25 * (1 - math.exp(-duration_hours / 48.0))
            )
        else:
            duration_bonus = 0.0

        probability = base_prob + divergence_bonus + duration_bonus
        return round(max(0.0, min(1.0, probability)), 4)

    @staticmethod
    def check_funding_consistency(
        composite_score: float,
        funding_rate: float,
    ) -> str:
        """检查复合情绪与资金费率的一致性。

        Parameters
        ----------
        composite_score : float
            复合情绪评分 (0-100)
        funding_rate : float
            当前资金费率

        Returns
        -------
        str
            "consistent" 或 "divergent"
        """
        # 情绪偏多（>60）应对应正资金费率
        # 情绪偏空（<40）应对应负资金费率
        sentiment_bullish = composite_score > 60
        sentiment_bearish = composite_score < 40
        funding_bullish = funding_rate > 0.0001
        funding_bearish = funding_rate < -0.0001

        if sentiment_bullish and funding_bearish:
            return "divergent"
        if sentiment_bearish and funding_bullish:
            return "divergent"

        return "consistent"
