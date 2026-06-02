"""市场情绪复合指标服务：编排多维情绪数据计算与落库。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.market_sentiment_composite.calculator import (
    MarketSentimentCompositeCalculator,
)
from logic_layer.market_sentiment_composite.repository import (
    MarketSentimentCompositeRepository,
)


class MarketSentimentCompositeService:
    """市场情绪复合指标编排服务。

    职责：
    - 从 sentiment_index、derivatives_sentiment 表读取情绪数据
    - 调用 calculator 计算复合评分、极端检测、背离、反转信号
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = MarketSentimentCompositeRepository(self.db)
        self.calculator = MarketSentimentCompositeCalculator()
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """获取 market_data 数据库连接（延迟初始化）。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建复合情绪状态所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_fear_greed(self) -> float:
        """从 sentiment_index 表读取最新恐惧贪婪指数。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT value FROM sentiment_index
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return float(rows[0]["value"])
        return 50.0  # 默认中性

    def _load_long_short_ratio(self) -> float:
        """从 derivatives_sentiment 表读取最新多空比。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT long_short_ratio FROM derivatives_sentiment
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return float(rows[0]["long_short_ratio"])
        return 1.0  # 默认平衡

    def _load_funding_rate(self) -> float:
        """从 derivatives_sentiment 表读取最新资金费率。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT funding_rate FROM derivatives_sentiment
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return float(rows[0]["funding_rate"])
        return 0.0

    def _load_social_sentiment(self) -> float:
        """从 sentiment_index 表读取社交媒体情绪。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT social_score FROM sentiment_index
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows and rows[0]["social_score"] is not None:
            return float(rows[0]["social_score"])
        return 50.0  # 默认中性

    def _load_sentiment_trend(self) -> float:
        """计算情绪趋势（最近 24h 变化率）。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT value FROM sentiment_index
               ORDER BY ts DESC LIMIT 24""",
            (),
        )
        if len(rows) < 2:
            return 0.0
        latest = float(rows[0]["value"])
        oldest = float(rows[-1]["value"])
        if oldest == 0:
            return 0.0
        return (latest - oldest) / oldest

    def _load_price_trend(self) -> float:
        """计算价格趋势（最近 24h BTC 价格变化率）。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT close FROM merged_klines
               WHERE symbol = 'BTC/USDT' AND timeframe = '1h'
               ORDER BY open_time DESC LIMIT 24""",
            (),
        )
        if len(rows) < 2:
            return 0.0
        latest = float(rows[0]["close"])
        oldest = float(rows[-1]["close"])
        if oldest == 0:
            return 0.0
        return (latest - oldest) / oldest

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self, no_save: bool = False) -> dict:
        """执行全部复合情绪计算并落库。

        Parameters
        ----------
        no_save : bool
            若为 True，只计算不落库

        Returns
        -------
        dict
            包含复合情绪状态的结果
        """
        ts = self._utc_now_iso()

        # 读取各维度数据
        fear_greed = self._load_fear_greed()
        long_short_ratio = self._load_long_short_ratio()
        funding_rate = self._load_funding_rate()
        social_sentiment = self._load_social_sentiment()

        # 计算复合评分
        composite_score = self.calculator.compute_composite_score(
            fear_greed=fear_greed,
            long_short_ratio=long_short_ratio,
            funding_rate=funding_rate,
            social_sentiment=social_sentiment,
        )

        # 极端情绪检测
        extreme_label = self.calculator.detect_extreme(composite_score)

        # 情绪-价格背离
        sentiment_trend = self._load_sentiment_trend()
        price_trend = self._load_price_trend()
        divergence = self.calculator.detect_sentiment_price_divergence(
            sentiment_trend=sentiment_trend,
            price_trend=price_trend,
        )

        # 反转概率
        reversal_probability = self.calculator.compute_reversal_probability(
            extreme_level=extreme_label,
            divergence_strength=divergence["strength"],
            duration_hours=0.0,  # 当前无持续时间跟踪
        )

        # 资金费率一致性
        funding_consistency = self.calculator.check_funding_consistency(
            composite_score=composite_score,
            funding_rate=funding_rate,
        )

        state = {
            "ts": ts,
            "composite_score": composite_score,
            "extreme_label": extreme_label,
            "divergence_type": divergence["type"],
            "divergence_strength": divergence["strength"],
            "reversal_probability": reversal_probability,
            "funding_consistency": funding_consistency,
        }

        if not no_save:
            self.repository.save_state(state)

        return state

    def load_latest_context_bundle(self) -> dict:
        """加载最新复合情绪分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if state is None:
            return {
                "as_of": self._utc_now_iso(),
                "composite_sentiment": None,
                "status": "no_data",
            }
        return {
            "as_of": self._utc_now_iso(),
            "composite_sentiment": state,
            "status": "ok",
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
