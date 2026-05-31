"""
流事件类型定义

MainLoop 生成器产出的标准化事件，供 WebSocket 消费。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class EventType(Enum):
    """流事件类型枚举。"""
    TEXT = "text"
    THINKING = "thinking"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    ASSISTANT_DONE = "assistant_done"
    ERROR = "error"


class StreamEvent:
    """MainLoop 生成器的单个产出事件。

    不同事件类型携带的载荷字段：

    - text / thinking:     delta
    - tool_start:          tool_id, tool_name, tool_input
    - tool_result:         tool_id, content
    - assistant_done:      stop_reason
    - error:               error_msg
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
    def to_dict(self) -> dict[str, Any]:
        """转为 JSON 可序列化的 dict，只包含值非 None 的字段以减小 payload。"""
        result: dict[str, Any] = {"type": self._event_type.value}
        field_names = ("delta", "tool_id", "tool_name", "tool_input", "content", "stop_reason", "error_msg")
        for field_name in field_names:
            value = getattr(self, f"_{field_name}")
            if value is not None:
                result[field_name] = value
        return result
