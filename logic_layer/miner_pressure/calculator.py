"""矿工压力计算引擎：Puell Multiple、减半周期、矿工投降指数、Hash Price。"""

from __future__ import annotations

import math


class MinerPressureCalculator:
    """纯计算逻辑，不依赖数据库。"""

    # 减半参数
    LAST_HALVING_BLOCK = 840_000  # April 2024
    BLOCKS_PER_HALVING = 210_000
    NEXT_HALVING_BLOCK = LAST_HALVING_BLOCK + BLOCKS_PER_HALVING  # 1,050,000
    AVG_BLOCK_TIME_MINUTES = 10

    @staticmethod
    def compute_puell_percentile(
        puell_multiple: float,
        historical_values: list[float],
    ) -> float:
        """计算 Puell Multiple 在历史分布中的百分位。

        Parameters
        ----------
        puell_multiple : float
            当前 Puell Multiple 值
        historical_values : list[float]
            历史 Puell Multiple 值序列

        Returns
        -------
        float
            百分位 [0, 100]
        """
        if not historical_values:
            return 50.0

        count_below = sum(1 for v in historical_values if v <= puell_multiple)
        percentile = (count_below / len(historical_values)) * 100.0
        return round(max(0.0, min(100.0, percentile)), 2)

    @staticmethod
    def classify_puell_zone(puell_multiple: float) -> str:
        """根据 Puell Multiple 值判定矿工状态区间。

        Parameters
        ----------
        puell_multiple : float
            当前 Puell Multiple 值

        Returns
        -------
        str
            "capitulation" | "recovery" | "normal" | "overheated"
        """
        if puell_multiple <= 0.5:
            return "capitulation"
        elif puell_multiple <= 0.8:
            return "recovery"
        elif puell_multiple <= 4.0:
            return "normal"
        else:
            return "overheated"

    @classmethod
    def compute_halving_phase(cls, current_block_height: int) -> dict:
        """计算减半周期阶段信息。

        Parameters
        ----------
        current_block_height : int
            当前区块高度

        Returns
        -------
        dict
            包含 days_since_last, days_until_next, cycle_progress_pct
        """
        blocks_since_last = current_block_height - cls.LAST_HALVING_BLOCK
        blocks_until_next = cls.NEXT_HALVING_BLOCK - current_block_height

        # 处理边界情况
        blocks_since_last = max(0, blocks_since_last)
        blocks_until_next = max(0, blocks_until_next)

        days_since_last = (blocks_since_last * cls.AVG_BLOCK_TIME_MINUTES) / (60 * 24)
        days_until_next = (blocks_until_next * cls.AVG_BLOCK_TIME_MINUTES) / (60 * 24)

        cycle_progress_pct = (
            (blocks_since_last / cls.BLOCKS_PER_HALVING) * 100.0
            if cls.BLOCKS_PER_HALVING > 0
            else 0.0
        )
        cycle_progress_pct = max(0.0, min(100.0, cycle_progress_pct))

        return {
            "days_since_last": round(days_since_last, 1),
            "days_until_next": round(days_until_next, 1),
            "cycle_progress_pct": round(cycle_progress_pct, 2),
        }

    @staticmethod
    def compute_miner_capitulation_index(
        puell_pct: float,
        hashrate_change_7d: float,
        reserve_outflow: float,
    ) -> float:
        """计算矿工投降综合指数。

        综合 Puell 百分位（反转）、算力变化、储备流出三个维度。

        Parameters
        ----------
        puell_pct : float
            Puell Multiple 百分位 [0, 100]
        hashrate_change_7d : float
            7日算力变化率（负值表示下降，如 -0.05 = -5%）
        reserve_outflow : float
            矿工储备净流出量（正值表示流出，归一化到 [0, 1]）

        Returns
        -------
        float
            矿工投降指数 [0, 100]，越高越接近投降
        """
        # Puell 百分位反转：百分位越低 -> 投降信号越强
        puell_stress = max(0.0, min(100.0, 100.0 - puell_pct))

        # 算力下降信号：下降越多 -> 信号越强
        # -0.1 (10% drop) => 100 分
        hashrate_stress = max(0.0, min(100.0, abs(min(0.0, hashrate_change_7d)) * 1000.0))

        # 储备流出信号：流出越多 -> 信号越强
        outflow_stress = max(0.0, min(100.0, reserve_outflow * 100.0))

        # 加权聚合
        index = (
            puell_stress * 0.4
            + hashrate_stress * 0.35
            + outflow_stress * 0.25
        )
        return round(max(0.0, min(100.0, index)), 2)

    @staticmethod
    def compute_hash_price_ratio(
        hash_price: float,
        estimated_cost: float,
    ) -> float:
        """计算 Hash Price 与电力成本的比值。

        Parameters
        ----------
        hash_price : float
            当前 Hash Price（每 TH/s 每日收入，USD）
        estimated_cost : float
            估算电力成本（每 TH/s 每日成本，USD）

        Returns
        -------
        float
            比值。>1 表示盈利，<1 表示亏损
        """
        if estimated_cost <= 0:
            return 0.0
        ratio = hash_price / estimated_cost
        return round(ratio, 4)
