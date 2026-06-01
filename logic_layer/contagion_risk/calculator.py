"""传染风险计算引擎：CoVaR、条件相关性、尾部 Beta、系统性风险。"""

from __future__ import annotations

import math
from datetime import datetime, timezone


class ContagionRiskCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_conditional_correlation(
        returns_a: list[float],
        returns_b: list[float],
        threshold_sigma: float = 2.0,
    ) -> float:
        """计算条件相关性：当 A 处于极端下跌时与 B 的相关性。

        Parameters
        ----------
        returns_a : list[float]
            资产 A 的收益率序列
        returns_b : list[float]
            资产 B 的收益率序列
        threshold_sigma : float
            极端事件阈值（标准差倍数）

        Returns
        -------
        float
            条件相关性 [-1, 1]
        """
        n = min(len(returns_a), len(returns_b))
        if n < 10:
            return 0.0

        ra = returns_a[:n]
        rb = returns_b[:n]

        # 计算 A 的均值和标准差
        mean_a = sum(ra) / n
        var_a = sum((x - mean_a) ** 2 for x in ra) / (n - 1)
        std_a = math.sqrt(var_a) if var_a > 0 else 0.0

        if std_a == 0:
            return 0.0

        # 筛选 A 处于极端下跌的时段
        threshold = mean_a - threshold_sigma * std_a
        stress_indices = [i for i in range(n) if ra[i] <= threshold]

        if len(stress_indices) < 5:
            return 0.0

        # 在极端时段计算相关性
        sa = [ra[i] for i in stress_indices]
        sb = [rb[i] for i in stress_indices]
        m = len(sa)
        mean_sa = sum(sa) / m
        mean_sb = sum(sb) / m
        var_sa = sum((x - mean_sa) ** 2 for x in sa) / (m - 1)
        var_sb = sum((x - mean_sb) ** 2 for x in sb) / (m - 1)
        std_sa = math.sqrt(var_sa) if var_sa > 0 else 0.0
        std_sb = math.sqrt(var_sb) if var_sb > 0 else 0.0

        if std_sa == 0 or std_sb == 0:
            return 0.0

        cov = sum((sa[i] - mean_sa) * (sb[i] - mean_sb) for i in range(m)) / (m - 1)
        corr = cov / (std_sa * std_sb)
        return round(max(-1.0, min(1.0, corr)), 4)

    @staticmethod
    def compute_covar(
        returns_a: list[float],
        returns_b: list[float],
        confidence: float = 0.95,
    ) -> float:
        """计算 CoVaR：当 B 处于 VaR 水平时 A 的条件 VaR。

        Parameters
        ----------
        returns_a : list[float]
            资产 A 的收益率序列
        returns_b : list[float]
            资产 B 的收益率序列（系统性资产）
        confidence : float
            置信水平（默认 95%）

        Returns
        -------
        float
            CoVaR 值（负数表示损失）
        """
        n = min(len(returns_a), len(returns_b))
        if n < 20:
            return 0.0

        ra = returns_a[:n]
        rb = returns_b[:n]

        # B 的 VaR 分位数
        sorted_rb = sorted(rb)
        var_index = int((1 - confidence) * n)
        var_index = max(0, min(var_index, n - 1))
        var_b = sorted_rb[var_index]

        # 筛选 B <= VaR 的时段，计算 A 的条件分布
        stress_indices = [i for i in range(n) if rb[i] <= var_b]
        if not stress_indices:
            return 0.0

        stress_a = sorted([ra[i] for i in stress_indices])
        covar_index = int((1 - confidence) * len(stress_a))
        covar_index = max(0, min(covar_index, len(stress_a) - 1))
        return round(stress_a[covar_index], 6)

    @staticmethod
    def compute_tail_beta(
        returns_asset: list[float],
        returns_market: list[float],
        percentile: float = 5.0,
    ) -> float:
        """计算尾部 Beta：市场极端下跌时资产的敏感度。

        Parameters
        ----------
        returns_asset : list[float]
            资产收益率序列
        returns_market : list[float]
            市场收益率序列
        percentile : float
            尾部百分位（默认 5%）

        Returns
        -------
        float
            尾部 Beta
        """
        n = min(len(returns_asset), len(returns_market))
        if n < 20:
            return 0.0

        ra = returns_asset[:n]
        rm = returns_market[:n]

        # 市场尾部阈值
        sorted_rm = sorted(rm)
        tail_index = int(percentile / 100.0 * n)
        tail_index = max(1, min(tail_index, n - 1))
        tail_threshold = sorted_rm[tail_index]

        # 筛选市场处于尾部的时段
        tail_indices = [i for i in range(n) if rm[i] <= tail_threshold]
        if len(tail_indices) < 5:
            return 0.0

        # 在尾部时段计算 beta = cov(ra, rm) / var(rm)
        tail_ra = [ra[i] for i in tail_indices]
        tail_rm = [rm[i] for i in tail_indices]
        m = len(tail_ra)
        mean_ra = sum(tail_ra) / m
        mean_rm = sum(tail_rm) / m

        var_rm = sum((x - mean_rm) ** 2 for x in tail_rm) / (m - 1)
        if var_rm == 0:
            return 0.0

        cov = sum(
            (tail_ra[i] - mean_ra) * (tail_rm[i] - mean_rm)
            for i in range(m)
        ) / (m - 1)
        beta = cov / var_rm
        return round(beta, 4)

    @staticmethod
    def compute_stablecoin_depeg_probability(
        price: float,
        peg: float = 1.0,
        volatility: float = 0.01,
    ) -> float:
        """估算稳定币脱锚概率。

        使用简化的正态分布模型估算价格偏离锚定值的概率。

        Parameters
        ----------
        price : float
            当前价格
        peg : float
            锚定价格（默认 1.0）
        volatility : float
            价格波动率（默认 0.01）

        Returns
        -------
        float
            脱锚概率 [0, 1]
        """
        if volatility <= 0:
            return 0.0

        deviation = abs(price - peg) / peg
        # z-score
        z = deviation / volatility

        # 简化的正态 CDF 近似（Abramowitz & Stegun）
        if z == 0:
            return 0.0
        t = 1.0 / (1.0 + 0.2316419 * z)
        d = 0.3989422804 * math.exp(-z * z / 2.0)
        p = d * t * (
            0.3193815 + t * (
                -0.3565638 + t * (
                    1.781478 + t * (
                        -1.821256 + t * 1.330274
                    )
                )
            )
        )
        # 双尾概率
        prob = 2.0 * p
        return round(max(0.0, min(1.0, prob)), 4)

    @staticmethod
    def compute_systemic_risk_score(metrics: list[dict]) -> float:
        """聚合系统性风险评分（0-100）。

        Parameters
        ----------
        metrics : list[dict]
            传染风险指标列表，每个包含 covar_95, conditional_correlation,
            tail_beta, systemic_contribution

        Returns
        -------
        float
            系统性风险综合评分 [0, 100]
        """
        if not metrics:
            return 0.0

        # 各维度加权
        covar_scores = []
        corr_scores = []
        beta_scores = []

        for m in metrics:
            covar = abs(m.get("covar_95") or 0.0)
            cond_corr = abs(m.get("conditional_correlation") or 0.0)
            tail_beta = abs(m.get("tail_beta") or 0.0)

            # CoVaR 归一化：假设 -0.1 为极端
            covar_scores.append(min(covar / 0.1, 1.0))
            # 条件相关性已在 [0, 1]
            corr_scores.append(min(cond_corr, 1.0))
            # 尾部 Beta 归一化：假设 3.0 为极端
            beta_scores.append(min(tail_beta / 3.0, 1.0))

        avg_covar = sum(covar_scores) / len(covar_scores)
        avg_corr = sum(corr_scores) / len(corr_scores)
        avg_beta = sum(beta_scores) / len(beta_scores)

        # 加权聚合
        score = (avg_covar * 0.4 + avg_corr * 0.3 + avg_beta * 0.3) * 100.0
        return round(max(0.0, min(100.0, score)), 2)
