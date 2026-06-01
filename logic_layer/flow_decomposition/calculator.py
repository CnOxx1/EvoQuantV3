"""流量分解计算引擎：VPIN、流量分类、吸筹/派发检测。"""

from __future__ import annotations

import math
from datetime import datetime, timezone


class FlowDecompositionCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_vpin(trades: list[dict], bucket_size: int = 50) -> float:
        """Volume-synchronized PIN 计算。

        Parameters
        ----------
        trades : list[dict]
            交易列表，每条包含 {"volume": float, "side": "buy"|"sell"}
        bucket_size : int
            每个 bucket 的成交量大小

        Returns
        -------
        float
            VPIN 值 (0~1)，越高表示信息不对称越严重
        """
        if not trades or bucket_size <= 0:
            return 0.0

        # 将交易按 volume bucket 分组
        buckets: list[dict] = []
        current_buy = 0.0
        current_sell = 0.0
        current_volume = 0.0

        for trade in trades:
            vol = abs(float(trade.get("volume", 0)))
            side = trade.get("side", "buy")
            remaining = vol

            while remaining > 0:
                space = bucket_size - current_volume
                fill = min(remaining, space)
                if side == "buy":
                    current_buy += fill
                else:
                    current_sell += fill
                current_volume += fill
                remaining -= fill

                if current_volume >= bucket_size:
                    buckets.append({"buy": current_buy, "sell": current_sell})
                    current_buy = 0.0
                    current_sell = 0.0
                    current_volume = 0.0

        if not buckets:
            return 0.0

        # VPIN = 平均 |buy - sell| / bucket_size
        order_imbalances = [
            abs(b["buy"] - b["sell"]) / bucket_size for b in buckets
        ]
        vpin = sum(order_imbalances) / len(order_imbalances)
        return round(min(1.0, max(0.0, vpin)), 4)

    @staticmethod
    def classify_flow(trades: list[dict]) -> dict:
        """根据交易大小和波动性将流量分为 smart/dumb money。

        Parameters
        ----------
        trades : list[dict]
            交易列表，每条包含 {"volume": float, "side": str, "price": float}

        Returns
        -------
        dict
            {"informed_flow_ratio": float, "retail_flow_ratio": float,
             "smart_money_direction": "buy"|"sell"|"neutral"}
        """
        if not trades:
            return {
                "informed_flow_ratio": 0.0,
                "retail_flow_ratio": 1.0,
                "smart_money_direction": "neutral",
            }

        # 按成交量大小分类：大单为 informed，小单为 retail
        volumes = [abs(float(t.get("volume", 0))) for t in trades]
        if not volumes:
            return {
                "informed_flow_ratio": 0.0,
                "retail_flow_ratio": 1.0,
                "smart_money_direction": "neutral",
            }

        avg_vol = sum(volumes) / len(volumes)
        threshold = avg_vol * 2.0  # 大于均值 2 倍视为大单

        informed_volume = 0.0
        retail_volume = 0.0
        smart_buy = 0.0
        smart_sell = 0.0
        total_volume = sum(volumes)

        for t in trades:
            vol = abs(float(t.get("volume", 0)))
            side = t.get("side", "buy")
            if vol >= threshold:
                informed_volume += vol
                if side == "buy":
                    smart_buy += vol
                else:
                    smart_sell += vol
            else:
                retail_volume += vol

        informed_ratio = informed_volume / total_volume if total_volume > 0 else 0.0
        retail_ratio = retail_volume / total_volume if total_volume > 0 else 1.0

        if smart_buy > smart_sell * 1.2:
            direction = "buy"
        elif smart_sell > smart_buy * 1.2:
            direction = "sell"
        else:
            direction = "neutral"

        return {
            "informed_flow_ratio": round(informed_ratio, 4),
            "retail_flow_ratio": round(retail_ratio, 4),
            "smart_money_direction": direction,
        }

    @staticmethod
    def detect_accumulation_distribution(
        net_flows: list[float], cvd_trend: float
    ) -> dict:
        """检测吸筹/派发阶段。

        Parameters
        ----------
        net_flows : list[float]
            净流量序列（正=买入主导，负=卖出主导）
        cvd_trend : float
            CVD 趋势斜率（正=累积买入，负=累积卖出）

        Returns
        -------
        dict
            {"accumulation_phase": int, "distribution_phase": int}
        """
        if not net_flows:
            return {"accumulation_phase": 0, "distribution_phase": 0}

        avg_flow = sum(net_flows) / len(net_flows)

        # 吸筹：净流入为正且 CVD 上升
        accumulation = 1 if (avg_flow > 0 and cvd_trend > 0) else 0
        # 派发：净流出为负且 CVD 下降
        distribution = 1 if (avg_flow < 0 and cvd_trend < 0) else 0

        return {
            "accumulation_phase": accumulation,
            "distribution_phase": distribution,
        }

    @staticmethod
    def compute_vpin_percentile(
        current_vpin: float, history: list[float]
    ) -> float:
        """计算当前 VPIN 在历史分布中的百分位。

        Parameters
        ----------
        current_vpin : float
            当前 VPIN 值
        history : list[float]
            历史 VPIN 值列表

        Returns
        -------
        float
            百分位 (0~100)
        """
        if not history:
            return 50.0
        count_below = sum(1 for v in history if v <= current_vpin)
        percentile = (count_below / len(history)) * 100.0
        return round(percentile, 2)
