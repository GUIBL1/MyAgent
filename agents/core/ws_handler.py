"""WebSocket 连接处理 — 接收前端消息，启动 agent 循环，推送流事件。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from agents.core.container import MyAgentApp


class WsSession:
    """管理单个 WebSocket 连接的会话历史。"""

    def __init__(self):
        self.messages: list[dict[str, Any]] = []


class WsHandler:
    """WebSocket 消息分发：接收前端 send → 启动 agent 生成器 → 推送事件回前端。"""

    def __init__(self):
        self._agent_app = MyAgentApp()

    # ======================== public ========================

    async def handle(self, websocket: WebSocket) -> None:
        """接受 WS 连接，进入消息循环。"""
        await websocket.accept()
        session = WsSession()

        try:
            async for raw_message in websocket.iter_text():
                try:
                    message: dict[str, Any] = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "error_msg": "invalid json"})
                    continue

                if message.get("type") == "send":
                    await self._handle_send(websocket, session, message.get("content", ""))

        except WebSocketDisconnect:
            pass

    # ======================== private ========================

    async def _handle_send(self, websocket: WebSocket, session: WsSession, user_content: str) -> None:
        """处理用户消息：追加到会话 → 启动 agent → 流式推送事件。"""
        if not user_content.strip():
            await websocket.send_json({"type": "error", "error_msg": "empty message"})
            return

        session.messages.append({"role": "user", "content": user_content})
        await websocket.send_json({"type": "user_message", "content": user_content})

        try:
            for stream_event in self._agent_app.start_agent_loop(session.messages):
                await websocket.send_json(stream_event.to_dict())
                # 防止一次积压多个事件发送前端，保持 UI 响应性
                await asyncio.sleep(0)
        except Exception as exc:
            await websocket.send_json({"type": "error", "error_msg": str(exc)})
