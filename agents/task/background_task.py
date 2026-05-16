#!/usr/bin/env python3
"""
background_task.py
后台命令执行模块。通过守护线程执行耗时命令，按 agent_name 隔离任务管理与通知队列。agent loop 在每轮调用前统一拉取完成通知注入上下文。

后台任务存储结构：
self._background_tasks = {
    "<agent_name>": {
        "<background_task_id>": {
            "status": "running" | "completed" | "error",
            "command": "原始命令字符串",
            "result": "命令输出文本（完成前为 None）",
        },
        ...
    },
    ...
}

通知队列结构：
self._notifications = {
    "<agent_name>": Queue(
        {"background_task_id": "str", "command": "str", "status": "str", "result": "str"},
        ...
    ),
    ...
}
"""

from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path
from queue import Queue, Empty


class BackgroundManager:
    """后台命令执行与通知管理器。"""

    def __init__(self, workdir: Path, default_background_timeout: int = 120):
        self._workdir = workdir
        self._default_background_timeout = default_background_timeout
        self._background_tasks: dict[str, dict[str, dict]] = {}
        self._notifications: dict[str, Queue] = {}
        self._bg_locks: dict[str, threading.RLock] = {}
        self._nq_locks: dict[str, threading.RLock] = {}

    # ======================== public ========================
    def run_background_task(
            self,
            agent_name: str,
            command: str,
            timeout: int | None = None
        ) -> str:
        """启动后台命令并立即返回任务 ID。timeout 为 None 时使用默认值。"""
        if timeout is None:
            timeout = self._default_background_timeout

        if not command.strip():
            return "Error: empty command."

        bg_task_id = str(uuid.uuid4())[:8]
        bg_lock = self._bg_locks.setdefault(agent_name, threading.RLock())
        nq_lock = self._nq_locks.setdefault(agent_name, threading.RLock())

        with bg_lock:
            if agent_name not in self._background_tasks:
                self._background_tasks[agent_name] = {}
            self._background_tasks[agent_name][bg_task_id] = {
                "status": "running",
                "command": command,
                "result": None,
            }

        with nq_lock:
            if agent_name not in self._notifications:
                self._notifications[agent_name] = Queue()

        threading.Thread(
            target=self._exec,
            args=(agent_name, bg_task_id, command, timeout),
            daemon=True,
        ).start()

        return f"Background task started with id: {bg_task_id}, command: {command}, timeout: {timeout}s."


    def check_background_task(
        self,
        agent_name: str,
        background_task_id: str
    ) -> str:
        """查询指定 agent 的单个后台任务状态。"""
        bg_lock = self._bg_locks.setdefault(agent_name, threading.RLock())
        with bg_lock:
            agent_tasks = self._background_tasks.get(agent_name, {})
            task = agent_tasks.get(background_task_id)
        if not task:
            return f"NotFound task with id: {background_task_id}, it may have completed or never run."

        base = f"Successfully get background task. id: {background_task_id}, status: {task['status']}, command: {task['command']}"
        result = task.get("result")
        if result:
            base += f", result: {result}"
        return base+"."


    def list_all_background_tasks(self, agent_name: str) -> str:
        """列出指定 agent 的全部后台任务。"""
        bg_lock = self._bg_locks.setdefault(agent_name, threading.RLock())
        with bg_lock:
            agent_tasks = self._background_tasks.get(agent_name, {})
        if not agent_tasks:
            return "No background tasks."

        tasks ="\n".join(
            f"id:{tid}, status:{task['status']}, command:{task['command']}"
            for tid, task in agent_tasks.items()
        )
        return "Background tasks:\n"+tasks


    def drain_and_get_notifications(self, agent_name: str) -> list[dict]:
        """清空指定 agent 的通知队列，返回完成通知列表。"""
        nq_lock = self._nq_locks.setdefault(agent_name, threading.RLock())
        with nq_lock:
            queue = self._notifications.get(agent_name)
        if queue is None:
            return []

        notifications: list[dict] = []
        while True:
            try:
                notifications.append(queue.get_nowait())
            except Empty:
                break
        return notifications

    # ======================== private ========================
    def _exec(self, agent_name: str, bg_task_id: str, command: str, timeout: int):
        """线程入口：执行命令并写入通知队列。"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self._workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip() or "(no output)."
            self._set_result(agent_name, bg_task_id, "completed", output)
        except Exception as exc:
            self._set_result(agent_name, bg_task_id, "error", str(exc))

        self._push_notification(agent_name, bg_task_id)
        self._cleanup_task(agent_name, bg_task_id)

    def _set_result(self, agent_name: str, bg_task_id: str, status: str, output: str):
        """更新任务状态与结果。"""
        bg_lock = self._bg_locks.setdefault(agent_name, threading.RLock())
        with bg_lock:
            if agent_name in self._background_tasks:
                self._background_tasks[agent_name][bg_task_id].update(
                    {"status": status, "result": output}
                )

    def _push_notification(self, agent_name: str, bg_task_id: str):
        """将完成通知写入队列。"""
        nq_lock = self._nq_locks.setdefault(agent_name, threading.RLock())
        with nq_lock:
            queue = self._notifications.get(agent_name)
        if queue is None:
            return

        bg_lock = self._bg_locks.setdefault(agent_name, threading.RLock())
        with bg_lock:
            task = self._background_tasks.get(agent_name, {}).get(bg_task_id, {})

        queue.put({
            "background_task_id": bg_task_id,
            "command": task.get("command", ""),
            "status": task.get("status", "error"),
            "result": task.get("result", ""),
        })

    def _cleanup_task(self, agent_name: str, bg_task_id: str):
        """通知推送后删除后台任务记录，防止存储膨胀。"""
        bg_lock = self._bg_locks.setdefault(agent_name, threading.RLock())
        with bg_lock:
            agent_tasks = self._background_tasks.get(agent_name)
            if agent_tasks:
                agent_tasks.pop(bg_task_id, None)
