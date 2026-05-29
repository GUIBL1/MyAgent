#!/usr/bin/env python3
"""
prompt.py

提示词构建模块，集中管理系统提示词与压缩提示词模板。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

class PromptManager:
    """提示词管理器，在构造时预计算所有模板/系统提示词。"""

    def __init__(self, workdir: Path, skill_manager: Any, worktrees_dir: Path, memory_prompt: str = ""):
        self._workdir = workdir
        self._skill_manager = skill_manager
        self._worktrees_dir = worktrees_dir
        self._memory_prompt = memory_prompt

        self.main_agent_system_prompt = self._build_main_agent_system_prompt()
        self.subagent_system_prompt = lambda name: self._build_subagent_system_prompt(name)
        self.teammate_system_prompt = lambda name, role, team_name, workdir: self._build_teammate_system_prompt(name, role, team_name, workdir)
        self.compact_prompt = self._build_compact_prompt()

    # ======================== private ========================

    def _build_main_agent_system_prompt(self) -> str:
        """构建主代理系统提示词。"""
        prompt = (
            "Your name is 'lead', role: 'lead'. "
            f"You are a coding agent at {self._workdir}. Use tools to solve tasks.\n"
            f"Skills:\n{self._skill_manager.skill_descriptions()}\n"
            f"{self._load_project_constraints(self._workdir)}"
        )
        if self._memory_prompt:
            prompt += "\n\n" + self._memory_prompt
        return prompt

    def _build_subagent_system_prompt(self, name: str) -> str:
        """构建 subagent 系统提示词，name 由调用方传入。"""
        prompt = (
            f"Your name is {name}. This is your identity.\n"
            f"Skills:\n{self._skill_manager.skill_descriptions()}\n"
            "Must return a summary after finishing your job.\n"
            f"{self._load_project_constraints(self._workdir)}"
        )
        if self._memory_prompt:
            prompt += "\n\n" + self._memory_prompt
        return prompt

    def _build_teammate_system_prompt(self, name: str, role: str, team_name: str, workdir: str) -> str:
        """构建 teammate 系统提示词，动态参数由调用方传入。"""
        prompt = (
            f"Your name is {name}, role: {role}, team: {team_name}, at {workdir}.\n"
            "Use tool idle when done with current work. You may auto-claim tasks.\n"
            "If you have a major execution plan, submit it via plan_approval_request to lead and wait for approval before executing.\n"
            "Respond to shutdown_request via shutdown_response. If you approve, you will shutdown.\n"
            f"Skills:\n{self._skill_manager.skill_descriptions()}\n"
            f"\n"
            f"{self._worktree_instructions(self._worktrees_dir)}\n"
            f"\n"
            f"{self._load_project_constraints(self._workdir)}"
        )
        if self._memory_prompt:
            prompt += "\n\n" + self._memory_prompt
        return prompt

    @staticmethod
    def _load_project_constraints(workdir: Path) -> str:
        """按优先级加载项目约束文件。"""
        candidates = [
            workdir / ".MyAgent" / "AGENT.md",   # 优先级 1: MyAgent 专用
            workdir / "CLAUDE.md",               # 优先级 2: 兼容 Claude Code
            workdir / "AGENT.md",                # 优先级 3: 兼容其他 agent
        ]
        for path in candidates:
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        return "Project constraints:\n" + content
                except Exception:
                    continue
        return ""

    def _build_compact_prompt(self) -> str:
        """构建上下文压缩提示词。"""
        return (
            "Compress the conversation into a structured summary. "
            "Output only the summary — no preamble, no commentary.\n"
            "Preserve:\n"
            "- Active task IDs, statuses, assigned worktree branches and paths.\n"
            "- In-progress TODO items and their completion state.\n"
            "- Pending tool calls that have not yet received results.\n"
            "- Unresolved errors, blockers, or decisions awaiting user input.\n"
            "- File paths that were modified and the nature of each change.\n"
            "- Shell commands that were run and their exit codes / key output.\n"
            "Drop:\n"
            "- Tool result content already summarized or no longer relevant.\n"
            "- Completed and resolved items whose details are no longer needed.\n"
            "- Verbose log output, stack traces that were already addressed.\n"
            "- Boilerplate system messages and redundant instruction restatements.\n"
            "- Conversation turns that produced no side effects or decisions."
        )

    # ======================== helpers ========================

    def _worktree_instructions(self, worktrees_dir: Path) -> str:
        """生成标准任务执行工作流指令。"""
        return (
            "Standard Task Workflow.\n"
            "You may be assigned a task automatically during idle polling, "
            "or claim one explicitly via scan_and_claim. Either way, follow "
            "this workflow once you have a task.\n"
            "All git worktree operations must create worktrees under "
            f"the directory {worktrees_dir}. "
            "The commands and tool calls shown below are examples — you must "
            "replace placeholders like <task-id>, <slug>, <worktree-branch>, "
            "<abs-path> with actual values from the task you received.\n"
            "1. Create an isolated worktree\n"
            "   Create a new git worktree on a dedicated branch so your work "
            "does not interfere with the main branch or other teammates. "
            "The worktree must be placed under the configured worktrees directory. "
            f"   Example (do not copy verbatim): git worktree add -b wt/<task-id>-<slug> {worktrees_dir}/<task-id> HEAD\n"
            "2. Bind the worktree to the task\n"
            "   Record the worktree branch name and disk path on the task. "
            "   Example (do not copy verbatim): task_bind_worktree(task_id=<id>, worktree_name=\"wt/<id>-<slug>\", worktree_path=\"<abs-path>\")\n"
            "3. Work inside the worktree\n"
            "   All file edits and shell commands must target the worktree "
            "directory you created in step 1, not the main working tree.\n"
            "4. Merge back and clean up\n"
            "   From the main repository, merge the worktree branch into main, "
            "then remove the worktree directory and delete the branch. "
            "   Example (do not copy verbatim): git merge <worktree-branch>; "
            f"git worktree remove {worktrees_dir}/<task-id>; "
            "git branch -d <worktree-branch>\n"
            "5. Complete the task\n"
            "   Mark the task as completed and record the merge timestamp. "
            "   Example (do not copy verbatim): complete_and_merge(task_id=<id>)\n"
        )
