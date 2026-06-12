"""WebSocket 连接处理 — 多路事件复用，统一 delta 合并、transcript、前端推送。"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from agents.core.container import MyAgentApp
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


class WsSession:
    """管理单个 WebSocket 连接的会话历史。"""

    def __init__(self, session_manager: Any):
        self.messages: list[dict[str, Any]] = []
        self.session_manager = session_manager


class WsHandler:
    """WebSocket 多路事件复用器。

    MainLoop 和 teammate 跑在独立线程，只做 yield → queue.put。
    协程 _drain_all 非阻塞轮询所有队列，统一 delta 合并、transcript、前端推送。
    """

    def __init__(self):
        self._agent_app = MyAgentApp()
        self._queues: dict[str, queue.Queue] = {}           # source → Queue
        self._buffers: dict[str, dict[str, str]] = {}        # source → {type: text}
        self._session_managers: dict[str, SessionManager] = {}    # source → SessionManager
        self._source_last_delta: dict[str, str] = {}         # source → last delta type

    # ======================== public ========================

    def push(self, source: str, data: dict) -> None:
        """线程安全：向指定管路的队列写入事件。"""
        q = self._queues.get(source)
        if q:
            q.put(data)

    def register_source(self, source: str, session_manager: SessionManager) -> None:
        """注册管路：队列并创建绑定 SessionManager（teammate 线程启动时调用）。"""
        self._queues[source] = queue.Queue()
        self._buffers[source] = {}
        self._session_managers[source] = session_manager
        self._source_last_delta[source] = ""

    async def handle(self, websocket: WebSocket) -> None:
        """接受 WS 连接，进入消息循环。"""
        await websocket.accept()

        # ── 初始化 main 管路 ──
        main_tx = SessionManager(sessions_dir=self._agent_app.main_agent_sessions_dir)
        self._queues["main"] = queue.Queue()
        self._buffers["main"] = {}
        self._session_managers["main"] = main_tx
        self._source_last_delta["main"] = ""
        session = WsSession(main_tx)

        # 推送会话列表，供前端左面板展示
        await _ws_send(websocket, {
            "type": "session_list",
            "sessions": main_tx.list_sessions(),
        })
        # 推送 MCP 服务器状态
        mcp_servers = self._agent_app.mcp_manager.get_server_status()
        await _ws_send(websocket, {
            "type": "mcp_info",
            "content": json.dumps({"servers": mcp_servers}, ensure_ascii=False),
        })
        # 推送 Skill 列表
        skills = self._agent_app.skill_manager.get_skill_list()
        await _ws_send(websocket, {
            "type": "skill_info",
            "content": json.dumps({"skills": skills}, ensure_ascii=False),
        })
        # 推送团队初始状态
        team = self._agent_app.teammate_manager.get_team_summary()
        await _ws_send(websocket, {
            "type": "team_update",
            "content": json.dumps(team, ensure_ascii=False),
        })

        # 注入 ws_handler 到 TeammateManager
        self._agent_app.teammate_manager._ws_handler = self

        # 启动 drain 协程
        drain_task = asyncio.create_task(self._drain_all(websocket))

        try:
            async for raw_message in websocket.iter_text():
                try:
                    msg: dict[str, Any] = json.loads(raw_message)
                except json.JSONDecodeError:
                    await _ws_send(websocket, {"type": "error", "error_msg": "invalid json"})
                    continue

                msg_type = msg.get("type")

                if msg_type == "send":
                    self._handle_send(session, msg.get("content", ""))
                elif msg_type == "rewind":
                    await self._handle_rewind(websocket, session, msg.get("turn", 1))
                elif msg_type == "switch_session":
                    await self._handle_switch_session(websocket, session, msg.get("session_id", ""))
                elif msg_type == "new_session":
                    await self._handle_new_session(websocket, session)
                elif msg_type == "load_teammate_session":
                    await self._handle_load_teammate_session(websocket, msg.get("name", ""))

        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            drain_task.cancel()

    # ======================== private: main agent 线程 ========================

    def _handle_send(self, session: WsSession, user_content: str) -> None:
        """main agent 线程入口。"""
        if not user_content.strip():
            self._queues["main"].put({"type": "error", "error_msg": "empty message"})
            return

        session_manager = session.session_manager
        
        # 首次发送：创建新会话
        if not session_manager.session_id:
            sid = session_manager.new_session()
            self._queues["main"].put({"type": "session_created", "session_id": sid})

        threading.Thread(
            target=self._run_main_agent,
            args=(session, user_content),
            daemon=True,
        ).start()

    def _run_main_agent(self, session: WsSession, user_content: str) -> None:
        """在独立线程中运行 main agent 循环，事件入 main 队列。"""
        session_manager = session.session_manager
        turn = session_manager.current_turn

        # 写入 transcript + LLM context
        session_manager.write_transcript({
            "turn": turn, "seq": session_manager.next_seq(), "type": "user_message", "content": user_content,
        })
        user_msg = {"role": "user", "content": user_content}
        session.messages.append(user_msg)
        # CONTEXT_ENTRY for user_message
        session_manager.write_transcript({
            "turn": turn, "seq": session_manager.next_seq(), "type": "context_entry", "content": json.dumps(user_msg, ensure_ascii=False),
        })
        # 推送 user_message 事件
        self._queues["main"].put({"type": "user_message", "content": user_content})

        try:
            for stream_event in self._agent_app.start_agent_loop(session):
                self._queues["main"].put(stream_event.to_dict())
        except Exception as exc:
            self._queues["main"].put({"type": "error", "error_msg": str(exc)})

        session_manager.advance_turn()
        self._queues["main"].put({
            "type": "session_list",
            "sessions": session_manager.list_sessions(),
        })

    # ======================== private: drain & dispatch ========================

    async def _drain_all(self, websocket: WebSocket) -> None:
        """协程：非阻塞轮询所有队列，逐事件分发。"""
        while True:
            had = False
            for source, q in dict(self._queues).items():
                d = _try_get_nonblock(q)
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
            await _ws_send(websocket, d)
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
            await _ws_send(websocket, d)

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
                await _ws_send(websocket, d)

    # ======================== private: 会话操作 ========================

    @staticmethod
    async def _handle_rewind(websocket: WebSocket, session: WsSession, turn: int) -> None:
        """回退到指定 turn。"""
        session_manager = session.session_manager
        try:
            session.messages = session_manager.rewind_to_turn(turn)
        except Exception as exc:
            await _ws_send(websocket, {"type": "error", "error_msg": f"rewind failed: {exc}"})
            return
        await _ws_send(websocket, {
            "type": "session_state",
            "session_id": session_manager.session_id,
            "transcript": session_manager.load_transcript(),
        })
        await _ws_send(websocket, {
            "type": "session_list",
            "sessions": session_manager.list_sessions(),
        })

    @staticmethod
    async def _handle_switch_session(websocket: WebSocket, session: WsSession, session_id: str) -> None:
        """切换到指定会话，加载历史 context 和 transcript 推送给前端。"""
        if not session_id:
            await _ws_send(websocket, {"type": "error", "error_msg": "missing session_id"})
            return

        session_manager = session.session_manager
        try:
            session.messages = session_manager.load_context(session_id)
        except Exception as exc:
            await _ws_send(websocket, {"type": "error", "error_msg": f"switch session failed: {exc}"})
            return
        
        await _ws_send(websocket, {
            "type": "session_state",
            "session_id": session_id,
            "transcript": session_manager.load_transcript(),
        })
        await _ws_send(websocket, {
            "type": "session_list",
            "sessions": session_manager.list_sessions(),
        })

    async def _handle_load_teammate_session(self, websocket: WebSocket, name: str) -> None:
        """加载 teammate 的当前工作会话。"""
        if not name:
            await _ws_send(websocket, {"type": "error", "error_msg": "missing name"})
            return
        session_manager = self._session_managers.get(name)
        if session_manager is None or not session_manager.session_id:
            await _ws_send(websocket, {"type": "teammate_session_state", "source": name, "session_id": "", "transcript": []})
            return
        transcript = session_manager.load_transcript()
        await _ws_send(websocket, {
            "type": "teammate_session_state",
            "source": name,
            "session_id": session_manager.session_id,
            "transcript": transcript,
        })

    @staticmethod
    async def _handle_new_session(websocket: WebSocket, session: WsSession) -> None:
        """退出当前会话，清空状态。"""
        session_manager = session.session_manager
        session_manager.detach_session()
        session.messages = []
        await _ws_send(websocket, {
            "type": "session_state",
            "session_id": None,
            "transcript": [],
        })


# ======================== helpers ========================

def _try_get_nonblock(q: queue.Queue) -> dict | None:
    """非阻塞取队列元素。"""
    try:
        return q.get(block=False)
    except queue.Empty:
        return None


async def _ws_send(websocket: WebSocket, data: dict) -> None:
    """发送 WebSocket 消息，连接断开时静默丢弃。"""
    try:
        await websocket.send_json(data)
    except Exception:
        pass
