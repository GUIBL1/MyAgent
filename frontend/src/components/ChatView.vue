<script setup lang="ts">
import { onMounted, ref, nextTick, watch } from 'vue'
import { useChat } from '../composables/useChat'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps<{
  leftPanelOpen: boolean
  rightPanelOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-left'): void
  (e: 'toggle-right'): void
}>()

const { messages, isStreaming, wsStatus, hasSession, connect, send } = useChat()
const input = ref('')
const chatEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

onMounted(() => connect())

// ---- 自动滚动到底部 ----
let autoScroll = true
function scrollToBottom() {
  if (!autoScroll) return
  nextTick(() => {
    if (chatEl.value) {
      chatEl.value.scrollTop = chatEl.value.scrollHeight
    }
  })
}
watch(() => messages.value.length, scrollToBottom)
watch(() => messages.value[messages.value.length - 1]?.blocks, scrollToBottom, { deep: true })

// 用户手动上滚时暂停自动滚动
function onScroll() {
  if (!chatEl.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatEl.value
  autoScroll = scrollHeight - scrollTop - clientHeight < 60
}

// ---- 发送 ----
function handleSend() {
  const text = input.value.trim()
  if (!text || isStreaming.value) return
  autoScroll = true
  send(text)
  input.value = ''
  nextTick(() => {
    if (inputEl.value) inputEl.value.style.height = 'auto'
  })
}

function autoResize() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  // 输入框增高时，消息区跟着上滚，保持最后一条可见
  scrollToBottom()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// ---- 渲染 MD ----
function mdHtml(text: string): string {
  return renderMarkdown(text)
}
</script>

<template>
  <div class="chat-container">
    <!-- 头部 -->
    <header class="chat-header">
      <div class="header-left">
        <button
          class="panel-toggle"
          :class="{ active: props.leftPanelOpen }"
          title="切换会话面板"
          @click="emit('toggle-left')"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <rect x="1.5" y="2.5" width="12" height="10" rx="1.5" />
            <line x1="4.5" y1="5.5" x2="10.5" y2="5.5" />
            <line x1="4.5" y1="8.5" x2="8.5" y2="8.5" />
          </svg>
        </button>
        <span class="logo">MyAgent</span>
      </div>
      <div class="header-right">
        <span class="status" :class="wsStatus">
          {{ wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中…' : '未连接' }}
        </span>
        <button
          class="panel-toggle"
          :class="{ active: props.rightPanelOpen }"
          title="切换状态面板"
          @click="emit('toggle-right')"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="3.5" cy="3.5" r="1" />
            <circle cx="3.5" cy="7.5" r="1" />
            <circle cx="3.5" cy="11.5" r="1" />
            <line x1="6.5" y1="3.5" x2="13.5" y2="3.5" />
            <line x1="6.5" y1="7.5" x2="13.5" y2="7.5" />
            <line x1="6.5" y1="11.5" x2="11.5" y2="11.5" />
          </svg>
        </button>
      </div>
    </header>

    <!-- 消息列表 -->
    <div class="chat-messages" ref="chatEl" @scroll="onScroll">
      <div v-if="messages.length === 0" class="empty-hint">
        {{ hasSession ? '输入消息继续对话' : '输入消息开始新会话，或从左侧选择已有会话' }}
      </div>

      <div
        v-for="(msg, mi) in messages"
        :key="mi"
        class="message"
        :class="msg.role"
      >
        <div class="message-role">{{ msg.role === 'user' ? 'You' : 'Agent' }}</div>

        <!-- 用户消息：靠右 -->
        <div v-if="msg.role === 'user'" class="message-bubble user-bubble">{{ msg.content }}</div>

        <!-- Assistant 消息 -->
        <div v-else class="message-body">
          <template v-for="(block, bi) in msg.blocks" :key="bi">
            <!-- 思考块：接收 delta 时展开，写完自动折叠 -->
            <div v-if="block.type === 'thinking'" class="thinking">
              <details :open="block.active">
                <summary>思考过程</summary>
                <div class="thinking-content md-body" v-html="mdHtml(block.content)"></div>
              </details>
            </div>

            <!-- 工具调用：运行时展开，完成自动折叠 -->
            <div v-else-if="block.type === 'tool'" class="tool-call" :class="block.status">
              <details :open="block.status === 'running'">
                <summary class="tool-header">
                  <span class="tool-dot"></span>
                  <code>{{ block.name }}</code>
                  <span class="tool-meta" :class="block.status">{{ block.status === 'running' ? '执行中…' : '完成' }}</span>
                </summary>
                <div class="tool-body">
                  <div class="tool-input"><pre>{{ JSON.stringify(block.input, null, 2) }}</pre></div>
                  <div v-if="block.result" class="tool-result">
                    <pre>{{ block.result }}</pre>
                  </div>
                </div>
              </details>
            </div>

            <!-- 文本块 → 流式 Markdown 渲染 -->
            <div
              v-else-if="block.type === 'text'"
              class="message-text md-body"
              v-html="mdHtml(block.content)"
            ></div>

            <!-- Micro Compact 块 -->
            <div v-else-if="block.type === 'micro_compact'" class="status-card micro-card">
              <details>
                <summary>
                  <span class="status-dot"></span>
                  <span>MICRO COMPACT</span>
                </summary>
                <div class="status-card-body">{{ block.content }}</div>
              </details>
            </div>

            <!-- Inbox Message 块 -->
            <div v-else-if="block.type === 'inbox_message'" class="status-card inbox-card">
              <details open>
                <summary>
                  <span class="status-dot"></span>
                  <span>收件箱 INBOX</span>
                </summary>
                <div class="status-card-body">{{ block.content }}</div>
              </details>
            </div>

            <!-- Background Notification 块 -->
            <div v-else-if="block.type === 'background_notification'" class="status-card bg-card">
              <details open>
                <summary>
                  <span class="status-dot done"></span>
                  <span>后台任务通知</span>
                </summary>
                <div class="status-card-body"><pre>{{ block.content }}</pre></div>
              </details>
            </div>

            <!-- Todo Reminder 块 -->
            <div v-else-if="block.type === 'todo_reminder'" class="todo-reminder-block">
              <span class="todo-icon-svg">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="1" y="2" width="12" height="10" rx="2"/>
                  <path d="M4 7l2 2 4-4"/>
                </svg>
              </span>
              <span><span class="todo-sys-label">SYSTEM</span> {{ block.content }}</span>
            </div>

            <!-- Auto Compact 块 -->
            <div v-else-if="block.type === 'auto_compact'" class="status-card compact-card" :class="{ done: block.compactStatus === 'done' }">
              <details open>
                <summary>
                  <span class="status-dot" :class="block.compactStatus === 'done' ? 'done' : 'running'"></span>
                  <span>上下文压缩 Auto Compact</span>
                  <span class="compact-badge">{{ block.compactStatus === 'done' ? '完成' : '进行中…' }}</span>
                </summary>
                <div class="status-card-body">
                  <div v-if="block.content" class="compact-start-msg">{{ block.content }}</div>
                  <div v-if="block.thinking" class="compact-thinking">
                    <div class="compact-label">Thinking</div>
                    <div class="compact-thinking-text">{{ block.thinking }}</div>
                  </div>
                  <div v-if="block.summary" class="compact-summary">
                    <div class="compact-label">Summary</div>
                    <div class="compact-summary-text">{{ block.summary }}</div>
                  </div>
                  <div v-if="block.result" class="compact-done-msg">{{ block.result }}</div>
                  <span v-if="block.compactStatus === 'running'" class="compact-cursor">|</span>
                </div>
              </details>
            </div>
          </template>

          <!-- 流式光标（跟在最后一个文本块后面） -->
          <span
            v-if="isStreaming && mi === messages.length - 1 && msg.role === 'assistant'"
            class="cursor"
          >|</span>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-area">
      <div class="input-row">
        <textarea
          ref="inputEl"
          v-model="input"
          :disabled="isStreaming"
          placeholder="输入消息… Enter 发送"
          rows="1"
          @input="autoResize"
          @keydown="handleKeydown"
        ></textarea>
        <button :disabled="isStreaming" class="btn-send" @click="handleSend">发送</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* CSS 变量定义在 index.html 全局 :root 中 */
.chat-container {
  display: flex; flex-direction: column;
  height: 100%; width: 100%;
  background: var(--bg);
}

/* ======================== Header ======================== */
.chat-header {
  display: flex; align-items: center; justify-content: space-between;
  position: relative; z-index: 10;
  margin: 12px 20px -6px;
  padding: 10px 18px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  background: var(--glass);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  overflow: hidden;
  flex-shrink: 0;
}
.header-left, .header-right {
  display: flex; align-items: center; gap: 10px;
}
.logo {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700; font-size: 16px;
  color: var(--fg);
  letter-spacing: -0.3px;
}
/* Panel Toggle Buttons */
.panel-toggle {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  background: none; border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-muted); cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  flex-shrink: 0;
}
.panel-toggle:hover { background: var(--amber-subtle); color: var(--amber); border-color: var(--amber); }
.panel-toggle.active { background: var(--amber-subtle); color: var(--amber); border-color: var(--amber); }
.status {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  padding: 3px 10px; border-radius: 10px;
}
.status.connected    { background: var(--green-subtle);  color: var(--green); }
.status.connecting   { background: var(--yellow-subtle); color: var(--yellow); }
.status.disconnected { background: var(--red-subtle);    color: var(--red); }

/* ======================== Messages ======================== */
.chat-messages {
  flex: 1; overflow-y: auto;
  padding: 34px 24px 34px;
  display: flex; flex-direction: column; gap: 24px;
  scroll-behavior: smooth;
}
.empty-hint {
  text-align: center; margin-top: 35%;
  font-size: 14px; color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
}
.message { display: flex; flex-direction: column; gap: 4px; }
.message.user      { align-self: flex-end; align-items: flex-end; max-width: 85%; }
.message.assistant { width: 100%; }
.message-body { min-width: 0; }

.message-role {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em;
  margin-bottom: 4px;
}
.message.user .message-role      { color: var(--amber); text-align: right; }
.message.assistant .message-role { color: var(--fg-muted); }

/* User bubble */
.message-bubble {
  font-family: 'DM Sans', sans-serif;
  font-size: 14px; line-height: 1.7;
  color: var(--fg);
}
.user-bubble {
  background: var(--amber-subtle);
  border: 1px solid var(--border);
  padding: 10px 14px; border-radius: var(--radius-lg);
  word-break: break-word;
}

/* ======================== Markdown ======================== */
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  margin: 16px 0 6px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600; color: var(--fg);
  letter-spacing: -0.2px;
}
.md-body :deep(h1) { font-size: 1.25em; }
.md-body :deep(h2) { font-size: 1.1em; border-bottom: 1px solid var(--border-light); padding-bottom: 4px; }
.md-body :deep(h3) { font-size: 1.0em; }
.md-body :deep(p)  { margin: 6px 0; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 1.6em; margin: 6px 0; }
.md-body :deep(li) { margin: 3px 0; }
.md-body :deep(strong) { font-weight: 600; color: var(--fg); }
.md-body :deep(em)     { font-style: italic; }

/* Inline code */
.md-body :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.88em; font-weight: 500;
  background: var(--code-bg);
  color: var(--code-fg);
  padding: 1px 6px; border-radius: var(--radius-sm);
  border: 1px solid var(--code-border);
}
/* Code block */
.md-body :deep(pre) {
  background: var(--surface-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  margin: 10px 0;
  overflow-x: auto;
  font-size: 13px; line-height: 1.6;
}
.md-body :deep(pre code) {
  background: none; color: #374151;
  border: none; padding: 0; font-size: inherit;
}

/* Blockquote */
.md-body :deep(blockquote) {
  border-left: 3px solid var(--amber);
  padding: 4px 0 4px 14px;
  margin: 8px 0;
  color: var(--fg-secondary);
  background: var(--amber-ghost);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
/* Links */
.md-body :deep(a) {
  color: var(--blue); text-decoration: none;
  transition: opacity 0.15s ease;
}
.md-body :deep(a:hover) { opacity: 0.75; }
/* Horizontal rule */
.md-body :deep(hr) {
  border: none; border-top: 1px solid var(--border-light);
  margin: 16px 0;
}
/* Tables */
.md-body :deep(table) {
  border-collapse: collapse; width: 100%; margin: 10px 0;
  font-size: 13px;
}
.md-body :deep(th) {
  background: var(--surface-hover); text-align: left;
  padding: 7px 12px; border: 1px solid var(--border);
  font-family: 'Space Grotesk', sans-serif; font-weight: 600;
  font-size: 12px; color: var(--fg-secondary);
}
.md-body :deep(td) {
  padding: 6px 12px; border: 1px solid var(--border-light);
  color: var(--fg);
}

/* ======================== Thinking Block ======================== */
.thinking {
  margin: 8px 0;
  background: var(--c-think-subtle);
  border: 1px solid var(--border);
  border-left: 3px solid var(--c-think);
  border-radius: var(--radius-md); overflow: hidden;
}
.thinking summary {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--c-think);
  user-select: none; list-style: none;
}
.thinking summary::-webkit-details-marker { display: none; }
.thinking summary::before {
  content: '';
  display: inline-block; flex-shrink: 0;
  width: 0; height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid var(--c-think);
  transition: transform 0.15s ease;
}
.thinking details[open] > summary::before {
  transform: rotate(180deg);
}
.thinking-content {
  padding: 8px 14px 14px;
  font-size: 12px; color: var(--fg-secondary);
  border-top: 1px solid var(--border-light);
  overflow-x: auto; word-break: break-word;
  line-height: 1.6;
}
.thinking-content :deep(pre) {
  background: var(--bg); margin: 4px 0; padding: 8px 10px;
  max-width: 100%; overflow-x: auto;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}
.thinking-content :deep(code) {
  font-size: 11px; word-break: break-all;
}

/* ======================== Tool Call Block ======================== */
.tool-call {
  margin: 8px 0;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  border-left: 3px solid var(--c-tool);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.tool-call details[open] > .tool-header {
  border-bottom: 1px solid var(--border-light);
  border-radius: var(--radius-md) var(--radius-md) 0 0;
}
.tool-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px;
  font-family: 'DM Sans', sans-serif;
  font-size: 12px;
  cursor: pointer; user-select: none;
  list-style: none;
}
.tool-header::-webkit-details-marker { display: none; }
.tool-header::before {
  content: '';
  display: inline-block; flex-shrink: 0;
  width: 0; height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid var(--c-tool);
  transition: transform 0.15s ease;
}
.tool-call details[open] > .tool-header::before {
  transform: rotate(180deg);
}
.tool-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: var(--c-tool);
}
.tool-call.done .tool-dot { background: var(--green); }
.tool-header code {
  font-family: 'JetBrains Mono', monospace;
  color: var(--c-tool); font-size: 11px;
}
.tool-meta {
  margin-left: auto;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.04em;
  padding: 2px 8px; border-radius: 10px;
}
.tool-meta.running { color: var(--c-tool); background: var(--c-tool-subtle); }
.tool-meta.done    { color: var(--green); background: var(--green-subtle); }
.tool-input pre, .tool-result pre {
  padding: 10px 14px; margin: 0;
  font-size: 12px; color: var(--fg-secondary);
  white-space: pre-wrap; word-break: break-word;
  font-family: 'JetBrains Mono', monospace; line-height: 1.5;
}
.tool-result { border-top: 1px solid var(--border-light); }

