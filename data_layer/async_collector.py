"""异步数据采集基础设施 — 为数据层提供并行采集能力。

使用 asyncio.gather() 并行化交易所 API 调用，
通过 asyncio.to_thread() 包装同步 ccxt 调用。
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from loguru import logger

T = TypeVar("T")

# 全局线程池，用于包装同步 ccxt 调用
_EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix="async-collector")


async def gather_with_concurrency(
    coros: list,
    max_concurrency: int = 8,
    return_exceptions: bool = True,
) -> list[Any]:
    """带并发限制的 asyncio.gather。

    Parameters
    ----------
    coros : list of coroutines
        待执行的协程列表
    max_concurrency : int
        最大并发数（防止交易所限流）
    return_exceptions : bool
        是否将异常作为结果返回而非抛出
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _limited(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(
        *[_limited(c) for c in coros],
        return_exceptions=return_exceptions,
    )


async def run_in_thread(fn: Callable[..., T], *args, **kwargs) -> T:
    """将同步函数放入线程池执行，返回 awaitable。

    用于包装 ccxt 同步调用：
        result = await run_in_thread(client.fetch_trades, symbol, limit=100)
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _EXECUTOR, lambda: fn(*args, **kwargs)
    )


def run_async_collection(coro) -> Any:
    """在同步上下文中运行异步采集协程。

    用于在现有同步 runner 中调用异步采集：
        results = run_async_collection(collector.fetch_all_async())
    """
    try:
        loop = asyncio.get_running_loop()
        # 已在事件循环中，创建 task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # 没有运行中的事件循环，直接 run
        return asyncio.run(coro)


def create_async_client(
    base_url: str,
    timeout: float = 20.0,
    max_retries: int = 3,
    rate_limit: float = 10.0,
    rate_burst: int = 20,
    **kwargs,
):
    """工厂函数 — 创建 AsyncBaseDataClient 实例（延迟导入避免循环依赖）。

    用于数据层模块快速创建异步客户端：
        client = create_async_client("https://api.example.com", rate_limit=5.0)
        async with client:
            data = await client.get("/v1/data")
    """
    from core.async_base_data_client import AsyncBaseDataClient

    return AsyncBaseDataClient(
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
        rate_limit=rate_limit,
        rate_burst=rate_burst,
        **kwargs,
    )
