#!/usr/bin/env python3
"""
command.py

REPL 交互与斜杠命令分发模块。

职责：
1. 读取用户输入。
2. 先分发斜杠命令。
3. 非命令输入进入主代理循环。
"""

from __future__ import annotations


class ReplLoop:
    """REPL 交互循环，封装命令分发与主代理调用。"""

    def __init__(self, my_agent_app):
        self._my_agent_app = my_agent_app

    # ======================== public ========================

    def repl_loop(self):
        """启动交互式命令行会话。"""
        history: list[dict] = []

        while True:
            try:
                command = input("\033[92mMyAgent >> \033[0m")
            except (EOFError, KeyboardInterrupt):
                break

            if command.strip().lower() in ("/q", "/exit", ""):
                break

            if self._handle_slash_command(command, history):
                continue

            history.append({"role": "user", "content": command})
            self._my_agent_app.agent_loop(history)

    # ======================== private ========================

    def _handle_slash_command(self, command: str, history: list[dict]) -> bool:
        """处理 REPL 斜杠命令。返回 True 表示已处理，False 表示非命令输入。"""
        cmd = command.strip()

        if cmd == "/compact":
            if history:
                print("[manual compact via /compact]")
                history[:] = self._my_agent_app.context_compression_manager.auto_compact(history)
            return True

        if cmd == "/tasks":
            print(self._my_agent_app.tasks_manager.list_all_tasks())
            return True

        if cmd == "/team":
            print(self._my_agent_app.teammate_manager.get_team_config())
            return True

        return False