/* ======================== Streaming Cursor ======================== */
.cursor {
  display: inline-block; color: var(--amber);
  animation: blink 0.8s step-end infinite;
  font-weight: 100; font-size: 1.1em; line-height: 1;
  margin-left: 1px;
}
@keyframes blink { 50% { opacity: 0; } }

/* ======================== Input ======================== */
.chat-input-area {
  position: relative; z-index: 10;
  margin: -6px 20px 12px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  background: var(--glass);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  overflow: hidden;
  flex-shrink: 0;
}
.input-row { display: flex; gap: 10px; align-items: flex-end; }
textarea {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 11px 16px;
  color: var(--fg);
  font-family: 'DM Sans', sans-serif;
  font-size: 14px; line-height: 1.6;
  resize: none; outline: none;
  min-height: 44px; max-height: 160px;
  overflow-x: hidden; overflow-y: auto;
  word-break: break-word; white-space: pre-wrap;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
textarea::-webkit-scrollbar { width: 5px; }
textarea::-webkit-scrollbar-track {
  background: transparent;
  margin: 6px 0;
}
textarea::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
textarea::-webkit-scrollbar-thumb:hover { background: #D4C4AD; }
textarea:focus {
  border-color: var(--amber);
  box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.1);
}
textarea::placeholder { color: var(--fg-muted); }
.btn-send {
  background: var(--amber); color: #FFFFFF;
  border: none; border-radius: var(--radius-lg);
  padding: 11px 24px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 13px; font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap; min-height: 44px;
  transition: background 0.15s ease, transform 0.1s ease;
}
.btn-send:hover  { background: var(--amber-hover); }
.btn-send:active { transform: scale(0.97); }
.btn-send:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

/* ======================== Status Events ======================== */

/* Shared collapsible status card */
.status-card {
  margin: 8px 0;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  overflow: hidden;
  font-size: 13px; line-height: 1.6;
}
.status-card summary {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em;
  user-select: none; list-style: none;
}
.status-card summary::-webkit-details-marker { display: none; }

/* 三角标 */
.status-card summary::before {
  content: '';
  display: inline-block; flex-shrink: 0;
  width: 0; height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid currentColor;
  transition: transform 0.15s ease;
}
.status-card details[open] > summary::before { transform: rotate(180deg); }

.status-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: var(--fg-muted);
}
.status-dot.running { background: var(--c-compact); }
.status-dot.done { background: var(--green); }
.status-card-body {
  padding: 0 14px 12px;
  color: var(--fg-secondary);
  white-space: pre-wrap; word-break: break-word;
  border-top: 1px solid var(--border-light);
}
.status-card-body pre {
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  background: var(--bg); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); padding: 10px 14px;
  color: var(--fg-secondary); white-space: pre-wrap; word-break: break-word;
  max-height: 200px; overflow-y: auto;
}

