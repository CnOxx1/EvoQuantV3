"""数据管道延迟追踪编排服务。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.pipeline_latency.models import DomainLatency, PipelineLatencyReport
from logic_layer.pipeline_latency.repository import PipelineLatencyRepository

logger = logging.getLogger(__name__)


class PipelineLatencyService:
    """数据管道延迟追踪入口 — 暴露各域端到端数据新鲜度指标。"""

    # 各域可接受的最大延迟（秒）
    FRESHNESS_THRESHOLDS: dict[str, dict[str, int]] = {
        "klines": {"fresh": 3600, "acceptable": 7200},
        "technical_indicators": {"fresh": 3600, "acceptable": 7200},
        "feature_standardization": {"fresh": 7200, "acceptable": 14400},
        "cross_asset": {"fresh": 7200, "acceptable": 14400},
        "portfolio_risk": {"fresh": 7200, "acceptable": 14400},
        "macro_context": {"fresh": 86400, "acceptable": 172800},
        "market_breadth": {"fresh": 7200, "acceptable": 14400},
        "asset_readiness": {"fresh": 7200, "acceptable": 14400},
        "ai_market_context": {"fresh": 7200, "acceptable": 14400},
        "exchange_comparison": {"fresh": 3600, "acceptable": 7200},
        "news": {"fresh": 3600, "acceptable": 7200},
    }

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = PipelineLatencyRepository(self.db)

    def init_storage(self):
        """无需建表 — 纯只读模块。"""

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_ts(ts_str: str | None) -> datetime | None:
        if not ts_str:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _classify_latency(self, domain: str, latency_seconds: float) -> str:
        thresholds = self.FRESHNESS_THRESHOLDS.get(domain, {"fresh": 7200, "acceptable": 14400})
        if latency_seconds <= thresholds["fresh"]:
            return "fresh"
        if latency_seconds <= thresholds["acceptable"]:
            return "acceptable"
        return "stale"

    def measure_all(self) -> PipelineLatencyReport:
        """测量所有域的数据延迟。"""
        now = self._utc_now()
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

        domain_fetchers = {
            "klines": self.repository.get_latest_klines_time,
            "technical_indicators": self.repository.get_latest_technical_indicators_time,
            "feature_standardization": self.repository.get_latest_feature_std_time,
            "cross_asset": self.repository.get_latest_cross_asset_time,
            "portfolio_risk": self.repository.get_latest_portfolio_risk_time,
            "macro_context": self.repository.get_latest_macro_context_time,
            "market_breadth": self.repository.get_latest_market_breadth_time,
            "asset_readiness": self.repository.get_latest_asset_readiness_time,
            "ai_market_context": self.repository.get_latest_ai_context_time,
            "exchange_comparison": self.repository.get_latest_exchange_comparison_time,
            "news": self.repository.get_latest_news_time,
        }

        domains: dict[str, DomainLatency] = {}
        for domain, fetcher in domain_fetchers.items():
            latest_ts_str = fetcher()
            latest_dt = self._parse_ts(latest_ts_str)
            if latest_dt is None:
                domains[domain] = DomainLatency(
                    domain=domain, status="unavailable", measured_at=now_iso
                )
                continue
            latency = (now - latest_dt).total_seconds()
            status = self._classify_latency(domain, latency)
            domains[domain] = DomainLatency(
                domain=domain,
                latest_data_time=latest_ts_str,
                measured_at=now_iso,
                latency_seconds=round(latency, 1),
                status=status,
            )

        # 汇总
        fresh_count = sum(1 for d in domains.values() if d.status == "fresh")
        acceptable_count = sum(1 for d in domains.values() if d.status == "acceptable")
        stale_count = sum(1 for d in domains.values() if d.status == "stale")
        unavailable_count = sum(1 for d in domains.values() if d.status == "unavailable")
        total = len(domains)

        available_latencies = [
            d.latency_seconds for d in domains.values() if d.latency_seconds is not None
        ]
        avg_latency = (
            round(sum(available_latencies) / len(available_latencies), 1)
            if available_latencies else None
        )
        max_latency = max(available_latencies) if available_latencies else None

        overall = "healthy" if stale_count == 0 and unavailable_count == 0 else (
            "degraded" if fresh_count + acceptable_count > stale_count + unavailable_count
            else "unhealthy"
        )

        return PipelineLatencyReport(
            measured_at=now_iso,
            domains=domains,
            summary={
                "total_domains": total,
                "fresh": fresh_count,
                "acceptable": acceptable_count,
                "stale": stale_count,
                "unavailable": unavailable_count,
                "avg_latency_seconds": avg_latency,
                "max_latency_seconds": max_latency,
                "overall_health": overall,
            },
        )

    def close(self):
        self.db.close()
