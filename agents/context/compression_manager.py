#!/usr/bin/env python3
"""
compression_manager.py

上下文压缩管理模块。

提供两级机制：
1. micro_compact：清理较旧工具结果，降低噪音与 context 消耗。
2. auto_compact：落盘完整会话后，让模型生成连续性摘要。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ContextCompressionManager:
    """上下文压缩管理器。"""

    def __init__(
        self,
        client: Any,
        model: str,
        backup_dir: Path,
        microcompact_tool_result_retention: int,
        compact_max_output_tokens: int,
        compact_prompt: str,
    ):
        self._client = client
        self._model = model
        self._backup_dir = backup_dir
        self._microcompact_tool_result_retention = microcompact_tool_result_retention
        self._compact_max_output_tokens = compact_max_output_tokens
        self._compact_prompt = compact_prompt

    # ======================== public ========================

    def micro_compact(self, messages: list):
        """保留最近 microcompact_tool_result_retention 条工具结果，清理其余工具调用结果。"""
        tool_results: list[dict[str, Any]] = []
        for message in messages:
            if message["role"] == "user" and isinstance(message.get("content"), list):
                for part in message["content"]:
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        tool_results.append(part)

        if len(tool_results) <= self._microcompact_tool_result_retention:
            return

        for part in tool_results[: -self._microcompact_tool_result_retention]:
            content = part.get("content")
            if isinstance(content, str):
                part["content"] = "[cleared]"


    def auto_compact(self, messages: list) -> list:
        """备份完整会话并将上下文替换为摘要。"""
        self._backup_dir.mkdir(exist_ok=True)
        backup_path = self._backup_dir / f"backup_{time.time_ns()}.jsonl"

        try:
            with backup_path.open("w") as f:
                for message in messages:
                    f.write(json.dumps(message, default=str, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"[compression] session backup failed: {exc}")
            return messages

        try:
            with self._client.messages.stream(
                model=self._model,
                system=self._compact_prompt,
                messages=messages,
                max_tokens=self._compact_max_output_tokens,
            ) as stream:
                response = stream.get_final_message()
            text_parts = [
                getattr(block, "text", "")
                for block in response.content
                if hasattr(block, "text")
            ]
            summary = "\n".join(text_parts).strip()
            if not summary:
                print("[compression] session summarization failed: empty summary.")
                return messages
            compact_messages = [{"role": "user", "content": summary}]
            return compact_messages
        except Exception as exc:
            print(f"[compression] session summarization failed: {exc}")
            return messages