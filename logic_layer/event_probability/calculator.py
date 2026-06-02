"""事件概率计算引擎：概率跳变检测、影响评分、事件-资产映射、情绪交叉验证。"""

from __future__ import annotations

import re


class EventProbabilityCalculator:
    """纯计算逻辑，不依赖数据库。"""

    # 事件关键词 -> 受影响资产映射表
    _KEYWORD_ASSET_MAP: dict[str, list[str]] = {
        "bitcoin": ["BTC/USDT"],
        "btc": ["BTC/USDT"],
        "ethereum": ["ETH/USDT"],
        "eth": ["ETH/USDT"],
        "solana": ["SOL/USDT"],
        "sol": ["SOL/USDT"],
        "sec": ["BTC/USDT", "ETH/USDT"],
        "regulation": ["BTC/USDT", "ETH/USDT"],
        "etf": ["BTC/USDT", "ETH/USDT"],
    }

    @staticmethod
    def detect_probability_jump(
        current_prob: float,
        previous_prob: float,
        threshold: float = 0.10,
    ) -> bool:
        """检测概率跳变：24h 变化是否超过阈值。

        Parameters
        ----------
        current_prob : float
            当前概率 [0, 1]
        previous_prob : float
            24h 前概率 [0, 1]
        threshold : float
            跳变阈值（默认 0.10 即 10%）

        Returns
        -------
        bool
            是否发生概率跳变
        """
        change = abs(current_prob - previous_prob)
        return change > threshold

    @staticmethod
    def compute_event_impact_score(
        volume_24h: float,
        liquidity: float,
        prob_change: float,
    ) -> float:
        """计算事件影响评分（0-100）。

        综合交易量、流动性和概率变化来评估事件对市场的潜在影响。

        Parameters
        ----------
        volume_24h : float
            24 小时交易量（美元）
        liquidity : float
            市场流动性（美元）
        prob_change : float
            概率变化幅度（绝对值）

        Returns
        -------
        float
            影响评分 [0, 100]
        """
        # 交易量分量：归一化到 0-1（假设 1M 为高交易量）
        vol_score = min(volume_24h / 1_000_000.0, 1.0) if volume_24h > 0 else 0.0

        # 流动性分量：低流动性意味着更大影响
        # 归一化：假设 10M 为高流动性（低影响）
        if liquidity > 0:
            liq_factor = 1.0 - min(liquidity / 10_000_000.0, 1.0)
        else:
            liq_factor = 1.0

        # 概率变化分量：归一化到 0-1（假设 0.5 为极端变化）
        prob_score = min(abs(prob_change) / 0.5, 1.0)

        # 加权聚合
        score = (vol_score * 0.3 + liq_factor * 0.3 + prob_score * 0.4) * 100.0
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def map_event_to_assets(question: str, category: str) -> list[str]:
        """根据事件问题文本和分类映射受影响的资产。

        使用关键词匹配来确定哪些加密资产会受到该事件的影响。

        Parameters
        ----------
        question : str
            预测市场问题文本
        category : str
            事件分类

        Returns
        -------
        list[str]
            受影响的资产交易对列表
        """
        text = f"{question} {category}".lower()
        affected: set[str] = set()

        for keyword, assets in EventProbabilityCalculator._KEYWORD_ASSET_MAP.items():
            # 使用单词边界匹配，避免误匹配
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text):
                affected.update(assets)

        # 如果没有匹配到任何关键词，默认关联 BTC
        if not affected:
            affected.add("BTC/USDT")

        return sorted(affected)

    @staticmethod
    def cross_validate_sentiment(
        prob_direction: str,
        news_sentiment: float,
    ) -> str:
        """交叉验证概率方向与新闻情绪是否一致。

        Parameters
        ----------
        prob_direction : str
            概率变化方向（"up" 或 "down"）
        news_sentiment : float
            新闻情绪分数 [-1, 1]，正值为乐观，负值为悲观

        Returns
        -------
        str
            验证结果："confirmed"（一致）/ "divergent"（分歧）/ "neutral"（中性）
        """
        # 情绪中性区间
        if abs(news_sentiment) < 0.1:
            return "neutral"

        # 判断方向一致性
        if prob_direction == "up" and news_sentiment > 0.1:
            return "confirmed"
        elif prob_direction == "down" and news_sentiment < -0.1:
            return "confirmed"
        elif prob_direction == "up" and news_sentiment < -0.1:
            return "divergent"
        elif prob_direction == "down" and news_sentiment > 0.1:
            return "divergent"

        return "neutral"