/* Micro Compact — gray */
.micro-card {
  width: 100%;
  background: var(--c-micro-subtle);
  border: 1px solid var(--border);
  border-left: 3px solid var(--c-micro);
}
.micro-card summary { color: var(--c-micro); }

/* Inbox — teal */
.inbox-card {
  background: linear-gradient(135deg, var(--c-inbox-subtle), var(--c-think-subtle));
  border-left: 3px solid var(--c-inbox);
}
.inbox-card summary { color: var(--c-inbox); }

/* Background notification — blue */
.bg-card {
  background: var(--surface-hover);
  border-left: 3px solid var(--c-bg);
}
.bg-card summary { color: var(--c-bg); }

/* Auto Compact — violet */
.compact-card {
  background: linear-gradient(135deg, var(--c-compact-subtle), rgba(124,58,237,0.02));
  border-left: 3px solid var(--c-compact);
}
.compact-card summary { color: var(--c-compact); }
.compact-badge {
  margin-left: auto;
  font-size: 10px; font-weight: 500;
  letter-spacing: 0.04em;
  padding: 2px 8px; border-radius: 10px;
  color: var(--c-compact); background: var(--c-compact-subtle);
}
.compact-card.done .compact-badge {
  color: var(--green); background: var(--green-subtle);
}
.compact-start-msg { color: var(--fg-muted); font-size: 12px; margin-bottom: 6px; }
.compact-done-msg  { color: var(--green); font-size: 12px; margin-top: 8px; font-weight: 500; }
.compact-label {
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em;
  margin-top: 8px; margin-bottom: 2px;
}
.compact-thinking .compact-label { color: var(--c-compact); }
.compact-summary .compact-label { color: var(--fg-secondary); }
.compact-thinking-text {
  color: var(--fg-muted); font-size: 12px; font-style: italic;
  white-space: pre-wrap; word-break: break-word;
}
.compact-summary-text {
  color: var(--fg-secondary); font-size: 13px;
  background: var(--surface); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); padding: 10px 14px; margin-top: 4px;
  white-space: pre-wrap; word-break: break-word;
}
.compact-cursor {
  display: inline-block; color: var(--c-compact);
  animation: blink 0.8s step-end infinite;
  font-weight: 100; font-size: 1.1em;
}
@keyframes blink { 50% { opacity: 0; } }

/* Todo Reminder — rose */
.todo-reminder-block {
  margin: 8px 0;
  display: flex; align-items: flex-start; gap: 9px;
  background: var(--c-todo-subtle);
  border: 1px solid var(--border);
  border-left: 3px solid var(--c-todo);
  border-radius: var(--radius-md);
  padding: 9px 14px;
  font-size: 13px; color: var(--fg-secondary); line-height: 1.5;
}
.todo-icon-svg {
  flex-shrink: 0; width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center;
  color: var(--c-todo);
}
.todo-sys-label {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--c-todo); margin-right: 6px;
}

/* ======================== Scrollbar ======================== */
.chat-messages::-webkit-scrollbar { width: 5px; }
.chat-messages::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}
.chat-messages::-webkit-scrollbar-thumb {
  background: var(--border); border-radius: 10px;
}
.chat-messages::-webkit-scrollbar-thumb:hover { background: #D4C4AD; }
</style>
