<script setup lang="ts">
import { renderMarkdown } from '../utils/markdown'

defineProps<{
  blocks: any[]
  streaming?: boolean
  isLast?: boolean
}>()

const emit = defineEmits<{
  (e: 'open-recall-detail', block: any): void
  (e: 'open-subagent-detail', block: any): void
}>()

function mdHtml(text: string): string { return renderMarkdown(text) }
</script>

<template>
  <template v-for="(block, bi) in blocks" :key="bi">
    <!-- 思考块 -->
    <div v-if="block.type === 'thinking'" class="thinking">
      <details :open="block.active">
        <summary>思考过程</summary>
        <div class="thinking-content md-body" v-html="mdHtml(block.content)"></div>
      </details>
    </div>

    <!-- 工具调用 -->
    <div v-else-if="block.type === 'tool'" class="tool-call" :class="block.status">
      <details :open="block.status === 'running'">
        <summary class="tool-header">
          <span class="tool-dot"></span>
          <code>{{ block.name }}</code>
          <span class="tool-summary-right">
            <span v-if="block.name === 'recall_memory'" class="detail-btn-inline" @click.prevent.stop="emit('open-recall-detail', block)">
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <circle cx="5.5" cy="5.5" r="4"/><line x1="9" y1="9" x2="11" y2="11"/>
                <line x1="5.5" y1="3.5" x2="5.5" y2="7.5"/><line x1="3.5" y1="5.5" x2="7.5" y2="5.5"/>
              </svg>
              查看详情
            </span>
            <span v-if="block.name === 'use_subagent'" class="detail-btn-inline" @click.prevent.stop="emit('open-subagent-detail', block)">
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <circle cx="5.5" cy="5.5" r="4"/><line x1="9" y1="9" x2="11" y2="11"/>
                <line x1="5.5" y1="3.5" x2="5.5" y2="7.5"/><line x1="3.5" y1="5.5" x2="7.5" y2="5.5"/>
              </svg>
              查看详情
            </span>
            <span class="tool-meta" :class="block.status">{{ block.status === 'running' ? '执行中…' : '完成' }}</span>
          </span>
        </summary>
        <div class="tool-body">
          <div class="tool-input"><pre>{{ JSON.stringify(block.input, null, 2) }}</pre></div>
          <div v-if="block.result" class="tool-result"><pre>{{ block.result }}</pre></div>
        </div>
      </details>
    </div>

    <!-- 文本块 -->
    <div v-else-if="block.type === 'text'" class="message-text md-body" v-html="mdHtml(block.content)"></div>

    <!-- Micro Compact -->
    <div v-else-if="block.type === 'micro_compact'" class="status-card micro-card">
      <details>
        <summary><span class="status-dot"></span><span>MICRO COMPACT</span></summary>
        <div class="status-card-body">{{ block.content }}</div>
      </details>
    </div>

    <!-- Inbox Message -->
    <div v-else-if="block.type === 'inbox_message'" class="status-card inbox-card">
      <details :open="block.active !== false">
        <summary><span class="status-dot"></span><span>收件箱 INBOX</span></summary>
        <div class="status-card-body">{{ block.content }}</div>
      </details>
    </div>

    <!-- Task Claimed -->
    <div v-else-if="block.type === 'task_claimed'" class="status-card task-card">
      <details :open="block.active !== false">
        <summary><span class="status-dot"></span><span>收到任务 TASK</span></summary>
        <div class="status-card-body">{{ block.content }}</div>
      </details>
    </div>

    <!-- Background Notification -->
    <div v-else-if="block.type === 'background_notification'" class="status-card bg-card">
      <details open>
        <summary><span class="status-dot done"></span><span>后台任务通知</span></summary>
        <div class="status-card-body"><pre>{{ block.content }}</pre></div>
      </details>
    </div>

    <!-- Todo Reminder -->
    <div v-else-if="block.type === 'todo_reminder'" class="todo-reminder-block">
      <span class="todo-icon-svg">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="1" y="2" width="12" height="10" rx="2"/><path d="M4 7l2 2 4-4"/>
        </svg>
      </span>
      <span><span class="todo-sys-label">SYSTEM</span> {{ block.content }}</span>
    </div>

    <!-- Auto Compact -->
    <div v-else-if="block.type === 'auto_compact'" class="status-card compact-card" :class="{ done: block.compactStatus === 'done' }">
      <details open>
        <summary>
          <span class="status-dot" :class="block.compactStatus === 'done' ? 'done' : 'running'"></span>
          <span>上下文压缩 Auto Compact</span>
          <span class="compact-badge">{{ block.compactStatus === 'done' ? '完成' : '进行中…' }}</span>
        </summary>
        <div class="status-card-body">
          <div v-if="block.content" class="compact-start-msg">{{ block.content }}</div>
          <div v-if="block.thinking" class="compact-thinking"><div class="compact-label">Thinking</div><div class="compact-thinking-text">{{ block.thinking }}</div></div>
          <div v-if="block.summary" class="compact-summary"><div class="compact-label">Summary</div><div class="compact-summary-text">{{ block.summary }}</div></div>
          <div v-if="block.result" class="compact-done-msg">{{ block.result }}</div>
          <span v-if="block.compactStatus === 'running'" class="compact-cursor">|</span>
        </div>
      </details>
    </div>
  </template>
  <span v-if="streaming && isLast" class="cursor">|</span>
