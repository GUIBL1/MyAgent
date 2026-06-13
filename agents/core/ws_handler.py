"""WebSocket 连接处理 — 多路事件复用，统一 delta 合并、transcript、前端推送。"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from agents.core.session_manager import SessionManager


# 不推前端的 EventType
_NON_RENDER_TYPES = {"context_entry", "context_patch"}

# 不写 transcript 的 EventType（元数据 / 动态状态 / 已由线程手动写入）
_NON_TRANSCRIPT_TYPES = {"session_list", "session_created", "team_update", "user_message"}

# 需要在 ws_handler 中 delta 缓冲合并的类型
_DELTA_TYPES = {
    "text", "thinking",
    "auto_compact_thinking", "auto_compact_text",
    "recall_expand_thinking", "recall_expand_text",
    "recall_rerank_thinking", "recall_rerank_text",
    "recall_synth_thinking", "recall_synth_text",
}


class WsHandler:
    """WebSocket 多路事件复用器。

    MainLoop 和 teammate 跑在独立线程，只做 yield → queue.put。
    协程 _drain_all 非阻塞轮询所有队列，统一 delta 合并、transcript、前端推送。
    """

    def __init__(
        self,
        mcp_manager,
        skill_manager,
        teammate_manager,
        main_loop,
    ):
        self._mcp_manager = mcp_manager
        self._skill_manager = skill_manager
        self._teammate_manager = teammate_manager
        self._main_loop = main_loop

        self._queues: dict[str, queue.Queue] = {}                 # source → Queue
        self._buffers: dict[str, dict[str, str]] = {}             # source → {type: text}
        self._session_managers: dict[str, SessionManager] = {}    # source → SessionManager
        self._source_last_delta: dict[str, str] = {}              # source → last delta type

    # ======================== public ========================

    def push(self, source: str, data: dict) -> None:
        """线程安全：向指定管路的队列写入事件。"""
        q = self._queues.get(source)
        if q:
            q.put(data)

    def register_source(self, source: str, session_manager: SessionManager) -> None:
        """注册管路：队列并创建绑定 SessionManager（teammate 与 main agent 线程调用）。"""
        self._queues[source] = queue.Queue()
        self._buffers[source] = {}
        self._session_managers[source] = session_manager
        self._source_last_delta[source] = ""

    def get_session_manager(self, source: str) -> SessionManager | None:
        """返回指定管路的 SessionManager，未注册时返回 None。"""
        return self._session_managers.get(source)

    async def handle(self, websocket: WebSocket) -> None:
        """接受 WS 连接，进入消息循环。"""
        await websocket.accept()

        # 提前注册 main 管路，确保在首次 send 前即可进行会话切换、回退等操作
        self._main_loop.ensure_session_manager()

        # 推送会话列表
        await self._ws_send(websocket, {
            "type": "session_list",
            "sessions": self.get_session_manager("main").list_sessions(),
        })
        # 推送 MCP 服务器状态
        mcp_servers = self._mcp_manager.get_server_status()
        await self._ws_send(websocket, {
            "type": "mcp_info",
            "content": json.dumps({"servers": mcp_servers}, ensure_ascii=False),
        })
        # 推送 Skill 列表
        skills = self._skill_manager.get_skill_list()
        await self._ws_send(websocket, {
            "type": "skill_info",
            "content": json.dumps({"skills": skills}, ensure_ascii=False),
        })
        # 推送团队初始状态
        team = self._teammate_manager.get_team_summary()
        await self._ws_send(websocket, {
            "type": "team_update",
            "content": json.dumps(team, ensure_ascii=False),
        })

        # 启动 drain 协程
        drain_task = asyncio.create_task(self._drain_all(websocket))

        try:
            async for raw_message in websocket.iter_text():
                try:
                    msg: dict[str, Any] = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._ws_send(websocket, {"type": "error", "error_msg": "invalid json"})
                    continue

                msg_type = msg.get("type")

                if msg_type == "send":
                    self._handle_send(msg.get("content", ""))
                elif msg_type == "stop":
                    self._handle_stop()
                elif msg_type == "rewind":
                    await self._handle_rewind(websocket, msg.get("turn", 1))
                elif msg_type == "switch_session":
                    await self._handle_switch_session(websocket, msg.get("session_id", ""))
                elif msg_type == "new_session":
                    await self._handle_new_session(websocket)
                elif msg_type == "load_teammate_session":
                    await self._handle_load_teammate_session(websocket, msg.get("name", ""))

        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            drain_task.cancel()

    # ======================== private: main agent 线程 ========================

    def _handle_send(self, user_content: str) -> None:
        """main agent 线程入口。委托 MainLoop.run_main_agent 处理完整生命周期。"""
        threading.Thread(
            target=self._main_loop.run_main_agent,
            args=(user_content,),
            daemon=True,
        ).start()

    def _handle_stop(self) -> None:
        """停止当前 agent 运行。"""
        self._main_loop.request_stop()

    # ======================== private: drain & dispatch ========================

    async def _drain_all(self, websocket: WebSocket) -> None:
        """协程：非阻塞轮询所有队列，逐事件分发。"""
        while True:
            had = False
            for source, q in dict(self._queues).items():
                d = self._try_get_nonblock(q)
                if d is None:
                    continue
                had = True
                await self._dispatch(source, websocket, d)
            if not had:
                await asyncio.sleep(0.05)

    async def _dispatch(self, source: str, websocket: WebSocket, d: dict[str, Any]) -> None:
        """单事件分发：delta 合并 → transcript → send_json。"""
        event_type = d.get("type", "")

        # 不写 transcript 的类型 → 直接转发
        if event_type in _NON_TRANSCRIPT_TYPES:
            await self._ws_send(websocket, d)
            return

        buffers = self._buffers.get(source, {})
        session_manager = self._session_managers.get(source)

        if event_type in _DELTA_TYPES:
            # 类型切换 → flush 旧缓冲
            prev = self._source_last_delta.get(source, "")
            if prev and prev != event_type:
                buf = buffers.get(prev, "")
                if buf and session_manager:
                    session_manager.write_transcript({"turn": session_manager.current_turn, "seq": session_manager.next_seq(), "type": prev, "content": buf})
                buffers[prev] = ""

            buffers.setdefault(event_type, "")
            buffers[event_type] += d.get("delta", "")
            self._source_last_delta[source] = event_type
            # 逐 delta 推送，非 main 管路带 source 字段
            if source != "main":
                d = {**d, "source": source}
            await self._ws_send(websocket, d)

        else:
            # 非 delta → flush 全部缓冲
            for bt, buf in buffers.items():
                if buf and session_manager:
                    session_manager.write_transcript({"turn": session_manager.current_turn, "seq": session_manager.next_seq(), "type": bt, "content": buf})
                buffers[bt] = ""
            self._source_last_delta[source] = ""

            # 写 transcript
            if session_manager:
                # context_patch：修正 transcript 中历史 CONTEXT_ENTRY
                if event_type == "context_patch":
                    try:
                        patches = json.loads(d.get("content", "[]"))
                        session_manager.apply_context_patch(patches)
                    except (json.JSONDecodeError, AttributeError):
                        pass
                session_manager.write_transcript({"turn": session_manager.current_turn,"seq": session_manager.next_seq(),**d})

            # 推送前端：非 main 管路带 source 字段（过滤非渲染类型）
            if event_type not in _NON_RENDER_TYPES:
                if source != "main":
                    d = {**d, "source": source}
                await self._ws_send(websocket, d)

    # ======================== private: 会话操作 ========================
    async def _handle_rewind(self, websocket: WebSocket, turn: int) -> None:
        """回退到指定 turn。"""
        session_manager = self._session_managers.get("main")
        if session_manager is None:
            await self._ws_send(websocket, {"type": "error", "error_msg": "no active session"})
            return
        try:
            self._main_loop.replace_messages(session_manager.rewind_to_turn(turn))
        except Exception as exc:
            await self._ws_send(websocket, {"type": "error", "error_msg": f"rewind failed: {exc}"})
            return
        await self._ws_send(websocket, {
            "type": "session_state",
            "session_id": session_manager.session_id,
            "transcript": session_manager.load_transcript(),
        })
        await self._ws_send(websocket, {
            "type": "session_list",
            "sessions": session_manager.list_sessions(),
        })

    async def _handle_switch_session(self, websocket: WebSocket, session_id: str) -> None:
        """切换到指定会话，加载历史 context 和 transcript 推送给前端。"""
        if not session_id:
            await self._ws_send(websocket, {"type": "error", "error_msg": "missing session_id"})
            return

        session_manager = self._session_managers.get("main")
        if session_manager is None:
            await self._ws_send(websocket, {"type": "error", "error_msg": "no active session"})
            return
        try:
            self._main_loop.replace_messages(session_manager.load_context(session_id))
        except Exception as exc:
            await self._ws_send(websocket, {"type": "error", "error_msg": f"switch session failed: {exc}"})
            return

        await self._ws_send(websocket, {
            "type": "session_state",
            "session_id": session_id,
            "transcript": session_manager.load_transcript(),
        })
        await self._ws_send(websocket, {
            "type": "session_list",
            "sessions": session_manager.list_sessions(),
        })

    async def _handle_load_teammate_session(self, websocket: WebSocket, name: str) -> None:
        """加载 teammate 的当前工作会话。"""
        if not name:
            await self._ws_send(websocket, {"type": "error", "error_msg": "missing name"})
            return
        session_manager = self._session_managers.get(name)
        if session_manager is None or not session_manager.session_id:
            await self._ws_send(websocket, {"type": "teammate_session_state", "source": name, "session_id": "", "transcript": []})
            return
        transcript = session_manager.load_transcript()
        await self._ws_send(websocket, {
            "type": "teammate_session_state",
            "source": name,
            "session_id": session_manager.session_id,
            "transcript": transcript,
        })

    async def _handle_new_session(self, websocket: WebSocket) -> None:
        """退出当前会话，清空状态。"""
        session_manager = self._session_managers.get("main")
        if session_manager:
            session_manager.detach_session()
        self._main_loop.clear_messages()
        await self._ws_send(websocket, {
            "type": "session_state",
            "session_id": None,
            "transcript": [],
        })

    # ======================== helpers ========================
    @staticmethod
    def _try_get_nonblock(q: queue.Queue) -> dict | None:
        """非阻塞取队列元素。"""
        try:
            return q.get(block=False)
        except queue.Empty:
            return None


    @staticmethod
    async def _ws_send(websocket: WebSocket, data: dict) -> None:
        """发送 WebSocket 消息，连接断开时静默丢弃。"""
        try:
            await websocket.send_json(data)
        except Exception:
            pass
