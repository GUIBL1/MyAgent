# MyAgent

多 agent 协作工具。Lead（主控）调度 SubAgent（子任务隔离执行）和 Teammate（持久队友协作），全部通过 WebSocket 推送到 Vue 3 前端实时渲染。

## 快速开始

```bash
pip install -e .
cd frontend && npm install && npm run build && cd ..

# 在工作目录下创建 .MyAgent/config/.env
mkdir -p .MyAgent/config
cat > .MyAgent/config/.env << EOF
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=sk-your-api-key
AGENT_MAIN_MODEL=deepseek-v4-pro
AGENT_SUBAGENT_MODEL=deepseek-v4-pro
AGENT_TEAMMATE_MODEL=deepseek-v4-pro
AGENT_COMPACT_MODEL=deepseek-v4-pro
EOF

myagent    # → http://127.0.0.1:8000
```

## 架构

```
WebSocket (ws://127.0.0.1:8000/ws/chat)
  └─ WsHandler — 多路事件复用器
       ├─ main 管路         ← MainLoop（主 agent，每次发送启动一个线程）
       └─ teammate-* 管路   ← TeammateManager（daemon 线程，工作+空闲两阶段）

每个 agent 循环 yield Iterator[StreamEvent] → 队列 → _dispatch
→ delta 缓冲合并 → transcript 写入 → WebSocket 推送 → Vue 3 前端
```

### Agent 角色

| 角色 | 线程 | 生命周期 | 上下文 |
|------|------|----------|--------|
| Lead | 每次发送新建 | 单轮用户消息 | 全部工具 |
| SubAgent | 同步调用 | yield 文本摘要后销毁 | 受限工具集 |
| Teammate | Daemon | 工作阶段（最多 N 轮）→ 空闲轮询 → 关机 | 持久身份 + 收件箱 |

### 右侧面板

三个标签页：
- **状态** — Token 用量进度条 + Todo 列表
- **能力** — MCP 服务器状态 + Skill 注册表
- **团队** — 队员列表 → 点击"运行查看"查看队友输出（实时流式 + 历史消息），支持嵌套子面板查看 `recall_memory` 和 `subagent` 详情

## 后端模块

```
agents/
├── config/           配置 — .env 加载、6+ Anthropic 客户端、路径常量
├── context/          ContextCompressionManager — micro_compact + auto_compact
├── core/
│   ├── container     MyAgentApp — 依赖注入组装全部对象
│   ├── main_loop     MainLoop — 主 agent 推理循环（压缩、收件箱、工具路由）
│   ├── prompt        PromptManager — 4 套系统提示词（lead/subagent/teammate/compact）
│   ├── session       SessionManager — 双文件持久化（transcript.jsonl + context.jsonl），支持回退
│   ├── stream_events EventType 枚举（33 种）+ StreamEvent 数据类
│   ├── subagent      SubAgent — 隔离子任务执行器，StreamEvent 生成器
│   ├── web_server    FastAPI + uvicorn，挂载前端 dist 静态文件
│   └── ws_handler    多路事件复用，delta 合并，transcript 分发
├── memory/           MemoryManager — write_memory（短期）+ recall_memory（RAG via Chroma）
├── skill/            SkillManager — 解析 SKILL.md 的 YAML 风格 front matter
├── task/
│   ├── background    BackgroundManager — daemon 线程后台 shell 执行 + 通知队列
│   ├── task          TaskManager — 文件持久化任务 CRUD、scan_and_claim
│   └── todo          TodoManager — 内存中按 agent 隔离的 todo 列表
├── team/
│   ├── message_bus   文件收件箱消息协议（JSONL），支持私聊/广播/关机/计划审批
│   └── teammate      TeammateManager — spawn/restart，working/idle/shutdown 生命周期
└── tools/
    ├── base_tools    run_shell（风险检测+确认）、read_file、write_file、edit_file
    ├── handlers      主 tool_name → handler 映射（23+ 内置 + MCP + memory）
    ├── mcp_manager   MCP 服务器子进程管理（工具、资源、提示）
    └── schemas       集中式 JSON Schema 定义，按 agent 类型分 4 个工具层级
```

## 关键设计决策

- **全生成器模式**：所有 LLM 调用者统一 yield `Iterator[StreamEvent]`，流式清洁
- **Delta 缓冲**：同类型连续 delta 在 ws_handler 中合并，类型切换时 flush
- **线程安全**：`queue.Queue` 跨线程通信，`SessionManager` 线程安全 transcript 写入
- **原子写入**：temp file + `os.replace` + 目录 fsync，所有持久化写操作
- **依赖注入**：`container.py` 集中创建全部对象，回填交叉引用（无循环导入）

## 存储结构

```
.MyAgent/
├── config/.env              API 密钥与模型设置
├── team/
│   ├── team_config.json     队员与状态（lead 始终存在）
│   └── inbox/*.jsonl        各队员收件箱
├── tasks/*.json             文件持久化任务记录
├── sessions/
│   ├── main_agent/           主 agent 会话 transcript
│   ├── teammates/            队友会话 transcript
│   └── backup/               auto_compact 归档快照
├── skills/                   SKILL.md 技能文件（name + description 前置元数据）
└── worktrees/                git worktree 隔离目录
```

## 环境变量

全部配置通过 `.MyAgent/config/.env`。核心变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANTHROPIC_BASE_URL` | — | API 基地址 |
| `ANTHROPIC_AUTH_TOKEN` | — | API 密钥 |
| `AGENT_MAIN_MODEL` | — | Lead 模型 |
| `AGENT_SUBAGENT_MODEL` | — | SubAgent 模型 |
| `AGENT_TEAMMATE_MODEL` | — | Teammate 模型 |
| `AGENT_COMPACT_MODEL` | — | 压缩模型 |
| `AGENT_WORKDIR` | `.` | 工作目录 |
| `MCP_ENABLED` | `false` | 启用 MCP 服务器 |
| `MEMORY_ENABLED` | `false` | 启用记忆子系统 |
| `AGENT_MAINAGENT_TOKEN_THRESHOLD` | `200000` | Token 预算 |
| `AGENT_TEAMMATE_POLL_INTERVAL` | `5` | 空闲轮询间隔（秒） |
| `AGENT_TEAMMATE_IDLE_TIMEOUT` | `300` | 空闲超时关机（秒） |
