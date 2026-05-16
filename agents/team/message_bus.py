#!/usr/bin/env python3
"""
message_bus.py

文件消息总线模块。

每个角色对应一个 JSONL 收件箱文件：`WORKDIR/.MyAgent/team/inbox/<name>.jsonl`。
读取收件箱后会自动清空消息。

文件数据结构：
    inbox/<name>.jsonl — 每行一条 JSON。

    通用字段（所有消息类型）：
        message_type: "message" | "message_reply" | "broadcast" | "shutdown_request" | "shutdown_response" | "plan_approval_request" | "plan_approval_response"
        from:         发送者名称
        content:      消息正文
        communication_id: 会话唯一标识
        timestamp:    消息时间戳

    额外字段（仅 response 类型）：
        decision:     "approved" | "rejected"（仅 shutdown_response、plan_approval_response）
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path


class MessageBus:
    """消息总线类，提供发送、回应、广播消息以及协议相关的接口。"""

    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self._inbox_locks: dict[str, threading.RLock] = {}

    # ======================== 消息收发 ========================

    def send_message(
            self,
            sender: str,
            receiver: str,
            content: str,
            message_type: str = "message"
        ) -> str:
        """向指定角色发送消息，返回发送结果字符串。"""
        if message_type != "message":
            return f"Unsupported message type: {message_type}, only 'message' is allowed."

        communication_id = str(uuid.uuid4())[:8]
        message = self._build_message(message_type, sender, content, communication_id)
        self._write_inbox(receiver, message)
        return f"Sent {message_type} to {receiver} (binding communication_id={communication_id})."


    def reply_message(
            self,
            sender: str,
            receiver: str,
            content: str,
            communication_id: str,
            message_type: str = "message_reply"
        ) -> str:
        """回复指定 communication_id 的消息。"""
        if message_type != "message_reply":
            return f"Unsupported message type: {message_type}, only 'message_reply' is allowed."

        message = self._build_message(message_type, sender, content, communication_id)
        self._write_inbox(receiver, message)
        return f"Replied {message_type} to {receiver} (binding communication_id={communication_id})."


    def read_inbox(self, name: str, tool_call: bool = False) -> str:
        """读取并清空指定角色收件箱。tool_call=True 时返回对 agent 友好的提示文本。"""
        lock = self._inbox_locks.setdefault(name, threading.RLock())
        with lock:
            inbox_path = self.inbox_dir / f"{name}.jsonl"
            if not inbox_path.exists():
                return "No messages." if tool_call else ""

            lines = [line for line in inbox_path.read_text(encoding="utf-8").strip().splitlines() if line]
            inbox_path.write_text("", encoding="utf-8")
            if not lines:
                return "No messages." if tool_call else ""

            msgs = [json.loads(line) for line in lines]
            parts: list[str] = []
            for i, msg in enumerate(msgs, 1):
                fields = [
                    f"Message {i}:",
                    f"  Sent from (sender name): {msg.get('from', 'unknown')}",
                    f"  Message type (message category): {msg.get('message_type', 'unknown')}",
                    f"  Content (message body): {msg.get('content', '')}",
                    f"  Communication ID (conversation binding): {msg.get('communication_id', '')}",
                    f"  Timestamp (send time): {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('timestamp', 0)))}",
                ]
                if msg.get("decision"):
                    fields.append(f"  Decision (approved / rejected): {msg['decision']}")
                parts.append("\n".join(fields))
            return "Received messages:\n" + "\n".join(parts)


    def broadcast(
            self,
            sender: str,
            content: str,
            receiver_list: list[str],
            message_type: str = "broadcast"
        ) -> str:
        """向指定角色列表广播消息。"""
        if message_type != "broadcast":
            return f"Unsupported message type: {message_type}, only 'broadcast' is allowed."

        receivers = [name for name in receiver_list if name != sender]
        if not receivers:
            return "No receivers to broadcast to."

        summary = []
        for receiver in receivers:
            communication_id = str(uuid.uuid4())[:8]
            message = self._build_message(message_type, sender, content, communication_id)
            self._write_inbox(receiver, message)
            summary.append(f"{receiver} (binding communication_id={communication_id})")

        return f"Broadcast to teammates: {', '.join(summary)}."

    # ======================== 关机协议 ========================

    def shutdown_request(
            self,
            sender: str,
            receiver: str,
            content: str,
            message_type: str = "shutdown_request"
        ) -> str:
        """发起关机请求。"""
        if message_type != "shutdown_request":
            return f"Unsupported message type: {message_type}, only 'shutdown_request' is allowed."

        communication_id = str(uuid.uuid4())[:8]
        message = self._build_message(message_type, sender, content, communication_id)
        self._write_inbox(receiver, message)
        return f"Sent {message_type} to {receiver} (binding communication_id={communication_id})."


    def shutdown_response(
            self,
            sender: str,
            receiver: str,
            content: str,
            communication_id: str,
            decision: str,
            message_type: str = "shutdown_response"
        ) -> str:
        """响应关机请求。"""
        if message_type != "shutdown_response":
            return f"Unsupported message type: {message_type}, only 'shutdown_response' is allowed."

        message = self._build_message(message_type, sender, content, communication_id, decision)
        self._write_inbox(receiver, message)
        return f"Replied {message_type} to {receiver} (binding communication_id={communication_id})."

    # ======================== 计划审批协议 ========================

    def plan_approval_request(
            self,
            sender: str,
            receiver: str,
            content: str,
            message_type: str = "plan_approval_request"
        ) -> str:
        """提交计划供审批。"""
        if message_type != "plan_approval_request":
            return f"Unsupported message type: {message_type}, only 'plan_approval_request' is allowed."

        communication_id = str(uuid.uuid4())[:8]
        message = self._build_message(message_type, sender, content, communication_id)
        self._write_inbox(receiver, message)
        return f"Sent {message_type} to {receiver} (binding communication_id={communication_id})."


    def plan_approval_response(
            self,
            sender: str,
            receiver: str,
            content: str,
            communication_id: str,
            decision: str,
            message_type: str = "plan_approval_response"
        ) -> str:
        """审批计划并回传结果。"""
        if message_type != "plan_approval_response":
            return f"Unsupported message type: {message_type}, only 'plan_approval_response' is allowed."

        message = self._build_message(message_type, sender, content, communication_id, decision)
        self._write_inbox(receiver, message)
        return f"Replied {message_type} to {receiver} (binding communication_id={communication_id})."

    # ======================== private ========================

    @staticmethod
    def _build_message(message_type: str, sender: str, content: str, communication_id: str, decision: str | None = None) -> dict:
        """构建标准消息体。"""
        msg = {
            "message_type": message_type,
            "from": sender,
            "content": content,
            "communication_id": communication_id,
            "timestamp": time.time(),
        }
        if decision:
            msg["decision"] = decision
        return msg

    def _write_inbox(self, receiver: str, message: dict):
        """线程安全地将消息写入收件箱文件。"""
        lock = self._inbox_locks.setdefault(receiver, threading.RLock())
        with lock:
            inbox_path = self.inbox_dir / f"{receiver}.jsonl"
            with inbox_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
