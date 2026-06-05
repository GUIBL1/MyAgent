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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agents.core.stream_events import EventType, StreamEvent


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

    def micro_compact(self, messages: list) -> Iterator[StreamEvent]:
        """保留最近 microcompact_tool_result_retention 条工具结果，清理其余工具调用结果。"""
        tool_results: list[tuple[int, int, dict[str, Any]]] = []  # (msg_idx, part_idx, part)
        for i, message in enumerate(messages):
            if message["role"] == "user" and isinstance(message.get("content"), list):
                for j, part in enumerate(message["content"]):
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        tool_results.append((i, j, part))

        if len(tool_results) <= self._microcompact_tool_result_retention:
            return

        cleared_count = 0
        patches: list[dict[str, Any]] = []
        total_messages = len(messages)
        for msg_idx, part_idx, part in tool_results[: -self._microcompact_tool_result_retention]:
            content = part.get("content")
            if isinstance(content, str) and content != "[cleared]":
                part["content"] = "[cleared]"
                cleared_count += 1
                # rev_msg_idx：逆序，0=最后一条 message，total_messages-1 前=最早
                patches.append({
                    "rev_msg_idx": total_messages - 1 - msg_idx,
                    "part_idx": part_idx,
                    "new_entry": {
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": part.get("tool_use_id", ""),
                            "content": "[cleared]",
                        }],
                    },
                })

        if cleared_count == 0:
            return

        yield StreamEvent(
            type=EventType.MICRO_COMPACT,
            content=f"已移除 {cleared_count} 条旧 tool result · 保留最近 {self._microcompact_tool_result_retention} 轮",
        )

        if patches:
            yield StreamEvent(
                type=EventType.CONTEXT_PATCH,
                content=json.dumps(patches, ensure_ascii=False),
            )

    def auto_compact(self, messages: list) -> Iterator[StreamEvent]:
        """全量压缩：备份 → 调模型生成摘要。"""
        self._backup_dir.mkdir(exist_ok=True)
        backup_path = self._backup_dir / f"backup_{time.time_ns()}.jsonl"

        try:
            with backup_path.open("w") as f:
                for message in messages:
                    f.write(json.dumps(message, default=str, ensure_ascii=False) + "\n")
        except OSError as exc:
            yield StreamEvent(type=EventType.AUTO_COMPACT_DONE, content=f"备份失败: {exc}")
            return

        yield StreamEvent(
            type=EventType.AUTO_COMPACT_START,
            content=f"上下文接近上限 · {len(messages)} 条消息 · 正在生成摘要",
        )

        try:
            with self._client.messages.stream(
                model=self._model,
                system=self._compact_prompt,
                messages=messages,
                max_tokens=self._compact_max_output_tokens,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "thinking_delta":
                            yield StreamEvent(type=EventType.AUTO_COMPACT_THINKING, delta=event.delta.thinking)
                        elif event.delta.type == "text_delta":
                            yield StreamEvent(type=EventType.AUTO_COMPACT_TEXT, delta=event.delta.text)

                response = stream.get_final_message()

            text_parts = [
                getattr(block, "text", "")
                for block in response.content
                if hasattr(block, "text")
            ]
            summary = "\n".join(text_parts).strip()

            if not summary:
                yield StreamEvent(type=EventType.AUTO_COMPACT_DONE, content="压缩失败：摘要为空")
                return

            yield StreamEvent(type=EventType.AUTO_COMPACT_DONE, content="压缩完成")
            compact_msg = {"role": "user", "content": summary}
            yield StreamEvent(
                type=EventType.CONTEXT_ENTRY,
                content=json.dumps(compact_msg, ensure_ascii=False),
            )

        except Exception as exc:
            yield StreamEvent(type=EventType.AUTO_COMPACT_DONE, content=f"压缩失败: {exc}")
