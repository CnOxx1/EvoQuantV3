"""持有者行为计算引擎：STH/LTH 比率、MVRV 百分位、SOPR 状态机、供给冲击概率。"""

from __future__ import annotations

import math
from datetime import datetime, timezone


class HolderBehaviorCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_sth_lth_ratio(sth_supply_pct: float, lth_supply_pct: float) -> float:
        """计算短期持有者与长期持有者的供给比率变化。

        Parameters
        ----------
        sth_supply_pct : float
            短期持有者供给百分比 (0-100)
        lth_supply_pct : float
            长期持有者供给百分比 (0-100)

        Returns
        -------
        float
            STH/LTH 供给比率，LTH 为 0 时返回 0.0
        """
        if lth_supply_pct <= 0:
            return 0.0
        ratio = sth_supply_pct / lth_supply_pct
        return round(ratio, 4)

    @staticmethod
    def compute_mvrv_percentile(mvrv: float, historical_values: list[float]) -> float:
        """计算当前 MVRV 在历史分布中的百分位。

        Parameters
        ----------
        mvrv : float
            当前 MVRV 值
        historical_values : list[float]
            历史 MVRV 值列表

        Returns
        -------
        float
            百分位 [0, 100]，值越高表示越处于高估区间
        """
        if not historical_values:
            return 50.0

        count_below = sum(1 for v in historical_values if v < mvrv)
        percentile = (count_below / len(historical_values)) * 100.0
        return round(max(0.0, min(100.0, percentile)), 2)

    @staticmethod
    def classify_sopr_state(sopr: float) -> str:
        """根据 SOPR 值判定市场状态。

        SOPR (Spent Output Profit Ratio):
        - > 1: 持有者以盈利卖出 -> profit_taking
        - < 1: 持有者以亏损卖出 -> capitulation
        - == 1: 盈亏平衡 -> neutral

        Parameters
        ----------
        sopr : float
            当前 SOPR 值

        Returns
        -------
        str
            "profit_taking" / "capitulation" / "neutral"
        """
        if sopr > 1.0:
            return "profit_taking"
        elif sopr < 1.0:
            return "capitulation"
        else:
            return "neutral"

    @staticmethod
    def compute_supply_shock_probability(illiquid_change_rate: float) -> float:
        """计算供给冲击概率。

        基于非流动性供给变化率，使用 sigmoid 函数映射到 [0, 1]。
        正值表示非流动性供给增加（供给冲击概率上升）。

        Parameters
        ----------
        illiquid_change_rate : float
            非流动性供给变化率（正值 = 供给锁定增加）

        Returns
        -------
        float
            供给冲击概率 [0, 1]
        """
        # Sigmoid 映射：k 控制灵敏度，中心点在 0
        k = 10.0
        try:
            prob = 1.0 / (1.0 + math.exp(-k * illiquid_change_rate))
        except OverflowError:
            prob = 0.0 if illiquid_change_rate < 0 else 1.0
        return round(max(0.0, min(1.0, prob)), 4)

    @staticmethod
    def determine_market_phase(
        mvrv_pct: float, sopr_state: str, supply_shock: float
    ) -> str:
        """综合判定当前市场阶段。

        Parameters
        ----------
        mvrv_pct : float
            MVRV 百分位 (0-100)
        sopr_state : str
            SOPR 状态 ("profit_taking"/"capitulation"/"neutral")
        supply_shock : float
            供给冲击概率 (0-1)

        Returns
        -------
        str
            市场阶段: "accumulation" / "markup" / "distribution" / "markdown"
        """
        # 积累阶段：MVRV 低位 + 投降 + 供给锁定增加
        if mvrv_pct < 25 and sopr_state == "capitulation":
            return "accumulation"

        # 派发阶段：MVRV 高位 + 获利了结
        if mvrv_pct > 75 and sopr_state == "profit_taking":
            return "distribution"

        # 上涨阶段：MVRV 中高位 + 供给冲击高
        if mvrv_pct >= 25 and supply_shock > 0.6:
            return "markup"

        # 下跌阶段：MVRV 中低位 + 供给冲击低 + 投降
        if mvrv_pct <= 50 and supply_shock < 0.4 and sopr_state == "capitulation":
            return "markdown"

        # 默认根据 MVRV 百分位判断
        if mvrv_pct > 60:
            return "distribution" if sopr_state == "profit_taking" else "markup"
        elif mvrv_pct < 40:
            return "accumulation" if sopr_state == "capitulation" else "markdown"
        else:
            return "markup" if supply_shock >= 0.5 else "markdown"
