"""清算级联计算引擎：聚集区识别、级联概率、热力图、链式清算估算。"""

from __future__ import annotations

import math


class LiquidationCascadeCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_liquidation_clusters(
        positions: list[dict],
        current_price: float,
        bins: int = 20,
    ) -> list[dict]:
        """将仓位按清算价格分组为聚集区。

        Parameters
        ----------
        positions : list[dict]
            仓位列表，每个包含 liquidation_price, size_usd, leverage, direction
        current_price : float
            当前市场价格
        bins : int
            分箱数量

        Returns
        -------
        list[dict]
            聚集区列表，包含 price_level, total_size_usd, leverage_avg,
            distance_pct, direction
        """
        if not positions or current_price <= 0:
            return []

        # 按方向分组
        longs = [p for p in positions if p.get("direction") == "long"]
        shorts = [p for p in positions if p.get("direction") == "short"]

        clusters: list[dict] = []
        for direction, group in [("long", longs), ("short", shorts)]:
            if not group:
                continue
            # 获取清算价格范围
            liq_prices = [
                float(p["liquidation_price"]) for p in group
                if p.get("liquidation_price") and float(p["liquidation_price"]) > 0
            ]
            if not liq_prices:
                continue

            min_p = min(liq_prices)
            max_p = max(liq_prices)
            if max_p == min_p:
                # 所有清算价格相同，单一聚集区
                total_size = sum(float(p.get("size_usd", 0)) for p in group)
                leverages = [float(p.get("leverage", 1)) for p in group]
                avg_lev = sum(leverages) / len(leverages)
                dist = abs(min_p - current_price) / current_price * 100.0
                clusters.append({
                    "price_level": round(min_p, 2),
                    "total_size_usd": round(total_size, 2),
                    "leverage_avg": round(avg_lev, 2),
                    "distance_pct": round(dist, 4),
                    "direction": direction,
                })
                continue

            # 分箱
            bin_width = (max_p - min_p) / bins
            for i in range(bins):
                bin_low = min_p + i * bin_width
                bin_high = bin_low + bin_width
                bin_positions = [
                    p for p in group
                    if bin_low <= float(p["liquidation_price"]) < bin_high
                ]
                if not bin_positions:
                    continue
                total_size = sum(
                    float(p.get("size_usd", 0)) for p in bin_positions
                )
                leverages = [
                    float(p.get("leverage", 1)) for p in bin_positions
                ]
                avg_lev = sum(leverages) / len(leverages)
                mid_price = (bin_low + bin_high) / 2.0
                dist = abs(mid_price - current_price) / current_price * 100.0
                clusters.append({
                    "price_level": round(mid_price, 2),
                    "total_size_usd": round(total_size, 2),
                    "leverage_avg": round(avg_lev, 2),
                    "distance_pct": round(dist, 4),
                    "direction": direction,
                })

        # 按距离排序（最近的优先）
        clusters.sort(key=lambda c: c["distance_pct"])
        return clusters

    @staticmethod
    def compute_cascade_probability(
        cluster_size_usd: float,
        daily_volume_usd: float,
        distance_pct: float,
    ) -> float:
        """计算级联清算触发概率。

        基于聚集区规模与日成交量的比值以及距离当前价格的远近。

        Parameters
        ----------
        cluster_size_usd : float
            聚集区清算量（USD）
        daily_volume_usd : float
            日成交量（USD）
        distance_pct : float
            距当前价格的百分比距离

        Returns
        -------
        float
            级联概率 [0, 1]
        """
        if daily_volume_usd <= 0 or distance_pct < 0:
            return 0.0

        # 规模因子：清算量占日成交量比例越大，影响越大
        size_ratio = cluster_size_usd / daily_volume_usd
        size_factor = min(size_ratio / 0.1, 1.0)  # 10% 日成交量为满分

        # 距离因子：越近概率越高（指数衰减）
        distance_factor = math.exp(-distance_pct / 3.0)

        # 综合概率
        prob = size_factor * 0.6 + distance_factor * 0.4
        return round(max(0.0, min(1.0, prob)), 4)

    @staticmethod
    def compute_cascade_severity(
        cascade_prob: float,
        cluster_size_usd: float,
        open_interest_usd: float,
    ) -> str:
        """根据级联概率和规模判定严重程度。

        Parameters
        ----------
        cascade_prob : float
            级联概率 [0, 1]
        cluster_size_usd : float
            聚集区清算量（USD）
        open_interest_usd : float
            未平仓合约总量（USD）

        Returns
        -------
        str
            "critical" / "high" / "medium" / "low"
        """
        if open_interest_usd <= 0:
            return "low"

        # 清算量占 OI 比例
        oi_ratio = cluster_size_usd / open_interest_usd

        # 综合评分 = 概率 * 影响力
        score = cascade_prob * 0.5 + min(oi_ratio / 0.05, 1.0) * 0.5

        if score >= 0.75:
            return "critical"
        elif score >= 0.50:
            return "high"
        elif score >= 0.25:
            return "medium"
        else:
            return "low"

    @staticmethod
    def compute_heatmap(
        positions: list[dict],
        current_price: float,
        range_pct: float = 10.0,
        bins: int = 20,
    ) -> list[dict]:
        """生成价格区间清算密度热力图。

        Parameters
        ----------
        positions : list[dict]
            仓位列表，每个包含 liquidation_price, size_usd, direction
        current_price : float
            当前市场价格
        range_pct : float
            上下价格范围百分比（默认 10%）
        bins : int
            分箱数量

        Returns
        -------
        list[dict]
            热力图数据，包含 price_from, price_to, long_liq_usd,
            short_liq_usd, net_pressure
        """
        if not positions or current_price <= 0:
            return []

        price_low = current_price * (1.0 - range_pct / 100.0)
        price_high = current_price * (1.0 + range_pct / 100.0)
        bin_width = (price_high - price_low) / bins

        heatmap: list[dict] = []
        for i in range(bins):
            bin_from = price_low + i * bin_width
            bin_to = bin_from + bin_width

            long_usd = 0.0
            short_usd = 0.0
            for p in positions:
                liq_price = float(p.get("liquidation_price", 0))
                if liq_price <= 0:
                    continue
                if bin_from <= liq_price < bin_to:
                    size = float(p.get("size_usd", 0))
                    if p.get("direction") == "long":
                        long_usd += size
                    else:
                        short_usd += size

            net = long_usd - short_usd
            heatmap.append({
                "price_from": round(bin_from, 2),
                "price_to": round(bin_to, 2),
                "long_liq_usd": round(long_usd, 2),
                "short_liq_usd": round(short_usd, 2),
                "net_pressure": round(net, 2),
            })

        return heatmap

    @staticmethod
    def estimate_cascade_chain(
        clusters: list[dict],
        initial_liquidation_usd: float,
    ) -> float:
        """估算链式清算总规模。

        每次清算产生的市场冲击可能触发相邻聚集区的进一步清算，
        使用衰减因子模拟级联传播。

        Parameters
        ----------
        clusters : list[dict]
            按距离排序的聚集区列表，包含 total_size_usd, distance_pct
        initial_liquidation_usd : float
            初始清算金额

        Returns
        -------
        float
            预估级联清算总金额（USD）
        """
        if not clusters or initial_liquidation_usd <= 0:
            return 0.0

        total = initial_liquidation_usd
        current_impact = initial_liquidation_usd

        # 按距离排序，逐层传播
        sorted_clusters = sorted(clusters, key=lambda c: c.get("distance_pct", 0))

        for cluster in sorted_clusters:
            cluster_size = float(cluster.get("total_size_usd", 0))
            distance = float(cluster.get("distance_pct", 100))

            if cluster_size <= 0 or distance <= 0:
                continue

            # 衰减因子：距离越远，触发比例越低
            trigger_ratio = math.exp(-distance / 2.0)
            # 当前冲击能触发的比例
            impact_ratio = min(current_impact / cluster_size, 1.0)
            triggered = cluster_size * trigger_ratio * impact_ratio

            if triggered < cluster_size * 0.01:
                # 触发量不足 1%，级联终止
                break

            total += triggered
            # 新触发的清算成为下一层的冲击源（衰减 50%）
            current_impact = triggered * 0.5

        return round(total, 2)
