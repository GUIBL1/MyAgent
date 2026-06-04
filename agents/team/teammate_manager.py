#!/usr/bin/env python3
"""
teammate_manager.py

agent team 管理模块。

职责：
1. 维护 teammate 生命周期（working / idle / shutdown）。
2. 在独立线程中运行 teammate agent 循环。
3. 支持空闲轮询自动认领任务与读收件箱消息。
4. 支持关机响应与计划审批提交。

agent team 文件存储结构:
WORKDIR/.MyAgent/team/
    team_config.json  # 团队成员与状态配置
    inbox/            # 消息收件箱目录，每个成员一个 JSONL 文件
        <name>.jsonl

文件存储结构：

team_config.json:
    {
        "team_name": "default",
        "members":
        [
            {"name": "alice", "role": "tester", "status": "working|idle|shutdown"},
            ...
        ]
    }

inbox/<name>.jsonl — 每行一条 JSON：

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
import os
import re
import stat
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


class TeammateManager:
    """持久 teammate 线程管理器。"""

    def __init__(
        self,
        team_dir: Path,
        message_bus : Any,
        task_manager: Any,
        client: Any,
        model: str,
        workdir: Path,
        poll_interval: int,
        idle_timeout: int,
        tool_handlers: dict,
        tools: list[dict],
        build_system_prompt: Any,
        context_compression_manager: Any = None,
        todo_manager: Any = None,
        background_manager: Any = None,
        token_threshold: int = 100000,
        compact_threshold_pct: float = 0.8,
        micro_compact_enabled: bool = False,
        max_iterations: int = 50,
        max_output_tokens: int = 10000,
        teammate_sessions_dir: Path | None = None,
    ):
        self._team_dir = team_dir
        self._team_dir.mkdir(exist_ok=True)

        self._message_bus = message_bus
        self._task_manager = task_manager
        self._tool_handlers = tool_handlers
        self._tools = tools
        self._build_system_prompt = build_system_prompt
        self._context_compression_manager = context_compression_manager
        self._todo_manager = todo_manager
        self._background_manager = background_manager
        self._token_threshold = token_threshold
        self._compact_threshold_pct = compact_threshold_pct
        self._micro_compact_enabled = micro_compact_enabled

        self._client = client
        self._model = model
        self._workdir = workdir
        self._poll_interval = poll_interval
        self._idle_timeout = idle_timeout
        self._max_iterations = max_iterations
        self._max_output_tokens = max_output_tokens
        self._teammate_sessions_dir = teammate_sessions_dir

        #读写锁，保护 team_config 的并发访问（内存数据与文件数据）
        self._team_config_lock = threading.RLock()
        self._team_config_path = self._team_dir / "team_config.json"
        self._team_config = self._load_config()

    # ======================== public ========================
    def spawn_teammate(self, name: str, role: str, prompt: str) -> str:
        """启动一个新的 teammate，或重启 shutdown 的 teammate。"""
        with self._team_config_lock:
            member = self._find_member(name)
            if member:
                if member["status"] != "shutdown":
                    return f"Error: '{name}' is currently active with status '{member['status']}'."

                member["status"] = "working"
                member["role"] = role
            else:
                member = {"name": name, "role": role, "status": "working"}
                self._team_config["members"].append(member)
            self._save_config()

        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
        )
        thread.start()

        return f"Successfully spawned a teammate with name: {name}, role: {role}."


    def get_team_config(self) -> str:
        """返回 agent team 配置（队名、成员列表）。"""
        with self._team_config_lock:
            return json.dumps(self._team_config, indent=2, ensure_ascii=False)


    def idle(self) -> str:
        """占位 idle 方法，保持接口完整性。"""
        return "Enter idle phase."

    # ======================== private ========================
    def _load_config(self) -> dict:
        """加载团队配置；若不存在则返回默认结构，并确保 lead 始终在成员列表中。"""
        if self._team_config_path.exists():
            with self._team_config_lock:
                config = json.loads(self._team_config_path.read_text(encoding="utf-8"))
        else:
            config = {"team_name": "default", "members": []}

        # 确保 lead 始终存在于团队配置中（主 agent 不通过 spawn_teammate 创建）
        members = config.setdefault("members", [])
        if not any(member["name"] == "lead" for member in members):
            members.append({"name": "lead", "role": "lead", "status": "working"})
        return config

    def _save_config(self):
        """原子保存团队配置到磁盘。"""
        with self._team_config_lock:
            content = json.dumps(self._team_config, indent=2, ensure_ascii=False)
            self._atomic_write_text(self._team_config_path, content)

    @staticmethod
    def _atomic_write_text(file_path: Path, content: str) -> None:
        """通过临时文件 + 原子替换落盘，避免半写入状态，继承原有权限。"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=file_path.parent,
                delete=False,
            ) as tmp:
                tmp.write(content)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)

            if file_path.exists():
                current_mode = stat.S_IMODE(file_path.stat().st_mode)
                os.chmod(temp_path, current_mode)

            os.replace(temp_path, file_path)
            try:
                dir_fd = os.open(str(file_path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _find_member(self, name: str) -> dict | None:
        """按名称查找成员记录。"""
        with self._team_config_lock:
            for member in self._team_config["members"]:
                if member["name"] == name:
                    return member
        return None

    def _set_status(self, name: str, status: str):
        """更新并持久化成员状态。"""
        with self._team_config_lock:
            member = self._find_member(name)
            if member:
                member["status"] = status
                self._save_config()

    def _teammate_loop(self, name: str, role: str, prompt: str):
        """teammate 的主循环（工作阶段 + 空闲阶段）。"""
        with self._team_config_lock:
            team_name = self._team_config.get("team_name", "default")
        system_prompt = self._build_system_prompt(
            name=name, role=role, team_name=team_name, workdir=str(self._workdir)
        )

        messages: list[dict] = [{"role": "user", "content": prompt}]
        session_path = self._build_session_path(name) if self._teammate_sessions_dir else None
        if session_path:
            self._write_jsonl(session_path, messages[0], mode="w")

        todo_agent_name = ""
        rounds_without_todo = 0
        background_task_agent_name = ""
        total_tokens = 0
        shutdown_approve = False

        while True:
            # 工作阶段：正常工具调用循环。
            for _ in range(self._max_iterations):
                # 每轮微压缩（受开关控制），超阈值触发全量压缩。
                if self._context_compression_manager:
                    if self._micro_compact_enabled:
                        self._context_compression_manager.micro_compact(messages)
                        if session_path:
                            self._write_jsonl(session_path, messages, mode="w")
                    if total_tokens >= self._token_threshold * self._compact_threshold_pct:
                        print(f"[teammate:{name} auto-compact]")
                        messages[:] = self._context_compression_manager.auto_compact(messages)
                        total_tokens = 0
                        if session_path:
                            self._write_jsonl(session_path, messages, mode="w")

                # 注入后台任务通知。
                if self._background_manager and background_task_agent_name:
                    notifications = self._background_manager.drain_and_get_notifications(agent_name=background_task_agent_name)
                    if notifications:
                        background_task_result = "\n\n".join(
                            f"Background task notification received (task id = {notification['background_task_id']})\ncommand: {notification['command']}\nstatus: {notification['status']}\nresult: {notification['result']}."
                            for notification in notifications
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": f"<background-task-results>\n{background_task_result}\n</background-task-results>",
                            }
                        )
                        if session_path:
                            self._write_jsonl(session_path, messages[-1], mode="a")

                # 注入收件箱消息。
                inbox = self._message_bus.read_inbox(name)
                if inbox:
                    messages.append({"role": "user", "content": f"<inbox>\n{inbox}\n</inbox>"})
                    if session_path:
                        self._write_jsonl(session_path, messages[-1], mode="a")

                try:
                    with self._client.messages.stream(
                        model=self._model,
                        system=system_prompt,
                        messages=messages,
                        tools=self._tools,
                        max_tokens=self._max_output_tokens,
                    ) as stream:
                        response = stream.get_final_message()
                except Exception:
                    self._set_status(name, "shutdown")
                    return

                total_tokens = response.usage.input_tokens + response.usage.output_tokens
                messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in response.content]})
                if session_path:
                    self._write_jsonl(session_path, messages[-1], mode="a")

                if response.stop_reason != "tool_use":
                    break

                results: list[dict] = []
                idle_requested = False
                used_todo = False

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    handler = self._tool_handlers.get(block.name)
                    try:
                        output = handler(**block.input) if handler else f"Unknown tool: {block.name}."
                    except Exception as exc:
                        output = f"Tool execution error: {exc}"

                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(output),
                        }
                    )

                    if block.name == "idle":
                        idle_requested = True

                    if block.name == "todo_write":
                        used_todo = True
                        todo_agent_name = block.input.get("name", todo_agent_name)

                    if block.name == "run_background_task":
                        background_task_agent_name = block.input.get("agent_name", background_task_agent_name)

                    if block.name == "shutdown_response" and block.input.get("decision") == "approved":
                        shutdown_approve = True


                # 连续多轮未使用 todo 工具将触发提醒（前提是存在未完成的 todo 项）。
                rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
                if todo_agent_name and rounds_without_todo >= 3:
                    if self._todo_manager and self._todo_manager.has_undo_items(todo_agent_name):
                        results.append(
                            {"type": "text", "text": "<reminder>Update your todos.</reminder>"}
                        )

                messages.append({"role": "user", "content": results})
                if session_path:
                    self._write_jsonl(session_path, messages[-1], mode="a")

                if idle_requested or shutdown_approve:
                    break


            if shutdown_approve:
                self._set_status(name, "shutdown")
                return

            # 空闲阶段：轮询新消息与认领空闲任务。
            self._set_status(name, "idle")
            resume = False

            poll_count = self._idle_timeout // max(self._poll_interval, 1)
            for _ in range(poll_count):
                time.sleep(self._poll_interval)

                # 检查是否有新消息，如果有则恢复工作循环优先处理。
                inbox = self._message_bus.read_inbox(name)
                if inbox:
                    messages.append({"role": "user", "content": f"<inbox>\n{inbox}\n</inbox>"})
                    if session_path:
                        self._write_jsonl(session_path, messages[-1], mode="a")
                    resume = True
                    break

                # 原子扫描并认领第一个空闲任务。
                claim_result = self._task_manager.scan_and_claim(name)
                if  claim_result:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"<auto-claimed-task>\n{claim_result}\n</auto-claimed-task>",
                        }
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "Task claimed. Working on it.",
                        }
                    )
                    if session_path:
                        self._write_jsonl(session_path, messages[-2:], mode="a")
                    resume = True
                    break


            if not resume:
                self._set_status(name, "shutdown")
                return

            self._set_status(name, "working")

    def _build_session_path(self, name: str) -> Path:
        """根据 name 与时间戳构造会话文件路径。"""
        safe = re.sub(r'[^\w]', '_', name.strip(), flags=re.UNICODE).strip('_') if name.strip() else "teammate"
        filename = f"{safe}_{int(time.time() * 1_000_000)}.jsonl"
        filepath = self._teammate_sessions_dir / filename
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return filepath

    def _write_jsonl(self, filepath: Path, entry: Any, mode: str = "a") -> None:
        """写入 JSONL 文件。entry 为单条消息或消息列表。mode="a" 追加，mode="w" 覆写。异常时仅打印警告。"""
        entries = entry if isinstance(entry, list) else [entry]
        try:
            with open(filepath, mode, encoding="utf-8") as f:
                for item in entries:
                    f.write(json.dumps(item, default=str, ensure_ascii=False) + "\n")
        except (OSError, TypeError) as exc:
            print(f"[teammate] session write failed: {exc}")
