#!/usr/bin/env python3
"""
container.py

依赖组装模块。

该模块负责集中创建主代理运行所需对象，并向上层暴露统一的 `MyAgentApp` 接口。
"""

from __future__ import annotations

from fastapi import WebSocket
from agents.config.config import Config
from agents.memory.memory_manager import MemoryManager
from agents.context.compression_manager import ContextCompressionManager
from agents.task.background_task import BackgroundManager
from agents.core.main_loop import MainLoop
from agents.core.ws_handler import WsHandler
from agents.skill.skill_manager import SkillManager
from agents.task.task_manager import TaskManager
from agents.task.todo_manager import TodoManager
from agents.core.prompt import PromptManager
from agents.core.subagent import SubAgent
from agents.team.message_bus import MessageBus
from agents.team.teammate_manager import TeammateManager
from agents.tools.base_tools import BaseTools
from agents.tools.handlers import ToolHandlers
from agents.tools.mcp_manager import MCPManager
from agents.tools.schemas import ToolSchemas


class MyAgentApp:
    """主代理应用对象，封装运行时依赖与公共入口。"""

    def __init__(self):
        self.config = Config()  # 加载配置与环境变量

        self.memory_manager = MemoryManager(
            embed_base_url=self.config.memory_embed_base_url,
            embed_auth_token=self.config.memory_embed_auth_token,
            embed_model=self.config.memory_embed_model,
            expand_client=self.config.memory_expand_client,
            expand_model=self.config.memory_expand_model,
            rerank_client=self.config.memory_rerank_client,
            rerank_model=self.config.memory_rerank_model,
            synthesize_client=self.config.memory_synthesize_client,
            synthesize_model=self.config.memory_synthesize_model,
            memory_enabled=self.config.memory_enabled,
            memory_dir=self.config.memory_dir,
            consolidation_interval_days=self.config.memory_consolidation_interval_days,
            max_memory_chars=self.config.memory_max_chars,
            forgetting_days=self.config.memory_forgetting_days,
            forgetting_interval_days=self.config.memory_forgetting_interval_days,
            max_vector_records=self.config.memory_max_vector_records,
            max_rag_candidates=self.config.memory_max_rag_candidates,
            expand_max_output_tokens=self.config.memory_expand_max_output_tokens,
            rerank_max_output_tokens=self.config.memory_rerank_max_output_tokens,
            synthesize_max_output_tokens=self.config.memory_synthesize_max_output_tokens,
        )

        self.mcp_manager = MCPManager(
            mcp_enabled=self.config.mcp_enabled,
            mcp_servers_config_path=self.config.mcp_servers_config_path,
        )

        self.base_tools = BaseTools(
            workdir=self.config.workdir,
            require_confirm_high_risk_command=self.config.require_confirm_high_risk_command,
            require_confirm_normal_command=self.config.require_confirm_normal_command
        )
        self.tool_schemas = ToolSchemas(
            mcp_tool_schemas=self.mcp_manager.get_tool_schemas(),
            memory_tool_schemas=self.memory_manager.get_tool_schemas(),
        )
        self.todo_manager = TodoManager()
        self.skill_manager = SkillManager(
            skills_dir=self.config.skills_dir
        )
        self.prompts = PromptManager(
            workdir=self.config.workdir,
            skill_manager=self.skill_manager,
            worktrees_dir=self.config.worktrees_dir,
            memory_prompt=self.memory_manager.build_memory_prompt(),
        )
        self.context_compression_manager = ContextCompressionManager(
            client=self.config.compact_client,
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
            client=self.config.subagent_client,
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
            tool_handlers={},  # 先占位，ToolHandlers 后回填
            build_system_prompt=self.prompts.subagent_system_prompt,
        )
        self.teammate_manager = TeammateManager(
            team_dir=self.config.team_dir,
            message_bus=self.message_bus,
            task_manager=self.tasks_manager,
            client=self.config.teammate_client,
            model=self.config.teammate_model,
            workdir=self.config.workdir,
            poll_interval=self.config.poll_interval,
            idle_timeout=self.config.idle_timeout,
            tool_handlers={},  # 先占位，ToolHandlers 后回填
            tools=self.tool_schemas.teammate_tools,
            build_system_prompt=self.prompts.teammate_system_prompt,
            context_compression_manager=self.context_compression_manager,
            todo_manager=self.todo_manager,
            background_manager=self.background_manager,
            token_threshold=self.config.teammate_token_threshold,
            compact_threshold_pct=self.config.teammate_compact_threshold_pct,
            micro_compact_enabled=self.config.teammate_micro_compact_enabled,
            max_iterations=self.config.teammate_max_iterations,
            max_output_tokens=self.config.teammate_max_output_tokens,
            teammate_sessions_dir=self.config.teammate_sessions_dir,
            ws_handler = None,  # 先占位，WsHandler 后回填
        )
        self.tool_handlers = ToolHandlers(
            base_tools=self.base_tools,
            todo_manager=self.todo_manager,
            skill_manager=self.skill_manager,
            subagent=self.subagent,
            tasks_manager=self.tasks_manager,
            background_manager=self.background_manager,
            message_bus=self.message_bus,
            teammate_manager=self.teammate_manager,
            mcp_handlers=self.mcp_manager.get_tool_handlers(),
            memory_handlers=self.memory_manager.get_tool_handlers(),
        )
        self.subagent.set_tool_handlers(self.tool_handlers.tool_handlers)
        self.teammate_manager.set_tool_handlers(self.tool_handlers.tool_handlers)
        self.main_loop = MainLoop(
            system_prompt=self.prompts.main_agent_system_prompt,
            tools=self.tool_schemas.main_agent_tools,
            tool_handlers=self.tool_handlers.tool_handlers,
            todo_manager=self.todo_manager,
            context_compression_manager=self.context_compression_manager,
            background_manager=self.background_manager,
            message_bus=self.message_bus,
            client=self.config.main_client,
            model=self.config.main_model,
            token_threshold=self.config.mainagent_token_threshold,
            compact_threshold_pct=self.config.mainagent_compact_threshold_pct,
            micro_compact_enabled=self.config.mainagent_micro_compact_enabled,
            max_output_tokens=self.config.mainagent_max_output_tokens,
            main_agent_sessions_dir=self.config.mainagent_sessions_dir,
            ws_handler = None,  # 先占位，WsHandler 后回填
        )

        # ws_handler 作为组件注入
        self.ws_handler = WsHandler(
            mcp_manager=self.mcp_manager,
            skill_manager=self.skill_manager,
            teammate_manager=self.teammate_manager,
            main_loop=self.main_loop,
        )
        # 回填 ws_handler 到 MainLoop 和 TeammateManager
        self.main_loop.set_ws_handler(self.ws_handler)
        self.teammate_manager.set_ws_handler(self.ws_handler)

    # ======================== public ========================

    async def handle(self, websocket: WebSocket) -> None:
        """统一入口：接受 WebSocket 连接，委托 WsHandler 处理。"""
        await self.ws_handler.handle(websocket)
