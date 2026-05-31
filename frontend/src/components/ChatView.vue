<script setup lang="ts">
import { onMounted, ref, nextTick, watch } from 'vue'
import { useChat } from '../composables/useChat'
import { renderMarkdown } from '../utils/markdown'

const { messages, isStreaming, wsStatus, connect, send } = useChat()
const input = ref('')
const chatEl = ref<HTMLElement | null>(null)

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
      <span class="logo">MyAgent</span>
      <span class="status" :class="wsStatus">
        {{ wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中…' : '未连接' }}
      </span>
    </header>

    <!-- 消息列表 -->
    <div class="chat-messages" ref="chatEl" @scroll="onScroll">
      <div v-if="messages.length === 0" class="empty-hint">
        输入消息开始与 Lead Agent 对话
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

            <!-- 工具调用 -->
            <div v-else-if="block.type === 'tool'" class="tool-call" :class="block.status">
              <div class="tool-header">
                <span class="tool-dot"></span>
                <code>{{ block.name }}</code>
                <span class="tool-meta">{{ block.status === 'running' ? '执行中…' : '完成' }}</span>
              </div>
              <div class="tool-input"><pre>{{ JSON.stringify(block.input, null, 2) }}</pre></div>
              <div v-if="block.result" class="tool-result">
                <pre>{{ block.result }}</pre>
              </div>
            </div>

            <!-- 文本块 → 流式 Markdown 渲染 -->
            <div
              v-else-if="block.type === 'text'"
              class="message-text md-body"
              v-html="mdHtml(block.content)"
            ></div>
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
          v-model="input"
          :disabled="isStreaming"
          placeholder="输入消息… Enter 发送"
          rows="1"
          @keydown="handleKeydown"
        ></textarea>
        <button :disabled="isStreaming" class="btn-send" @click="handleSend">发送</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-container {
  display: flex; flex-direction: column;
  height: 100vh; max-width: 860px; margin: 0 auto;
  width: 100%;
}

/* ---- 头部 ---- */
.chat-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-bottom: 1px solid rgba(255,255,255,0.07);
  flex-shrink: 0;
}
.logo { font-weight: 600; font-size: 15px; color: #7c8aff; }
.status { font-size: 11px; padding: 2px 8px; border-radius: 9px; }
.status.connected { background: rgba(94,196,158,0.12); color: #5ec49e; }
.status.connecting { background: rgba(229,183,88,0.12); color: #e5b758; }
.status.disconnected { background: rgba(229,83,91,0.12); color: #e5535b; }

/* ---- 消息区 ---- */
.chat-messages {
  flex: 1; overflow-y: auto; padding: 20px 24px;
  display: flex; flex-direction: column; gap: 20px;
}
.empty-hint {
  color: #636378; text-align: center; margin-top: 40%;
  font-size: 14px;
}
.message { display: flex; flex-direction: column; gap: 2px; }
.message.user { align-self: flex-end; align-items: flex-end; max-width: 85%; }
.message.assistant { align-self: flex-start; max-width: 100%; }
.message-body { min-width: 0; }
.message-role {
  font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; margin-bottom: 4px;
}
.message.user .message-role { color: #6ea8fe; text-align: right; }
.message.assistant .message-role { color: #636378; }

/* 消息气泡 */
.message-bubble { font-size: 14px; line-height: 1.75; color: #e4e4ec; }
.user-bubble {
  background: rgba(94,106,210,0.12); border: 1px solid rgba(94,106,210,0.15);
  padding: 10px 14px; border-radius: 8px; word-break: break-word;
}

/* ---- Markdown 渲染内容 ---- */
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  margin: 12px 0 6px; color: #e4e4ec; font-weight: 600;
}
.md-body :deep(h1) { font-size: 1.3em; }
.md-body :deep(h2) { font-size: 1.15em; border-bottom: 1px solid rgba(255,255,255,0.07); padding-bottom: 4px; }
.md-body :deep(h3) { font-size: 1.05em; }
.md-body :deep(p) { margin: 4px 0; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 1.5em; margin: 4px 0; }
.md-body :deep(li) { margin: 2px 0; }
.md-body :deep(strong) { font-weight: 600; color: #f0f0f5; }
.md-body :deep(em) { font-style: italic; }

/* 内联代码 */
.md-body :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.9em;
  background: rgba(124,138,255,0.10);
  color: #b4c0ff;
  padding: 1px 6px; border-radius: 3px;
  border: 1px solid rgba(124,138,255,0.12);
}
/* 代码块 */
.md-body :deep(pre) {
  background: #0e0e16;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 12px 14px;
  margin: 8px 0;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.55;
}
.md-body :deep(pre code) {
  background: none; color: #c9d1d9;
  border: none; padding: 0; font-size: inherit;
}

/* 引用块 */
.md-body :deep(blockquote) {
  border-left: 3px solid #5f6ed0;
  padding: 4px 0 4px 14px;
  margin: 6px 0;
  color: #9898aa;
}
/* 链接 */
.md-body :deep(a) { color: #7c8aff; text-decoration: none; }
.md-body :deep(a:hover) { text-decoration: underline; }
/* 分割线 */
.md-body :deep(hr) {
  border: none; border-top: 1px solid rgba(255,255,255,0.07);
  margin: 12px 0;
}
/* 表格 */
.md-body :deep(table) {
  border-collapse: collapse; width: 100%; margin: 8px 0;
  font-size: 13px;
}
.md-body :deep(th) {
  background: rgba(255,255,255,0.04);
  text-align: left; padding: 6px 10px;
  border: 1px solid rgba(255,255,255,0.08);
  font-weight: 600;
}
.md-body :deep(td) {
  padding: 5px 10px;
  border: 1px solid rgba(255,255,255,0.06);
}

/* ---- 思考块 ---- */
.thinking {
  margin: 6px 0; background: rgba(124,138,255,0.05);
  border: 1px solid rgba(124,138,255,0.10);
  border-radius: 6px; overflow: hidden;
}
.thinking summary {
  padding: 7px 12px; cursor: pointer; font-size: 12px;
  color: #b4a0ff; user-select: none;
}
.thinking-content {
  padding: 8px 12px 12px; font-size: 12px;
  color: #8e8ca0;
  border-top: 1px solid rgba(124,138,255,0.08);
  overflow-x: auto;
  word-break: break-word;
}
.thinking-content :deep(pre) {
  background: rgba(0,0,0,0.2); margin: 4px 0; padding: 8px 10px;
  max-width: 100%; overflow-x: auto;
}
.thinking-content :deep(code) {
  font-size: 11px;
  word-break: break-all;
}

/* ---- 工具调用块 ---- */
.tool-call {
  margin: 6px 0; background: #12121a;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px; overflow: hidden;
}
.tool-header {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px;
}
.tool-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: #e5b758;
}
.tool-call.done .tool-dot { background: #5ec49e; }
.tool-header code { color: #7dd3e8; font-family: 'JetBrains Mono', monospace; }
.tool-meta { margin-left: auto; font-size: 11px; color: #636378; }
.tool-input pre, .tool-result pre {
  padding: 8px 12px; margin: 0; font-size: 12px;
  color: #9898aa; white-space: pre-wrap; word-break: break-word;
  font-family: 'JetBrains Mono', monospace; line-height: 1.5;
}
.tool-result { border-top: 1px solid rgba(255,255,255,0.04); }

/* ---- 流式光标 ---- */
.cursor {
  display: inline-block; color: #7c8aff;
  animation: blink 0.8s step-end infinite;
  font-weight: 100; font-size: 1.1em; line-height: 1;
  margin-left: 1px;
}
@keyframes blink { 50% { opacity: 0; } }

/* ---- 输入区域 ---- */
.chat-input-area {
  border-top: 1px solid rgba(255,255,255,0.07);
  padding: 14px 20px; flex-shrink: 0;
}
.input-row { display: flex; gap: 8px; }
textarea {
  flex: 1; background: #0e0e16; border: 1px solid rgba(255,255,255,0.07);
  border-radius: 8px; padding: 10px 14px; color: #e4e4ec;
  font-family: inherit; font-size: 14px; resize: none;
  outline: none; min-height: 42px; max-height: 150px;
}
textarea:focus { border-color: #5f6ed0; }
textarea::placeholder { color: #636378; }
.btn-send {
  background: #5f6ed0; color: #fff; border: none;
  padding: 10px 22px; border-radius: 8px; cursor: pointer;
  font-family: inherit; font-size: 13px; font-weight: 600;
  white-space: nowrap;
}
.btn-send:hover { background: #7c8aff; }
.btn-send:disabled { opacity: 0.4; cursor: not-allowed; }

/* 滚动条 */
.chat-messages::-webkit-scrollbar { width: 4px; }
.chat-messages::-webkit-scrollbar-track { background: transparent; }
.chat-messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 10px; }
</style>
