"""稳定币脉冲计算引擎：净铸造脉冲、链迁移方向、expansion/contraction 信号、BTC 相关性。"""

from __future__ import annotations


class StablecoinPulseCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_net_mint_pulse(
        mint_volumes: list[float], burn_volumes: list[float]
    ) -> float:
        """计算 24h 滚动净铸造脉冲（归一化）。

        Parameters
        ----------
        mint_volumes : list[float]
            铸造量序列（24h 滚动窗口内各时段铸造量）
        burn_volumes : list[float]
            销毁量序列（24h 滚动窗口内各时段销毁量）

        Returns
        -------
        float
            净铸造脉冲值，正值表示净铸造扩张，负值表示净销毁收缩
        """
        if not mint_volumes and not burn_volumes:
            return 0.0

        total_mint = sum(mint_volumes) if mint_volumes else 0.0
        total_burn = sum(burn_volumes) if burn_volumes else 0.0
        net = total_mint - total_burn

        # 归一化：以总量为基准
        denominator = total_mint + total_burn
        if denominator == 0:
            return 0.0

        pulse = net / denominator
        return round(pulse, 6)

    @staticmethod
    def classify_expansion_signal(pulse: float) -> str:
        """根据脉冲值分类扩张/收缩信号。

        Parameters
        ----------
        pulse : float
            净铸造脉冲值

        Returns
        -------
        str
            "expansion" / "contraction" / "neutral"
        """
        if pulse > 0.15:
            return "expansion"
        elif pulse < -0.15:
            return "contraction"
        return "neutral"

    @staticmethod
    def compute_chain_migration(chain_flows: dict[str, float]) -> str:
        """计算链迁移主方向（资金流入最大的链）。

        Parameters
        ----------
        chain_flows : dict[str, float]
            各链净流入量，如 {"ethereum": 1.2e9, "tron": -0.5e9, "bsc": 0.3e9}

        Returns
        -------
        str
            资金净流入最大的链名称，无数据时返回 "unknown"
        """
        if not chain_flows:
            return "unknown"

        dominant_chain = max(chain_flows, key=chain_flows.get)
        return dominant_chain

    @staticmethod
    def compute_btc_correlation(
        pulse_series: list[float], btc_returns: list[float]
    ) -> float:
        """计算稳定币脉冲序列与 BTC 收益率的相关系数。

        使用皮尔逊相关系数衡量脉冲信号与 BTC 价格走势的同步性。

        Parameters
        ----------
        pulse_series : list[float]
            稳定币脉冲值时间序列
        btc_returns : list[float]
            BTC 收益率时间序列（与 pulse_series 等长）

        Returns
        -------
        float
            皮尔逊相关系数 [-1, 1]，数据不足时返回 0.0
        """
        n = min(len(pulse_series), len(btc_returns))
        if n < 3:
            return 0.0

        x = pulse_series[:n]
        y = btc_returns[:n]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = (sum((xi - mean_x) ** 2 for xi in x)) ** 0.5
        std_y = (sum((yi - mean_y) ** 2 for yi in y)) ** 0.5

        if std_x == 0 or std_y == 0:
            return 0.0

        correlation = cov / (std_x * std_y)
        return round(max(-1.0, min(1.0, correlation)), 6)
