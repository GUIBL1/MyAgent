#!/usr/bin/env python3
"""
subagent.py

subagent 执行模块。

subagent 拥有独立消息上下文，执行完成后仅返回摘要文本，用于隔离主对话上下文噪音。
对外提供 SubAgent 类，包含 run_subagent 工具方法。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any


class SubAgent:
    """SubAgent 类，封装 subagent 独立消息上下文循环。"""

    def __init__(
        self,
        client: Any,
        model: str,
        max_iterations: int,
        token_threshold: int,
        compact_threshold_pct: float,
        micro_compact_enabled: bool,
        max_output_tokens: int,
        explore_subagent_tools: list[dict[str, Any]],
        general_subagent_tools: list[dict[str, Any]],
        todo_manager: Any,
        context_compression_manager: Any,
        subagent_sessions_dir: Path,
        handlers: dict[str, Any],
        build_system_prompt: Any,
    ):
        self._client = client
        self._model = model
        self._max_iterations = max_iterations
        self._token_threshold = token_threshold
        self._compact_threshold_pct = compact_threshold_pct
        self._micro_compact_enabled = micro_compact_enabled
        self._max_output_tokens = max_output_tokens
        self._explore_subagent_tools = explore_subagent_tools
        self._general_subagent_tools = general_subagent_tools
        self._todo_manager = todo_manager
        self._context_compression_manager = context_compression_manager
        self._subagent_sessions_dir = subagent_sessions_dir
        self._handlers = handlers
        self._build_system_prompt = build_system_prompt

    # ======================== public ========================

    def run_subagent(
        self,
        prompt: str,
        agent_type: str = "explore",
        name: str = ""
    ) -> str:
        """运行 subagent 循环，并返回最终文本摘要。"""
        system_prompt = self._build_system_prompt(name)

        tools = self._explore_subagent_tools if agent_type == "explore" else self._general_subagent_tools
        session_path = self._build_session_path(name)

        todo_agent_name = ""
        rounds_without_todo = 0
        total_tokens = 0

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        self._write_jsonl(session_path, messages[0], mode="w")  # 首条消息，覆写模式写入

        response = None

        for _ in range(self._max_iterations):
            if self._context_compression_manager:
                if self._micro_compact_enabled:
                    self._context_compression_manager.micro_compact(messages)
                    self._write_jsonl(session_path, messages, mode="w")  # 覆写为压缩后的消息
                if total_tokens >= self._token_threshold * self._compact_threshold_pct:
                    print("[subagent auto-compact]")
                    messages[:] = self._context_compression_manager.auto_compact(messages)
                    total_tokens = 0
                    self._write_jsonl(session_path, messages, mode="w")  # 覆写为压缩后的消息

            try:
                with self._client.messages.stream(
                    model=self._model,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=self._max_output_tokens,
                ) as stream:
                    response = stream.get_final_message()
            except Exception as exc:
                return f"Subagent failed: LLM API error {exc}"

            total_tokens = response.usage.input_tokens + response.usage.output_tokens

            messages.append({"role": "assistant", "content": response.content})
            self._write_jsonl(session_path, messages[-1], mode="a")  # 追加模式写入最新消息

            if response.stop_reason != "tool_use":
                break

            results: list[dict[str, str]] = []
            used_todo = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                handler = self._handlers.get(tool_name)
                try:
                    output = (
                        handler(**tool_input)
                        if handler
                        else f"Unknown tool: {tool_name}."
                    )
                except Exception as exc:
                    output = f"Tool {tool_name} failed with error: {exc}"

                result_entry = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                }
                results.append(result_entry)

                if tool_name == "todo_write":
                    used_todo = True
                    todo_agent_name = tool_input.get("name", todo_agent_name)

            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if todo_agent_name and rounds_without_todo >= 3:
                if self._todo_manager and self._todo_manager.has_undo_items(todo_agent_name):
                    reminder = {"type": "text", "text": "<reminder>Update your todos.</reminder>"}
                    results.append(reminder)

            messages.append({"role": "user", "content": results})
            self._write_jsonl(session_path, messages[-1], mode="a")  # 追加模式写入最新消息

        if response:
            text_parts = [
                getattr(block, "text", "")
                for block in (getattr(response, "content", None) or [])
                if hasattr(block, "text")
            ]
            summary = "\n".join(text_parts).strip()
            return summary or "No summary."
        return "Subagent failed."

    # ======================== private ========================

    def _build_session_path(self, name: str) -> Path:
        """根据 name 与时间戳构造会话文件路径。"""
        safe = re.sub(r'[^\w]', '_', name.strip(), flags=re.UNICODE).strip('_') if name.strip() else "subagent"
        filename = f"{safe}_{int(time.time() * 1_000_000)}.jsonl"
        filepath = self._subagent_sessions_dir / filename
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
            print(f"[subagent] session write failed: {exc}")