</template>

<style scoped>
/* CSS 变量定义在 index.html 全局 :root 中 */

/* ======================== Markdown ======================== */
.md-body :deep(h1), .md-body :deep(h2), .md-body :deep(h3), .md-body :deep(h4) {
  margin: 16px 0 6px; font-family: 'Space Grotesk', sans-serif; font-weight: 600; color: var(--fg); letter-spacing: -0.2px;
}
.md-body :deep(h1) { font-size: 1.25em; }
.md-body :deep(h2) { font-size: 1.1em; border-bottom: 1px solid var(--border-light); padding-bottom: 4px; }
.md-body :deep(h3) { font-size: 1.0em; }
.md-body :deep(p)  { margin: 6px 0; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 1.6em; margin: 6px 0; }
.md-body :deep(li) { margin: 3px 0; }
.md-body :deep(strong) { font-weight: 600; color: var(--fg); }
.md-body :deep(em)     { font-style: italic; }
.md-body :deep(code) {
  font-family: 'JetBrains Mono', monospace; font-size: 0.88em; font-weight: 500;
  background: var(--code-bg); color: var(--code-fg); padding: 1px 6px; border-radius: var(--radius-sm); border: 1px solid var(--code-border);
}
.md-body :deep(pre) {
  background: var(--surface-hover); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; margin: 10px 0; overflow-x: auto; font-size: 13px; line-height: 1.6;
}
.md-body :deep(pre code) { background: none; color: #374151; border: none; padding: 0; font-size: inherit; }
.md-body :deep(blockquote) {
  border-left: 3px solid var(--amber); padding: 4px 0 4px 14px; margin: 8px 0; color: var(--fg-secondary); background: var(--amber-ghost); border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.md-body :deep(a) { color: var(--blue); text-decoration: none; transition: opacity 0.15s ease; }
.md-body :deep(a:hover) { opacity: 0.75; }
.md-body :deep(hr) { border: none; border-top: 1px solid var(--border-light); margin: 16px 0; }
.md-body :deep(table) { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }
.md-body :deep(th) { background: var(--surface-hover); text-align: left; padding: 7px 12px; border: 1px solid var(--border); font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 12px; color: var(--fg-secondary); }
.md-body :deep(td) { padding: 6px 12px; border: 1px solid var(--border-light); color: var(--fg); }

/* ======================== Thinking ======================== */
.thinking {
  margin: 8px 0; background: var(--c-think-subtle); border: 1px solid var(--border); border-left: 3px solid var(--c-think); border-radius: var(--radius-md); overflow: hidden;
}
.thinking summary {
  display: flex; align-items: center; gap: 6px; padding: 8px 14px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--c-think); user-select: none; list-style: none;
}
.thinking summary::-webkit-details-marker { display: none; }
.thinking summary::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent; border-left: 5px solid var(--c-think); transition: transform 0.15s ease; }
.thinking details[open] > summary::before { transform: rotate(90deg); }
.thinking-content { padding: 8px 14px 14px; font-size: 12px; color: var(--fg-secondary); border-top: 1px solid var(--border-light); overflow-x: auto; word-break: break-word; line-height: 1.6; }
.thinking-content :deep(pre) { background: var(--bg); margin: 4px 0; padding: 8px 10px; max-width: 100%; overflow-x: auto; border: 1px solid var(--border-light); border-radius: var(--radius-sm); }
.thinking-content :deep(code) { font-size: 11px; word-break: break-all; }

/* ======================== Tool Call ======================== */
.tool-call {
  margin: 8px 0; background: var(--surface-hover); border: 1px solid var(--border); border-left: 3px solid var(--c-tool); border-radius: var(--radius-md); overflow: hidden;
}
.tool-call details[open] > .tool-header { border-bottom: 1px solid var(--border-light); border-radius: var(--radius-md) var(--radius-md) 0 0; }
.tool-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px; font-family: 'DM Sans', sans-serif; font-size: 12px; cursor: pointer; user-select: none; list-style: none;
}
.tool-header::-webkit-details-marker { display: none; }
.tool-header::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent; border-left: 5px solid var(--c-tool); transition: transform 0.15s ease; }
.tool-call details[open] > .tool-header::before { transform: rotate(90deg); }
.tool-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--c-tool); }
.tool-call.done .tool-dot { background: var(--green); }
.tool-header code { font-family: 'JetBrains Mono', monospace; color: var(--c-tool); font-size: 11px; }
.tool-meta { margin-left: auto; font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 8px; border-radius: 10px; }
.tool-meta.running { color: var(--c-tool); background: var(--c-tool-subtle); }
.tool-meta.done    { color: var(--green); background: var(--green-subtle); }
.tool-input pre, .tool-result pre { padding: 10px 14px; margin: 0; font-size: 12px; color: var(--fg-secondary); white-space: pre-wrap; word-break: break-word; font-family: 'JetBrains Mono', monospace; line-height: 1.5; }
.tool-result { border-top: 1px solid var(--border-light); }
.tool-summary-right { margin-left: auto; display: flex; align-items: center; gap: 6px; }

