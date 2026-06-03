"""WebSocket 连接处理 — 接收前端消息，启动 agent 循环，推送流事件。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from agents.core.container import MyAgentApp


# 不推前端的 EventType
_NON_RENDER_TYPES = {"context_entry", "context_patch"}

# 需要在 ws_handler 中 delta 缓冲合并的类型
_DELTA_TYPES = {"text", "thinking"}


class WsSession:
    """管理单个 WebSocket 连接的会话历史。"""

    def __init__(self, session_manager: Any):
        self.messages: list[dict[str, Any]] = []
        self.session_manager = session_manager


class WsHandler:
    """WebSocket 消息分发：接收前端 send → 启动 agent 生成器 → 推送事件回前端。"""

    def __init__(self):
        self._agent_app = MyAgentApp()

    # ======================== public ========================

    async def handle(self, websocket: WebSocket) -> None:
        """接受 WS 连接，进入消息循环。"""
        await websocket.accept()
        session_manager = self._agent_app.session_manager
        session = WsSession(session_manager)

        # 推送会话列表，供前端左面板展示
        await websocket.send_json({
            "type": "session_list",
            "sessions": session_manager.list_sessions(),
        })

        try:
            async for raw_message in websocket.iter_text():
                try:
                    message: dict[str, Any] = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "error_msg": "invalid json"})
                    continue

                msg_type = message.get("type")

                if msg_type == "send":
                    await self._handle_send(websocket, session, message.get("content", ""))

                elif msg_type == "rewind":
                    await self._handle_rewind(websocket, session, message.get("turn", 1))

                elif msg_type == "switch_session":
                    await self._handle_switch_session(websocket, session, message.get("session_id", ""))

        except WebSocketDisconnect:
            pass

    # ======================== private ========================

    async def _handle_send(self, websocket: WebSocket, session: WsSession, user_content: str) -> None:
        """处理用户消息：首次发送时自动创建会话，然后启动 agent。"""
        if not user_content.strip():
            await websocket.send_json({"type": "error", "error_msg": "empty message"})
            return

        session_manager = session.session_manager

        # 首次发送：创建新会话
        if not session_manager.session_id:
            session_manager.new_session()
            await websocket.send_json({
                "type": "session_created",
                "session_id": session_manager.session_id,
            })

        turn = session_manager.current_turn

        # 1) 写入 transcript + LLM context
        session_manager.write_transcript({
            "turn": turn, "seq": session_manager.next_seq(), "type": "user_message", "content": user_content,
        })

        user_msg = {"role": "user", "content": user_content}
        session.messages.append(user_msg)
        # CONTEXT_ENTRY for user_message
        session_manager.write_transcript({
            "turn": turn, "seq": session_manager.next_seq(), "type": "context_entry", "content": json.dumps(user_msg, ensure_ascii=False),
        })

        # 2) 推送前端
        await websocket.send_json({"type": "user_message", "content": user_content})

        # 3) 启动 agent，缓冲 delta + 写入 transcript
        text_buffer = ""
        thinking_buffer = ""
        buffer_type = ""  # "text" | "thinking"

        try:
            for stream_event in self._agent_app.start_agent_loop(session.messages):
                d = stream_event.to_dict()
                event_type = d["type"]

                if event_type in _DELTA_TYPES:
                    # 类型切换 → flush 缓冲
                    if buffer_type and buffer_type != event_type:
                        self._flush_buffer(
                            session_manager, turn, buffer_type, text_buffer if "text" in buffer_type else thinking_buffer,
                        )
                        if "text" in buffer_type:
                            text_buffer = ""
                        else:
                            thinking_buffer = ""

                    delta = d.get("delta", "")
                    if "text" in event_type:
                        text_buffer += delta
                        buffer_type = event_type
                    else:
                        thinking_buffer += delta
                        buffer_type = event_type

                    # 推 WebSocket（逐 delta 实时渲染）
                    await websocket.send_json(d)

                else:
                    # 非 delta 事件 → flush 缓冲
                    if text_buffer:
                        self._flush_buffer(session_manager, turn, "text", text_buffer)
                        text_buffer = ""
                    if thinking_buffer:
                        self._flush_buffer(session_manager, turn, "thinking", thinking_buffer)
                        thinking_buffer = ""
                    buffer_type = ""

                    # 写 transcript
                    meta = {"turn": turn, "seq": session_manager.next_seq()}
                    session_manager.write_transcript({**meta, **d})

                    # context_patch：修正 transcript 中历史 CONTEXT_ENTRY
                    if event_type == "context_patch":
                        try:
                            patches = json.loads(d.get("content", "[]"))
                            session_manager.apply_context_patch(patches)
                        except json.JSONDecodeError:
                            pass

                    # 推前端（过滤非渲染类型）
                    if event_type not in _NON_RENDER_TYPES:
                        await websocket.send_json(d)

                await asyncio.sleep(0)

        except Exception as exc:
            await websocket.send_json({"type": "error", "error_msg": str(exc)})
            return

        # flush 最后缓冲区
        if text_buffer:
            self._flush_buffer(session_manager, turn, "text", text_buffer)
        if thinking_buffer:
            self._flush_buffer(session_manager, turn, "thinking", thinking_buffer)

        # 推进 turn + 推送最新会话列表
        session_manager.advance_turn()
        await self._push_session_list(websocket)

    # ---- 推送 ----

    async def _push_session_list(self, websocket: WebSocket) -> None:
        """推送最新会话列表到前端左面板。"""
        session_manager = self._agent_app.session_manager
        await websocket.send_json({
            "type": "session_list", "sessions": session_manager.list_sessions(),
        })

    # ---- delta 缓冲 flush ----

    @staticmethod
    def _flush_buffer(session_manager: Any, turn: int, flush_type: str, text: str) -> None:
        """将合并后的 text/thinking 写入 transcript。"""
        if not text:
            return
        session_manager.write_transcript({
            "turn": turn, "seq": session_manager.next_seq(), "type": flush_type, "content": text,
        })

    # ---- 命令处理 ----

    async def _handle_rewind(self, websocket: WebSocket, session: WsSession, turn: int) -> None:
        """回退到指定 turn。"""
        session_manager = session.session_manager
        try:
            session.messages = session_manager.rewind_to_turn(turn)
        except Exception as exc:
            await websocket.send_json({"type": "error", "error_msg": f"rewind failed: {exc}"})
            return

        await websocket.send_json({
            "type": "session_state",
            "session_id": session_manager.session_id,
            "transcript": session_manager.load_transcript(),
        })
        await self._push_session_list(websocket)

    async def _handle_switch_session(self, websocket: WebSocket, session: WsSession, session_id: str) -> None:
        """切换到指定会话，加载历史 context 和 transcript 推送给前端。"""
        if not session_id:
            await websocket.send_json({"type": "error", "error_msg": "missing session_id"})
            return

        session_manager = session.session_manager
        try:
            session.messages = session_manager.load_context(session_id)
        except Exception as exc:
            await websocket.send_json({"type": "error", "error_msg": f"switch session failed: {exc}"})
            return

        await websocket.send_json({
            "type": "session_state",
            "session_id": session_id,
            "transcript": session_manager.load_transcript(),
        })
        await self._push_session_list(websocket)
