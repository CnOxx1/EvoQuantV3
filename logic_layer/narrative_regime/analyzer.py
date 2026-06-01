"""叙事状态机计算引擎：叙事聚类、生命周期分类、注意力评分、阶段转换检测。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


class NarrativeRegimeAnalyzer:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def cluster_narratives(
        news_topics: list[dict], social_topics: list[dict]
    ) -> list[dict]:
        """将新闻和社交话题聚类为叙事。

        Parameters
        ----------
        news_topics : list[dict]
            新闻话题列表 [{topic, keywords, mentions, sentiment}...]
        social_topics : list[dict]
            社交话题列表 [{topic, keywords, mentions, sentiment}...]

        Returns
        -------
        list[dict]
            聚类后的叙事列表
        """
        # 合并所有话题
        all_topics = []
        for t in news_topics:
            all_topics.append({**t, "source": "news"})
        for t in social_topics:
            all_topics.append({**t, "source": "social"})

        if not all_topics:
            return []

        # 基于关键词重叠进行简单聚类
        clusters: list[dict] = []
        used: set[int] = set()

        for i, topic_a in enumerate(all_topics):
            if i in used:
                continue
            keywords_a = set(topic_a.get("keywords", []))
            cluster_topics = [topic_a]
            used.add(i)

            for j, topic_b in enumerate(all_topics):
                if j in used:
                    continue
                keywords_b = set(topic_b.get("keywords", []))
                overlap = keywords_a & keywords_b
                if len(overlap) >= max(1, len(keywords_a) // 3):
                    cluster_topics.append(topic_b)
                    used.add(j)
                    keywords_a |= keywords_b

            # 生成叙事 ID
            sorted_kw = sorted(keywords_a)
            narrative_id = hashlib.md5(
                "|".join(sorted_kw).encode()
            ).hexdigest()[:12]

            total_mentions = sum(t.get("mentions", 0) for t in cluster_topics)
            avg_sentiment = (
                sum(t.get("sentiment", 0) for t in cluster_topics)
                / len(cluster_topics)
            )

            clusters.append({
                "narrative_id": narrative_id,
                "narrative_name": cluster_topics[0].get("topic", "unknown"),
                "keywords": sorted_kw,
                "mentions": total_mentions,
                "avg_sentiment": round(avg_sentiment, 4),
                "source_count": len(cluster_topics),
            })

        return clusters

    @staticmethod
    def classify_lifecycle_phase(attention_history: list[float]) -> str:
        """根据注意力趋势判定叙事生命周期阶段。

        Parameters
        ----------
        attention_history : list[float]
            时间序列注意力分数（从旧到新）

        Returns
        -------
        str
            emerging / growing / peak / decaying
        """
        if not attention_history or len(attention_history) < 2:
            return "emerging"

        n = len(attention_history)
        recent = attention_history[n // 2:]
        earlier = attention_history[: n // 2]

        recent_avg = sum(recent) / len(recent) if recent else 0
        earlier_avg = sum(earlier) / len(earlier) if earlier else 0

        current = attention_history[-1]
        peak_val = max(attention_history)

        # 判定逻辑
        if current >= peak_val * 0.9 and recent_avg > earlier_avg:
            return "peak"
        elif recent_avg > earlier_avg * 1.3:
            return "growing"
        elif recent_avg < earlier_avg * 0.7:
            return "decaying"
        else:
            return "emerging"

    @staticmethod
    def compute_attention_score(
        mentions: int, sentiment_intensity: float, volume_correlation: float
    ) -> float:
        """计算叙事注意力分数（0-100）。

        Parameters
        ----------
        mentions : int
            提及次数
        sentiment_intensity : float
            情绪强度（绝对值）
        volume_correlation : float
            与交易量的相关性（0-1）

        Returns
        -------
        float
            0-100 注意力分数
        """
        # 提及次数贡献（对数缩放，最大 40 分）
        mention_score = min(40.0, 10.0 * (mentions ** 0.5)) if mentions > 0 else 0.0

        # 情绪强度贡献（最大 30 分）
        sentiment_score = min(30.0, abs(sentiment_intensity) * 30.0)

        # 交易量相关性贡献（最大 30 分）
        volume_score = max(0.0, min(30.0, volume_correlation * 30.0))

        total = mention_score + sentiment_score + volume_score
        return round(max(0.0, min(100.0, total)), 2)

    @staticmethod
    def map_narrative_to_tokens(
        narrative_keywords: list[str], token_metadata: dict
    ) -> list[str]:
        """根据叙事关键词匹配相关代币。

        Parameters
        ----------
        narrative_keywords : list[str]
            叙事关键词列表
        token_metadata : dict
            {symbol: {tags: [...], description: str, sector: str}}

        Returns
        -------
        list[str]
            匹配的代币符号列表
        """
        if not narrative_keywords or not token_metadata:
            return []

        keywords_lower = {kw.lower() for kw in narrative_keywords}
        matched: list[str] = []

        for symbol, meta in token_metadata.items():
            tags = {t.lower() for t in meta.get("tags", [])}
            desc = (meta.get("description") or "").lower()
            sector = (meta.get("sector") or "").lower()

            # 检查关键词与标签/描述/板块的重叠
            tag_overlap = keywords_lower & tags
            desc_match = any(kw in desc for kw in keywords_lower)
            sector_match = sector in keywords_lower

            if tag_overlap or desc_match or sector_match:
                matched.append(symbol)

        return sorted(matched)

    @staticmethod
    def detect_phase_transition(
        prev_phase: str, current_metrics: dict
    ) -> str | None:
        """检测叙事阶段是否发生转换。

        Parameters
        ----------
        prev_phase : str
            前一阶段 (emerging/growing/peak/decaying)
        current_metrics : dict
            当前指标 {attention_score, attention_trend, mentions_delta}

        Returns
        -------
        str | None
            新阶段（如果发生转换），否则 None
        """
        attention = current_metrics.get("attention_score", 0)
        trend = current_metrics.get("attention_trend", 0)
        mentions_delta = current_metrics.get("mentions_delta", 0)

        # 状态转换规则
        transitions = {
            "emerging": lambda: "growing" if trend > 0.2 and attention > 20 else None,
            "growing": lambda: (
                "peak" if attention > 70 and trend < 0.1
                else "decaying" if trend < -0.3
                else None
            ),
            "peak": lambda: "decaying" if trend < -0.2 or attention < 50 else None,
            "decaying": lambda: (
                "growing" if trend > 0.3 and mentions_delta > 0
                else None
            ),
        }

        check_fn = transitions.get(prev_phase)
        if check_fn is None:
            return None

        new_phase = check_fn()
        return new_phase
