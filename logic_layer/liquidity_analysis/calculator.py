"""liquidity_analysis 流动性计算器。"""

import math


class LiquidityCalculator:
    """流动性指标计算器。

    核心计算：
    1. 滑点曲线建模：基于订单簿深度估算不同规模订单的滑点
    2. 流动性评分：综合 spread、深度、滑点的加权评分
    3. 流动性预警：检测流动性异常下降
    """

    # 滑点计算的订单规模档位（USD）
    ORDER_SIZES = [10_000, 100_000, 1_000_000]

    # 流动性评分权重
    SCORE_WEIGHTS = {
        "spread": 0.3,       # spread 越小越好
        "depth": 0.4,        # 深度越大越好
        "balance": 0.3,      # 买卖平衡度
    }

    # 预警阈值
    SPREAD_WARNING_BPS = 20      # spread > 20bps 预警
    SPREAD_CRITICAL_BPS = 50     # spread > 50bps 严重
    DEPTH_DROP_PCT = 0.5         # 深度下降 50% 预警
    IMBALANCE_THRESHOLD = 3.0    # 买卖比 > 3:1 或 < 1:3

    def compute_spread_bps(self, best_bid: float, best_ask: float) -> float:
        """计算 bid-ask spread（basis points）。"""
        if best_bid <= 0 or best_ask <= 0:
            return 0.0
        mid = (best_bid + best_ask) / 2
        spread = (best_ask - best_bid) / mid * 10000
        return round(spread, 2)

    def estimate_slippage(self, order_size_usd: float, depth_levels: list[tuple[float, float]]) -> float:
        """估算给定订单规模的滑点（bps）。

        depth_levels: [(price, quantity_usd), ...] 按价格排序的订单簿层级
        """
        if not depth_levels or order_size_usd <= 0:
            return 0.0

        mid_price = depth_levels[0][0]
        filled = 0.0
        cost = 0.0

        for price, qty_usd in depth_levels:
            remaining = order_size_usd - filled
            if remaining <= 0:
                break
            fill_amount = min(remaining, qty_usd)
            cost += fill_amount * price
            filled += fill_amount

        if filled <= 0:
            return 999.0  # 无法成交

        avg_price = cost / filled
        slippage_bps = abs(avg_price - mid_price) / mid_price * 10000
        return round(slippage_bps, 2)

    def compute_liquidity_score(self, spread_bps: float, bid_depth_usd: float,
                                 ask_depth_usd: float) -> float:
        """计算综合流动性评分（0~100）。"""
        # Spread 分数：0bps=100, 50bps=0
        spread_score = max(0, 100 - spread_bps * 2)

        # 深度分数：基于总深度（$10M=100, $100K=20）
        total_depth = bid_depth_usd + ask_depth_usd
        depth_score = min(100, math.log10(max(total_depth, 1)) / math.log10(10_000_000) * 100)

        # 平衡度分数：完美平衡=100
        if bid_depth_usd > 0 and ask_depth_usd > 0:
            ratio = min(bid_depth_usd, ask_depth_usd) / max(bid_depth_usd, ask_depth_usd)
            balance_score = ratio * 100
        else:
            balance_score = 0

        score = (
            self.SCORE_WEIGHTS["spread"] * spread_score +
            self.SCORE_WEIGHTS["depth"] * depth_score +
            self.SCORE_WEIGHTS["balance"] * balance_score
        )
        return round(min(100, max(0, score)), 1)

    def detect_alerts(self, entity_key: str, spread_bps: float,
                      bid_depth_usd: float, ask_depth_usd: float,
                      historical_depth: float = 0) -> list[dict]:
        """检测流动性预警。"""
        alerts = []

        # Spread 预警
        if spread_bps >= self.SPREAD_CRITICAL_BPS:
            alerts.append({
                "alert_type": "spread_blow",
                "severity": "critical",
                "current_value": spread_bps,
                "normal_value": 5.0,
                "description": f"Spread 异常放大至 {spread_bps:.1f}bps",
            })
        elif spread_bps >= self.SPREAD_WARNING_BPS:
            alerts.append({
                "alert_type": "spread_blow",
                "severity": "warning",
                "current_value": spread_bps,
                "normal_value": 5.0,
                "description": f"Spread 偏高 {spread_bps:.1f}bps",
            })

        # 深度下降预警
        total_depth = bid_depth_usd + ask_depth_usd
        if historical_depth > 0 and total_depth < historical_depth * (1 - self.DEPTH_DROP_PCT):
            alerts.append({
                "alert_type": "depth_drop",
                "severity": "critical" if total_depth < historical_depth * 0.3 else "warning",
                "current_value": total_depth,
                "normal_value": historical_depth,
                "description": f"订单簿深度下降 {(1 - total_depth/historical_depth)*100:.0f}%",
            })

        # 买卖失衡预警
        if bid_depth_usd > 0 and ask_depth_usd > 0:
            ratio = max(bid_depth_usd, ask_depth_usd) / min(bid_depth_usd, ask_depth_usd)
            if ratio >= self.IMBALANCE_THRESHOLD:
                side = "买盘" if bid_depth_usd > ask_depth_usd else "卖盘"
                alerts.append({
                    "alert_type": "imbalance",
                    "severity": "warning",
                    "current_value": ratio,
                    "normal_value": 1.5,
                    "description": f"订单簿{side}偏重，比率 {ratio:.1f}:1",
                })

        # 薄订单簿预警
        if total_depth < 100_000:
            alerts.append({
                "alert_type": "thin_book",
                "severity": "critical",
                "current_value": total_depth,
                "normal_value": 500_000,
                "description": f"订单簿极薄，总深度仅 ${total_depth:,.0f}",
            })

        return alerts
