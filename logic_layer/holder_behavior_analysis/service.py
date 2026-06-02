"""持有者行为分析服务：编排 STH/LTH 比率、MVRV、SOPR、供给冲击计算。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.holder_behavior_analysis.calculator import HolderBehaviorCalculator
from logic_layer.holder_behavior_analysis.repository import HolderBehaviorRepository


class HolderBehaviorService:
    """持有者行为编排服务。

    职责：
    - 从 holder_metrics 读取链上持有者数据（market_data DB）
    - 从 exchange_reserves 读取交易所储备数据（market_data DB）
    - 调用 calculator 计算 STH/LTH 比率、MVRV 百分位、SOPR 状态、供给冲击
    - 综合判定市场阶段
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = HolderBehaviorRepository(self.db)
        self.calculator = HolderBehaviorCalculator()

    def init_storage(self):
        """创建持有者行为分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_holder_metrics(self) -> dict | None:
        """从 holder_metrics 表加载最新链上持有者数据。

        Returns
        -------
        dict | None
            包含 sth_supply_pct, lth_supply_pct, mvrv, sopr 的字典
        """
        rows = self.db.fetch_all(
            """SELECT sth_supply_pct, lth_supply_pct, mvrv, sopr
               FROM holder_metrics
               ORDER BY ts DESC
               LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None

    def _load_historical_mvrv(self, limit: int = 365) -> list[float]:
        """从 holder_metrics 表加载历史 MVRV 值。

        Parameters
        ----------
        limit : int
            历史数据点数（默认 365 天）

        Returns
        -------
        list[float]
            历史 MVRV 值列表
        """
        rows = self.db.fetch_all(
            """SELECT mvrv FROM holder_metrics
               WHERE mvrv IS NOT NULL
               ORDER BY ts DESC
               LIMIT ?""",
            (limit,),
        )
        return [float(r["mvrv"]) for r in rows] if rows else []

    def _load_exchange_reserves(self) -> dict | None:
        """从 exchange_reserves 表加载最新交易所储备数据。

        Returns
        -------
        dict | None
            包含 illiquid_change_rate 的字典
        """
        rows = self.db.fetch_all(
            """SELECT illiquid_change_rate
               FROM exchange_reserves
               ORDER BY ts DESC
               LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self, no_save: bool = False) -> dict:
        """执行全部持有者行为分析计算。

        Parameters
        ----------
        no_save : bool
            为 True 时只计算不落库

        Returns
        -------
        dict
            包含计算结果的字典
        """
        holder_data = self._load_holder_metrics()
        reserve_data = self._load_exchange_reserves()

        if holder_data is None:
            return {"error": "no holder_metrics data available"}

        ts = self._utc_now_iso()

        # STH/LTH 比率
        sth_pct = float(holder_data.get("sth_supply_pct") or 0.0)
        lth_pct = float(holder_data.get("lth_supply_pct") or 0.0)
        sth_lth_ratio = self.calculator.compute_sth_lth_ratio(sth_pct, lth_pct)

        # MVRV 百分位
        mvrv = float(holder_data.get("mvrv") or 0.0)
        historical_mvrv = self._load_historical_mvrv()
        mvrv_percentile = self.calculator.compute_mvrv_percentile(
            mvrv, historical_mvrv
        )

        # SOPR 状态
        sopr = float(holder_data.get("sopr") or 1.0)
        sopr_state = self.calculator.classify_sopr_state(sopr)

        # 供给冲击概率
        illiquid_change_rate = 0.0
        if reserve_data is not None:
            illiquid_change_rate = float(
                reserve_data.get("illiquid_change_rate") or 0.0
            )
        supply_shock_prob = self.calculator.compute_supply_shock_probability(
            illiquid_change_rate
        )

        # 市场阶段判定
        market_phase = self.calculator.determine_market_phase(
            mvrv_percentile, sopr_state, supply_shock_prob
        )

        state = {
            "ts": ts,
            "sth_lth_ratio": sth_lth_ratio,
            "mvrv_percentile": mvrv_percentile,
            "sopr_state": sopr_state,
            "supply_shock_prob": supply_shock_prob,
            "market_phase": market_phase,
        }

        if not no_save:
            self.repository.save_state(state)

        return state

    # ------------------------------------------------------------------
    # 上下文输出
    # ------------------------------------------------------------------

    def load_latest_context_bundle(self) -> dict:
        """加载最新持有者行为分析结果，供 AI 上下文消费。"""
        latest = self.repository.load_latest_state()
        if latest is None:
            return {
                "as_of": self._utc_now_iso(),
                "holder_behavior": None,
                "market_phase": "unknown",
                "signals": [],
            }

        signals = self._extract_signals(latest)
        return {
            "as_of": self._utc_now_iso(),
            "holder_behavior": latest,
            "market_phase": latest.get("market_phase", "unknown"),
            "signals": signals,
        }

    @staticmethod
    def _extract_signals(state: dict) -> list[str]:
        """从持有者行为状态中提取关键信号。"""
        signals = []
        mvrv_pct = state.get("mvrv_percentile", 50.0)
        if mvrv_pct >= 90:
            signals.append("mvrv_extreme_high")
        elif mvrv_pct <= 10:
            signals.append("mvrv_extreme_low")

        sopr_state = state.get("sopr_state", "neutral")
        if sopr_state == "capitulation":
            signals.append("holder_capitulation")
        elif sopr_state == "profit_taking":
            signals.append("holder_profit_taking")

        supply_shock = state.get("supply_shock_prob", 0.5)
        if supply_shock > 0.8:
            signals.append("supply_shock_high")
        elif supply_shock < 0.2:
            signals.append("supply_shock_low")

        return signals

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
