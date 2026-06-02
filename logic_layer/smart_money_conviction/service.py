"""Smart Money 信念指数服务：编排 conviction index、方向分类、散户背离、PnL 趋势。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.smart_money_conviction.calculator import SmartMoneyConvictionCalculator
from logic_layer.smart_money_conviction.repository import SmartMoneyConvictionRepository


class SmartMoneyConvictionService:
    """Smart Money 信念指数编排服务。

    职责：
    - 从 whale_positions、retail_flows 读取市场数据
    - 调用 calculator 计算信念指数、方向、背离
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = SmartMoneyConvictionRepository(self.db)
        self.calculator = SmartMoneyConvictionCalculator()
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建 Smart Money 信念指数分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_whale_positions(self) -> dict:
        """从 whale_positions 加载鲸鱼持仓数据。

        Returns
        -------
        dict
            包含 avg_pnl, position_direction, consistency, bullish, bearish
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT direction, pnl_pct, size_usd
               FROM whale_positions
               ORDER BY created_at DESC LIMIT 50""",
            (),
        )
        if not rows:
            return {
                "avg_pnl": 0.0, "position_direction": 0.0,
                "consistency": 0.0, "bullish": 0, "bearish": 0,
            }

        pnls = [float(r.get("pnl_pct") or 0) for r in rows]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0

        bullish = sum(1 for r in rows if r.get("direction") == "long")
        bearish = sum(1 for r in rows if r.get("direction") == "short")
        total = bullish + bearish
        if total > 0:
            direction = (bullish - bearish) / total
            consistency = max(bullish, bearish) / total
        else:
            direction = 0.0
            consistency = 0.0

        return {
            "avg_pnl": avg_pnl,
            "position_direction": direction,
            "consistency": consistency,
            "bullish": bullish,
            "bearish": bearish,
        }

    def _load_retail_flow(self) -> float:
        """加载散户资金流向指标。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT net_flow FROM retail_flows
               ORDER BY created_at DESC LIMIT 10""",
            (),
        )
        if not rows:
            return 0.0
        flows = [float(r["net_flow"]) for r in rows]
        avg_flow = sum(flows) / len(flows)
        # 归一化到 [-1, 1]
        return max(-1.0, min(1.0, avg_flow / 1_000_000.0))

    def _load_pnl_series(self) -> list[float]:
        """加载历史 PnL 序列。"""
        rows = self.db.fetch_all(
            """SELECT conviction_index FROM smart_money_conviction_states
               ORDER BY ts ASC LIMIT 20""",
            (),
        )
        return [float(r["conviction_index"]) / 100.0 for r in rows
                if r["conviction_index"]]

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部 Smart Money 信念指数分析计算并落库。"""
        ts = self._utc_now_iso()

        whale_data = self._load_whale_positions()
        retail_flow = self._load_retail_flow()
        pnl_series = self._load_pnl_series()

        conviction_index = self.calculator.compute_conviction_index(
            avg_pnl=whale_data["avg_pnl"],
            position_direction=whale_data["position_direction"],
            consistency=whale_data["consistency"],
        )
        direction = self.calculator.classify_direction(conviction_index)
        retail_divergence = self.calculator.compute_retail_divergence(
            smart_money_direction=whale_data["position_direction"],
            retail_flow=retail_flow,
        )
        pnl_trend = self.calculator.compute_pnl_trend(pnl_series)

        # 持仓变化描述
        if whale_data["position_direction"] > 0.3:
            position_change = "increasing_long"
        elif whale_data["position_direction"] < -0.3:
            position_change = "increasing_short"
        else:
            position_change = "mixed"

        entry = {
            "ts": ts,
            "conviction_index": conviction_index,
            "direction": direction,
            "pnl_trend": pnl_trend,
            "position_change": position_change,
            "retail_divergence": retail_divergence,
            "whale_count_bullish": whale_data["bullish"],
            "whale_count_bearish": whale_data["bearish"],
        }

        self.repository.save_state(entry)
        return entry

    def load_latest_context_bundle(self) -> dict:
        """加载最新 Smart Money 信念指数分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "conviction_index": 50.0,
                "direction": "neutral",
                "retail_divergence": 0.0,
                "whale_count_bullish": 0,
                "whale_count_bearish": 0,
            }
        return {
            "as_of": state.get("ts", self._utc_now_iso()),
            "conviction_index": state.get("conviction_index", 50.0),
            "direction": state.get("direction", "neutral"),
            "retail_divergence": state.get("retail_divergence", 0.0),
            "whale_count_bullish": state.get("whale_count_bullish", 0),
            "whale_count_bearish": state.get("whale_count_bearish", 0),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
