#!/usr/bin/env python3
"""
loop.py

主代理循环模块。

循环职责：
1. 调用压缩管线。
2. 注入后台通知与收件箱消息。
3. 执行模型工具调用。
4. 触发 Todo 提醒。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class MainLoop:
    """主代理循环，封装压缩管线、通知注入、工具调用与 Todo 提醒。"""

    def __init__(
        self,
        *,
        system_prompt: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Any],
        todo_manager: Any,
        context_compression_manager: Any,
        background_manager: Any,
        message_bus: Any,
        client: Any,
        model: str,
        token_threshold: int,
        compact_threshold_pct: float,
        micro_compact_enabled: bool,
        max_output_tokens: int,
        sessions_dir: Path | None = None,
        tool_display: Any = None,
    ):
        self._system_prompt = system_prompt
        self._tools = tools
        self._tool_handlers = tool_handlers
        self._todo_manager = todo_manager
        self._context_compression_manager = context_compression_manager
        self._background_manager = background_manager
        self._message_bus = message_bus
        self._client = client
        self._model = model
        self._token_threshold = token_threshold
        self._compact_threshold_pct = compact_threshold_pct
        self._micro_compact_enabled = micro_compact_enabled
        self._max_output_tokens = max_output_tokens
        self._sessions_dir = sessions_dir
        self._session_path = self._build_session_path() if self._sessions_dir else None
        self._tool_display = tool_display

    # ======================== public ========================

    def run_main_loop(self, messages: list) -> None:
        """执行主代理循环，直到模型停止发起工具调用。"""
        todo_agent_name = ""
        background_task_agent_name = "lead"
        rounds_without_todo = 0
        total_tokens = 0

        # 全量覆写会话文件，确保与 LLM 实际收到的 messages 一致。
        if self._session_path:
            self._write_jsonl(self._session_path, messages, mode="w")

        while True:
            # 每轮微压缩（受开关控制），超阈值触发全量压缩。
            if self._micro_compact_enabled:
                self._context_compression_manager.micro_compact(messages)
                if self._session_path:
                    self._write_jsonl(self._session_path, messages, mode="w")
            if total_tokens >= self._token_threshold * self._compact_threshold_pct:
                print("[auto-compact triggered]")
                messages[:] = self._context_compression_manager.auto_compact(messages)
                total_tokens = 0
                if self._session_path:
                    self._write_jsonl(self._session_path, messages, mode="w")

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
                            "content": f"<background-results>\n{background_task_result}\n</background-results>",
                        }
                    )
                    if self._session_path:
                        self._write_jsonl(self._session_path, messages[-1], mode="a")

            # 注入 lead 收件箱消息。
            inbox = self._message_bus.read_inbox("lead")
            if inbox:
                messages.append({"role": "user", "content": f"<inbox>\n{inbox}\n</inbox>"})
                if self._session_path:
                    self._write_jsonl(self._session_path, messages[-1], mode="a")

            in_thinking = False
            first_text = True
            with self._client.messages.stream(
                model=self._model,
                system=self._system_prompt,
                messages=messages,
                tools=self._tools,
                max_tokens=self._max_output_tokens,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "thinking":
                            in_thinking = True
                            print("\033[95m<think>\033[0m\n", end="", flush=True)
                        elif event.content_block.type == "text":
                            in_thinking = False

                    elif event.type == "content_block_delta":
                        if event.delta.type == "thinking_delta":
                            print(event.delta.thinking, end="", flush=True)
                        elif event.delta.type == "text_delta":
                            if in_thinking:
                                print("\n\033[95m</think>\033[0m", flush=True)
                                in_thinking = False
                            if first_text:
                                print("\033[96mReply >>\033[0m ", end="")
                                first_text = False
                            print(event.delta.text, end="", flush=True)

                    elif event.type == "content_block_stop":
                        if in_thinking:
                            print("\n\033[95m</think>\033[0m", flush=True)
                            in_thinking = False

                response = stream.get_final_message()
            if not first_text:
                print()

            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            messages.append({"role": "assistant", "content": response.content})
            if self._session_path:
                self._write_jsonl(self._session_path, messages[-1], mode="a")

            if response.stop_reason != "tool_use":
                return

            results: list[dict] = []
            used_todo = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if self._tool_display:
                    self._tool_display.show_call(block.name)
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

                if block.name == "todo_write":
                    used_todo = True
                    todo_agent_name = block.input.get("name", todo_agent_name)

                if block.name == "run_background_task":
                    background_task_agent_name = block.input.get("agent_name", background_task_agent_name)

            # 连续多轮未使用 todo 工具将触发提醒（前提是存在未完成的 todo 项）。
            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if todo_agent_name and self._todo_manager.has_undo_items(todo_agent_name) and rounds_without_todo >= 3:
                # 轻提醒，避免 Todo 状态长期不更新。
                results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})

            messages.append({"role": "user", "content": results})
            if self._session_path:
                self._write_jsonl(self._session_path, messages[-1], mode="a")

    # ======================== private ========================

    def _build_session_path(self) -> Path:
        """根据时间戳构造主代理会话文件路径。"""
        filename = f"main_agent_{int(time.time() * 1_000_000)}.jsonl"
        filepath = self._sessions_dir / filename
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
            print(f"[main_agent] session write failed: {exc}")
