"""Unit tests for logic_layer.logic_pipeline.service module functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch

from logic_layer.logic_pipeline.service import (
    _run_phase,
    _run_phase_parallel,
    run_full_pipeline,
)


def test_run_phase_success(tmp_path):
    """_run_phase executes tasks and returns success status."""
    call_log = []

    def task_a():
        call_log.append("a")

    def task_b():
        call_log.append("b")

    results = _run_phase("TestPhase", [("mod_a", task_a), ("mod_b", task_b)])
    assert results == {"mod_a": "success", "mod_b": "success"}
    assert call_log == ["a", "b"]


def test_run_phase_handles_failure(tmp_path):
    """_run_phase captures exceptions and marks module as error."""
    def task_ok():
        pass

    def task_fail():
        raise ValueError("boom")

    results = _run_phase("TestPhase", [("ok", task_ok), ("fail", task_fail)])
    assert results["ok"] == "success"
    assert "error:" in results["fail"]
    assert "ValueError" in results["fail"]


def test_run_phase_parallel_executes_all(tmp_path):
    """_run_phase_parallel runs tasks concurrently and returns results."""
    import threading
    threads_seen = set()

    def task():
        threads_seen.add(threading.current_thread().ident)

    tasks = [(f"mod_{i}", task) for i in range(3)]
    results = _run_phase_parallel("TestPhase", tasks, max_workers=3, timeout=10)
    assert all(v == "success" for v in results.values())
    assert len(results) == 3


@patch("logic_layer.logic_pipeline.service._run_classic_pipeline")
@patch("logic_layer.logic_pipeline.service._invalidate_api_cache_by_modules")
def test_run_full_pipeline_returns_summary(mock_cache, mock_classic, tmp_path):
    """run_full_pipeline returns structured summary dict."""
    mock_classic.return_value = {
        "technical_indicators": "success",
        "cross_asset_analysis": "success",
        "portfolio_risk": "error: RuntimeError",
    }

    result = run_full_pipeline()
    assert result["success_count"] == 2
    assert result["total_count"] == 3
    assert result["mode"] == "classic"
    assert "started_at" in result
    assert "finished_at" in result
    assert result["results"]["technical_indicators"] == "success"


def test_run_phase_skips_uninitialized_source():
    """缺失可选数据表应被标记为输入源未就绪，而非模块错误。"""

    def task_missing_source():
        raise RuntimeError("no such table: news_articles")

    results = _run_phase("TestPhase", [("news_sentiment", task_missing_source)])

    assert results == {"news_sentiment": "skipped:source_unavailable"}


def test_run_phase_parallel_skips_uninitialized_source():
    """并行阶段应保持与串行阶段一致的输入源跳过语义。"""

    def task_missing_source():
        raise RuntimeError('relation "macro_timeseries" does not exist')

    results = _run_phase_parallel(
        "TestPhase",
        [("macro_context", task_missing_source)],
        max_workers=1,
        timeout=10,
    )

    assert results == {"macro_context": "skipped:source_unavailable"}
