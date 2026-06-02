"""DeFi 压力指数计算引擎：压力指数、级联概率、协议风险排名、系统性阈值检测。"""

from __future__ import annotations


class DefiStressCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_stress_index(
        liquidation_rate: float,
        utilization_avg: float,
        hf_distribution: dict,
    ) -> float:
        """计算 DeFi 压力指数（0-100）。

        综合清算率、资金池利用率和健康因子分布。

        Parameters
        ----------
        liquidation_rate : float
            近期清算率（24h 清算量 / TVL），如 0.02 表示 2%
        utilization_avg : float
            主要借贷池平均利用率（0-1）
        hf_distribution : dict
            健康因子分布，如 {"below_1.1": 0.15, "below_1.3": 0.30, "above_1.5": 0.55}

        Returns
        -------
        float
            压力指数 [0, 100]
        """
        # 清算率因子：>5% 为极端，映射到 0-40
        liq_score = min(40.0, liquidation_rate / 0.05 * 40.0)

        # 利用率因子：>90% 为高压，映射到 0-30
        util_score = min(30.0, utilization_avg / 0.90 * 30.0)

        # 低健康因子占比因子：HF < 1.1 的比例越高越危险，映射到 0-30
        low_hf_ratio = hf_distribution.get("below_1.1", 0.0)
        hf_score = min(30.0, low_hf_ratio / 0.20 * 30.0)

        stress = liq_score + util_score + hf_score
        return round(max(0.0, min(100.0, stress)), 2)

    @staticmethod
    def compute_cascade_probability(
        hf_distribution: dict, price_drop_pct: float
    ) -> float:
        """计算给定价格下跌幅度下的级联清算概率。

        Parameters
        ----------
        hf_distribution : dict
            健康因子分布，键为阈值区间，值为该区间仓位占比
        price_drop_pct : float
            假设价格下跌百分比（如 5.0 表示 5%）

        Returns
        -------
        float
            级联清算概率 [0, 1]
        """
        if not hf_distribution:
            return 0.0

        # 价格下跌会导致 HF 按比例下降
        # HF < 1.0 + price_drop/100 的仓位将面临清算
        # 简化模型：基于已有分布估算受影响比例
        below_1_1 = hf_distribution.get("below_1.1", 0.0)
        below_1_3 = hf_distribution.get("below_1.3", 0.0)
        above_1_5 = hf_distribution.get("above_1.5", 0.0)

        # 下跌 5% 时：HF < 1.1 的全部清算 + 部分 1.1-1.3
        # 下跌 10% 时：HF < 1.3 的全部清算 + 部分 1.3-1.5
        # 下跌 20% 时：大部分仓位面临清算
        if price_drop_pct <= 5.0:
            at_risk = below_1_1 + (below_1_3 - below_1_1) * (price_drop_pct / 10.0)
        elif price_drop_pct <= 10.0:
            at_risk = below_1_3 + (1.0 - below_1_3 - above_1_5) * ((price_drop_pct - 5.0) / 15.0)
        else:
            at_risk = min(1.0, below_1_3 + (1.0 - above_1_5) * (price_drop_pct / 25.0))

        # 级联效应放大因子：清算会进一步压低价格
        cascade_multiplier = 1.0 + at_risk * 0.5
        probability = min(1.0, at_risk * cascade_multiplier)

        return round(max(0.0, probability), 6)

    @staticmethod
    def rank_protocol_risk(protocol_metrics: list[dict]) -> list[dict]:
        """对协议按风险排名。

        Parameters
        ----------
        protocol_metrics : list[dict]
            协议指标列表，每项包含 name, utilization, liquidation_rate, tvl

        Returns
        -------
        list[dict]
            按风险得分降序排列的协议列表，附加 risk_score 字段
        """
        if not protocol_metrics:
            return []

        scored = []
        for p in protocol_metrics:
            util = float(p.get("utilization", 0))
            liq_rate = float(p.get("liquidation_rate", 0))
            tvl = float(p.get("tvl", 0))

            # 风险得分：利用率 * 40% + 清算率 * 40% + TVL 集中度 * 20%
            util_score = min(1.0, util / 0.95) * 40.0
            liq_score = min(1.0, liq_rate / 0.05) * 40.0
            # TVL 越大系统性风险越高
            tvl_score = min(1.0, tvl / 10_000_000_000.0) * 20.0

            risk_score = round(util_score + liq_score + tvl_score, 2)
            scored.append({**p, "risk_score": risk_score})

        scored.sort(key=lambda x: x["risk_score"], reverse=True)
        return scored

    @staticmethod
    def detect_systemic_threshold(
        stress_index: float, cascade_prob: float
    ) -> bool:
        """检测是否突破系统性风险阈值。

        当压力指数和级联概率同时超过临界值时触发。

        Parameters
        ----------
        stress_index : float
            DeFi 压力指数 [0, 100]
        cascade_prob : float
            级联清算概率 [0, 1]

        Returns
        -------
        bool
            True 表示系统性风险阈值已突破
        """
        # 双重条件：压力指数 > 70 且级联概率 > 30%
        if stress_index > 70 and cascade_prob > 0.30:
            return True
        # 极端单一条件：压力指数 > 90 或级联概率 > 60%
        if stress_index > 90 or cascade_prob > 0.60:
            return True
        return False
