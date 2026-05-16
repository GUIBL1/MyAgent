#!/usr/bin/env python3
"""
tool_display.py

工具调用终端展示模块。

职责：以统一格式向用户展示 LLM 发起的工具调用。
"""

from __future__ import annotations


class ToolDisplay:
    """工具调用终端展示，集中管理工具调用的终端输出格式。"""

    # ======================== public ========================

    def show_call(self, tool_name: str) -> None:
        """打印工具调用提示。"""
        print(f"\033[94m调用工具：{tool_name}\033[0m")

    def show_result(self, tool_name: str, _output: str) -> None:
        """打印工具执行结果。"""
        _ = tool_name
        pass  # 后续扩展：截断长输出、高亮关键信息等