/* Detail button in tool card */
.detail-btn-inline {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px;
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--c-tool); background: var(--c-tool-subtle);
  border: 1px solid rgba(6,182,212,0.2); border-radius: var(--radius-sm);
  cursor: pointer; transition: 0.15s ease;
  white-space: nowrap;
}
.detail-btn-inline:hover { background: rgba(6,182,212,0.15); }

/* ======================== Text ======================== */
.message-text { font-family: 'DM Sans', sans-serif; font-size: 14px; line-height: 1.65; color: var(--fg); }

/* ======================== Status Cards ======================== */
.status-card { margin: 8px 0; border-radius: var(--radius-md); border: 1px solid var(--border); overflow: hidden; font-size: 13px; line-height: 1.6; }
.status-card summary { display: flex; align-items: center; gap: 8px; padding: 8px 14px; cursor: pointer; font-family: 'Space Grotesk', sans-serif; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; user-select: none; list-style: none; }
.status-card summary::-webkit-details-marker { display: none; }
.status-card summary::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent; border-left: 5px solid currentColor; transition: transform 0.15s ease; }
.status-card details[open] > summary::before { transform: rotate(90deg); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--fg-muted); }
.status-dot.running { background: var(--c-compact); }
.status-dot.done { background: var(--green); }
.status-card-body { padding: 0 14px 12px; color: var(--fg-secondary); white-space: pre-wrap; word-break: break-word; border-top: 1px solid var(--border-light); }
.status-card-body pre { font-family: 'JetBrains Mono', monospace; font-size: 12px; background: var(--bg); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 14px; color: var(--fg-secondary); white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; }
.micro-card { width: 100%; background: var(--c-micro-subtle); border-left: 3px solid var(--c-micro); }
.micro-card summary { color: var(--c-micro); }
.inbox-card { background: linear-gradient(135deg, var(--c-inbox-subtle), var(--c-think-subtle)); border-left: 3px solid var(--c-inbox); }
.inbox-card summary { color: var(--c-inbox); }
.task-card { background: var(--green-subtle); border-left: 3px solid var(--green); }
.task-card summary { color: var(--green); }
.bg-card { background: var(--surface-hover); border-left: 3px solid var(--c-bg); }
.bg-card summary { color: var(--c-bg); }
.compact-card { background: linear-gradient(135deg, var(--c-compact-subtle), rgba(124,58,237,0.02)); border-left: 3px solid var(--c-compact); }
.compact-card summary { color: var(--c-compact); }
.compact-badge { margin-left: auto; font-size: 10px; font-weight: 500; letter-spacing: 0.04em; padding: 2px 8px; border-radius: 10px; color: var(--c-compact); background: var(--c-compact-subtle); }
.compact-card.done .compact-badge { color: var(--green); background: var(--green-subtle); }
.compact-start-msg { color: var(--fg-muted); font-size: 12px; margin-bottom: 6px; }
.compact-done-msg  { color: var(--green); font-size: 12px; margin-top: 8px; font-weight: 500; }
.compact-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 8px; margin-bottom: 2px; }
.compact-thinking .compact-label { color: var(--c-compact); }
.compact-summary .compact-label { color: var(--fg-secondary); }
.compact-thinking-text { color: var(--fg-muted); font-size: 12px; font-style: italic; white-space: pre-wrap; word-break: break-word; }
.compact-summary-text { color: var(--fg-secondary); font-size: 13px; background: var(--surface); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 14px; margin-top: 4px; white-space: pre-wrap; word-break: break-word; }
.compact-cursor { display: inline-block; color: var(--c-compact); animation: blink 0.8s step-end infinite; font-weight: 100; font-size: 1.1em; }

/* ======================== Todo Reminder ======================== */
.todo-reminder-block {
  margin: 8px 0; display: flex; align-items: flex-start; gap: 9px;
  background: var(--c-todo-subtle); border: 1px solid var(--border); border-left: 3px solid var(--c-todo); border-radius: var(--radius-md); padding: 9px 14px; font-size: 13px; color: var(--fg-secondary); line-height: 1.5;
}
.todo-icon-svg { flex-shrink: 0; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; color: var(--c-todo); }
.todo-sys-label { font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--c-todo); margin-right: 6px; }

/* ======================== Cursor ======================== */
.cursor { display: inline-block; color: var(--amber); animation: blink 0.8s step-end infinite; font-weight: 100; font-size: 1.1em; line-height: 1; margin-left: 1px; }
@keyframes blink { 50% { opacity: 0; } }
</style>
