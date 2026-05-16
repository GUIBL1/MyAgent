# MyAgent

多 agent 协作编码工具。以单一大模型实例驱动三个角色——**Lead**（主控）、**SubAgent**（子任务）、**Teammate**（队友）——在独立线程中协同完成复杂任务。

## 架构

```
用户输入 → ReplLoop → MainLoop ⇄ LLM（流式）
                        ↓ tool_use
                   ToolHandlers ──→ BaseTools       (shell / file)
                                 ├─ TaskManager      (持久化任务)
                                 ├─ SubAgent         (隔离子代理)
                                 ├─ TeammateManager  (daemon 队友)
                                 ├─ MessageBus       (团队通信)
                                 ├─ BackgroundManager(后台命令)
                                 └─ SkillManager     (技能加载)
```

三种 Agent 各有独立的消息上下文和 LLM 调用循环：

- **Lead** — 主线程常驻，负责分解任务、调度队友、审批计划。流式输出到终端。
- **SubAgent** — 同步调用，隔离上下文中完成探索/读写任务，返回文本摘要即销毁。
- **Teammate** — daemon 线程持久运行，工作阶段自主调用工具，空闲阶段轮询收件箱并自动认领任务板上的空闲任务。

## 功能

**代码执行** — `run_shell` `read_file` `write_file` `edit_file`，原子写入、路径越界防护、高风险命令拦截。

**任务管理** — 文件持久化任务板（`create_task` `update_task` `delete_task`），支持状态流转、依赖阻断（blockedBy）、owner 分配。

**团队协作** — 文件收件箱消息协议（JSONL），支持私聊、广播、关机请求/响应、计划提交/审批。

**工作树隔离** — teammate 自动 `scan_and_claim` 空闲任务，在独立 git worktree 中编码完成后合并回主干。

**上下文管理** — `micro_compact` 清理旧工具结果，`auto_compact` 备份后压缩为 LLM 摘要，`/compact` 命令手动触发。

**其他** — 后台命令 daemon 线程执行、技能按需加载、Todo 列表自动提醒。

## 使用

```bash
# 安装
pip install -e .

# 配置 — 在工作目录下创建 .MyAgent/config/.env
cat > .MyAgent/config/.env << EOF
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=sk-your-api-key
AGENT_MAIN_MODEL=deepseek-v4-pro
AGENT_SUBAGENT_MODEL=deepseek-v4-pro
AGENT_TEAMMATE_MODEL=deepseek-v4-pro
AGENT_COMPACT_MODEL=deepseek-v4-pro
EOF

# 启动
myagent
```

REPL 命令：`/tasks` 查看任务 · `/team` 查看团队 · `/compact` 压缩上下文 · `/q` 退出。

## 工作目录

首次运行自动创建 `.MyAgent/`，所有状态数据自包含在内：

```
.MyAgent/
├── config/.env              ← 唯一配置入口
├── team/
│   ├── team_config.json     ← 团队成员与状态
│   └── inbox/*.jsonl        ← 各成员收件箱
├── tasks/*.json             ← 持久化任务
├── sessions/
│   ├── main_agent/          ← lead 会话
│   ├── subagents/           ← subagent 会话
│   ├── teammates/           ← teammate 会话
│   └── backup/              ← 压缩前快照
├── skills/                  ← SKILL.md 技能文件
└── worktrees/               ← git worktree 隔离目录
```

删除 `.MyAgent/` 即重置全部状态，在不同目录下运行互不干扰。
