#!/usr/bin/env python3
"""
runtime.py

运行时入口模块。

该文件仅保留入口职责：
1. 创建主代理应用对象。
2. 启动 REPL 交互循环。
"""

from __future__ import annotations

from agents.core.container import MyAgentApp
from agents.core.command import ReplLoop


class Runtime:
    """运行时入口，封装应用创建与 REPL 启动。"""

    def __init__(self):
        self._my_agent_app = MyAgentApp()

    # ======================== public ========================

    def run(self):
        """创建应用并启动命令行交互会话。"""
        ReplLoop(self._my_agent_app).repl_loop()


def main():
    """CLI 入口点，供 pyproject.toml 的 console_scripts 调用。"""
    Runtime().run()
