"""叙事状态机服务：编排叙事检测、生命周期分类、阶段转换检测。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.narrative_regime.analyzer import NarrativeRegimeAnalyzer
from logic_layer.narrative_regime.repository import NarrativeRegimeRepository


class NarrativeRegimeService:
    """叙事状态机编排服务。

    职责：
    - 从 news_sentiment / social_sentiment 读取话题数据
    - 调用 analyzer 进行叙事聚类、注意力计算、阶段转换检测
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = NarrativeRegimeRepository(self.db)
        self.analyzer = NarrativeRegimeAnalyzer()

    def init_storage(self):
        """创建叙事状态机所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_news_topics(self) -> list[dict]:
        """从 news_sentiment_results 加载新闻话题。"""
        rows = self.db.fetch_all(
            """SELECT topic, keywords, mention_count, sentiment_score
               FROM news_sentiment_results
               ORDER BY created_at DESC LIMIT 100""",
            (),
        )
        if not rows:
            return []
        topics = []
        for row in rows:
            keywords = row.get("keywords") or "[]"
            if isinstance(keywords, str):
                try:
                    keywords = json.loads(keywords)
                except (json.JSONDecodeError, TypeError):
                    keywords = []
            topics.append({
                "topic": row.get("topic", ""),
                "keywords": keywords,
                "mentions": row.get("mention_count", 0),
                "sentiment": row.get("sentiment_score", 0),
            })
        return topics

    def _load_social_topics(self) -> list[dict]:
        """从 social_sentiment 相关表加载社交话题。"""
        rows = self.db.fetch_all(
            """SELECT topic, keywords, mention_count, sentiment_score
               FROM social_sentiment_results
               ORDER BY created_at DESC LIMIT 100""",
            (),
        )
        if not rows:
            return []
        topics = []
        for row in rows:
            keywords = row.get("keywords") or "[]"
            if isinstance(keywords, str):
                try:
                    keywords = json.loads(keywords)
                except (json.JSONDecodeError, TypeError):
                    keywords = []
            topics.append({
                "topic": row.get("topic", ""),
                "keywords": keywords,
                "mentions": row.get("mention_count", 0),
                "sentiment": row.get("sentiment_score", 0),
            })
        return topics

    def _load_alternative_data(self) -> dict:
        """从 alternative_data 相关表加载辅助数据。"""
        rows = self.db.fetch_all(
            """SELECT symbol, tags, description, sector
               FROM alternative_data_tokens
               ORDER BY symbol""",
            (),
        )
        if not rows:
            return {}
        token_metadata: dict = {}
        for row in rows:
            tags = row.get("tags") or "[]"
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (json.JSONDecodeError, TypeError):
                    tags = []
            token_metadata[row["symbol"]] = {
                "tags": tags,
                "description": row.get("description", ""),
                "sector": row.get("sector", ""),
            }
        return token_metadata

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def compute_narratives(self) -> list[dict]:
        """编排叙事检测：聚类 -> 生命周期 -> 注意力评分 -> 代币映射。"""
        news_topics = self._load_news_topics()
        social_topics = self._load_social_topics()
        token_metadata = self._load_alternative_data()

        clusters = self.analyzer.cluster_narratives(news_topics, social_topics)
        if not clusters:
            return []

        ts = self._utc_now_iso()
        entries: list[dict] = []

        for cluster in clusters:
            mentions = cluster.get("mentions", 0)
            sentiment = cluster.get("avg_sentiment", 0)
            # 简化：用 mentions 构造注意力历史
            attention_score = self.analyzer.compute_attention_score(
                mentions=mentions,
                sentiment_intensity=abs(sentiment),
                volume_correlation=0.5,
            )
            # 用当前得分作为单点历史判定阶段
            phase = self.analyzer.classify_lifecycle_phase(
                [attention_score * 0.7, attention_score * 0.85, attention_score]
            )
            related = self.analyzer.map_narrative_to_tokens(
                cluster.get("keywords", []), token_metadata
            )

            entries.append({
                "ts": ts,
                "narrative_id": cluster["narrative_id"],
                "narrative_name": cluster["narrative_name"],
                "lifecycle_phase": phase,
                "attention_score": attention_score,
                "capital_flow_correlation": 0.0,
                "related_tokens": json.dumps(related),
            })

        self.repository.save_narratives(entries)
        return entries

    def detect_transitions(self) -> list[dict]:
        """检测叙事阶段转换。"""
        active = self.repository.load_active_narratives()
        if not active:
            return []

        ts = self._utc_now_iso()
        transitions: list[dict] = []

        for narrative in active:
            prev_phase = narrative.get("lifecycle_phase", "emerging")
            attention = narrative.get("attention_score", 0)

            # 构造当前指标
            current_metrics = {
                "attention_score": attention,
                "attention_trend": 0.0,
                "mentions_delta": 0,
            }

            new_phase = self.analyzer.detect_phase_transition(
                prev_phase, current_metrics
            )
            if new_phase is not None:
                transitions.append({
                    "ts": ts,
                    "narrative_id": narrative["narrative_id"],
                    "from_phase": prev_phase,
                    "to_phase": new_phase,
                    "trigger_event": f"attention={attention:.1f}",
                })

        if transitions:
            self.repository.save_transitions(transitions)
        return transitions

    # ------------------------------------------------------------------
    # 主编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部叙事状态机计算并落库。"""
        results: dict = {}
        results["narratives"] = self.compute_narratives()
        results["transitions"] = self.detect_transitions()
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新叙事状态机结果，供 AI 上下文消费。"""
        active = self.repository.load_active_narratives()
        transitions = self.repository.load_recent_transitions(limit=10)
        return {
            "as_of": self._utc_now_iso(),
            "active_narratives": active,
            "recent_transitions": transitions,
            "narrative_count": len(active),
        }

    def close(self):
        self.db.close()
