"""深度 regime 计算引擎：盘口深度结构分类、墙位持续性、滑点曲线、深度价格背离。"""

from __future__ import annotations


class DepthRegimeCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def classify_regime(
        bid_depth: float, ask_depth: float, imbalance: float
    ) -> str:
        """根据盘口深度和失衡度分类 regime。

        Parameters
        ----------
        bid_depth : float
            买盘总深度（USD）
        ask_depth : float
            卖盘总深度（USD）
        imbalance : float
            深度失衡度（bid-ask 比值偏离 1 的程度）

        Returns
        -------
        str
            "thick" / "thin" / "asymmetric" / "vacuum"
        """
        total_depth = bid_depth + ask_depth
        if total_depth <= 0:
            return "vacuum"

        # 极薄盘口阈值（总深度低于 50K USD）
        if total_depth < 50_000:
            return "vacuum"

        # 薄盘口阈值（总深度低于 500K USD）
        if total_depth < 500_000:
            return "thin"

        # 失衡检测：bid/ask 比值偏离过大
        if abs(imbalance) > 0.4:
            return "asymmetric"

        return "thick"

    @staticmethod
    def compute_wall_strength(
        wall_size: float, avg_level_size: float, persistence_count: int
    ) -> float:
        """计算挂单墙强度。

        综合墙体大小相对于平均档位和持续出现次数。

        Parameters
        ----------
        wall_size : float
            墙体挂单量（USD）
        avg_level_size : float
            平均每档挂单量（USD）
        persistence_count : int
            墙体在快照中持续出现的次数

        Returns
        -------
        float
            墙强度 [0, 100]
        """
        if avg_level_size <= 0:
            return 0.0

        # 大小因子：墙体相对于平均档位的倍数，5x 为满分
        size_ratio = wall_size / avg_level_size
        size_score = min(50.0, size_ratio / 5.0 * 50.0)

        # 持续性因子：出现 10 次以上为满分
        persist_score = min(50.0, persistence_count / 10.0 * 50.0)

        strength = size_score + persist_score
        return round(max(0.0, min(100.0, strength)), 2)

    @staticmethod
    def estimate_slippage(
        amount_usd: float, depth_levels: list[tuple[float, float]]
    ) -> float:
        """预估给定下单量的滑点。

        逐档消耗盘口深度计算平均成交价偏离。

        Parameters
        ----------
        amount_usd : float
            下单量（USD）
        depth_levels : list[tuple[float, float]]
            盘口档位列表 [(price, size_usd), ...]，按价格排序

        Returns
        -------
        float
            预估滑点百分比（如 0.15 表示 0.15%）
        """
        if not depth_levels or amount_usd <= 0:
            return 0.0

        remaining = amount_usd
        total_cost = 0.0
        base_price = depth_levels[0][0]

        if base_price <= 0:
            return 0.0

        for price, size_usd in depth_levels:
            if remaining <= 0:
                break
            fill = min(remaining, size_usd)
            total_cost += fill * price / base_price
            remaining -= fill

        if remaining > 0:
            # 剩余部分假设 5% 滑点
            total_cost += remaining * 1.05
            filled = amount_usd
        else:
            filled = amount_usd

        if filled <= 0:
            return 0.0

        avg_price_ratio = total_cost / filled
        slippage_pct = (avg_price_ratio - 1.0) * 100.0
        return round(max(0.0, slippage_pct), 4)

    @staticmethod
    def compute_depth_price_divergence(
        depth_change: float, price_change: float
    ) -> float:
        """计算深度变化与价格变化的背离度。

        当深度下降但价格上涨时，可能预示虚假突破。

        Parameters
        ----------
        depth_change : float
            深度变化率（如 -0.2 表示深度下降 20%）
        price_change : float
            价格变化率（如 0.05 表示价格上涨 5%）

        Returns
        -------
        float
            背离度 [-1, 1]，正值表示深度减少+价格上涨（看空信号）
        """
        # 背离 = 价格方向与深度方向相反的程度
        if depth_change == 0 and price_change == 0:
            return 0.0

        # 负深度变化 + 正价格变化 = 正背离（bearish）
        # 正深度变化 + 负价格变化 = 负背离（bullish divergence）
        divergence = -depth_change * price_change

        # 归一化到 [-1, 1]
        normalized = max(-1.0, min(1.0, divergence * 10.0))
        return round(normalized, 6)
