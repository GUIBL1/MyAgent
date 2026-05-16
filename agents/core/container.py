#!/usr/bin/env python3
"""
container.py

依赖组装模块。

该模块负责集中创建主代理运行所需对象，并向上层暴露统一的 `MyAgentApp` 接口。
"""

from __future__ import annotations

from agents.config.config import Config
from agents.context.compression_manager import ContextCompressionManager
from agents.task.background_task import BackgroundManager
from agents.core.main_loop import MainLoop
from agents.skill.skill_manager import SkillManager
from agents.task.task_manager import TaskManager
from agents.task.todo_manager import TodoManager
from agents.core.prompt import PromptManager
from agents.core.subagent import SubAgent
from agents.team.message_bus import MessageBus
from agents.team.teammate_manager import TeammateManager
from agents.tools.base_tools import BaseTools
from agents.tools.handlers import ToolHandlers
from agents.tools.schemas import ToolSchemas
from agents.tools.tool_display import ToolDisplay


class MyAgentApp:
    """主代理应用对象，封装运行时依赖与公共入口。"""

    def __init__(self):
        self.config = Config()  # 加载配置与环境变量
        self.base_tools = BaseTools(
            workdir=self.config.workdir,
            require_confirm_high_risk_command=self.config.require_confirm_high_risk_command,
            require_confirm_normal_command=self.config.require_confirm_normal_command
        )
        self.tool_schemas = ToolSchemas()
        self.todo_manager = TodoManager()
        self.skill_manager = SkillManager(
            skills_dir=self.config.skills_dir
        )
        self.prompts = PromptManager(
            workdir=self.config.workdir,
            skill_manager=self.skill_manager,
            worktrees_dir=self.config.worktrees_dir
        )
        self.context_compression_manager = ContextCompressionManager(
            client=self.config.client,
            model=self.config.compact_model,
            backup_dir=self.config.sessions_backup_dir,
            microcompact_tool_result_retention=self.config.microcompact_tool_result_retention,
            compact_max_output_tokens=self.config.compact_max_output_tokens,
            compact_prompt=self.prompts.compact_prompt,
        )
        self.tasks_manager = TaskManager(
            tasks_dir=self.config.tasks_dir
        )
        self.message_bus = MessageBus(
            inbox_dir=self.config.inbox_dir
        )
        self.background_manager = BackgroundManager(
            workdir=self.config.workdir,
            default_background_timeout=self.config.default_background_timeout
        )
        self.subagent = SubAgent(
            client=self.config.client,
            model=self.config.subagent_model,
            max_iterations=self.config.subagent_max_iterations,
            max_output_tokens=self.config.subagent_max_output_tokens,
            token_threshold=self.config.subagent_token_threshold,
            compact_threshold_pct=self.config.subagent_compact_threshold_pct,
            micro_compact_enabled=self.config.subagent_micro_compact_enabled,
            explore_subagent_tools=self.tool_schemas.explore_subagent_tools,
            general_subagent_tools=self.tool_schemas.general_subagent_tools,
            todo_manager=self.todo_manager,
            context_compression_manager=self.context_compression_manager,
            subagent_sessions_dir=self.config.subagent_sessions_dir,
            handlers={},  # 先占位，ToolHandlers 后回填
            system_prompt_template=self.prompts.subagent_system_prompt,
        )
        self.teammate_manager = TeammateManager(
            team_dir=self.config.team_dir,
            message_bus=self.message_bus,
            task_manager=self.tasks_manager,
            client=self.config.client,
            model=self.config.teammate_model,
            workdir=self.config.workdir,
            poll_interval=self.config.poll_interval,
            idle_timeout=self.config.idle_timeout,
            tool_handlers={},  # 先占位，ToolHandlers 后回填
            tools=self.tool_schemas.teammate_tools,
            system_prompt_template=self.prompts.teammate_system_prompt,
            context_compression_manager=self.context_compression_manager,
            todo_manager=self.todo_manager,
            background_manager=self.background_manager,
            token_threshold=self.config.teammate_token_threshold,
            compact_threshold_pct=self.config.teammate_compact_threshold_pct,
            micro_compact_enabled=self.config.teammate_micro_compact_enabled,
            max_iterations=self.config.teammate_max_iterations,
            max_output_tokens=self.config.teammate_max_output_tokens,
            teammate_sessions_dir=self.config.teammate_sessions_dir,
        )
        self.tool_display = ToolDisplay()
        self.tool_handlers = ToolHandlers(
            base_tools=self.base_tools,
            todo_manager=self.todo_manager,
            skill_manager=self.skill_manager,
            subagent=self.subagent,
            tasks_manager=self.tasks_manager,
            background_manager=self.background_manager,
            message_bus=self.message_bus,
            teammate_manager=self.teammate_manager,
        )
        self.subagent._handlers = self.tool_handlers.tool_handlers  # 回填
        self.teammate_manager._tool_handlers = self.tool_handlers.tool_handlers  # 回填

        self.main_loop = MainLoop(
            system_prompt=self.prompts.main_agent_system_prompt,
            tools=self.tool_schemas.main_agent_tools,
            tool_handlers=self.tool_handlers.tool_handlers,
            todo_manager=self.todo_manager,
            context_compression_manager=self.context_compression_manager,
            background_manager=self.background_manager,
            message_bus=self.message_bus,
            client=self.config.client,
            model=self.config.main_model,
            token_threshold=self.config.mainagent_token_threshold,
            compact_threshold_pct=self.config.mainagent_compact_threshold_pct,
            micro_compact_enabled=self.config.mainagent_micro_compact_enabled,
            max_output_tokens=self.config.mainagent_max_output_tokens,
            sessions_dir=self.config.mainagent_sessions_dir,
            tool_display=self.tool_display,
        )


    def agent_loop(self, messages: list):
        """执行一轮完整主代理循环。"""
        self.main_loop.run_main_loop(messages)
