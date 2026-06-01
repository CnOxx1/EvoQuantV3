"""链上领先-滞后计算引擎：互相关、最优滞后、Granger 因果、预测力。"""

from __future__ import annotations

import math


class OnchainLeadLagCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_cross_correlation(
        signal_series: list[float],
        price_series: list[float],
        max_lag: int = 24,
    ) -> list[dict]:
        """计算信号序列与价格序列在各滞后期的互相关系数。

        Parameters
        ----------
        signal_series : list[float]
            链上信号时间序列
        price_series : list[float]
            价格收益率时间序列
        max_lag : int
            最大滞后期数（小时）

        Returns
        -------
        list[dict]
            每个滞后期的 {"lag": int, "correlation": float}
        """
        n = min(len(signal_series), len(price_series))
        if n < 10:
            return []

        sig = signal_series[:n]
        prc = price_series[:n]

        # 计算均值和标准差
        mean_s = sum(sig) / n
        mean_p = sum(prc) / n
        std_s = math.sqrt(sum((x - mean_s) ** 2 for x in sig) / (n - 1))
        std_p = math.sqrt(sum((x - mean_p) ** 2 for x in prc) / (n - 1))

        if std_s == 0 or std_p == 0:
            return []

        results = []
        for lag in range(-max_lag, max_lag + 1):
            # 正 lag 表示信号领先价格 lag 期
            if lag >= 0:
                s_slice = sig[:n - lag] if lag > 0 else sig
                p_slice = prc[lag:] if lag > 0 else prc
            else:
                s_slice = sig[-lag:]
                p_slice = prc[:n + lag]

            m = len(s_slice)
            if m < 5:
                continue

            ms = sum(s_slice) / m
            mp = sum(p_slice) / m
            cov = sum(
                (s_slice[i] - ms) * (p_slice[i] - mp) for i in range(m)
            ) / (m - 1)
            vs = sum((x - ms) ** 2 for x in s_slice) / (m - 1)
            vp = sum((x - mp) ** 2 for x in p_slice) / (m - 1)
            ds = math.sqrt(vs) if vs > 0 else 0.0
            dp = math.sqrt(vp) if vp > 0 else 0.0

            if ds == 0 or dp == 0:
                corr = 0.0
            else:
                corr = cov / (ds * dp)
                corr = max(-1.0, min(1.0, corr))

            results.append({"lag": lag, "correlation": round(corr, 4)})

        return results

    @staticmethod
    def find_optimal_lag(
        signal_series: list[float],
        price_series: list[float],
        max_lag: int = 24,
    ) -> dict:
        """找到绝对相关性最高的最优滞后期。

        Parameters
        ----------
        signal_series : list[float]
            链上信号时间序列
        price_series : list[float]
            价格收益率时间序列
        max_lag : int
            最大滞后期数

        Returns
        -------
        dict
            {"optimal_lag": int, "correlation": float, "direction": str}
        """
        calc = OnchainLeadLagCalculator()
        cross_corrs = calc.compute_cross_correlation(
            signal_series, price_series, max_lag
        )
        if not cross_corrs:
            return {"optimal_lag": 0, "correlation": 0.0, "direction": "none"}

        best = max(cross_corrs, key=lambda x: abs(x["correlation"]))
        direction = "positive" if best["correlation"] >= 0 else "negative"
        return {
            "optimal_lag": best["lag"],
            "correlation": best["correlation"],
            "direction": direction,
        }

    @staticmethod
    def compute_granger_causality(
        signal_series: list[float],
        price_series: list[float],
        max_lag: int = 6,
    ) -> dict:
        """简化 Granger 因果检验：比较受限模型与非受限模型的拟合优度。

        使用 F 统计量近似判断信号是否 Granger 因果于价格。

        Parameters
        ----------
        signal_series : list[float]
            链上信号时间序列
        price_series : list[float]
            价格收益率时间序列
        max_lag : int
            最大滞后阶数

        Returns
        -------
        dict
            {"f_stat": float, "p_value_approx": float, "significant": bool}
        """
        n = min(len(signal_series), len(price_series))
        if n < max_lag + 10:
            return {"f_stat": 0.0, "p_value_approx": 1.0, "significant": False}

        sig = signal_series[:n]
        prc = price_series[:n]

        # 构建回归数据：y = prc[max_lag:]
        y = prc[max_lag:]
        T = len(y)

        # 受限模型：仅用价格自身滞后预测
        # RSS_r = sum((y_i - y_hat_restricted)^2)
        # 非受限模型：价格滞后 + 信号滞后
        # RSS_u = sum((y_i - y_hat_unrestricted)^2)

        # 简化实现：使用均值回归作为基准
        mean_y = sum(y) / T

        # 受限模型：用价格滞后 1 期的简单线性回归
        x_r = prc[max_lag - 1: n - 1]  # 价格滞后 1 期
        rss_r = OnchainLeadLagCalculator._simple_regression_rss(x_r, y)

        # 非受限模型：用信号滞后 max_lag 期
        x_u = sig[:T]  # 信号对齐
        # 组合预测：价格滞后 + 信号滞后的残差
        rss_u = OnchainLeadLagCalculator._dual_regression_rss(x_r, x_u, y)

        # F 统计量: ((RSS_r - RSS_u) / q) / (RSS_u / (T - k))
        q = max_lag  # 额外参数数量
        k = max_lag + 2  # 非受限模型参数数量

        if rss_u <= 0 or T <= k:
            return {"f_stat": 0.0, "p_value_approx": 1.0, "significant": False}

        f_stat = ((rss_r - rss_u) / q) / (rss_u / (T - k))
        f_stat = max(0.0, f_stat)

        # p 值近似：使用 F 分布的简化近似
        p_value = OnchainLeadLagCalculator._f_distribution_p_approx(
            f_stat, q, T - k
        )

        return {
            "f_stat": round(f_stat, 4),
            "p_value_approx": round(p_value, 4),
            "significant": p_value < 0.05,
        }

    @staticmethod
    def compute_predictive_power(
        signal_series: list[float],
        price_returns: list[float],
        lag: int,
    ) -> float:
        """计算滞后回归的 R-squared，衡量信号对价格的预测力。

        Parameters
        ----------
        signal_series : list[float]
            链上信号时间序列
        price_returns : list[float]
            价格收益率时间序列
        lag : int
            滞后期数（信号领先价格的小时数）

        Returns
        -------
        float
            R-squared [0, 1]
        """
        if lag < 0:
            lag = abs(lag)

        n = min(len(signal_series), len(price_returns))
        if n < lag + 10:
            return 0.0

        # 信号在前，价格在后（信号领先 lag 期）
        x = signal_series[:n - lag]
        y = price_returns[lag:n]
        m = min(len(x), len(y))
        if m < 10:
            return 0.0

        x = x[:m]
        y = y[:m]

        # 简单线性回归 y = a + b*x
        mean_x = sum(x) / m
        mean_y = sum(y) / m

        ss_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(m))
        ss_xx = sum((xi - mean_x) ** 2 for xi in x)
        ss_yy = sum((yi - mean_y) ** 2 for yi in y)

        if ss_xx == 0 or ss_yy == 0:
            return 0.0

        b = ss_xy / ss_xx
        a = mean_y - b * mean_x

        # 计算 R-squared
        ss_res = sum((y[i] - (a + b * x[i])) ** 2 for i in range(m))
        r_squared = 1.0 - (ss_res / ss_yy)
        return round(max(0.0, min(1.0, r_squared)), 4)

    @staticmethod
    def detect_signal_trigger(
        signal_values: list[float],
        threshold_sigma: float = 2.0,
    ) -> bool:
        """检测当前信号值是否超过阈值（均值 + N 倍标准差）。

        Parameters
        ----------
        signal_values : list[float]
            信号历史值序列（最后一个为当前值）
        threshold_sigma : float
            阈值标准差倍数

        Returns
        -------
        bool
            当前值是否超过阈值
        """
        if len(signal_values) < 10:
            return False

        current = signal_values[-1]
        history = signal_values[:-1]

        mean = sum(history) / len(history)
        var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
        std = math.sqrt(var) if var > 0 else 0.0

        if std == 0:
            return False

        z_score = abs(current - mean) / std
        return z_score >= threshold_sigma

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _simple_regression_rss(x: list[float], y: list[float]) -> float:
        """简单线性回归的残差平方和。"""
        m = min(len(x), len(y))
        if m < 3:
            return sum(yi ** 2 for yi in y[:m])

        x = x[:m]
        y = y[:m]
        mean_x = sum(x) / m
        mean_y = sum(y) / m

        ss_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(m))
        ss_xx = sum((xi - mean_x) ** 2 for xi in x)

        if ss_xx == 0:
            return sum((yi - mean_y) ** 2 for yi in y)

        b = ss_xy / ss_xx
        a = mean_y - b * mean_x
        rss = sum((y[i] - (a + b * x[i])) ** 2 for i in range(m))
        return rss

    @staticmethod
    def _dual_regression_rss(
        x1: list[float], x2: list[float], y: list[float]
    ) -> float:
        """双变量线性回归的残差平方和（简化实现）。"""
        m = min(len(x1), len(x2), len(y))
        if m < 5:
            return sum(yi ** 2 for yi in y[:m])

        x1 = x1[:m]
        x2 = x2[:m]
        y = y[:m]

        mean_x1 = sum(x1) / m
        mean_x2 = sum(x2) / m
        mean_y = sum(y) / m

        # 正规方程的简化求解
        s11 = sum((x1[i] - mean_x1) ** 2 for i in range(m))
        s22 = sum((x2[i] - mean_x2) ** 2 for i in range(m))
        s12 = sum(
            (x1[i] - mean_x1) * (x2[i] - mean_x2) for i in range(m)
        )
        s1y = sum((x1[i] - mean_x1) * (y[i] - mean_y) for i in range(m))
        s2y = sum((x2[i] - mean_x2) * (y[i] - mean_y) for i in range(m))

        det = s11 * s22 - s12 * s12
        if abs(det) < 1e-12:
            # 退化为单变量回归
            return OnchainLeadLagCalculator._simple_regression_rss(x1, y)

        b1 = (s22 * s1y - s12 * s2y) / det
        b2 = (s11 * s2y - s12 * s1y) / det
        a = mean_y - b1 * mean_x1 - b2 * mean_x2

        rss = sum(
            (y[i] - (a + b1 * x1[i] + b2 * x2[i])) ** 2 for i in range(m)
        )
        return rss

    @staticmethod
    def _f_distribution_p_approx(f_stat: float, df1: int, df2: int) -> float:
        """F 分布 p 值的简化近似（基于正态近似）。

        使用 Wilson-Hilferty 变换将 F 统计量近似为正态分布。
        """
        if f_stat <= 0 or df1 <= 0 or df2 <= 0:
            return 1.0

        # Wilson-Hilferty 近似
        a = df1
        b = df2
        x = f_stat

        # 变换为近似正态
        num = (x * a / b) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * b))
        den_sq = (2.0 / (9.0 * b)) + (x * a / b) ** (2.0 / 3.0) * (
            2.0 / (9.0 * a)
        )
        if den_sq <= 0:
            return 0.001

        z = num / math.sqrt(den_sq)

        # 标准正态 CDF 的上尾概率
        if z <= 0:
            return 1.0

        # Abramowitz & Stegun 近似
        t = 1.0 / (1.0 + 0.2316419 * z)
        d = 0.3989422804 * math.exp(-z * z / 2.0)
        p = d * t * (
            0.3193815
            + t * (
                -0.3565638
                + t * (1.781478 + t * (-1.821256 + t * 1.330274))
            )
        )
        return round(max(0.0, min(1.0, p)), 4)
