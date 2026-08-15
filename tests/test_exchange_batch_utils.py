from __future__ import annotations

import time

from data_layer.exchange_data import batch_utils


def test_parallel_fetch_returns_all_non_none_results(monkeypatch):
    monkeypatch.setattr(batch_utils, "EXCHANGE_MIN_REQUEST_INTERVAL_SECONDS", 0)
    batch_utils._exchange_next_request_at.clear()

    results = batch_utils.parallel_fetch(
        lambda exchange, value: value if value % 2 == 0 else None,
        [("okx", 1), ("okx", 2), ("okx", 4)],
        max_workers=3,
        task_label="test",
    )

    assert sorted(results) == [2, 4]


def test_parallel_fetch_spaces_requests_for_same_exchange(monkeypatch):
    interval_seconds = 0.03
    monkeypatch.setattr(
        batch_utils,
        "EXCHANGE_MIN_REQUEST_INTERVAL_SECONDS",
        interval_seconds,
    )
    batch_utils._exchange_next_request_at.clear()
    started_at: list[float] = []

    def fetch(exchange_name: str, value: int) -> int:
        started_at.append(time.monotonic())
        return value

    results = batch_utils.parallel_fetch(
        fetch,
        [("okx", 1), ("okx", 2)],
        max_workers=2,
        task_label="test",
    )

    assert sorted(results) == [1, 2]
    assert len(started_at) == 2
    assert max(started_at) - min(started_at) >= interval_seconds * 0.8
