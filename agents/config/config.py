#!/usr/bin/env python3
"""
config.py

环境与路径配置模块。

职责：
1. 加载环境变量并初始化 LLM 客户端。
2. 解析当前工作目录。
3. 提供统一的状态目录路径常量。
4. 提供各组件独立的模型配置与运行时参数。
"""

from __future__ import annotations

import os
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv


class Config:
    """集中管理所有环境配置与路径常量。"""

    def __init__(self):
        # 从 WORKDIR/.MyAgent/config/.env 加载配置。
        # 目录不存在时自动创建，文件不存在时静默跳过。
        _env_path = Path.cwd() / ".MyAgent" / "config" / ".env"
        _env_path.parent.mkdir(parents=True, exist_ok=True)
        load_dotenv(dotenv_path=_env_path, override=True)

        # main agent
        self.main_client = Anthropic(
            base_url=os.getenv("AGENT_MAIN_BASE_URL"),
            auth_token=os.getenv("AGENT_MAIN_AUTH_TOKEN"),
        )
        self.main_model = os.getenv("AGENT_MAIN_MODEL")

        # subagent
        self.subagent_client = Anthropic(
            base_url=os.getenv("AGENT_SUBAGENT_BASE_URL"),
            auth_token=os.getenv("AGENT_SUBAGENT_AUTH_TOKEN"),
        )
        self.subagent_model = os.getenv("AGENT_SUBAGENT_MODEL")

        # teammate
        self.teammate_client = Anthropic(
            base_url=os.getenv("AGENT_TEAMMATE_BASE_URL"),
            auth_token=os.getenv("AGENT_TEAMMATE_AUTH_TOKEN"),
        )
        self.teammate_model = os.getenv("AGENT_TEAMMATE_MODEL")

        # compact
        self.compact_client = Anthropic(
            base_url=os.getenv("AGENT_COMPACT_BASE_URL"),
            auth_token=os.getenv("AGENT_COMPACT_AUTH_TOKEN"),
        )
        self.compact_model = os.getenv("AGENT_COMPACT_MODEL")

        # memory embed
        self.memory_embed_base_url = os.getenv("AGENT_MEMORY_EMBED_BASE_URL")
        self.memory_embed_auth_token = os.getenv("AGENT_MEMORY_EMBED_AUTH_TOKEN")
        self.memory_embed_model = os.getenv("AGENT_MEMORY_EMBED_MODEL")

        # memory expand
        self.memory_expand_client = Anthropic(
            base_url=os.getenv("AGENT_MEMORY_EXPAND_BASE_URL"),
            auth_token=os.getenv("AGENT_MEMORY_EXPAND_AUTH_TOKEN"),
        )
        self.memory_expand_model = os.getenv("AGENT_MEMORY_EXPAND_MODEL")

        # memory rerank
        self.memory_rerank_client = Anthropic(
            base_url=os.getenv("AGENT_MEMORY_RERANK_BASE_URL"),
            auth_token=os.getenv("AGENT_MEMORY_RERANK_AUTH_TOKEN"),
        )
        self.memory_rerank_model = os.getenv("AGENT_MEMORY_RERANK_MODEL")

        # memory synthesize
        self.memory_synthesize_client = Anthropic(
            base_url=os.getenv("AGENT_MEMORY_SYNTHESIZE_BASE_URL"),
            auth_token=os.getenv("AGENT_MEMORY_SYNTHESIZE_AUTH_TOKEN"),
        )
        self.memory_synthesize_model = os.getenv("AGENT_MEMORY_SYNTHESIZE_MODEL")

        # 定义全局路径常量，确保所有模块使用统一的目录结构
        self.workdir = Path.cwd()
        # 本地状态目录，存储系统运行需要的文件
        self.local_state_dir = self.workdir / ".MyAgent"
        self.local_state_dir.mkdir(exist_ok=True)

        # Agent Teams 配置存储路径
        self.team_dir = self.local_state_dir / "team"
        # Agent Inbox 供 Agent Team 成员通信
        self.inbox_dir = self.team_dir / "inbox"

        # 任务系统存储目录
        self.tasks_dir = self.local_state_dir / "tasks"

        # Skills 存储目录
        self.skills_dir = self.local_state_dir / "skills"

        # MCP 开关
        self.mcp_enabled = self._env_bool("AGENT_MCP_ENABLED", True)
        # MCP 服务器配置文件路径
        self.mcp_servers_config_path = self.local_state_dir / "config" / "mcp_servers.json"

        # 会话存储目录
        self.sessions_dir = self.local_state_dir / "sessions"
        # 压缩后会话的原始会话备份目录
        self.sessions_backup_dir = self.sessions_dir / "backup"
        # Teammate 会话目录
        self.teammate_sessions_dir = self.sessions_dir / "teammates"
        # MainAgent 会话目录
        self.mainagent_sessions_dir = self.sessions_dir / "main_agent"

        # 工作树物理目录（由 LLM 通过 bash 管理，代码只约定路径）
        self.worktrees_dir = self.local_state_dir / "worktrees"


        self.global_state_dir = Path.home() / ".MyAgent"

        # 记忆系统存储目录（全局，跨项目共享）
        self.memory_dir = self.global_state_dir / "memory"


        # ======================== 运行时参数 ========================

        # main agent 每次 LLM 调用的最大输出 token 数
        self.mainagent_max_output_tokens = int(os.getenv("AGENT_MAINAGENT_MAX_OUTPUT_TOKENS", "10000"))
        # main agent 上下文 token 上限，达到该阈值时触发自动压缩
        self.mainagent_token_threshold = int(os.getenv("AGENT_MAINAGENT_TOKEN_THRESHOLD", "100000"))
        # main agent 自动压缩触发比例，当上下文 token 数达到 token_threshold * 此比例时触发
        self.mainagent_compact_threshold_pct = float(os.getenv("AGENT_MAINAGENT_COMPACT_THRESHOLD_PCT", "0.8"))
        # main agent 是否开启每轮微压缩
        self.mainagent_micro_compact_enabled = self._env_bool("AGENT_MAINAGENT_MICRO_COMPACT_ENABLED", False)

        # microcompact 时保留的最近工具结果数量
        self.microcompact_tool_result_retention = int(os.getenv("AGENT_MICROCOMPACT_TOOL_RESULT_RETENTION", "3"))
        # auto_compact 时模型摘要输出的最大 token 数
        self.compact_max_output_tokens = int(os.getenv("AGENT_COMPACT_MAX_OUTPUT_TOKENS", "10000"))

        # 后台任务的默认超时秒数
        self.default_background_timeout = int(os.getenv("AGENT_DEFAULT_BACKGROUND_TIMEOUT", "120"))

        # teammate 空闲轮询的周期间隔，单位秒
        self.poll_interval = int(os.getenv("AGENT_POLL_INTERVAL", "5"))
        # teammate 空闲轮询的总时长上限，超时未收到消息或任务则自动关机
        self.idle_timeout = int(os.getenv("AGENT_IDLE_TIMEOUT", "60"))

        # 高风险命令执行前是否需要用户确认
        self.require_confirm_high_risk_command = self._env_bool("AGENT_REQUIRE_CONFIRM_HIGH_RISK_COMMAND", True)
        # 普通命令执行前是否需要用户确认
        self.require_confirm_normal_command = self._env_bool("AGENT_REQUIRE_CONFIRM_NORMAL_COMMAND", True)

        # subagent 每次 LLM 调用的最大输出 token 数
        self.subagent_max_output_tokens = int(os.getenv("AGENT_SUBAGENT_MAX_OUTPUT_TOKENS", "8000"))
        # subagent 工作循环的最大迭代次数
        self.subagent_max_iterations = int(os.getenv("AGENT_SUBAGENT_MAX_ITERATIONS", "50"))
        # subagent 上下文 token 上限
        self.subagent_token_threshold = int(os.getenv("AGENT_SUBAGENT_TOKEN_THRESHOLD", "100000"))
        # subagent 自动压缩触发比例
        self.subagent_compact_threshold_pct = float(os.getenv("AGENT_SUBAGENT_COMPACT_THRESHOLD_PCT", "0.8"))
        # subagent 是否开启每轮微压缩
        self.subagent_micro_compact_enabled = self._env_bool("AGENT_SUBAGENT_MICRO_COMPACT_ENABLED", False)

        # teammate 工作阶段的最大迭代次数
        self.teammate_max_iterations = int(os.getenv("AGENT_TEAMMATE_MAX_ITERATIONS", "50"))
        # teammate 每次 LLM 调用的最大输出 token 数
        self.teammate_max_output_tokens = int(os.getenv("AGENT_TEAMMATE_MAX_OUTPUT_TOKENS", "10000"))
        # teammate 上下文 token 上限
        self.teammate_token_threshold = int(os.getenv("AGENT_TEAMMATE_TOKEN_THRESHOLD", "100000"))
        # teammate 自动压缩触发比例
        self.teammate_compact_threshold_pct = float(os.getenv("AGENT_TEAMMATE_COMPACT_THRESHOLD_PCT", "0.8"))
        # teammate 是否开启每轮微压缩
        self.teammate_micro_compact_enabled = self._env_bool("AGENT_TEAMMATE_MICRO_COMPACT_ENABLED", False)

        # 记忆系统开关
        self.memory_enabled = self._env_bool("AGENT_MEMORY_ENABLED", True)
        # 记忆整理时间阈值（天）
        self.memory_consolidation_interval_days = int(os.getenv("AGENT_MEMORY_CONSOLIDATION_INTERVAL_DAYS", "30"))
        # MEMORY.md 空间阈值（字符数）
        self.memory_max_chars = int(os.getenv("AGENT_MEMORY_MAX_CHARS", "1500"))
        # 记忆过期天数，距末次访问超此天数且访问次数<2的记忆将被遗忘
        self.memory_forgetting_days = int(os.getenv("AGENT_MEMORY_FORGETTING_DAYS", "90"))
        # 遗忘触发间隔（天），距上次遗忘超过此天数才再次执行
        self.memory_forgetting_interval_days = int(os.getenv("AGENT_MEMORY_FORGETTING_INTERVAL_DAYS", "90"))
        # Chroma 向量记录硬上限
        self.memory_max_vector_records = int(os.getenv("AGENT_MEMORY_MAX_VECTOR_RECORDS", "5000"))
        # RAG 召回 + 重排序后送入合成的最大候选数
        self.memory_max_rag_candidates = int(os.getenv("AGENT_MEMORY_MAX_RAG_CANDIDATES", "10"))
        # expand / rerank / synthesize 各自最大输出 token 数
        self.memory_expand_max_output_tokens = int(os.getenv("AGENT_MEMORY_EXPAND_MAX_TOKENS", "100000"))
        self.memory_rerank_max_output_tokens = int(os.getenv("AGENT_MEMORY_RERANK_MAX_TOKENS", "100000"))
        self.memory_synthesize_max_output_tokens = int(os.getenv("AGENT_MEMORY_SYNTHESIZE_MAX_TOKENS", "100000"))

    # ======================== private ========================

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        """读取布尔环境变量，非法值回退到默认值。"""
        raw_value = os.getenv(name)
        if raw_value is None:
            return default

        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
