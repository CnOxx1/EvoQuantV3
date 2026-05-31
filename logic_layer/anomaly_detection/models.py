"""anomaly_detection 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyEvent:
    """单条异常事件。"""
    entity_key: str
    anomaly_type: str      # price_spike, volume_surge, correlation_break, spread_blow, funding_extreme
    severity: str          # critical, warning, info
    score: float           # 0~1 异常得分
    description: str       # 人类可读描述
    metric_name: str       # 触发指标名
    metric_value: float    # 当前值
    threshold: float       # 触发阈值
    zscore: float          # z-score
    detected_at: str       # ISO 8601


@dataclass(frozen=True)
class AnomalySummary:
    """某实体的异常摘要。"""
    entity_key: str
    total_anomalies_24h: int
    critical_count: int
    warning_count: int
    max_score: float
    dominant_type: str     # 最频繁的异常类型
    risk_level: str        # high, elevated, normal
