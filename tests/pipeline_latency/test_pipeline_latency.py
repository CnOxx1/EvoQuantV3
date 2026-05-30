"""数据管道延迟追踪模块单元测试。"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from logic_layer.pipeline_latency.models import DomainLatency, PipelineLatencyReport
from logic_layer.pipeline_latency.service import PipelineLatencyService


class TestPipelineLatencyService:
    """延迟追踪服务测试。"""

    def test_measure_all_no_data(self):
        mock_db = MagicMock()
        mock_db.conn.execute.return_value.fetchone.return_value = None

        service = PipelineLatencyService(db=mock_db)
        report = service.measure_all()

        assert isinstance(report, PipelineLatencyReport)
        assert report.summary["total_domains"] == 11
        assert report.summary["unavailable"] == 11

    def test_measure_all_fresh_data(self):
        mock_db = MagicMock()
        service = PipelineLatencyService(db=mock_db)

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")

        # Mock all fetchers to return recent timestamp
        for attr in dir(service.repository):
            if attr.startswith("get_latest_"):
                setattr(service.repository, attr, MagicMock(return_value=recent))

        report = service.measure_all()
        assert report.summary["fresh"] == 11
        assert report.summary["stale"] == 0
        assert report.summary["overall_health"] == "healthy"

    def test_measure_all_stale_data(self):
        mock_db = MagicMock()
        service = PipelineLatencyService(db=mock_db)

        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

        for attr in dir(service.repository):
            if attr.startswith("get_latest_"):
                setattr(service.repository, attr, MagicMock(return_value=old))

        report = service.measure_all()
        assert report.summary["stale"] > 0
        assert report.summary["overall_health"] in ("degraded", "unhealthy")
