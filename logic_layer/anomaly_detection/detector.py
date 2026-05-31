"""anomaly_detection 检测器。"""

import math
import statistics


class AnomalyDetector:
    """统计异常检测器。

    检测维度：
    1. 价格异动：收益率 z-score 超阈值
    2. 成交量突变：成交量 z-score 超阈值
    3. 相关性崩塌：滚动相关性突变
    4. 价差异常：bid-ask spread 异常放大
    5. 资金费率极值：funding rate 超历史极值
    """

    # z-score 阈值
    ZSCORE_WARNING = 2.5
    ZSCORE_CRITICAL = 3.5

    # 各类型特定阈值
    PRICE_SPIKE_PCT = 0.05       # 5% 瞬间涨跌
    VOLUME_SURGE_MULT = 3.0      # 成交量 3x 均值
    CORRELATION_BREAK = 0.4      # 相关性变化 > 0.4
    FUNDING_EXTREME = 0.001      # funding rate > 0.1%

    def detect_price_anomaly(self, returns: list[float]) -> list[dict]:
        """检测价格异动。"""
        if len(returns) < 20:
            return []

        anomalies = []
        mean = statistics.mean(returns[:-1])
        std = statistics.stdev(returns[:-1]) if len(returns) > 2 else 0.001
        if std == 0:
            std = 0.001

        latest = returns[-1]
        zscore = (latest - mean) / std

        if abs(zscore) >= self.ZSCORE_CRITICAL:
            anomalies.append({
                "type": "price_spike",
                "severity": "critical",
                "score": min(1.0, abs(zscore) / 5.0),
                "metric_name": "return_zscore",
                "metric_value": round(latest, 6),
                "threshold": round(mean + self.ZSCORE_CRITICAL * std, 6),
                "zscore": round(zscore, 4),
                "description": f"价格{'暴涨' if latest > 0 else '暴跌'} {abs(latest)*100:.2f}%，z-score={zscore:.1f}",
            })
        elif abs(zscore) >= self.ZSCORE_WARNING:
            anomalies.append({
                "type": "price_spike",
                "severity": "warning",
                "score": min(0.7, abs(zscore) / 5.0),
                "metric_name": "return_zscore",
                "metric_value": round(latest, 6),
                "threshold": round(mean + self.ZSCORE_WARNING * std, 6),
                "zscore": round(zscore, 4),
                "description": f"价格异动 {latest*100:.2f}%，z-score={zscore:.1f}",
            })

        return anomalies

    def detect_volume_anomaly(self, volumes: list[float]) -> list[dict]:
        """检测成交量突变。"""
        if len(volumes) < 20:
            return []

        anomalies = []
        historical = volumes[:-1]
        mean = statistics.mean(historical)
        std = statistics.stdev(historical) if len(historical) > 2 else mean * 0.3
        if std == 0:
            std = mean * 0.1 or 1

        latest = volumes[-1]
        zscore = (latest - mean) / std
        ratio = latest / mean if mean > 0 else 0

        if ratio >= self.VOLUME_SURGE_MULT * 2:
            anomalies.append({
                "type": "volume_surge",
                "severity": "critical",
                "score": min(1.0, ratio / 10.0),
                "metric_name": "volume_ratio",
                "metric_value": round(ratio, 2),
                "threshold": self.VOLUME_SURGE_MULT * 2,
                "zscore": round(zscore, 4),
                "description": f"成交量激增 {ratio:.1f}x 均值",
            })
        elif ratio >= self.VOLUME_SURGE_MULT:
            anomalies.append({
                "type": "volume_surge",
                "severity": "warning",
                "score": min(0.6, ratio / 10.0),
                "metric_name": "volume_ratio",
                "metric_value": round(ratio, 2),
                "threshold": self.VOLUME_SURGE_MULT,
                "zscore": round(zscore, 4),
                "description": f"成交量放大 {ratio:.1f}x 均值",
            })

        return anomalies

    def detect_funding_anomaly(self, funding_rates: list[float]) -> list[dict]:
        """检测资金费率极值。"""
        if len(funding_rates) < 10:
            return []

        anomalies = []
        latest = funding_rates[-1]
        mean = statistics.mean(funding_rates[:-1])
        std = statistics.stdev(funding_rates[:-1]) if len(funding_rates) > 2 else 0.0001
        if std == 0:
            std = 0.0001

        zscore = (latest - mean) / std

        if abs(latest) >= self.FUNDING_EXTREME * 3:
            anomalies.append({
                "type": "funding_extreme",
                "severity": "critical",
                "score": min(1.0, abs(latest) / (self.FUNDING_EXTREME * 5)),
                "metric_name": "funding_rate",
                "metric_value": round(latest, 6),
                "threshold": self.FUNDING_EXTREME * 3,
                "zscore": round(zscore, 4),
                "description": f"资金费率极端 {latest*100:.4f}%，方向={'多头拥挤' if latest > 0 else '空头拥挤'}",
            })
        elif abs(latest) >= self.FUNDING_EXTREME:
            anomalies.append({
                "type": "funding_extreme",
                "severity": "warning",
                "score": min(0.5, abs(latest) / (self.FUNDING_EXTREME * 5)),
                "metric_name": "funding_rate",
                "metric_value": round(latest, 6),
                "threshold": self.FUNDING_EXTREME,
                "zscore": round(zscore, 4),
                "description": f"资金费率偏高 {latest*100:.4f}%",
            })

        return anomalies

    def detect_correlation_break(self, correlations: list[float]) -> list[dict]:
        """检测相关性崩塌。"""
        if len(correlations) < 5:
            return []

        anomalies = []
        recent_avg = statistics.mean(correlations[-5:])
        historical_avg = statistics.mean(correlations[:-5]) if len(correlations) > 5 else recent_avg
        change = abs(recent_avg - historical_avg)

        if change >= self.CORRELATION_BREAK:
            anomalies.append({
                "type": "correlation_break",
                "severity": "critical" if change >= 0.6 else "warning",
                "score": min(1.0, change / 0.8),
                "metric_name": "correlation_change",
                "metric_value": round(change, 4),
                "threshold": self.CORRELATION_BREAK,
                "zscore": round(change / 0.2, 4),
                "description": f"相关性突变 Δ={change:.2f}（从 {historical_avg:.2f} 到 {recent_avg:.2f}）",
            })

        return anomalies
