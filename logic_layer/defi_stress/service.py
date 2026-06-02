"""DeFi 压力指数服务：编排压力指数、级联概率、协议风险排名、系统性阈值检测。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.defi_stress.calculator import DefiStressCalculator
from logic_layer.defi_stress.repository import DefiStressRepository


class DefiStressService:
    """DeFi 压力指数编排服务。

    职责：
    - 从 defi_protocols、liquidations 读取市场数据
    - 调用 calculator 计算压力指数、级联概率、协议风险
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = DefiStressRepository(self.db)
        self.calculator = DefiStressCalculator()
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建 DeFi 压力指数分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_liquidation_data(self) -> dict:
        """从 liquidations 加载清算数据。

        Returns
        -------
        dict
            包含 liquidation_rate, total_at_risk_usd
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT liquidation_amount_usd, tvl
               FROM defi_liquidations
               ORDER BY created_at DESC LIMIT 24""",
            (),
        )
        if not rows:
            return {"liquidation_rate": 0.0, "total_at_risk_usd": 0.0}

        total_liq = sum(float(r.get("liquidation_amount_usd") or 0) for r in rows)
        avg_tvl = sum(float(r.get("tvl") or 0) for r in rows) / len(rows)
        rate = total_liq / avg_tvl if avg_tvl > 0 else 0.0
        return {"liquidation_rate": rate, "total_at_risk_usd": total_liq}

    def _load_utilization_data(self) -> float:
        """加载主要借贷池平均利用率。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT utilization FROM defi_protocols
               ORDER BY created_at DESC LIMIT 10""",
            (),
        )
        if not rows:
            return 0.0
        utils = [float(r["utilization"]) for r in rows]
        return sum(utils) / len(utils)

    def _load_hf_distribution(self) -> dict:
        """加载健康因子分布。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT health_factor, position_usd
               FROM defi_positions
               ORDER BY created_at DESC LIMIT 200""",
            (),
        )
        if not rows:
            return {"below_1.1": 0.0, "below_1.3": 0.0, "above_1.5": 0.0}

        total_usd = sum(float(r.get("position_usd") or 0) for r in rows)
        if total_usd <= 0:
            return {"below_1.1": 0.0, "below_1.3": 0.0, "above_1.5": 0.0}

        below_1_1 = sum(
            float(r.get("position_usd") or 0) for r in rows
            if float(r.get("health_factor") or 999) < 1.1
        ) / total_usd
        below_1_3 = sum(
            float(r.get("position_usd") or 0) for r in rows
            if float(r.get("health_factor") or 999) < 1.3
        ) / total_usd
        above_1_5 = sum(
            float(r.get("position_usd") or 0) for r in rows
            if float(r.get("health_factor") or 0) >= 1.5
        ) / total_usd

        return {
            "below_1.1": below_1_1,
            "below_1.3": below_1_3,
            "above_1.5": above_1_5,
        }

    def _load_protocol_metrics(self) -> list[dict]:
        """加载协议级指标。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT name, utilization, liquidation_rate, tvl
               FROM defi_protocols
               ORDER BY tvl DESC LIMIT 20""",
            (),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部 DeFi 压力指数分析计算并落库。"""
        ts = self._utc_now_iso()

        liq_data = self._load_liquidation_data()
        utilization_avg = self._load_utilization_data()
        hf_distribution = self._load_hf_distribution()
        protocol_metrics = self._load_protocol_metrics()

        stress_index = self.calculator.compute_stress_index(
            liquidation_rate=liq_data["liquidation_rate"],
            utilization_avg=utilization_avg,
            hf_distribution=hf_distribution,
        )
        cascade_prob_5 = self.calculator.compute_cascade_probability(
            hf_distribution, 5.0
        )
        cascade_prob_10 = self.calculator.compute_cascade_probability(
            hf_distribution, 10.0
        )
        cascade_prob_20 = self.calculator.compute_cascade_probability(
            hf_distribution, 20.0
        )

        ranked = self.calculator.rank_protocol_risk(protocol_metrics)
        highest_risk = ranked[0]["name"] if ranked else "unknown"

        systemic_breached = self.calculator.detect_systemic_threshold(
            stress_index, cascade_prob_10
        )

        entry = {
            "ts": ts,
            "stress_index": stress_index,
            "cascade_prob_5pct": cascade_prob_5,
            "cascade_prob_10pct": cascade_prob_10,
            "cascade_prob_20pct": cascade_prob_20,
            "highest_risk_protocol": highest_risk,
            "systemic_threshold_breached": systemic_breached,
            "total_at_risk_usd": liq_data["total_at_risk_usd"],
        }

        self.repository.save_state(entry)
        return entry

    def load_latest_context_bundle(self) -> dict:
        """加载最新 DeFi 压力指数分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "stress_index": 0.0,
                "cascade_prob_5pct": 0.0,
                "cascade_prob_10pct": 0.0,
                "cascade_prob_20pct": 0.0,
                "highest_risk_protocol": "unknown",
                "systemic_threshold_breached": False,
                "total_at_risk_usd": 0.0,
            }
        return {
            "as_of": state.get("ts", self._utc_now_iso()),
            "stress_index": state.get("stress_index", 0.0),
            "cascade_prob_5pct": state.get("cascade_prob_5pct", 0.0),
            "cascade_prob_10pct": state.get("cascade_prob_10pct", 0.0),
            "cascade_prob_20pct": state.get("cascade_prob_20pct", 0.0),
            "highest_risk_protocol": state.get("highest_risk_protocol", "unknown"),
            "systemic_threshold_breached": bool(state.get("systemic_threshold_breached")),
            "total_at_risk_usd": state.get("total_at_risk_usd", 0.0),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
