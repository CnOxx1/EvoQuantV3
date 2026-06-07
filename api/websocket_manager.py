"""WebSocket 连接管理器 — 支持频道级广播。

v4.2.0 优化: broadcast() 序列化一次发送多次（原实现已正确），
新增 broadcast_sync 中 orjson 快速路径。
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from loguru import logger

# v4.2.0: 尝试使用 orjson 加速 JSON 序列化
try:
    import orjson

    def _serialize(data: dict[str, Any]) -> str:
        return orjson.dumps(data, default=str).decode("utf-8")
except ImportError:
    def _serialize(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)


class ConnectionManager:
    """管理 WebSocket 连接，按频道组织广播。

    支持的频道:
        - "pipeline": 管道执行完成通知
        - "health": 健康状态变更推送
        - "indicators:{symbol}": 特定币对指标更新
    """

    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)
        logger.debug("WebSocket 连接已建立: channel={}", channel)

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        async with self._lock:
            self._connections[channel].discard(websocket)
            if not self._connections[channel]:
                del self._connections[channel]
        logger.debug("WebSocket 连接已断开: channel={}", channel)

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """向指定频道的所有连接广播 JSON 消息。

        v4.2.0: 使用 orjson 快速路径序列化，只序列化一次发送多次。
        """
        async with self._lock:
            connections = set(self._connections.get(channel, set()))

        if not connections:
            return

        # 序列化一次，发送多次
        message = _serialize(data)
        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # 清理已断开的连接
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[channel].discard(ws)

    def broadcast_sync(self, channel: str, data: dict[str, Any]) -> None:
        """从同步上下文安全广播（用于 pipeline 等同步线程）。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.broadcast(channel, data), loop
                )
            else:
                loop.run_until_complete(self.broadcast(channel, data))
        except RuntimeError:
            # 无可用事件循环时静默跳过
            pass

    @property
    def active_connections(self) -> int:
        return sum(len(conns) for conns in self._connections.values())

    @property
    def active_channels(self) -> list[str]:
        return list(self._connections.keys())


# 全局单例
ws_manager = ConnectionManager()
