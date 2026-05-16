#!/usr/bin/env python3
"""
task_manager.py

持久化任务管理模块。

任务以 JSON 文件保存在 `WORKDIR./MyAgent/tasks/task_<id>.json`，
支持状态、负责人、依赖关系与工作树绑定字段。

task JSON 结构示例：
{
  "id": 1,                         // int, 任务唯一编号
  "subject": "任务标题",           // str, 必填
  "description": "详细描述",       // str, 必填
  "status": "pending",            // str, 取值 "pending" | "in_progress" | "completed"
  "owner": "执行任务 agent 名",    // str | null, 负责人
  "blockedBy": [2, 5],            // list[int], 依赖的任务 ID 列表
  "worktree": "worktree_name",    // str, 绑定的工作树名称（可以为空）
  "worktree_path": "/path/to",    // str, 工作树磁盘路径（可以为空）
  "merged_at": null,              // float | null, 合并时间戳
  "created_at": 1745678901.23,    // float, 创建时间戳
  "updated_at": 1745678901.23     // float, 每次保存时更新
}
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class TaskManager:
    """基于文件系统的任务 CRUD 管理器。"""
    def __init__(self, tasks_dir: Path):
        self._tasks_dir = tasks_dir
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._VALID_STATUSES = {"pending", "in_progress", "completed"}
        self._lock = threading.RLock()
        self._worktree_index: dict[str, int] = {}  # worktree_name -> task_id
        self._build_worktree_index()


    # ======================== public ========================
    def create_task(
        self,
        subject: str,
        description: str,
        blocked_by: list[int] | None = None
    ) -> str:
        """创建新任务，默认状态为 pending。"""
        with self._lock:
            task = {
                "id": self._next_id(),
                "subject": subject,
                "description": description,
                "status": "pending",
                "owner": None,
                "blockedBy": blocked_by or [],
                "worktree": "",
                "worktree_path": "",
                "merged_at": None,
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            self._save(task)
            return "Successfully created task:\n" + json.dumps(task, indent=2, ensure_ascii=False)


    def get_task_details(self, task_id: int) -> str:
        """按 ID 返回任务详情。"""
        with self._lock:
            try:
                task = self._load(task_id)
                return "Task details:\n" + json.dumps(task, indent=2, ensure_ascii=False)
            except Exception as exc:
                return f"Error loading task {task_id}: {exc}"


    def update_task(
        self,
        task_id: int,
        status: str | None = None,
        add_blocked_by: list[int] | None = None,
        remove_blocked_by: list[int] | None = None,
        owner: str | None = None,
    ) -> str:
        """按任务 ID 更新任务状态、依赖关系或负责人。"""
        with self._lock:
            try:
                task = self._load(task_id)
            except Exception as exc:
                return f"Error updating task {task_id}: {exc}"

            if status:
                if status not in self._VALID_STATUSES:
                    return f"Error: invalid status '{status}', must be one of {sorted(self._VALID_STATUSES)}."
                task["status"] = status
                if status == "completed":
                    self._clear_dependency(task_id)

            if add_blocked_by:
                task["blockedBy"] = list(set(task.get("blockedBy", []) + add_blocked_by))

            if remove_blocked_by:
                task["blockedBy"] = [
                    blocked_id
                    for blocked_id in task.get("blockedBy", [])
                    if blocked_id not in remove_blocked_by
                ]

            if owner:
                task["owner"] = owner

            self._save(task)
            return "Successfully updated task:\n" + json.dumps(task, indent=2, ensure_ascii=False)


    def delete_task(self, task_id: int) -> str:
        """删除已完成任务的 JSON 文件，彻底清除。"""
        with self._lock:
            try:
                task = self._load(task_id)
            except Exception as exc:
                return f"Error: Task {task_id} delete failed with {exc}"

            if task.get("status") != "completed":
                return f"Error: Task {task_id} is not completed, cannot delete."
            if task.get("worktree") and not task.get("merged_at"):
                return f"Error: Task {task_id} has unmerged worktree '{task['worktree']}', merge and clean up first."

            if task.get("worktree"):
                self._worktree_index.pop(task["worktree"], None)
            self._path(task_id).unlink()
            return f"Task {task_id} deleted successfully."


    def list_all_tasks(self) -> str:
        """获取所有任务的完整详细信息。"""
        with self._lock:
            tasks = [
                json.loads(file_path.read_text(encoding="utf-8"))
                for file_path in sorted(self._tasks_dir.glob("task_*.json"))
            ]
            if not tasks:
                return "No tasks."

            results: list[str] = []
            for task in tasks:
                results.append(f"Task {task['id']}:\n{json.dumps(task, indent=2, ensure_ascii=False)}")
            return "\n".join(results)


    def scan_and_claim(self, agent_name: str, tool_call: bool = False) -> str:
        """原子扫描第一个空闲任务并认领。tool_call=True 时返回对 agent 友好的提示文本。"""
        with self._lock:
            for file_path in sorted(self._tasks_dir.glob("task_*.json")):
                task = json.loads(file_path.read_text(encoding="utf-8"))
                if (
                    task.get("status") == "pending"
                    and not task.get("owner")
                    and not task.get("blockedBy")
                ):
                    task["owner"] = agent_name
                    task["status"] = "in_progress"
                    self._save(task)
                    task_claimed = [f"Successfully claimed task.",
                                    f"id:{task['id']}.",
                                    f"Task subject:{task['subject']}.",
                                    f"Task description:{task['description']}."]
                    return "\n".join(task_claimed)
            return "NO idle tasks for claiming." if tool_call else ""


    def task_bind_worktree(
            self,
            task_id: int,
            worktree_name: str,
            worktree_path: str
        ) -> str:
        """将任务绑定到指定工作树，记录分支名和磁盘路径。"""
        with self._lock:
            try:
                task = self._load(task_id)
            except Exception as exc:
                return f"Error: {exc}"

            existing = self._worktree_index.get(worktree_name)
            if existing is not None and existing != task_id:
                return f"Error: worktree '{worktree_name}' already bound to task {existing}"

            task["worktree"] = worktree_name
            task["worktree_path"] = worktree_path
            self._worktree_index[worktree_name] = task_id
            self._save(task)
            return f"Successfully bound worktree '{worktree_name}' to task {task_id}."


    def complete_and_merge(self, task_id: int) -> str:
        """标记 worktree 已合并、任务 completed，并解除依赖。"""
        with self._lock:
            try:
                task = self._load(task_id)
            except Exception as exc:
                return f"Error: {exc}"

            if not task.get("worktree"):
                return f"Error: Task {task_id} has no worktree to merge"

            task["merged_at"] = time.time()
            task["status"] = "completed"
            self._clear_dependency(task_id)

            self._save(task)
            return f"Successfully completed and merged task {task_id}."

    # ======================== private ========================

    def _build_worktree_index(self):
        """启动时扫描所有 task JSON，构建 worktree_name -> task_id 的内存索引。"""
        with self._lock:
            self._worktree_index.clear()
            for file_path in self._tasks_dir.glob("task_*.json"):
                try:
                    task = json.loads(file_path.read_text(encoding="utf-8"))
                    worktree = task.get("worktree", "")
                    if worktree:
                        self._worktree_index[worktree] = task["id"]
                except Exception:
                    continue

    def _next_id(self) -> int:
        """根据现有任务文件计算下一个可用 ID。"""
        with self._lock:
            ids = []
            for file_path in self._tasks_dir.glob("task_*.json"):
                try:
                    ids.append(int(file_path.stem.split("_")[1]))
                except Exception:
                    continue
            return max(ids, default=0) + 1

    def _path(self, task_id: int) -> Path:
        """返回指定任务 ID 对应的文件路径。"""
        return self._tasks_dir / f"task_{task_id}.json"

    def _load(self, task_id: int) -> dict:
        """加载单个任务 JSON。"""
        with self._lock:
            path = self._path(task_id)
            if not path.exists():
                raise ValueError(f"Task {task_id} not found.")
            return json.loads(path.read_text())

    def _save(self, task: dict):
        """保存任务 JSON，并更新时间戳。"""
        with self._lock:
            task["updated_at"] = time.time()
            self._path(task["id"]).write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")

    def _clear_dependency(self, completed_id: int):
        """某任务完成后，从其他任务的 blockedBy 中移除该 ID。"""
        with self._lock:
            for file_path in self._tasks_dir.glob("task_*.json"):
                task = json.loads(file_path.read_text(encoding="utf-8"))
                if completed_id in task.get("blockedBy", []):
                    task["blockedBy"].remove(completed_id)
                    self._save(task)
