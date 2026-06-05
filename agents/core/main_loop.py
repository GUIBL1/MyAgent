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
from collections.abc import Iterator
from typing import Any

from agents.core.stream_events import EventType, StreamEvent


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

    # ======================== public ========================

    def run_main_loop(self, session: Any) -> Iterator[StreamEvent]:
        """执行主代理循环，直到模型停止发起工具调用。"""
        messages = session.messages
        session_manager = session.session_manager

        todo_agent_name = ""
        background_task_agent_name = "lead"
        rounds_without_todo = 0
        total_tokens = 0

        # 覆写 context.jsonl
        if session_manager.session_id:
            session_manager.save_context_full(messages)

        while True:
            # 每轮微压缩（受开关控制），超阈值触发全量压缩。
            if self._micro_compact_enabled:
                yield from self._context_compression_manager.micro_compact(messages)
                if session_manager.session_id:
                    session_manager.save_context_full(messages)
            # 全量压缩
            if total_tokens >= self._token_threshold * self._compact_threshold_pct:
                for compact_event in self._context_compression_manager.auto_compact(messages):
                    yield compact_event
                    if compact_event.event_type == EventType.CONTEXT_ENTRY:
                        # 摘要替换 messages
                        ce = json.loads(compact_event.content)
                        messages[:] = [ce]
                        total_tokens = 0
                        if session_manager.session_id:
                            session_manager.save_context_full(messages)

            # 注入后台任务通知。
            if self._background_manager and background_task_agent_name:
                notifications = self._background_manager.drain_and_get_notifications(agent_name=background_task_agent_name)
                if notifications:
                    background_task_result = "\n\n".join(
                        f"Background task notification received (task id = {notification['background_task_id']})\ncommand: {notification['command']}\nstatus: {notification['status']}\nresult: {notification['result']}."
                        for notification in notifications
                    )
                    bg_msg = f"<background-results>\n{background_task_result}\n</background-results>"

                    yield StreamEvent(
                        type=EventType.BACKGROUND_NOTIFICATION,
                        content=background_task_result,
                    )
                    yield StreamEvent(
                        type=EventType.CONTEXT_ENTRY,
                        content=json.dumps({"role": "user", "content": bg_msg}, ensure_ascii=False, default=str),
                    )
                    messages.append({"role": "user", "content": bg_msg})
                    if session_manager.session_id:
                        session_manager.write_context(messages[-1])

            # 注入 lead 收件箱消息。
            inbox = self._message_bus.read_inbox("lead")
            if inbox:
                yield StreamEvent(
                    type=EventType.INBOX_MESSAGE,
                    content=inbox,
                )
                yield StreamEvent(
                    type=EventType.CONTEXT_ENTRY,
                    content=json.dumps({"role": "user", "content": f"<inbox>\n{inbox}\n</inbox>"}, ensure_ascii=False, default=str),
                )
                messages.append({"role": "user", "content": f"<inbox>\n{inbox}\n</inbox>"})
                if session_manager.session_id:
                    session_manager.write_context(messages[-1])

            with self._client.messages.stream(
                model=self._model,
                system=self._system_prompt,
                messages=messages,
                tools=self._tools,
                max_tokens=self._max_output_tokens,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "thinking_delta":
                            yield StreamEvent(type=EventType.THINKING, delta=event.delta.thinking)
                        elif event.delta.type == "text_delta":
                            yield StreamEvent(type=EventType.TEXT, delta=event.delta.text)

                response = stream.get_final_message()

            total_tokens = response.usage.input_tokens + response.usage.output_tokens

            yield StreamEvent(
                type=EventType.TOKEN_USAGE,
                content=f"本轮: {total_tokens} tokens (in: {response.usage.input_tokens}, out: {response.usage.output_tokens})",
            )

            assistant_content = [b.model_dump(exclude_none=True) for b in response.content]
            messages.append({"role": "assistant", "content": assistant_content})
            if session_manager.session_id:
                session_manager.write_context(messages[-1])
            yield StreamEvent(
                type=EventType.CONTEXT_ENTRY,
                content=json.dumps({"role": "assistant", "content": assistant_content}, ensure_ascii=False, default=str),
            )

            if response.stop_reason != "tool_use":
                yield StreamEvent(type=EventType.ASSISTANT_DONE, stop_reason=response.stop_reason)
                return

            results: list[dict] = []
            used_todo = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                yield StreamEvent(
                    type=EventType.TOOL_START,
                    tool_id=block.id,
                    tool_name=block.name,
                    tool_input=dict(block.input) if block.input else {},
                )

                handler = self._tool_handlers.get(block.name)
                try:
                    handler_output = handler(**block.input) if handler else f"Unknown tool: {block.name}."
                except Exception as exc:
                    handler_output = f"Tool execution error: {exc}"

                if isinstance(handler_output, str):
                    tool_result_content = handler_output
                    sub_events: list[StreamEvent] = []
                elif hasattr(handler_output, '__iter__'):
                    # Generator handler（如 subagent）：收集子事件 + 最终 return 值
                    sub_events = []
                    final_result = ""
                    try:
                        for item in handler_output:
                            if isinstance(item, StreamEvent):
                                sub_events.append(item)
                            else:
                                final_result = item
                        tool_result_content = str(final_result) if final_result else ""
                    except Exception as exc:
                        tool_result_content = f"Tool execution error: {exc}"
                else:
                    tool_result_content = str(handler_output)
                    sub_events = []

                # 转发子事件到前端子面板
                if sub_events:
                    yield StreamEvent(
                        type=EventType.SUB_PANEL_ENTER,
                        tool_id=block.id,
                        tool_name=block.name,
                    )
                    yield from sub_events
                    yield StreamEvent(
                        type=EventType.SUB_PANEL_EXIT,
                        tool_id=block.id,
                    )

                # 主 tool 结果
                yield StreamEvent(
                    type=EventType.TOOL_RESULT,
                    tool_id=block.id,
                    content=tool_result_content,
                )

                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_result_content,
                })

                if block.name == "todo_write":
                    used_todo = True
                    if isinstance(block.input, dict):
                        todo_agent_name = block.input.get("name", todo_agent_name)

                if block.name == "run_background_task":
                    if isinstance(block.input, dict):
                        background_task_agent_name = block.input.get("agent_name", background_task_agent_name)

            # 连续多轮未使用 todo 工具将触发提醒（前提是存在未完成的 todo 项）。
            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if todo_agent_name and self._todo_manager.has_undo_items(todo_agent_name) and rounds_without_todo >= 3:
                yield StreamEvent(
                    type=EventType.TODO_REMINDER,
                    content="Update your todos.",
                )
                yield StreamEvent(
                    type=EventType.CONTEXT_ENTRY,
                    content=json.dumps({"role": "user", "content": "<reminder>Update your todos.</reminder>"}, ensure_ascii=False, default=str),
                )
                results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})

            messages.append({"role": "user", "content": results})
            if session_manager.session_id:
                session_manager.write_context(messages[-1])
            yield StreamEvent(
                type=EventType.CONTEXT_ENTRY,
                content=json.dumps({"role": "user", "content": results}, ensure_ascii=False, default=str),
            )
