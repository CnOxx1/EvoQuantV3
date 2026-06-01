"""跨场所套利计算引擎：价差检测、持续性分析、市场效率评分。"""

from __future__ import annotations

import math
from itertools import combinations


class CrossVenueArbCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_spread_bps(price_a: float, price_b: float) -> float:
        """计算两个价格之间的基点价差。

        Parameters
        ----------
        price_a : float
            场所 A 的价格
        price_b : float
            场所 B 的价格

        Returns
        -------
        float
            基点价差（绝对值）
        """
        if price_a <= 0 or price_b <= 0:
            return 0.0
        mid = (price_a + price_b) / 2.0
        spread = abs(price_a - price_b) / mid * 10000.0
        return round(spread, 4)

    @staticmethod
    def detect_arbitrage(
        prices: list[dict], min_spread_bps: float = 5.0
    ) -> list[dict]:
        """检测所有场所对之间超过阈值的套利机会。

        Parameters
        ----------
        prices : list[dict]
            每个元素包含 venue, price 字段
        min_spread_bps : float
            最小价差阈值（基点），默认 5.0

        Returns
        -------
        list[dict]
            检测到的套利机会列表
        """
        if len(prices) < 2:
            return []

        opportunities = []
        for i, j in combinations(range(len(prices)), 2):
            p_a = prices[i]
            p_b = prices[j]
            price_a = p_a.get("price", 0.0)
            price_b = p_b.get("price", 0.0)
            if price_a <= 0 or price_b <= 0:
                continue

            mid = (price_a + price_b) / 2.0
            spread_bps = abs(price_a - price_b) / mid * 10000.0

            if spread_bps >= min_spread_bps:
                # 确定买卖方向
                if price_a < price_b:
                    venue_buy, venue_sell = p_a["venue"], p_b["venue"]
                    pb, ps = price_a, price_b
                else:
                    venue_buy, venue_sell = p_b["venue"], p_a["venue"]
                    pb, ps = price_b, price_a

                opportunities.append({
                    "venue_buy": venue_buy,
                    "venue_sell": venue_sell,
                    "price_buy": round(pb, 6),
                    "price_sell": round(ps, 6),
                    "spread_bps": round(spread_bps, 4),
                })
        return opportunities

    @staticmethod
    def compute_persistence(
        spreads_history: list[dict], window_minutes: int = 60
    ) -> list[dict]:
        """分析套利机会的持续性。

        Parameters
        ----------
        spreads_history : list[dict]
            历史价差记录，每个包含 venue_pair, spread_bps, timestamp_epoch
        window_minutes : int
            分析窗口（分钟），默认 60

        Returns
        -------
        list[dict]
            每个场所对的持续性指标
        """
        if not spreads_history:
            return []

        # 按 venue_pair 分组
        grouped: dict[str, list[dict]] = {}
        for entry in spreads_history:
            pair = entry.get("venue_pair", "")
            grouped.setdefault(pair, []).append(entry)

        results = []
        window_seconds = window_minutes * 60

        for venue_pair, entries in grouped.items():
            if len(entries) < 2:
                continue

            # 按时间排序
            sorted_entries = sorted(
                entries, key=lambda x: x.get("timestamp_epoch", 0)
            )

            # 计算平均价差
            spreads = [e.get("spread_bps", 0.0) for e in sorted_entries]
            avg_spread = sum(spreads) / len(spreads) if spreads else 0.0

            # 计算持续时间（首尾时间差）
            t_first = sorted_entries[0].get("timestamp_epoch", 0)
            t_last = sorted_entries[-1].get("timestamp_epoch", 0)
            duration = t_last - t_first

            # 计算频率（每小时出现次数）
            if window_seconds > 0:
                frequency = len(sorted_entries) / (window_seconds / 3600.0)
            else:
                frequency = 0.0

            results.append({
                "venue_pair": venue_pair,
                "avg_spread_bps": round(avg_spread, 4),
                "duration_seconds": int(duration),
                "frequency_per_hour": round(frequency, 4),
            })

        return results

    @staticmethod
    def compute_venue_correlation(
        prices_a: list[float], prices_b: list[float]
    ) -> float:
        """计算两个场所价格序列的相关性。

        Parameters
        ----------
        prices_a : list[float]
            场所 A 的价格序列
        prices_b : list[float]
            场所 B 的价格序列

        Returns
        -------
        float
            皮尔逊相关系数 [-1, 1]
        """
        n = min(len(prices_a), len(prices_b))
        if n < 5:
            return 0.0

        pa = prices_a[:n]
        pb = prices_b[:n]

        mean_a = sum(pa) / n
        mean_b = sum(pb) / n

        var_a = sum((x - mean_a) ** 2 for x in pa) / (n - 1)
        var_b = sum((x - mean_b) ** 2 for x in pb) / (n - 1)
        std_a = math.sqrt(var_a) if var_a > 0 else 0.0
        std_b = math.sqrt(var_b) if var_b > 0 else 0.0

        if std_a == 0 or std_b == 0:
            return 0.0

        cov = sum(
            (pa[i] - mean_a) * (pb[i] - mean_b) for i in range(n)
        ) / (n - 1)
        corr = cov / (std_a * std_b)
        return round(max(-1.0, min(1.0, corr)), 4)

    @staticmethod
    def estimate_profit(
        spread_bps: float, volume_usd: float, fee_bps: float = 2.0
    ) -> float:
        """估算扣除手续费后的净利润。

        Parameters
        ----------
        spread_bps : float
            价差（基点）
        volume_usd : float
            交易量（美元）
        fee_bps : float
            单边手续费（基点），默认 2.0

        Returns
        -------
        float
            净利润（美元）
        """
        if spread_bps <= 0 or volume_usd <= 0:
            return 0.0
        # 双边手续费
        total_fee_bps = fee_bps * 2.0
        net_spread_bps = spread_bps - total_fee_bps
        if net_spread_bps <= 0:
            return 0.0
        profit = volume_usd * (net_spread_bps / 10000.0)
        return round(profit, 2)

    @staticmethod
    def compute_market_efficiency_score(
        arb_opportunities: list[dict],
    ) -> float:
        """计算市场效率评分。

        评分范围 0-100，100 表示完全有效（无套利机会）。

        Parameters
        ----------
        arb_opportunities : list[dict]
            当前检测到的套利机会列表，每个包含 spread_bps 字段

        Returns
        -------
        float
            市场效率评分 [0, 100]
        """
        if not arb_opportunities:
            return 100.0

        # 基于套利机会数量和平均价差计算效率损失
        count = len(arb_opportunities)
        spreads = [
            abs(o.get("spread_bps", 0.0)) for o in arb_opportunities
        ]
        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        max_spread = max(spreads) if spreads else 0.0

        # 数量惩罚：每个机会扣 5 分，上限 50 分
        count_penalty = min(count * 5.0, 50.0)
        # 价差惩罚：平均价差每 10bps 扣 10 分，上限 30 分
        spread_penalty = min(avg_spread / 10.0 * 10.0, 30.0)
        # 极端价差惩罚：最大价差超过 50bps 额外扣分
        extreme_penalty = min(max(max_spread - 50.0, 0.0) / 10.0 * 5.0, 20.0)

        score = 100.0 - count_penalty - spread_penalty - extreme_penalty
        return round(max(0.0, min(100.0, score)), 2)
