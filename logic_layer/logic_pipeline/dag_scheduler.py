"""逻辑层 DAG 调度器 — 基于依赖图的并行执行。

替代原有的固定 5 阶段串行模型，根据模块间真实依赖关系
自动计算执行顺序，最大化并行度。
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from loguru import logger

# DAG 最大并行线程数
DAG_MAX_WORKERS = int(os.environ.get("LOGIC_PIPELINE_DAG_WORKERS", "6"))
# 单模块超时
DAG_TASK_TIMEOUT = int(os.environ.get("LOGIC_PIPELINE_DAG_TIMEOUT", "300"))


class ModuleNode:
    """DAG 中的模块节点。"""

    __slots__ = ("name", "fn", "depends_on")

    def __init__(self, name: str, fn: Callable, depends_on: list[str] | None = None):
        self.name = name
        self.fn = fn
        self.depends_on: list[str] = depends_on or []


def topological_levels(nodes: list[ModuleNode]) -> list[list[ModuleNode]]:
    """将 DAG 节点按拓扑层级分组，同层节点可并行执行。"""
    name_to_node = {n.name: n for n in nodes}
    in_degree: dict[str, int] = {n.name: 0 for n in nodes}
    dependents: dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        for dep in node.depends_on:
            if dep in name_to_node:
                in_degree[node.name] += 1
                dependents[dep].append(node.name)

    # BFS 分层
    levels: list[list[ModuleNode]] = []
    queue = deque([n for n in nodes if in_degree[n.name] == 0])

    while queue:
        level = list(queue)
        levels.append(level)
        next_queue: deque[ModuleNode] = deque()
        for node in level:
            for dep_name in dependents[node.name]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    next_queue.append(name_to_node[dep_name])
        queue = next_queue

    return levels


def run_dag(
    nodes: list[ModuleNode],
    max_workers: int = DAG_MAX_WORKERS,
    timeout: int = DAG_TASK_TIMEOUT,
) -> dict[str, str]:
    """按 DAG 拓扑层级执行所有模块，同层并行。

    Returns
    -------
    dict[str, str]
        {module_name: "success" | "error: ..." | "skipped: dependency failed"}
    """
    levels = topological_levels(nodes)
    all_results: dict[str, str] = {}
    failed_modules: set[str] = set()

    for level_idx, level in enumerate(levels):
        # 跳过依赖已失败的模块
        runnable = []
        for node in level:
            failed_deps = [d for d in node.depends_on if d in failed_modules]
            if failed_deps:
                all_results[node.name] = f"skipped: dependency {failed_deps[0]} failed"
                failed_modules.add(node.name)
            else:
                runnable.append(node)

        if not runnable:
            continue

        level_name = f"Level-{level_idx}"
        if len(runnable) == 1:
            # 单模块串行执行
            node = runnable[0]
            status = _execute_module(level_name, node)
            all_results[node.name] = status
            if status != "success":
                failed_modules.add(node.name)
        else:
            # 多模块并行执行
            with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable))) as executor:
                future_to_node = {
                    executor.submit(_execute_module, level_name, node): node
                    for node in runnable
                }
                try:
                    for future in as_completed(future_to_node, timeout=timeout):
                        node = future_to_node[future]
                        try:
                            status = future.result()
                        except Exception as exc:
                            status = f"error: {type(exc).__name__}"
                        all_results[node.name] = status
                        if status != "success":
                            failed_modules.add(node.name)
                except TimeoutError:
                    for future, node in future_to_node.items():
                        if node.name not in all_results:
                            all_results[node.name] = "error: TimeoutError"
                            failed_modules.add(node.name)
                            logger.error("DAG [{}] {} 超时 (>{}s)", level_name, node.name, timeout)

    return all_results


def _execute_module(level_name: str, node: ModuleNode) -> str:
    """执行单个模块，返回状态字符串。"""
    started = time.monotonic()
    try:
        node.fn()
        elapsed = time.monotonic() - started
        logger.info("DAG [{}] {} 完成 ({:.1f}s)", level_name, node.name, elapsed)
        return "success"
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.error("DAG [{}] {} 失败 ({:.1f}s): {}", level_name, node.name, elapsed, exc)
        return f"error: {type(exc).__name__}"
