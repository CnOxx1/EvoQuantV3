"""散户 FOMO/FUD 复合指数服务：编排 FOMO 指数、FUD 指数、逆向信号、反转概率。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.retail_fomo_index.calculator import RetailFomoIndexCalculator
from logic_layer.retail_fomo_index.repository import RetailFomoIndexRepository


class RetailFomoIndexService:
    """散户 FOMO/FUD 复合指数编排服务。

    职责：
    - 从 search_trends、social_metrics、listings 读取市场数据
    - 调用 calculator 计算 FOMO/FUD 指数、逆向信号
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = RetailFomoIndexRepository(self.db)
        self.calculator = RetailFomoIndexCalculator()
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建散户 FOMO/FUD 复合指数分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_search_data(self) -> dict:
        """从 search_trends 加载搜索热度数据。

        Returns
        -------
        dict
            包含 search_score, search_decline, search_momentum
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT interest_score AS score FROM search_trends
               WHERE category = 'crypto'
               ORDER BY timestamp DESC LIMIT 14""",
            (),
        )
        if not rows:
            return {"search_score": 50.0, "search_decline": 0.0, "search_momentum": 0.0}

        scores = [float(r["score"]) for r in rows]
        current = scores[0]
        avg_recent = sum(scores[:7]) / min(7, len(scores))
        avg_older = sum(scores[7:]) / max(1, len(scores[7:])) if len(scores) > 7 else avg_recent

        decline = max(0.0, (avg_older - avg_recent) / max(1.0, avg_older) * 100.0)
        momentum = (avg_recent - avg_older) / max(1.0, avg_older)

        return {
            "search_score": current,
            "search_decline": decline,
            "search_momentum": momentum,
        }

    def _load_social_data(self) -> dict:
        """加载社交指标数据（社交表不存在时返回默认值）。"""
        # social_metrics 表不存在于当前 schema，返回安全默认值
        return {"social_zscore": 0.0, "social_negativity": 0.0}

    def _load_listing_heat(self) -> float:
        """加载新币上线热度（无此表时返回默认值）。"""
        # listing_metrics 表不存在于当前 schema，返回安全默认值
        return 0.0

    def _load_fear_greed(self) -> float:
        """加载恐贪指数。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT fear_greed_index FROM sentiment_index
               ORDER BY collected_at DESC LIMIT 1""",
            (),
        )
        if not rows:
            return 50.0
        return float(rows[0]["fear_greed_index"])

    def _load_historical_reversals(self) -> list[float]:
        """加载历史极端事件后的反转幅度。"""
        rows = self.db.fetch_all(
            """SELECT fomo_index, fud_index FROM retail_fomo_states
               ORDER BY ts ASC LIMIT 50""",
            (),
        )
        # 简化：返回历史极端值后的变化
        reversals = []
        for i in range(1, len(rows)):
            prev = dict(rows[i - 1])
            curr = dict(rows[i])
            prev_extreme = max(
                float(prev.get("fomo_index") or 0),
                float(prev.get("fud_index") or 0),
            )
            curr_extreme = max(
                float(curr.get("fomo_index") or 0),
                float(curr.get("fud_index") or 0),
            )
            if prev_extreme > 70:
                reversals.append(prev_extreme - curr_extreme)
        return reversals

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部散户 FOMO/FUD 复合指数分析计算并落库。"""
        ts = self._utc_now_iso()

        search_data = self._load_search_data()
        social_data = self._load_social_data()
        listing_heat = self._load_listing_heat()
        fear_greed = self._load_fear_greed()
        historical_reversals = self._load_historical_reversals()

        fomo_index = self.calculator.compute_fomo_index(
            search_score=search_data["search_score"],
            social_zscore=social_data["social_zscore"],
            listing_heat=listing_heat,
            fear_greed=fear_greed,
        )
        fud_index = self.calculator.compute_fud_index(
            search_decline=search_data["search_decline"],
            social_negativity=social_data["social_negativity"],
            fear_greed=fear_greed,
        )
        contrarian_strength = self.calculator.compute_contrarian_strength(
            fomo_index, fud_index
        )
        extreme_score = max(fomo_index, fud_index)
        reversal_probability = self.calculator.estimate_reversal_probability(
            extreme_score, historical_reversals
        )

        # 恐贪极端判断（<20 或 >80）
        fear_greed_extreme = fear_greed < 20 or fear_greed > 80

        entry = {
            "ts": ts,
            "fomo_index": fomo_index,
            "fud_index": fud_index,
            "contrarian_signal_strength": contrarian_strength,
            "reversal_probability": reversal_probability,
            "search_momentum": search_data["search_momentum"],
            "social_volume_zscore": social_data["social_zscore"],
            "listing_heat": listing_heat,
            "fear_greed_extreme": fear_greed_extreme,
        }

        self.repository.save_state(entry)
        return entry

    def load_latest_context_bundle(self) -> dict:
        """加载最新散户 FOMO/FUD 分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "fomo_index": 0.0,
                "fud_index": 0.0,
                "contrarian_signal_strength": 0.0,
                "reversal_probability": 0.0,
                "components": {
                    "search_momentum": 0.0,
                    "social_volume_zscore": 0.0,
                    "listing_heat": 0.0,
                    "fear_greed_extreme": False,
                },
            }
        return {
            "as_of": state.get("ts", self._utc_now_iso()),
            "fomo_index": state.get("fomo_index", 0.0),
            "fud_index": state.get("fud_index", 0.0),
            "contrarian_signal_strength": state.get("contrarian_signal_strength", 0.0),
            "reversal_probability": state.get("reversal_probability", 0.0),
            "components": {
                "search_momentum": state.get("search_momentum", 0.0),
                "social_volume_zscore": state.get("social_volume_zscore", 0.0),
                "listing_heat": state.get("listing_heat", 0.0),
                "fear_greed_extreme": bool(state.get("fear_greed_extreme")),
            },
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
