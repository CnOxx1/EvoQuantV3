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
            """SELECT score FROM search_trends
               WHERE category = 'crypto'
               ORDER BY created_at DESC LIMIT 14""",
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
        """加载社交指标数据。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT volume, sentiment_score FROM social_metrics
               ORDER BY created_at DESC LIMIT 30""",
            (),
        )
        if not rows:
            return {"social_zscore": 0.0, "social_negativity": 0.0}

        volumes = [float(r.get("volume") or 0) for r in rows]
        sentiments = [float(r.get("sentiment_score") or 0) for r in rows]

        # 计算 Z-score
        if len(volumes) >= 2:
            mean_vol = sum(volumes) / len(volumes)
            std_vol = (sum((v - mean_vol) ** 2 for v in volumes) / len(volumes)) ** 0.5
            zscore = (volumes[0] - mean_vol) / std_vol if std_vol > 0 else 0.0
        else:
            zscore = 0.0

        # 社交负面情绪比例（sentiment < -0.3）
        neg_count = sum(1 for s in sentiments[:10] if s < -0.3)
        negativity = neg_count / min(10, len(sentiments))

        return {"social_zscore": zscore, "social_negativity": negativity}

    def _load_listing_heat(self) -> float:
        """加载新币上线热度。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT listing_count, avg_first_day_volume
               FROM listing_metrics
               ORDER BY created_at DESC LIMIT 7""",
            (),
        )
        if not rows:
            return 0.0

        # 热度 = 近期上币数量 * 首日成交量的归一化
        total_listings = sum(int(r.get("listing_count") or 0) for r in rows)
        avg_vol = sum(float(r.get("avg_first_day_volume") or 0) for r in rows) / len(rows)

        # 归一化到 0-100（假设每周 10 个新币且平均首日 1M 为正常）
        listing_norm = min(1.0, total_listings / 10.0)
        vol_norm = min(1.0, avg_vol / 1_000_000.0)
        heat = (listing_norm * 0.4 + vol_norm * 0.6) * 100.0
        return round(heat, 2)

    def _load_fear_greed(self) -> float:
        """加载恐贪指数。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT value FROM fear_greed_index
               ORDER BY created_at DESC LIMIT 1""",
            (),
        )
        if not rows:
            return 50.0
        return float(rows[0]["value"])

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
            prev_extreme = max(
                float(rows[i - 1].get("fomo_index") or 0),
                float(rows[i - 1].get("fud_index") or 0),
            )
            curr_extreme = max(
                float(rows[i].get("fomo_index") or 0),
                float(rows[i].get("fud_index") or 0),
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
