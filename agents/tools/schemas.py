#!/usr/bin/env python3
"""
schemas.py

工具协议定义模块。

该模块只负责声明模型可调用的工具清单与输入 schema ，不包含任何执行逻辑。

提供 4 层级工具集合：
    explore_subagent_tools       — explore subagent
    general_subagent_tools       — general-purpose subagent
    teammate_tools               — teammates
    main_agent_tools             — main agent
"""

from __future__ import annotations

from typing import Any

class ToolSchemas:
    """工具协议定义，集中管理 4 个层级 Agent 的工具 schema。"""

    def __init__(self, mcp_tool_schemas: list[dict] | None = None):
        self.mcp_tools = mcp_tool_schemas or []
        self.explore_subagent_tools = [_TOOL_DEFS[k] for k in _EXPLORE_SUBAGENT_TOOLS] + self.mcp_tools
        self.general_subagent_tools = [_TOOL_DEFS[k] for k in _GENERAL_SUBAGENT_TOOLS] + self.mcp_tools
        self.teammate_tools = [_TOOL_DEFS[k] for k in _TEAMMATE_TOOLS] + self.mcp_tools
        self.main_agent_tools = [_TOOL_DEFS[k] for k in _MAIN_AGENT_TOOLS] + self.mcp_tools

# 4 个层级工具集

_EXPLORE_SUBAGENT_TOOLS = [
    "run_shell",
    "read_file",
    "todo_write",
    "load_skill",
]

_GENERAL_SUBAGENT_TOOLS = [
    "run_shell",
    "read_file",
    "todo_write",
    "load_skill",
    "write_file",
    "edit_file",
]

_TEAMMATE_TOOLS = [
    "run_shell",
    "read_file",
    "write_file",
    "edit_file",
    "todo_write",
    "load_skill",
    "use_subagent",
    "run_background_task",
    "check_background_task",
    "list_all_background_tasks",
    "scan_and_claim",
    "task_bind_worktree",
    "complete_and_merge",
    "send_message",
    "reply_message",
    "read_inbox",
    "broadcast",
    "shutdown_response",
    "plan_approval_request",
    "get_team_config",
    "idle",
]

_MAIN_AGENT_TOOLS = [
    "run_shell",
    "read_file",
    "write_file",
    "edit_file",
    "todo_write",
    "load_skill",
    "use_subagent",
    "create_task",
    "get_task_details",
    "update_task",
    "delete_task",
    "list_all_tasks",
    "run_background_task",
    "check_background_task",
    "list_all_background_tasks",
    "send_message",
    "reply_message",
    "read_inbox",
    "broadcast",
    "shutdown_request",
    "plan_approval_response",
    "spawn_teammate",
    "get_team_config",
]

