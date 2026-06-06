#!/usr/bin/env python3
"""
subagent.py

subagent 执行模块。

subagent 拥有独立消息上下文，执行完成后仅返回摘要文本，用于隔离主对话上下文噪音。
对外提供 SubAgent 类，包含 run_subagent 工具方法。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from agents.core.stream_events import EventType, StreamEvent


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
        self._handlers = handlers
        self._build_system_prompt = build_system_prompt

    # ======================== public ========================

    def run_subagent(
        self,
        prompt: str,
        agent_type: str = "explore",
        name: str = ""
    ) -> Iterator[StreamEvent | str]:
        """运行 subagent 循环，yield 事件流，最终 return 文本摘要。"""
        system_prompt = self._build_system_prompt(name)
        tools = self._explore_subagent_tools if agent_type == "explore" else self._general_subagent_tools

        todo_agent_name = ""
        rounds_without_todo = 0
        total_tokens = 0

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        response = None

        for _ in range(self._max_iterations):
            if self._context_compression_manager:
                if self._micro_compact_enabled:
                    for compact_event in self._context_compression_manager.micro_compact(messages):
                        if compact_event.event_type == EventType.MICRO_COMPACT:
                            yield compact_event
                if total_tokens >= self._token_threshold * self._compact_threshold_pct:
                    for compact_event in self._context_compression_manager.auto_compact(messages):
                        if compact_event.event_type == EventType.CONTEXT_ENTRY:
                            messages[:] = [json.loads(compact_event.content)]
                            total_tokens = 0
                        else:
                            yield compact_event

            try:
                with self._client.messages.stream(
                    model=self._model,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=self._max_output_tokens,
                ) as stream:
                    for api_event in stream:
                        if api_event.type == "content_block_delta":
                            if api_event.delta.type == "thinking_delta":
                                yield StreamEvent(
                                    type=EventType.THINKING,
                                    delta=api_event.delta.thinking,
                                )
                            elif api_event.delta.type == "text_delta":
                                yield StreamEvent(
                                    type=EventType.TEXT,
                                    delta=api_event.delta.text,
                                )

                    response = stream.get_final_message()
            except Exception as exc:
                yield StreamEvent(
                    type=EventType.ERROR,
                    error_msg=f"LLM API error: {exc}",
                )
                yield f"Subagent failed: LLM API error {exc}"
                return

            total_tokens = response.usage.input_tokens + response.usage.output_tokens

            yield StreamEvent(
                type=EventType.TOKEN_USAGE,
                content=f"本轮: {total_tokens} tokens (in: {response.usage.input_tokens}, out: {response.usage.output_tokens})",
            )

            messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in response.content]})

            if response.stop_reason != "tool_use":
                yield StreamEvent(type=EventType.ASSISTANT_DONE)
                break

            results: list[dict[str, str]] = []
            used_todo = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                yield StreamEvent(
                    type=EventType.TOOL_START,
                    tool_id=block.id,
                    tool_name=tool_name,
                    tool_input=dict(tool_input) if tool_input else {},
                )

                handler = self._handlers.get(tool_name)
                try:
                    handler_output = (
                        handler(**tool_input)
                        if handler
                        else f"Unknown tool: {tool_name}."
                    )
                except Exception as exc:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        tool_id=block.id,
                        error_msg=str(exc),
                    )
                    handler_output = f"Tool {tool_name} failed with error: {exc}"

                if isinstance(handler_output, str):
                    tool_result_content = handler_output
                elif hasattr(handler_output, '__iter__'):
                    # Generator handler（如 recall_memory）：逐事件流式推送
                    sub_panel_opened = False
                    final_result = ""
                    try:
                        for item in handler_output:
                            if isinstance(item, StreamEvent):
                                if not sub_panel_opened:
                                    yield StreamEvent(
                                        type=EventType.SUB_PANEL_ENTER,
                                        tool_id=block.id,
                                        tool_name=tool_name,
                                    )
                                    sub_panel_opened = True
                                yield item
                            else:
                                final_result = item
                        tool_result_content = str(final_result) if final_result else ""
                    except Exception as exc:
                        tool_result_content = f"Tool execution error: {exc}"
                    if sub_panel_opened:
                        yield StreamEvent(
                            type=EventType.SUB_PANEL_EXIT,
                            tool_id=block.id,
                        )
                else:
                    tool_result_content = str(handler_output)

                yield StreamEvent(
                    type=EventType.TOOL_RESULT,
                    tool_id=block.id,
                    content=tool_result_content,
                )

                result_entry = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_result_content,
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

        if response:
            text_parts = [
                getattr(block, "text", "")
                for block in (getattr(response, "content", None) or [])
                if hasattr(block, "text")
            ]
            summary = "\n".join(text_parts).strip()
            yield summary or "No summary."
        else:
            yield "Subagent failed."
