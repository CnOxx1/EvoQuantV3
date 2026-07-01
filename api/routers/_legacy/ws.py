"""WebSocket 路由 — 实时推送频道。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from api.websocket_manager import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{channel}")
async def ws_endpoint(websocket: WebSocket, channel: str):
    """WebSocket 实时推送端点。

    支持的频道:
        - pipeline: 管道执行完成通知
        - health: 健康状态变更
        - indicators:{symbol}: 特定币对技术指标更新
    """
    await ws_manager.connect(websocket, channel)
    try:
        while True:
            # 接收客户端消息（用于 keepalive/ping）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, channel)
    except Exception as e:
        logger.debug("WebSocket 异常断开 (channel={}): {}", channel, e)
        await ws_manager.disconnect(websocket, channel)


@router.get("/ws/status")
def ws_status() -> dict:
    """WebSocket 连接状态摘要。"""
    return {
        "active_connections": ws_manager.active_connections,
        "active_channels": ws_manager.active_channels,
    }
