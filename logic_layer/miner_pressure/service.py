"""矿工压力服务：编排 Puell Multiple、减半周期、矿工投降、Hash Price 计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.miner_pressure.calculator import MinerPressureCalculator
from logic_layer.miner_pressure.repository import MinerPressureRepository


class MinerPressureService:
    """矿工压力编排服务。

    职责：
    - 从 miner_metrics、exchange_reserves 读取矿工与交易所数据
    - 调用 calculator 计算 Puell 百分位、减半阶段、投降指数、Hash Price 比值
    - 综合计算矿工压力评分
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = MinerPressureRepository(self.db)
        self.calculator = MinerPressureCalculator()

    def init_storage(self):
        """创建矿工压力分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_miner_metrics(self) -> dict:
        """从 miner_metrics 表读取最新矿工指标。

        Returns
        -------
        dict
            包含 puell_multiple, hashrate, hashrate_change_7d,
            hash_price, block_height 等字段
        """
        rows = self.db.fetch_all(
            """SELECT puell_multiple, hashrate, difficulty_adjustment_pct AS hashrate_change_7d,
                      hash_price, 0 AS block_height, 0 AS estimated_cost
               FROM miner_metrics
               ORDER BY collected_at DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return {}

    def _load_historical_puell(self, limit: int = 365) -> list[float]:
        """从 miner_metrics 加载历史 Puell Multiple 值。

        Parameters
        ----------
        limit : int
            回溯条数（默认 365 天）

        Returns
        -------
        list[float]
            历史 Puell Multiple 值序列
        """
        rows = self.db.fetch_all(
            """SELECT puell_multiple
               FROM miner_metrics
               WHERE puell_multiple IS NOT NULL
               ORDER BY collected_at DESC LIMIT ?""",
            (limit,),
        )
        return [float(r["puell_multiple"]) for r in rows] if rows else []

    def _load_exchange_reserve_data(self) -> dict:
        """从 exchange_reserves 表读取矿工相关的交易所储备数据。

        Returns
        -------
        dict
            包含 reserve_outflow（归一化矿工储备净流出）
        """
        rows = self.db.fetch_all(
            """SELECT reserve_balance
               FROM exchange_reserves
               WHERE asset = 'BTC'
               ORDER BY collected_at DESC LIMIT 7""",
            (),
        )
        if not rows or len(rows) < 2:
            return {"reserve_outflow": 0.0}

        # 计算7日净流出（正值 = 流出）：用余额变化近似
        balances = [float(r["reserve_balance"] or 0) for r in rows]
        # 第一个是最新，最后一个是最旧；余额减少=流出
        net_change = balances[-1] - balances[0]  # 正值=储备减少=流出
        avg_balance = sum(balances) / len(balances)

        # 归一化到 [0, 1]
        if avg_balance > 0:
            outflow_ratio = max(0.0, net_change / avg_balance)
        else:
            outflow_ratio = 0.0

        return {"reserve_outflow": min(1.0, outflow_ratio)}

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def _compute_pressure_score(
        self,
        puell_percentile: float,
        capitulation_index: float,
        hash_price_ratio: float,
        cycle_progress_pct: float,
    ) -> float:
        """综合计算矿工压力评分。

        Parameters
        ----------
        puell_percentile : float
            Puell 百分位 [0, 100]
        capitulation_index : float
            矿工投降指数 [0, 100]
        hash_price_ratio : float
            Hash Price 比值
        cycle_progress_pct : float
            减半周期进度 [0, 100]

        Returns
        -------
        float
            矿工压力综合评分 [0, 100]
        """
        # Puell 压力：百分位越低 -> 压力越大
        puell_pressure = max(0.0, min(100.0, 100.0 - puell_percentile))

        # Hash Price 压力：比值越低 -> 压力越大
        if hash_price_ratio >= 2.0:
            hp_pressure = 0.0
        elif hash_price_ratio >= 1.0:
            hp_pressure = (2.0 - hash_price_ratio) * 50.0
        else:
            hp_pressure = 50.0 + (1.0 - hash_price_ratio) * 50.0
        hp_pressure = max(0.0, min(100.0, hp_pressure))

        # 周期压力：减半前后压力较高（0-20% 和 80-100% 进度时）
        if cycle_progress_pct <= 20.0:
            cycle_pressure = (20.0 - cycle_progress_pct) / 20.0 * 60.0
        elif cycle_progress_pct >= 80.0:
            cycle_pressure = (cycle_progress_pct - 80.0) / 20.0 * 40.0
        else:
            cycle_pressure = 0.0

        # 加权聚合
        score = (
            capitulation_index * 0.35
            + puell_pressure * 0.25
            + hp_pressure * 0.25
            + cycle_pressure * 0.15
        )
        return round(max(0.0, min(100.0, score)), 2)

    def run_all(self) -> dict:
        """执行全部矿工压力分析计算并落库。"""
        miner_data = self._load_miner_metrics()
        reserve_data = self._load_exchange_reserve_data()

        if not miner_data:
            return {"state": None, "message": "no miner_metrics data available"}

        ts = self._utc_now_iso()

        # Puell Multiple 分析
        puell_multiple = float(miner_data.get("puell_multiple") or 1.0)
        historical_puell = self._load_historical_puell()
        puell_percentile = self.calculator.compute_puell_percentile(
            puell_multiple, historical_puell
        )
        puell_zone = self.calculator.classify_puell_zone(puell_multiple)

        # 减半周期
        block_height = int(miner_data.get("block_height") or 840_000)
        halving_phase = self.calculator.compute_halving_phase(block_height)

        # 矿工投降指数
        hashrate_change_7d = float(miner_data.get("hashrate_change_7d") or 0.0)
        reserve_outflow = float(reserve_data.get("reserve_outflow", 0.0))
        capitulation_index = self.calculator.compute_miner_capitulation_index(
            puell_percentile, hashrate_change_7d, reserve_outflow
        )

        # Hash Price 比值
        hash_price = float(miner_data.get("hash_price") or 0.0)
        estimated_cost = float(miner_data.get("estimated_cost") or 0.0)
        hash_price_ratio = self.calculator.compute_hash_price_ratio(
            hash_price, estimated_cost
        )

        # 综合压力评分
        pressure_score = self._compute_pressure_score(
            puell_percentile,
            capitulation_index,
            hash_price_ratio,
            halving_phase["cycle_progress_pct"],
        )

        state = {
            "ts": ts,
            "puell_percentile": puell_percentile,
            "puell_zone": puell_zone,
            "halving_days_until_next": int(halving_phase["days_until_next"]),
            "halving_cycle_pct": halving_phase["cycle_progress_pct"],
            "capitulation_index": capitulation_index,
            "hash_price_ratio": hash_price_ratio,
            "pressure_score": pressure_score,
        }

        self.repository.save_state(state)
        return {"state": state}

    def load_latest_context_bundle(self) -> dict:
        """加载最新矿工压力分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "miner_pressure": None,
                "capitulation_signal": False,
                "halving_phase": None,
            }

        capitulation_signal = (
            state.get("puell_zone") == "capitulation"
            or (state.get("capitulation_index") or 0) >= 70.0
        )

        return {
            "as_of": self._utc_now_iso(),
            "miner_pressure": {
                "pressure_score": state.get("pressure_score"),
                "puell_percentile": state.get("puell_percentile"),
                "puell_zone": state.get("puell_zone"),
                "capitulation_index": state.get("capitulation_index"),
                "hash_price_ratio": state.get("hash_price_ratio"),
            },
            "capitulation_signal": capitulation_signal,
            "halving_phase": {
                "days_until_next": state.get("halving_days_until_next"),
                "cycle_progress_pct": state.get("halving_cycle_pct"),
            },
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
