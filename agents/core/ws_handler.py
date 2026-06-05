"""WebSocket 连接处理 — 接收前端消息，启动 agent 循环，推送流事件。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from agents.core.container import MyAgentApp
from agents.core.session_manager import SessionManager


# 不推前端的 EventType
_NON_RENDER_TYPES = {"context_entry", "context_patch"}

# 需要在 ws_handler 中 delta 缓冲合并的类型
_DELTA_TYPES = {
    "text", "thinking",
    "auto_compact_thinking", "auto_compact_text",
    "recall_expand_thinking", "recall_expand_text",
    "recall_rerank_thinking", "recall_rerank_text",
    "recall_synth_thinking", "recall_synth_text",
}


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
        # 每连接独立 SessionManager，避免并发连接互相覆盖 session 状态
        session_manager = SessionManager(sessions_dir=self._agent_app.main_agent_sessions_dir)
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

                elif msg_type == "new_session":
                    await self._handle_new_session(websocket, session)

        except (WebSocketDisconnect, RuntimeError):
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
            sid = session_manager.new_session()
            await websocket.send_json({
                "type": "session_created",
                "session_id": sid,
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
        buffers: dict[str, str] = {dt: "" for dt in _DELTA_TYPES}
        buffer_type = ""

        try:
            for stream_event in self._agent_app.start_agent_loop(session):
                d = stream_event.to_dict()
                event_type = d["type"]

                if event_type in _DELTA_TYPES:
                    # 类型切换 → flush 旧缓冲
                    if buffer_type and buffer_type != event_type:
                        prev_buf = buffers.get(buffer_type, "")
                        if prev_buf:
                            self._flush_buffer(session_manager, turn, buffer_type, prev_buf)
                        buffers[buffer_type] = ""

                    delta = d.get("delta", "")
                    if event_type in buffers:
                        buffers[event_type] += delta
                    buffer_type = event_type

                    # 推 WebSocket（逐 delta 实时渲染）
                    await websocket.send_json(d)

                else:
                    # 非 delta 事件 → flush 全部缓冲
                    for bt, buf in buffers.items():
                        if buf:
                            self._flush_buffer(session_manager, turn, bt, buf)
                            buffers[bt] = ""
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

        except WebSocketDisconnect:
            return
        except Exception as exc:
            try:
                await websocket.send_json({"type": "error", "error_msg": str(exc)})
            except Exception:
                pass
            return

        # flush 最后缓冲区
        for bt, buf in buffers.items():
            if buf:
                self._flush_buffer(session_manager, turn, bt, buf)

        # 推进 turn + 推送最新会话列表
        session_manager.advance_turn()
        await self._push_session_list(websocket, session_manager)

    # ---- 推送 ----

    async def _push_session_list(self, websocket: WebSocket, session_manager: Any) -> None:
        """推送最新会话列表到前端左面板。"""
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
        await self._push_session_list(websocket, session_manager)

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
        await self._push_session_list(websocket, session_manager)

    async def _handle_new_session(self, websocket: WebSocket, session: WsSession) -> None:
        """退出当前会话，清空状态，等待用户发送消息时再创建会话。"""
        session_manager = session.session_manager
        session_manager.detach_session()
        session.messages = []
        await websocket.send_json({
            "type": "session_state",
            "session_id": None,
            "transcript": [],
        })
