"""并行获取工具 — 基于 ThreadPoolExecutor 的通用并行采集。"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Sequence

from loguru import logger


MAX_COLLECTION_WORKERS = int(os.environ.get("MAX_COLLECTION_WORKERS", "16"))
EXCHANGE_MIN_REQUEST_INTERVAL_SECONDS = max(
    0.0,
    float(os.environ.get("EXCHANGE_MIN_REQUEST_INTERVAL_MS", "100")) / 1000,
)

_exchange_schedule_lock = threading.Lock()
_exchange_next_request_at: dict[str, float] = {}


def _exchange_name_from_task(task: tuple) -> str | None:
    """从交易所采集任务的首个参数中提取交易所名。"""
    if not task or not isinstance(task[0], str):
        return None
    return task[0].strip().lower() or None


def _wait_for_exchange_slot(exchange_name: str | None) -> None:
    """为同一交易所分配全局请求时隙，避免线程池瞬时突发。"""
    if not exchange_name or EXCHANGE_MIN_REQUEST_INTERVAL_SECONDS <= 0:
        return

    with _exchange_schedule_lock:
        now = time.monotonic()
        scheduled_at = max(now, _exchange_next_request_at.get(exchange_name, now))
        _exchange_next_request_at[exchange_name] = (
            scheduled_at + EXCHANGE_MIN_REQUEST_INTERVAL_SECONDS
        )

    delay = scheduled_at - now
    if delay > 0:
        time.sleep(delay)


def parallel_fetch(
    fetch_fn: Callable[..., Any],
    tasks: Sequence[tuple],
    max_workers: int | None = None,
    task_label: str = "fetch",
) -> list[Any]:
    """并行执行多个采集任务，并对同一交易所施加共享请求间隔。"""
    workers = min(max_workers or MAX_COLLECTION_WORKERS, len(tasks))
    if workers <= 0 or not tasks:
        return []

    def run_task(task: tuple) -> Any:
        _wait_for_exchange_slot(_exchange_name_from_task(task))
        return fetch_fn(*task)

    results: list[Any] = []
    errors = 0

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=task_label) as pool:
        future_to_task = {pool.submit(run_task, task): task for task in tasks}
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                if result is not None:
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)
            except Exception as error:
                task = future_to_task[future]
                errors += 1
                logger.debug("{} 任务失败 {}: {}", task_label, task[:2], error)

    if errors:
        logger.warning("{}: {}/{} 任务失败", task_label, errors, len(tasks))

    return results
