from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AlertRule:
    name: str
    condition: str  # expression evaluated against metrics
    threshold: float
    severity: str  # "warning" | "critical"
    cooldown_seconds: int = 300


@dataclass
class Alert:
    rule_name: str
    severity: str
    message: str
    timestamp: float = field(default_factory=time.time)


class AlertEvaluator:
    def __init__(self, rules: list[AlertRule] | None = None) -> None:
        self.rules = rules or [
            AlertRule("high_error_rate", "error_rate > 0.1", 0.1, "critical", 300),
            AlertRule("slow_response", "p95_latency > 2.0", 2.0, "warning", 600),
            AlertRule("memory_pressure", "memory_usage_pct > 85", 85, "warning", 300),
            AlertRule("db_pool_exhaustion", "pool_available < 2", 2, "critical", 120),
            AlertRule("stale_data", "max_stale_seconds > 600", 600, "warning", 900),
            AlertRule("circuit_open", "circuit_breaker_open == 1", 1, "critical", 60),
        ]
        self._last_fired: dict[str, float] = {}

    def evaluate(self, metrics: dict) -> list[Alert]:
        alerts: list[Alert] = []
        now = time.time()
        for rule in self.rules:
            last = self._last_fired.get(rule.name, 0)
            if now - last < rule.cooldown_seconds:
                continue
            try:
                if eval(rule.condition, {"__builtins__": {}}, metrics):  # noqa: S307
                    alert = Alert(
                        rule_name=rule.name,
                        severity=rule.severity,
                        message=f"{rule.name}: {rule.condition} (threshold={rule.threshold})",
                        timestamp=now,
                    )
                    alerts.append(alert)
                    self._last_fired[rule.name] = now
            except Exception:
                continue
        return alerts


alert_evaluator = AlertEvaluator()
