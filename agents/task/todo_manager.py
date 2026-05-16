#!/usr/bin/env python3
"""
todo_manager.py

内存 todo 注册表模块。

维护以 agent_name 为键的 todo 列表，供每个 agent 使用。
提供以下能力：
1. todo_write(agent_name, items)：替换指定 agent 的 todo 列表，并返回渲染文本。
2. has_undo_items(agent_name)：判断是否存在未完成的 todo 项。

todo 条目格式：
    {"content": "what to do", "status": "pending|in_progress|completed"}
"""

from __future__ import annotations


class TodoManager:
    """以 agent_name 为键的纯内存 todo 注册表。"""

    def __init__(self):
        self._agents_todo_list: dict[str, list[dict[str, str]]] = {}
        self._VALID_STATUSES = frozenset({"pending", "in_progress", "completed"})

    # ======================== public ========================

    def todo_write(
        self,
        agent_name: str, # agent_name 作为键，替换对应的 todo 列表
        items: list # 新的 todo 列表
    ) -> str:
        """替换指定 agent 的 todo 列表，校验后返回渲染文本。"""
        validated: list[dict[str, str]] = []
        in_progress_count = 0

        try:
            for index, item in enumerate(items):
                content = str(item.get("content", "")).strip()
                status = str(item.get("status", "")).lower()

                if not content:
                    raise ValueError(f"Item {index}: content required.")
                if not status:
                    raise ValueError(f"Item {index}: status required.")
                if status not in self._VALID_STATUSES:
                    raise ValueError(f"Item {index}: invalid status '{status}'. Status must be one of {', '.join(self._VALID_STATUSES)}.")

                if status == "in_progress":
                    in_progress_count += 1

                validated.append({"content": content, "status": status})

            if in_progress_count > 1:
                raise ValueError("Only one in_progress todo item allowed.")

            self._agents_todo_list[agent_name] = validated
            return f"Successfully updated todos:\n{self._render(agent_name)}."
        except Exception as exc:
            return f"Error: {exc}"


    def has_undo_items(self, agent_name: str) -> bool:
        """判断是否存在未完成 todo 项。"""
        items = self._agents_todo_list.get(agent_name, [])
        return any(item.get("status") != "completed" for item in items)

    # ======================== private ========================

    def _render(self, agent_name: str) -> str:
        """渲染名为 agent_name 的 agent 的 todo。"""
        items = self._agents_todo_list.get(agent_name, [])

        if not items:
            return "No todo."

        lines: list[str] = []
        for item in items:
            lines.append(f"[{item['status']}]: {item['content']}")

        todo_list = "\n".join(lines)
        return f"<todos>:\n{todo_list}\n</todos>"
