"""并行获取工具 — 基于 ThreadPoolExecutor 的通用并行采集。"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Sequence

from loguru import logger


MAX_COLLECTION_WORKERS = int(os.environ.get("MAX_COLLECTION_WORKERS", "16"))


def parallel_fetch(
    fetch_fn: Callable[..., Any],
    tasks: Sequence[tuple],
    max_workers: int | None = None,
    task_label: str = "fetch",
) -> list[Any]:
    """并行执行多个采集任务，返回非 None 结果列表。

    Args:
        fetch_fn: 采集函数，接受 task tuple 解包为参数
        tasks: 参数元组列表，每个元素解包传入 fetch_fn
        max_workers: 最大并发数（默认 MAX_COLLECTION_WORKERS）
        task_label: 日志标签
    """
    workers = min(max_workers or MAX_COLLECTION_WORKERS, len(tasks))
    if workers <= 0 or not tasks:
        return []

    results: list[Any] = []
    errors = 0

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=task_label) as pool:
        future_to_task = {
            pool.submit(fetch_fn, *task): task for task in tasks
        }
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                if result is not None:
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)
            except Exception as e:
                task = future_to_task[future]
                errors += 1
                logger.debug("{} 任务失败 {}: {}", task_label, task[:2], e)

    if errors:
        logger.warning("{}: {}/{} 任务失败", task_label, errors, len(tasks))

    return results
