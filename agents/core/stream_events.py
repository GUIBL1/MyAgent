"""
流事件类型定义

MainLoop / SubAgent / Compact 等模块产出的标准化事件，供 WebSocket 消费。

事件按前端渲染方式分为三类：
渲染事件：TEXT / THINKING / TOOL_START / TOOL_RESULT / ASSISTANT_DONE / ERROR
    前端直接渲染到当前面板（主对话或子面板，由 SUB_PANEL_ENTER/EXIT 控制切换）
状态事件：MICRO_COMPACT / AUTO_COMPACT_* / BACKGROUND_NOTIFICATION / INBOX_MESSAGE /TODO_REMINDER / TOKEN_USAGE
    各有独特 UI，前端按类型区分渲染
非渲染事件：CONTEXT_ENTRY / CONTEXT_PATCH
    不推前端，仅写 transcript.jsonl 供会话回放和 rewind
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class EventType(Enum):
    """流事件类型枚举。"""

    # === 渲染事件 ===
    TEXT = "text"
    THINKING = "thinking"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    ASSISTANT_DONE = "assistant_done"
    ERROR = "error"

    # === 子面板切换 ===
    SUB_PANEL_ENTER = "sub_panel_enter"
    SUB_PANEL_EXIT = "sub_panel_exit"

    # === 状态事件 ===
    MICRO_COMPACT = "micro_compact"
    AUTO_COMPACT_START = "auto_compact_start"
    AUTO_COMPACT_THINKING = "auto_compact_thinking"
    AUTO_COMPACT_TEXT = "auto_compact_text"
    AUTO_COMPACT_DONE = "auto_compact_done"
    BACKGROUND_NOTIFICATION = "background_notification"
    INBOX_MESSAGE = "inbox_message"
    TASK_CLAIMED = "task_claimed"
    TODO_REMINDER = "todo_reminder"
    TODO_UPDATE = "todo_update"
    TEAM_UPDATE = "team_update"
    TOKEN_USAGE = "token_usage"

    # === Memory Recall 管道事件 ===
    RECALL_EXPAND_START = "recall_expand_start"
    RECALL_EXPAND_THINKING = "recall_expand_thinking"
    RECALL_EXPAND_TEXT = "recall_expand_text"
    RECALL_EXPAND_DONE = "recall_expand_done"
    RECALL_QUERY_START = "recall_query_start"
    RECALL_QUERY_RESULT = "recall_query_result"
    RECALL_RETRIEVE_DONE = "recall_retrieve_done"
    RECALL_RERANK_START = "recall_rerank_start"
    RECALL_RERANK_THINKING = "recall_rerank_thinking"
    RECALL_RERANK_TEXT = "recall_rerank_text"
    RECALL_RERANK_DONE = "recall_rerank_done"
    RECALL_SYNTH_START = "recall_synth_start"
    RECALL_SYNTH_INPUT = "recall_synth_input"
    RECALL_SYNTH_THINKING = "recall_synth_thinking"
    RECALL_SYNTH_TEXT = "recall_synth_text"
    RECALL_SYNTH_DONE = "recall_synth_done"

    # === 非渲染事件 ===
    CONTEXT_ENTRY = "context_entry"
    CONTEXT_PATCH = "context_patch"


class StreamEvent:
    """MainLoop 生成器的单个产出事件。

    不同事件类型携带的载荷字段：

    ┌──────────────────────┬──────────────────────────────────────┐
    │ 事件类型              │ 载荷字段                              │
    ├──────────────────────┼──────────────────────────────────────┤
    │ TEXT                 │ delta                                │
    │ THINKING             │ delta                                │
    │ TOOL_START           │ tool_id, tool_name, tool_input       │
    │ TOOL_RESULT          │ tool_id, content                     │
    │ ASSISTANT_DONE       │ stop_reason                          │
    │ ERROR                │ error_msg                            │
    │ SUB_PANEL_ENTER      │ tool_id, tool_name                   │
    │ SUB_PANEL_EXIT       │ tool_id                              │
    │ MICRO_COMPACT        │ content                              │
    │ AUTO_COMPACT_START   │ content                              │
    │ AUTO_COMPACT_THINKING│ delta                                │
    │ AUTO_COMPACT_TEXT    │ delta                                │
    │ AUTO_COMPACT_DONE    │ content                              │
    │ BACKGROUND_NOTIFICATION│ content                            │
    │ INBOX_MESSAGE        │ content                              │
    │ TASK_CLAIMED         │ content (任务摘要)                     │
    │ TODO_REMINDER        │ content                              │
    │ TODO_UPDATE          │ content (JSON: agent_name + items)   │
    │ TOKEN_USAGE          │ content (JSON: used + total)         │
    │ TEAM_UPDATE          │ content (JSON: team_name + members)  │
    │ RECALL_EXPAND_START  │ content                              │
    │ RECALL_EXPAND_THINKING│ delta                                │
    │ RECALL_EXPAND_TEXT   │ delta                                │
    │ RECALL_EXPAND_DONE   │ content (JSON: variants + original)   │
    │ RECALL_QUERY_START   │ content (JSON: query + index)         │
    │ RECALL_QUERY_RESULT  │ content (JSON: query + hits)          │
    │ RECALL_RETRIEVE_DONE │ content (去重汇总)                    │
    │ RECALL_RERANK_START  │ content                              │
    │ RECALL_RERANK_THINKING│ delta                                │
    │ RECALL_RERANK_TEXT   │ delta                                │
    │ RECALL_RERANK_DONE   │ content (JSON: top_k + total)         │
    │ RECALL_SYNTH_START   │ content                              │
    │ RECALL_SYNTH_INPUT   │ content (JSON: fragments)             │
    │ RECALL_SYNTH_THINKING│ delta                                │
    │ RECALL_SYNTH_TEXT    │ delta                                │
    │ RECALL_SYNTH_DONE    │ content (最终合成回答)                 │
    │ CONTEXT_ENTRY        │ content (序列化的 Anthropic API msg)  │
    │ CONTEXT_PATCH        │ content (序列化的 patch list)         │
    └──────────────────────┴──────────────────────────────────────┘
    """

    def __init__(
        self,
        type: EventType,
        delta: str | None = None,
        tool_id: str | None = None,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        content: str | None = None,
        stop_reason: str | None = None,
        error_msg: str | None = None,
    ):
        self._event_type = type
        self._delta = delta
        self._tool_id = tool_id
        self._tool_name = tool_name
        self._tool_input = tool_input
        self._content = content
        self._stop_reason = stop_reason
        self._error_msg = error_msg

    # ======================== public ========================

    @property
    def event_type(self) -> EventType:
        return self._event_type

    @property
    def content(self) -> str | None:
        return self._content

    def to_dict(self) -> dict[str, Any]:
        """转为 JSON 可序列化的 dict，只包含值非 None 的字段以减小 payload。"""
        result: dict[str, Any] = {"type": self._event_type.value}
        field_names = ("delta", "tool_id", "tool_name", "tool_input", "content", "stop_reason", "error_msg")
        for field_name in field_names:
            value = getattr(self, f"_{field_name}")
            if value is not None:
                result[field_name] = value
        return result
