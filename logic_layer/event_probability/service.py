"""事件概率服务：编排概率提取、跳变检测、事件映射、情绪验证。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.event_probability.calculator import EventProbabilityCalculator
from logic_layer.event_probability.repository import EventProbabilityRepository


class EventProbabilityService:
    """事件概率编排服务。

    职责：
    - 从 prediction_markets / prediction_market_history 读取预测市场数据
    - 调用 calculator 计算概率跳变、影响评分、资产映射
    - 交叉验证新闻情绪
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = EventProbabilityRepository(self.db)
        self.calculator = EventProbabilityCalculator()

    def init_storage(self):
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    def _load_prediction_markets(self) -> list[dict]:
        """从 prediction_markets 表加载当前预测市场数据。"""
        rows = self.db.fetch_all(
            """SELECT market_id, question, category, outcome_yes_price AS probability,
                      volume_24h, liquidity
               FROM prediction_markets
               ORDER BY volume_24h DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []

    def _load_market_history(self, market_id: str) -> list[dict]:
        """从 prediction_market_history 表加载历史概率。"""
        rows = self.db.fetch_all(
            """SELECT outcome_yes_price AS probability, collected_at AS recorded_at
               FROM prediction_market_history
               WHERE market_id = ?
               ORDER BY collected_at DESC
               LIMIT 48""",
            (market_id,),
        )
        return [dict(r) for r in rows] if rows else []

    def _load_news_sentiment(self, keywords: list[str]) -> float:
        """从 news_sentiment 相关表加载与关键词相关的情绪均值。"""
        if not keywords:
            return 0.0
        conditions = " OR ".join("title LIKE ?" for _ in keywords)
        params = tuple(f"%{kw}%" for kw in keywords)
        rows = self.db.fetch_all(
            f"""SELECT sentiment_score
               FROM news_articles
               WHERE ({conditions})
               ORDER BY published_at DESC
               LIMIT 20""",
            params,
        )
        if not rows:
            return 0.0
        scores = [float(r["sentiment_score"]) for r in rows if r.get("sentiment_score") is not None]
        return sum(scores) / len(scores) if scores else 0.0

    def _get_previous_probability(self, market_id: str) -> float | None:
        """获取 24h 前的概率值。"""
        history = self._load_market_history(market_id)
        if len(history) >= 24:
            return float(history[23]["probability"])
        elif history:
            return float(history[-1]["probability"])
        return None

    def compute_event_probabilities(self) -> dict:
        """计算事件概率状态并落库。"""
        markets = self._load_prediction_markets()
        if not markets:
            return {"states": [], "jump_count": 0}

        ts = self._utc_now_iso()
        entries: list[dict] = []
        jump_count = 0

        for market in markets:
            market_id = market["market_id"]
            question = market.get("question", "")
            category = market.get("category", "")
            probability = float(market.get("probability") or 0.0)
            volume_24h = float(market.get("volume_24h") or 0.0)
            liquidity = float(market.get("liquidity") or 0.0)

            prev_prob = self._get_previous_probability(market_id)
            if prev_prob is not None:
                prob_change = probability - prev_prob
            else:
                prob_change = 0.0

            is_jump = self.calculator.detect_probability_jump(
                probability, prev_prob if prev_prob is not None else probability
            )
            if is_jump:
                jump_count += 1

            impact_score = self.calculator.compute_event_impact_score(
                volume_24h, liquidity, prob_change
            )

            affected_assets = self.calculator.map_event_to_assets(question, category)

            prob_direction = "up" if prob_change > 0 else "down" if prob_change < 0 else "up"
            keywords = question.lower().split()[:5]
            news_sentiment = self._load_news_sentiment(keywords)
            sentiment_validation = self.calculator.cross_validate_sentiment(
                prob_direction, news_sentiment
            )

            entry = {
                "ts": ts,
                "market_id": market_id,
                "question": question,
                "probability": probability,
                "prob_change_24h": round(prob_change, 4),
                "impact_score": impact_score,
                "affected_assets": json.dumps(affected_assets),
                "sentiment_validation": sentiment_validation,
                "is_jump": 1 if is_jump else 0,
            }
            entries.append(entry)

        self.repository.save_states(entries)
        return {"ts": ts, "states": entries, "jump_count": jump_count, "total_markets": len(entries)}

    def run_all(self) -> dict:
        """执行全部事件概率分析计算并落库。"""
        results: dict = {}
        results["event_probabilities"] = self.compute_event_probabilities()
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新事件概率分析结果，供 AI 上下文消费。"""
        states = self.repository.load_latest_states()
        high_impact = [s for s in states if (s.get("impact_score") or 0) >= 50.0]
        jumps = [s for s in states if s.get("is_jump")]
        return {
            "as_of": self._utc_now_iso(),
            "event_probability_states": states,
            "high_impact_events": high_impact,
            "jump_alerts": jumps,
            "summary": {
                "total_markets": len(states),
                "high_impact_count": len(high_impact),
                "jump_count": len(jumps),
            },
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