# 工具定义注册表，按名称索引，每个工具定义只写一次
_TOOL_DEFS: dict[str, dict[str, Any]] = {
    "run_shell": {
        "name": "run_shell",
        "description": "Run a shell command in the workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum execution time in seconds. If not provided, defaults to 120 seconds.",
                },
            },
            "required": ["command"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "Read a text file from the workspace. Paths that resolve outside the workspace are rejected. Supports line-range slicing (inclusive on both ends). Binary files may produce garbled output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace. Absolute paths and .. traversal that escapes the workspace are rejected.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based line number to start reading from (inclusive). Must be >= 1. Omit to read from the first line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based line number to stop reading at (inclusive). Must be >= start_line if both are provided. Omit to read to the end of file."
                },
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file atomically (temp file + os.replace). Overwrites existing files; creates parent directories as needed. Paths escaping the workspace are rejected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace. New or existing file. Parent directories are created if missing."
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write. The file is replaced in its entirety; to modify part of a file use edit_file instead."
                },
            },
            "required": ["path", "content"],
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": "Replace the first occurrence of old_text with new_text in a file. Fails if old_text is not found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace. Must point to an existing text file."
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace. Must exist in the file; otherwise the edit fails. Should be specific enough to avoid unintended replacements."
                },
                "new_text": {
                    "type": "string",
                    "description": "The replacement text. Can be empty (to delete) or any string."
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    "todo_write": {
        "name": "todo_write",
        "description": "Replace your current todo list with a new one. Use it when create or update your todo list. Each item must have content and status. At most one item may be in_progress. Returns the rendered todo list on success, or an error message on validation failure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Your name.",
                },
                "todo_list": {
                    "type": "array",
                    "description": "The complete new todo list. Replaces all previous items.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "What to do. Must be non-empty. Keep it short and actionable.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Work state. Only one item may be in_progress at a time.",
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
            "required": ["name", "todo_list"],
        },
    },
    "load_skill": {
        "name": "load_skill",
        "description": "Load the full content of a skill by its exact name. "
        "Use this before relying on any specialized domain knowledge (framework, library, tool, platform etc.). "
        "Skills contain up-to-date docs, conventions, and constraints. "
        "If the skill is not found, the tool returns an error with a list of available skill names. "
        "On success, it returns the complete skill body wrapped in <skill> tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The exact name of the skill to load.",
                },
            },
            "required": ["skill_name"],
        },
    },
    "use_subagent": {
        "name": "use_subagent",
        "description":
            "Spawn an isolated subagent to handle a task independently, "
            "returning a text summary when done. "
            "The subagent runs in its own message context. "
            "Use this for: (1) broad codebase exploration that would produce "
            "too many tool results in the main conversation, (2) self-contained "
            "research or fact-finding tasks, (3) work that benefits from a "
            "focused context window without interference from main-thread "
            "history. "
            "Do NOT use for: trivial single-step lookups, tasks that require "
            "continuous back-and-forth with the main agent. "
            "Agent types: 'explore' has read-only tools (run_shell, read_file, "
            "todo_write, load_skill); 'general-purpose' adds write_file and "
            "edit_file. Choose 'explore' unless the task explicitly requires "
            "modifying files. "
            "Name must be unique per conversation — use a short descriptive "
            "label like 'config-audit' or 'db-schema-research'. "
            "Subagents cannot spawn further subagents. "
            "Each invocation counts as one tool call; batch independent "
            "research into a single subagent call rather than spawning many.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Complete task description for the subagent. Must be self-contained — include all context, constraints, and what a good answer looks like. The subagent has no access to the main conversation history.",
                },
                "agent_type": {
                    "type": "string",
                    "enum": ["explore", "general-purpose"],
                    "description": "Tool set for the subagent. 'explore' = read-only (run_shell, read_file, todo_write, load_skill). 'general-purpose' = explore + write_file + edit_file.",
                },
                "name": {
                    "type": "string",
                    "description": "Unique short identifier for this subagent, e.g. 'config-audit' or 'db-schema-research'. Must be unique per conversation.",
                },
            },
            "required": ["prompt", "agent_type", "name"],
        },
    },
    "create_task": {
        "name": "create_task",
        "description":
            "Create a persistent task stored as a JSON file on disk. "
            "Tasks survive across conversation turns and can be claimed "
            "by teammates, tracked through status changes, and organized "
            "with dependency chains. "
            "New tasks always start as 'pending' with no owner. "
            "Use this for: (1) tracking work items that outlive a single "
            "response, (2) creating a queue of tasks for teammates to "
            "claim, (3) recording planned work with explicit dependencies "
            "so blocked tasks aren't picked up prematurely. "
            "Do NOT use for: ephemeral to-do items within a single "
            "response (use todo_write instead), or notes that don't "
            "represent actionable work. "
            "blocked_by accepts a list of existing task IDs that must "
            "be completed before this task becomes unblocked. A task "
            "with non-empty blocked_by will not be auto-claimed by "
            "teammates until all blockers resolve.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Short, actionable title for the task. Must be non-empty. Example: 'Add authentication middleware'.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed explanation of what needs to be done. Include context, constraints, and acceptance criteria. Must be non-empty.",
                },
                "blocked_by": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of task IDs that must be completed before this task can start. Omit or pass empty array if no dependencies.",
                },
            },
            "required": ["subject", "description"],
        },
    },
    "get_task_details": {
        "name": "get_task_details",
        "description":
            "Fetch the full JSON details of a persistent task by its numeric ID. "
            "Returns all fields: id (int, unique task number), "
            "subject (str, task title), description (str, detailed instructions), "
            "status (pending | in_progress | completed), "
            "owner (str | null, claiming agent name), "
            "blockedBy (list[int], IDs of tasks that must finish first), "
            "worktree (str, bound worktree branch name), "
            "worktree_path (str, disk path of the worktree), "
            "merged_at (float | null, timestamp when worktree was merged), "
            "created_at (float, creation timestamp), "
            "updated_at (float, last modification timestamp). "
            "Use this before updating a task to inspect its current state, "
            "or when you need to check ownership, dependency chains, or "
            "worktree bindings. "
            "Returns an error message if the task ID does not exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The numeric task ID to look up. Must reference an existing task created via create_task.",
                },
            },
            "required": ["task_id"],
        },
    },
    "update_task": {
        "name": "update_task",
        "description":
            "Update one or more fields of a persistent task by its numeric ID. "
            "All parameters except task_id are optional — only the fields "
            "you provide will be modified; omitted fields keep their current "
            "values. "
            "Status changes: setting status to 'completed' automatically "
            "clears this task's ID from other tasks' blockedBy lists, "
            "unblocking dependents. Invalid status values are rejected with "
            "an error listing valid options. "
            "Dependency management: add_blocked_by appends new blocker IDs "
            "(deduplicating via set union), remove_blocked_by removes "
            "specific blocker IDs. Use add_blocked_by to introduce a "
            "dependency and remove_blocked_by when a dependency no longer "
            "applies. "
            "Ownership: set owner to an agent name string to assign or "
            "reassign the task. Setting owner without changing status is "
            "valid. "
            "Returns the full updated task JSON on success, or an error "
            "message if the task ID does not exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The numeric task ID to update. Must reference an existing task.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "New status for the task. Setting to 'completed' also removes this task as a blocker from all dependent tasks.",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Task IDs to add to this task's blockedBy list. Merged with existing blockers (duplicates ignored).",
                },
                "remove_blocked_by": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Task IDs to remove from this task's blockedBy list. Non-existent IDs are silently skipped.",
                },
                "owner": {
                    "type": "string",
                    "description": "Agent name to set as the task owner. Does not automatically change status.",
                },
            },
            "required": ["task_id"],
        },
    },
    "delete_task": {
        "name": "delete_task",
        "description":
            "Permanently delete a task's JSON file from disk. This is irreversible — the task record is gone, not archived. "
            "The task must be 'completed' and its worktree (if any) must already be merged (merged_at must be set). "
            "Returns an error if the task is not completed or has an unmerged worktree. On success the worktree binding is also removed from the in-memory index.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The numeric task ID to permanently delete. Task must be completed and have no unmerged worktree.",
                },
            },
            "required": ["task_id"],
        },
    },
    "list_all_tasks": {
        "name": "list_all_tasks",
        "description":
            "Return the full JSON details of all tasks in the system. "
            "Each task is printed with its complete record — id, subject, "
            "description, status, owner, blockedBy, worktree, worktree_path, "
            "merged_at, created_at, updated_at — formatted as indented JSON "
            "under a 'Task n:' header. "
            "Use this to get a complete overview of all work items, their "
            "dependencies, and their current state in a single call. "
            "For a single task, use get_task_details instead. "
            "Returns 'No tasks.' if the task board is empty.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "scan_and_claim": {
        "name": "scan_and_claim",
        "description":
            "Claim the first available task from the shared task board. "
            "Only claims tasks that are pending, unowned, and unblocked. "
            "Returns the task details on success, or 'NO idle tasks for "
            "claiming.' if nothing is available. ",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Your name. Used to set the task owner field.",
                },
            },
            "required": ["agent_name"],
        },
    },
    "task_bind_worktree": {
        "name": "task_bind_worktree",
        "description": "Bind a git worktree (branch name + disk path) to a task. Does not run git commands — only records metadata. A worktree can only be bound to one task at a time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The task id to bind the worktree to."
                },
                "worktree_name": {
                    "type": "string",
                    "description": "Worktree branch name, e.g. wt/1-auth."
                },
                "worktree_path": {
                    "type": "string",
                    "description": "Absolute path to the worktree directory on disk."
                },
            },
            "required": ["task_id", "worktree_name", "worktree_path"],
        },
    },
    "complete_and_merge": {
        "name": "complete_and_merge",
        "description": "Mark your task as completed and its worktree as merged. Call this after you have merged the worktree branch back to main and cleaned up the worktree directory. Fails if the task has no bound worktree.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The id of the task to complete and merge. Must have a bound worktree."
                },
            },
            "required": ["task_id"],
        },
    },
    "run_background_task": {
        "name": "run_background_task",
        "description": "Run a shell command in a background daemon thread and return a task ID immediately. The command continues executing while you do other work. Use this for long-running commands (builds, installs, tests) so they don't block your conversation loop. You will receive a notification in subsequent sessions when the task completes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Your name.",
                },
                "command": {
                    "type": "string",
                    "description": "The shell command to run in the background.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum execution time in seconds. Omit to use the system default.",
                },
            },
            "required": ["agent_name", "command"],
        },
    },
    "check_background_task": {
        "name": "check_background_task",
        "description": "Check the status and result of a single background task by its ID. Returns the task status (running/completed/error), the original command, and the output if finished. Completed tasks may not be queryable after their notification has been delivered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Your name.",
                },
                "background_task_id": {
                    "type": "string",
                    "description": "The task ID returned by run_background_task.",
                },
            },
            "required": ["agent_name", "background_task_id"],
        },
    },
    "list_all_background_tasks": {
        "name": "list_all_background_tasks",
        "description": "List all your currently running background tasks with their IDs, statuses, and commands. Completed tasks are removed after notification and will not appear here.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Your name.",
                },
            },
            "required": ["agent_name"],
        },
    },
    "send_message": {
        "name": "send_message",
        "description": "Send a text message to a teammate. Use this to communicate with teammates of the team. Returns a binding communication_id for tracking replies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "receiver": {
                    "type": "string",
                    "description": "The teammate name to send the message to.",
                },
                "content": {
                    "type": "string",
                    "description": "The message text.",
                },
            },
            "required": ["sender", "receiver", "content"],
        },
    },
    "reply_message": {
        "name": "reply_message",
        "description": "Reply to a received message referenced by its communication_id. Binds the reply to the same conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "receiver": {
                    "type": "string",
                    "description": "The teammate name to reply to.",
                },
                "content": {
                    "type": "string",
                    "description": "The reply text.",
                },
                "communication_id": {
                    "type": "string",
                    "description": "The communication_id from the original message you are replying to.",
                },
            },
            "required": ["sender", "receiver", "content", "communication_id"],
        },
    },
    "read_inbox": {
        "name": "read_inbox",
        "description": "Read and clear all messages in your inbox. Messages are deleted after reading. Returns a formatted list of messages with sender, type, content, and communication_id. Returns 'No messages.' if the inbox is empty.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Your name.",
                },
            },
            "required": ["name"],
        },
    },
    "broadcast": {
        "name": "broadcast",
        "description": "Send the same message to multiple teammates at once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "content": {
                    "type": "string",
                    "description": "The message content to broadcast.",
                },
                "receiver_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of teammate names to receive the broadcast.",
                },
            },
            "required": ["sender", "content", "receiver_list"],
        },
    },
    "shutdown_request": {
        "name": "shutdown_request",
        "description": "Request a specific teammate to shut down gracefully.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "receiver": {
                    "type": "string",
                    "description": "The teammate name to request shutdown from.",
                },
                "content": {
                    "type": "string",
                    "description": "The shutdown request message content.",
                },
            },
            "required": ["sender", "receiver", "content"],
        },
    },
    "shutdown_response": {
        "name": "shutdown_response",
        "description": "Respond to a shutdown request. You must explicitly approve or reject.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "receiver": {
                    "type": "string",
                    "description": "The name of the agent who sent the shutdown request you are responding to.",
                },
                "content": {
                    "type": "string",
                    "description": "Your response message.",
                },
                "communication_id": {
                    "type": "string",
                    "description": "The communication_id from the shutdown request message.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected"],
                    "description": "Whether you approve or reject the shutdown.",
                },
            },
            "required": ["sender", "receiver", "content", "communication_id", "decision"],
        },
    },
    "plan_approval_request": {
        "name": "plan_approval_request",
        "description": "Submit your work plan for approval. The reviewer will respond with approved or rejected, optionally with feedback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "receiver": {
                    "type": "string",
                    "description": "The name of the agent to review your plan (typically 'lead').",
                },
                "content": {
                    "type": "string",
                    "description": "Your plan description. Be thorough — the reviewer cannot ask clarifying questions.",
                },
            },
            "required": ["sender", "receiver", "content"],
        },
    },
    "plan_approval_response": {
        "name": "plan_approval_response",
        "description": "Approve or reject a submitted plan. Include feedback explaining your decision.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Your name.",
                },
                "receiver": {
                    "type": "string",
                    "description": "The teammate name whose plan you are responding to.",
                },
                "content": {
                    "type": "string",
                    "description": "Feedback explaining your decision, especially if rejected.",
                },
                "communication_id": {
                    "type": "string",
                    "description": "The communication_id from the plan_approval_request message.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected"],
                    "description": "Approved if the plan is acceptable, rejected if it needs changes.",
                },
            },
            "required": ["sender", "receiver", "content", "communication_id", "decision"],
        },
    },


    "spawn_teammate": {
        "name": "spawn_teammate",
        "description":
            "Launch a persistent autonomous teammate agent in daemon thread. "
            "The teammate runs independently with its own message loop, "
            "alternating between a working phase and an idle polling phase where it checks for new inbox "
            "messages and automatically claims unassigned tasks from the shared board. "
            "Teammates persist across conversation turns — they can receive and send"
            "messages, respond to shutdown requests, and submit plans for approval. "
            "Use teammates for long-running, loosely-coupled work that benefits "
            "from parallel execution alongside the main agent(you). "
            "name must be unique within the team. role describes what the "
            "teammate is responsible for (e.g. 'tester', 'reviewer', 'builder'). "
            "prompt is the initial task description — be thorough since it "
            "defines the teammate's entire work scope. "
            "Calling spawn_teammate for a previously shutdown teammate restarts "
            "it with the new role and prompt. "
            "Returns a success message with the teammate name and role, or an "
            "error if a teammate with that name is already active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the teammate. Must be unique within the team. If a shutdown teammate with this name exists, it will be restarted.",
                },
                "role": {
                    "type": "string",
                    "description": "The teammate's responsibility, e.g. 'tester', 'reviewer', 'builder'. Used in the system prompt to shape behavior.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Complete initial task description. Be thorough — this defines the teammate's entire work scope. Include context, constraints, and expected outcomes.",
                },
            },
            "required": ["name", "role", "prompt"],
        },
    },
    "get_team_config": {
        "name": "get_team_config",
        "description":
            "Return the full team configuration as formatted JSON. "
            "Shows the team name plus every member with their name, role, and current status (working | idle | shutdown). "
            "Use this to see who is available on the team, check teammate statuses and verify the current team composition.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "idle": {
        "name": "idle",
        "description":
            "Use it when you have finished your current work and want to enter the idle polling phase. "
            "In idle state, you will wait for new inbox messages or automatically scans and claims the first available unassigned, unblocked task from the shared task board. "
            "If received a message or claimed a task, you will start working on it in the next turn. "
            "If no messages or claimable tasks arrive within the idle timeout period, you will shut down automatically. "
            "Use this when you have completed your assigned work and have nothing else to do — do not call idle if you still have pending tasks or unfinished work.",
        "input_schema": {
            "type": "object",
            "properties": {}
        },
    },
}
