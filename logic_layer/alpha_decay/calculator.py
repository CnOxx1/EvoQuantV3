"""信号衰减计算引擎：半衰期、自相关、拥挤度、信号惊奇度。"""

from __future__ import annotations

import math


class AlphaDecayCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_autocorrelation(values: list[float], lag: int = 1) -> float:
        """计算时间序列的自相关系数。

        Parameters
        ----------
        values : list[float]
            信号值序列
        lag : int
            滞后期数，默认1

        Returns
        -------
        float
            自相关系数 [-1, 1]
        """
        n = len(values)
        if n < lag + 2:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        if variance == 0:
            return 0.0
        covariance = sum(
            (values[i] - mean) * (values[i - lag] - mean)
            for i in range(lag, n)
        ) / (n - lag)
        return max(-1.0, min(1.0, covariance / variance))

    @staticmethod
    def compute_half_life(signal_values: list[float]) -> float:
        """通过自相关衰减计算信号半衰期（小时）。

        Parameters
        ----------
        signal_values : list[float]
            信号值时间序列（每小时采样）

        Returns
        -------
        float
            半衰期（小时），自相关衰减到0.5所需时间
        """
        n = len(signal_values)
        if n < 4:
            return 0.0

        # 逐步增加 lag，找到自相关首次低于 0.5 的位置
        for lag in range(1, n // 2):
            ac = AlphaDecayCalculator.compute_autocorrelation(signal_values, lag)
            if ac <= 0.5:
                # 线性插值估算精确半衰期
                if lag == 1:
                    return float(lag)
                prev_ac = AlphaDecayCalculator.compute_autocorrelation(
                    signal_values, lag - 1
                )
                if prev_ac == ac:
                    return float(lag)
                fraction = (prev_ac - 0.5) / (prev_ac - ac)
                return round((lag - 1) + fraction, 2)
        # 自相关始终高于 0.5，返回最大检测窗口
        return float(n // 2)

    @staticmethod
    def compute_crowding_score(signals: list[dict]) -> dict:
        """计算信号拥挤度。

        Parameters
        ----------
        signals : list[dict]
            信号列表，每个 dict 包含 signal_name, direction (+1/-1), strength

        Returns
        -------
        dict
            包含 crowding_score, agreeing_signals, disagreeing_signals,
            contrarian_signal
        """
        if not signals:
            return {
                "crowding_score": 0.0,
                "agreeing_signals": 0,
                "disagreeing_signals": 0,
                "contrarian_signal": "",
            }

        # 统计方向一致性
        directions = [s.get("direction", 0) for s in signals]
        bullish = sum(1 for d in directions if d > 0)
        bearish = sum(1 for d in directions if d < 0)
        total = len(signals)

        # 多数方向
        majority = max(bullish, bearish)
        minority = min(bullish, bearish)
        agreeing = majority
        disagreeing = minority

        # 拥挤度分数：多数方向占比 * 100
        crowding_score = round((majority / total) * 100, 2) if total > 0 else 0.0

        # 找到最强反向信号
        majority_dir = 1 if bullish >= bearish else -1
        contrarian_signals = [
            s for s in signals if s.get("direction", 0) == -majority_dir
        ]
        contrarian_signal = ""
        if contrarian_signals:
            contrarian_signals.sort(
                key=lambda x: abs(x.get("strength", 0)), reverse=True
            )
            contrarian_signal = contrarian_signals[0].get("signal_name", "")

        return {
            "crowding_score": crowding_score,
            "agreeing_signals": agreeing,
            "disagreeing_signals": disagreeing,
            "contrarian_signal": contrarian_signal,
        }

    @staticmethod
    def compute_signal_surprise(
        current_value: float, history: list[float]
    ) -> float:
        """计算信号惊奇度（z-score）。

        Parameters
        ----------
        current_value : float
            当前信号值
        history : list[float]
            历史信号值序列

        Returns
        -------
        float
            z-score，衡量当前值相对历史的异常程度
        """
        if not history or len(history) < 2:
            return 0.0
        mean = sum(history) / len(history)
        variance = sum((v - mean) ** 2 for v in history) / len(history)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std == 0:
            return 0.0
        return round((current_value - mean) / std, 4)

    @staticmethod
    def detect_divergence(signals: list[dict]) -> list[dict]:
        """检测方向相反的信号对。

        Parameters
        ----------
        signals : list[dict]
            信号列表，每个 dict 包含 signal_name, direction (+1/-1), strength

        Returns
        -------
        list[dict]
            方向相反的信号对列表
        """
        if len(signals) < 2:
            return []

        divergences = []
        for i in range(len(signals)):
            for j in range(i + 1, len(signals)):
                dir_i = signals[i].get("direction", 0)
                dir_j = signals[j].get("direction", 0)
                if dir_i != 0 and dir_j != 0 and dir_i != dir_j:
                    divergences.append({
                        "signal_a": signals[i].get("signal_name", ""),
                        "signal_b": signals[j].get("signal_name", ""),
                        "direction_a": dir_i,
                        "direction_b": dir_j,
                        "strength_a": signals[i].get("strength", 0),
                        "strength_b": signals[j].get("strength", 0),
                    })
        return divergences
