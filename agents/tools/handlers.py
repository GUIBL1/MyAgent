#!/usr/bin/env python3
"""
handlers.py

工具执行映射模块。

该模块集中组装 `工具名 -> 处理函数` 映射，
"""

from __future__ import annotations

from typing import Any


class ToolHandlers:
    """工具执行映射，集中组装 工具名 → 处理函数 映射。"""

    def __init__(
        self,
        *,
        base_tools,
        todo_manager,
        skill_manager,
        subagent,
        tasks_manager,
        background_manager,
        message_bus,
        teammate_manager,
        mcp_handlers: dict[str, Any] | None = None,
    ):
        self.tool_handlers: dict[str, Any] = {
            "run_shell": lambda **kw: base_tools.run_shell(
                command=kw["command"],
                timeout=kw.get("timeout", 120),
            ),
            "read_file": lambda **kw: base_tools.read_file(
                path=kw["path"],
                start_line=kw.get("start_line"),
                end_line=kw.get("end_line"),
            ),
            "write_file": lambda **kw: base_tools.write_file(
                path=kw["path"],
                content=kw["content"],
            ),
            "edit_file": lambda **kw: base_tools.edit_file(
                path=kw["path"],
                old_text=kw["old_text"],
                new_text=kw["new_text"],
            ),
            "todo_write": lambda **kw: todo_manager.todo_write(
                agent_name=kw["name"],
                items=kw["todo_list"],
            ),
            "load_skill": lambda **kw: skill_manager.load_skill(
                skill_name=kw["skill_name"]
            ),
            "use_subagent": lambda **kw: subagent.run_subagent(
                prompt=kw["prompt"],
                agent_type=kw["agent_type"],
                name=kw["name"],
            ),
            "create_task": lambda **kw: tasks_manager.create_task(
                subject=kw["subject"],
                description=kw["description"],
                blocked_by=kw.get("blocked_by"),
            ),
            "get_task_details": lambda **kw: tasks_manager.get_task_details(
                task_id=kw["task_id"]
            ),
            "update_task": lambda **kw: tasks_manager.update_task(
                task_id=kw["task_id"],
                status=kw.get("status"),
                add_blocked_by=kw.get("add_blocked_by"),
                remove_blocked_by=kw.get("remove_blocked_by"),
                owner=kw.get("owner"),
            ),
            "delete_task": lambda **kw: tasks_manager.delete_task(
                task_id=kw["task_id"]
            ),
            "list_all_tasks": lambda **kw: tasks_manager.list_all_tasks(),
            "scan_and_claim": lambda **kw: tasks_manager.scan_and_claim(
                agent_name=kw["agent_name"],
                tool_call=True
            ),
            "task_bind_worktree": lambda **kw: tasks_manager.task_bind_worktree(
                task_id=kw["task_id"],
                worktree_name=kw["worktree_name"],
                worktree_path=kw["worktree_path"],
            ),
            "complete_and_merge": lambda **kw: tasks_manager.complete_and_merge(
                task_id=kw["task_id"]
            ),
            "run_background_task": lambda **kw: background_manager.run_background_task(
                agent_name=kw["agent_name"],
                command=kw["command"],
                timeout=kw.get("timeout")
            ),
            "check_background_task": lambda **kw: background_manager.check_background_task(
                agent_name=kw["agent_name"],
                background_task_id=kw["background_task_id"]
            ),
            "list_all_background_tasks": lambda **kw: background_manager.list_all_background_tasks(
                agent_name=kw["agent_name"]
            ),
            "send_message": lambda **kw: message_bus.send_message(
                sender=kw["sender"],
                receiver=kw["receiver"],
                content=kw["content"],
            ),
            "reply_message": lambda **kw: message_bus.reply_message(
                sender=kw["sender"],
                receiver=kw["receiver"],
                content=kw["content"],
                communication_id=kw["communication_id"],
            ),
            "read_inbox": lambda **kw: message_bus.read_inbox(
                name=kw["name"],
                tool_call=True
            ),
            "broadcast": lambda **kw: message_bus.broadcast(
                sender=kw["sender"],
                content=kw["content"],
                receiver_list=kw["receiver_list"],
            ),
            "shutdown_request": lambda **kw: message_bus.shutdown_request(
                sender=kw["sender"],
                receiver=kw["receiver"],
                content=kw["content"],
            ),
            "shutdown_response": lambda **kw: message_bus.shutdown_response(
                sender=kw["sender"],
                receiver=kw["receiver"],
                content=kw["content"],
                communication_id=kw["communication_id"],
                decision=kw["decision"],
            ),
            "plan_approval_request": lambda **kw: message_bus.plan_approval_request(
                sender=kw["sender"],
                receiver=kw["receiver"],
                content=kw["content"],
            ),
            "plan_approval_response": lambda **kw: message_bus.plan_approval_response(
                sender=kw["sender"],
                receiver=kw["receiver"],
                content=kw["content"],
                communication_id=kw["communication_id"],
                decision=kw["decision"],
            ),
            "spawn_teammate": lambda **kw: teammate_manager.spawn_teammate(
                name=kw["name"],
                role=kw["role"],
                prompt=kw["prompt"]
            ),
            "get_team_config": lambda **kw: teammate_manager.get_team_config(),
            "idle": lambda **kw: teammate_manager.idle(),
        }
        if mcp_handlers:
            for name, handler in mcp_handlers.items():
                if name not in self.tool_handlers:
                    self.tool_handlers[name] = handler
