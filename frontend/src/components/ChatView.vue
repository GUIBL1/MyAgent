<script setup lang="ts">
import { computed, onMounted, ref, nextTick, watch } from 'vue'
import { useChat } from '../composables/useChat'
import type { RecallMemoryBlock, SubagentBlock } from '../composables/useChat'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps<{
  leftPanelOpen: boolean
  rightPanelOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-left'): void
  (e: 'toggle-right'): void
}>()

const { messages, isStreaming, wsStatus, hasSession, subPanelStack, connect, send } = useChat()
const activeSubPanel = computed(() => {
  const top = subPanelStack.value[subPanelStack.value.length - 1]
  return top || null
})
const recallPanelData = computed(() => {
  if (!activeSubPanel.value || activeSubPanel.value.toolName !== 'recall_memory') return null
  return activeSubPanel.value.data as RecallMemoryBlock
})
const subagentPanelData = computed(() => {
  if (!activeSubPanel.value || activeSubPanel.value.toolName !== 'use_subagent') return null
  return activeSubPanel.value.data as SubagentBlock
})
const input = ref('')
const chatEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)
const recallBodyEl = ref<HTMLElement | null>(null)
const subagentBodyEl = ref<HTMLElement | null>(null)

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

// 子面板自动滚到底部（仅当用户在底部时）
let recallAutoScroll = true
function onRecallScroll() {
  if (!recallBodyEl.value) return
  const { scrollTop, scrollHeight, clientHeight } = recallBodyEl.value
  recallAutoScroll = scrollHeight - scrollTop - clientHeight < 100
}
watch(() => recallPanelData.value, () => {
  if (!recallAutoScroll) return
  nextTick(() => {
    if (recallBodyEl.value) {
      recallBodyEl.value.scrollTop = recallBodyEl.value.scrollHeight
    }
  })
}, { deep: true })

// Subagent 子面板滚动
let subagentAutoScroll = true
function onSubagentScroll() {
  if (!subagentBodyEl.value) return
  const { scrollTop, scrollHeight, clientHeight } = subagentBodyEl.value
  subagentAutoScroll = scrollHeight - scrollTop - clientHeight < 100
}
watch(() => subagentPanelData.value, () => {
  if (!subagentAutoScroll) return
  nextTick(() => {
    if (subagentBodyEl.value) {
      subagentBodyEl.value.scrollTop = subagentBodyEl.value.scrollHeight
    }
  })
}, { deep: true })

// 用户手动上滚时暂停自动滚动
function onScroll() {
  if (!chatEl.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatEl.value
  autoScroll = scrollHeight - scrollTop - clientHeight < 100
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

// ---- Recall sub-panel ----
function openRecallDetail(block: any) {
  recallAutoScroll = true
  // 优先在 subagent 子面板内查找（若当前面板为 subagent）
  if (subagentPanelData.value) {
    for (const msg of subagentPanelData.value.messages) {
      for (const b of msg.blocks) {
        if (b.type === 'recall_memory' && b.toolId === block.id) {
          subPanelStack.value.push({ toolId: block.id, toolName: 'recall_memory', data: b as any })
          nextTick(() => {
            if (recallBodyEl.value) recallBodyEl.value.scrollTop = recallBodyEl.value.scrollHeight
          })
          return
        }
      }
    }
  }
  // 其次在主聊天区的所有 subagent block 内查找
  for (const chatMsg of messages.value) {
    for (const b of chatMsg.blocks) {
      if (b.type === 'subagent') {
        for (const saMsg of (b as SubagentBlock).messages) {
          for (const sblk of saMsg.blocks) {
            if (sblk.type === 'recall_memory' && sblk.toolId === block.id) {
              subPanelStack.value.push({ toolId: block.id, toolName: 'recall_memory', data: sblk as any })
              nextTick(() => {
                if (recallBodyEl.value) recallBodyEl.value.scrollTop = recallBodyEl.value.scrollHeight
              })
              return
            }
          }
        }
      }
    }
  }
  // 最后在主聊天区直接查找（现有行为）
  for (const msg of messages.value) {
    for (const b of msg.blocks) {
      if (b.type === 'recall_memory' && b.toolId === block.id) {
        subPanelStack.value.push({ toolId: block.id, toolName: 'recall_memory', data: b as any })
        nextTick(() => {
          if (recallBodyEl.value) recallBodyEl.value.scrollTop = recallBodyEl.value.scrollHeight
        })
        return
      }
    }
  }
}

function openSubagentDetail(block: any) {
  subagentAutoScroll = true
  for (const msg of messages.value) {
    for (const b of msg.blocks) {
      if (b.type === 'subagent' && b.toolId === block.id) {
        subPanelStack.value.push({ toolId: block.id, toolName: 'use_subagent', data: b as any })
        nextTick(() => {
          if (subagentBodyEl.value) subagentBodyEl.value.scrollTop = subagentBodyEl.value.scrollHeight
        })
        return
      }
    }
  }
}

function closeSubPanelTop() {
  subPanelStack.value.pop()
}

function closeAllSubPanels() {
  subPanelStack.value = []
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

    <!-- 消息区（子面板打开时隐藏） -->
    <div class="chat-body-wrapper">
    <div v-if="subPanelStack.length === 0" class="chat-messages" ref="chatEl" @scroll="onScroll">
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
                  <span class="tool-summary-right">
                    <span v-if="block.name === 'recall_memory'" class="detail-btn-inline" @click.prevent.stop="openRecallDetail(block)">
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                        <circle cx="5.5" cy="5.5" r="4"/><line x1="9" y1="9" x2="11" y2="11"/>
                        <line x1="5.5" y1="3.5" x2="5.5" y2="7.5"/><line x1="3.5" y1="5.5" x2="7.5" y2="5.5"/>
                      </svg>
                      查看详情
                    </span>
                    <span v-if="block.name === 'use_subagent'" class="detail-btn-inline" @click.prevent.stop="openSubagentDetail(block)">
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
              <details :open="block.active !== false">
                <summary>
                  <span class="status-dot"></span>
                  <span>收件箱 INBOX</span>
                </summary>
                <div class="status-card-body">{{ block.content }}</div>
              </details>
            </div>

            <!-- Task Claimed 块 -->
            <div v-else-if="block.type === 'task_claimed'" class="status-card task-card">
              <details :open="block.active !== false">
                <summary>
                  <span class="status-dot"></span>
                  <span>收到任务 TASK</span>
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

    <div v-if="subPanelStack.length > 0" class="sub-panel-view">
      <div class="sub-panel-topbar">
        <button class="recall-back-btn" @click="closeSubPanelTop">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="7.5,2 3.5,6 7.5,10"/>
          </svg>
          返回对话
        </button>
        <div v-if="recallPanelData" class="recall-sub-title">Memory Recall<span v-if="recallPanelData.synth.query"> · {{ recallPanelData.synth.query }}</span></div>
        <div v-else-if="subagentPanelData" class="recall-sub-title">Subagent · {{ subagentPanelData.agentType }}<span v-if="subagentPanelData.name"> · {{ subagentPanelData.name }}</span></div>
      </div>

      <!-- ═══════════ Recall Memory Body ═══════════ -->
        <div v-if="recallPanelData" ref="recallBodyEl" class="recall-panel-body" @scroll="onRecallScroll">

          <!-- ── Stage 1: Expand ── -->
          <div class="recall-stage recall-stage-expand" :class="recallPanelData.expand.status">
            <details :open="recallPanelData.expand.status !== 'pending'">
              <summary>
                <span class="recall-stage-dot"></span>
                STAGE 1 · Query Expansion
                <span class="recall-stage-badge">{{ recallPanelData.expand.status === 'running' ? '执行中' : recallPanelData.expand.status === 'done' ? '完成' : '等待中' }}</span>
              </summary>
              <div class="recall-stage-body">
                <div v-if="recallPanelData.expand.status !== 'pending'" class="recall-explain">将原始查询发给 LLM，生成 3–10 条不同角度表述的变体查询，覆盖同义词改写、抽象泛化、关键词组合等方向，提高召回覆盖度。</div>
                <div v-if="recallPanelData.expand.thinking" class="recall-think-block">
                  <details :open="recallPanelData.active && recallPanelData.expand.status === 'running' && !recallPanelData.expand.text"><summary>EXPANSION THINKING</summary>
                    <div class="recall-think-content">{{ recallPanelData.expand.thinking }}</div>
                  </details>
                </div>
                <div v-if="recallPanelData.expand.text" class="recall-text-block">
                  <details :open="recallPanelData.active && recallPanelData.expand.status === 'running' && !!recallPanelData.expand.text"><summary>EXPANSION OUTPUT</summary>
                    <div class="recall-text-content">{{ recallPanelData.expand.text }}</div>
                  </details>
                </div>
                <div v-if="recallPanelData.expand.variants.length" class="recall-variant-list">
                  <div class="recall-variant-label">生成变体查询（含原始查询共 {{ recallPanelData.expand.count }} 条）：</div>
                  <div v-for="(v, vi) in recallPanelData.expand.variants" :key="vi" class="recall-variant-item">
                    <span class="recall-variant-idx">{{ vi + 1 }}</span><span>{{ v }}<span v-if="vi === 0" class="recall-variant-original">原始</span></span>
                  </div>
                </div>
                <span v-if="recallPanelData.expand.status === 'running'" class="recall-blink">|</span>
              </div>
            </details>
          </div>

          <!-- ── Stage 2: Retrieve ── -->
          <div class="recall-stage recall-stage-retrieve" :class="recallPanelData.retrieve.status">
            <details :open="recallPanelData.retrieve.status !== 'pending'">
              <summary>
                <span class="recall-stage-dot"></span>
                STAGE 2 · Multi-Query Retrieval
                <span class="recall-stage-badge">{{ recallPanelData.retrieve.status === 'running' ? '执行中' : recallPanelData.retrieve.status === 'done' ? '完成' : '等待中' }}</span>
              </summary>
              <div class="recall-stage-body">
                <div v-if="recallPanelData.retrieve.status !== 'pending'" class="recall-explain">将每条变体查询转为向量，分别检索 Chroma 向量数据库，去重合并候选记忆。</div>
                <div v-for="(qr, qri) in recallPanelData.retrieve.queries" :key="qri" class="recall-query-card">
                  <details :open="qr.active">
                    <summary class="recall-qr-header">查询 <code>{{ qr.query }}</code><span class="recall-qr-hits">{{ qr.error ? '失败' : qr.active ? '查询中…' : qr.hit_count + ' 条命中' }}</span></summary>
                    <div v-if="qr.error" class="recall-qr-error">{{ qr.error }}</div>
                    <div v-for="(hit, hi) in qr.hits" :key="hi" class="recall-qr-item">
                      <div class="recall-qr-id">{{ hit.id }}<span v-if="hit.duplicate" class="recall-dup-tag">重复</span></div>
                      <div class="recall-qr-dist">distance: {{ hit.distance }} · access: {{ hit.access_count }}</div>
                      <div class="recall-qr-doc">{{ hit.doc }}</div>
                    </div>
                  </details>
                </div>
                <div v-if="recallPanelData.retrieve.status === 'done'" class="recall-retrieve-summary">去重后共 <strong>{{ recallPanelData.retrieve.total_candidates }}</strong> 条候选记忆</div>
              </div>
            </details>
          </div>

          <!-- ── Stage 3: Rerank ── -->
          <div class="recall-stage recall-stage-rerank" :class="recallPanelData.rerank.status">
            <details :open="recallPanelData.rerank.status !== 'pending'">
              <summary>
                <span class="recall-stage-dot"></span>
                STAGE 3 · LLM Reranking
                <span class="recall-stage-badge">{{ recallPanelData.rerank.status === 'running' ? '执行中' : recallPanelData.rerank.status === 'done' ? '完成' : '等待中' }}</span>
              </summary>
              <div class="recall-stage-body">
                <div v-if="recallPanelData.rerank.status !== 'pending'" class="recall-explain">将去重后的候选记忆送给重排序 LLM，按语义匹配度、向量距离、历史访问频率综合打分，输出降序排列。</div>
                <div v-if="recallPanelData.rerank.thinking" class="recall-think-block">
                  <details :open="recallPanelData.active && recallPanelData.rerank.status === 'running' && !recallPanelData.rerank.text"><summary>RERANK THINKING</summary>
                    <div class="recall-think-content">{{ recallPanelData.rerank.thinking }}</div>
                  </details>
                </div>
                <div v-if="recallPanelData.rerank.text" class="recall-text-block">
                  <details :open="recallPanelData.active && recallPanelData.rerank.status === 'running' && !!recallPanelData.rerank.text"><summary>RERANK OUTPUT</summary>
                    <div class="recall-text-content">{{ recallPanelData.rerank.text }}</div>
                  </details>
                </div>
                <div v-if="recallPanelData.rerank.ranked_ids.length" class="recall-ranked-list">
                  <div class="recall-ranked-label">排序结果（top {{ recallPanelData.rerank.top_k }} 送入合成）：</div>
                  <div v-for="(rid, ri) in recallPanelData.rerank.ranked_ids" :key="ri" class="recall-ranked-item" :class="{ 'recall-ranked-top': ri < recallPanelData.rerank.top_k }">
                    <span class="recall-rank-num">{{ ri + 1 }}</span>
                    <span class="recall-rank-id">{{ rid }}</span>
                    <span v-if="ri >= recallPanelData.rerank.top_k" class="recall-rank-skip">舍弃</span>
                  </div>
                </div>
                <span v-if="recallPanelData.rerank.status === 'running'" class="recall-blink">|</span>
              </div>
            </details>
          </div>

          <!-- ── Stage 4: Synthesize ── -->
          <div class="recall-stage recall-stage-synth" :class="recallPanelData.synth.status">
            <details :open="recallPanelData.synth.status !== 'pending'">
              <summary>
                <span class="recall-stage-dot"></span>
                STAGE 4 · LLM Synthesis
                <span class="recall-stage-badge">{{ recallPanelData.synth.status === 'running' ? '执行中' : recallPanelData.synth.status === 'done' ? '完成' : '等待中' }}</span>
              </summary>
              <div class="recall-stage-body">
                <div v-if="recallPanelData.synth.status !== 'pending'" class="recall-explain">将重排结果组装为记忆片段列表，送合成 LLM 生成面向原始查询的最终回答。如有矛盾以索引小的片段为准。</div>
                <div v-if="recallPanelData.synth.fragments.length" class="recall-synth-input">
                  <details :open="recallPanelData.active && recallPanelData.synth.status === 'running' && !recallPanelData.synth.thinking && !recallPanelData.synth.text"><summary class="recall-si-header">合成输入 · {{ recallPanelData.synth.fragments.length }} 条记忆片段</summary>
                    <div class="recall-si-body">
                      <div v-for="(f, fi) in recallPanelData.synth.fragments" :key="fi">
                        <span class="recall-frag-tag">[{{ f.index }}]</span> {{ f.content }}
                      </div>
                    </div>
                  </details>
                </div>
                <div v-if="recallPanelData.synth.thinking" class="recall-think-block">
                  <details :open="recallPanelData.active && recallPanelData.synth.status === 'running' && !recallPanelData.synth.text"><summary>SYNTHESIS THINKING</summary>
                    <div class="recall-think-content">{{ recallPanelData.synth.thinking }}</div>
                  </details>
                </div>
                <div v-if="recallPanelData.synth.text" class="recall-text-block">
                  <details :open="recallPanelData.active && recallPanelData.synth.status === 'running' && !!recallPanelData.synth.text"><summary>SYNTHESIS OUTPUT</summary>
                    <div class="recall-text-content">{{ recallPanelData.synth.text }}</div>
                  </details>
                </div>
                <div v-if="recallPanelData.synth.result" class="recall-final-result">
                  <div class="recall-fr-label">合成结果</div>
                  <div class="md-body" v-html="mdHtml(recallPanelData.synth.result)"></div>
                </div>
                <span v-if="recallPanelData.synth.status === 'running'" class="recall-blink">|</span>
              </div>
            </details>
          </div>

        </div>

        <!-- ═══════════ Subagent Body ═══════════ -->
        <div v-else-if="subagentPanelData" ref="subagentBodyEl" class="recall-panel-body subagent-panel-body" @scroll="onSubagentScroll">
          <template v-for="(msg, mi) in subagentPanelData.messages" :key="mi">
            <div class="subagent-msg">
              <div class="subagent-msg-body">
                <template v-for="(block, bi) in msg.blocks" :key="bi">
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
                          <span v-if="block.name === 'recall_memory'" class="detail-btn-inline" @click.prevent.stop="openRecallDetail(block)">
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
                        <div v-if="block.result" class="tool-result">
                          <pre>{{ block.result }}</pre>
                        </div>
                      </div>
                    </details>
                  </div>

                  <!-- 文本块 -->
                  <div
                    v-else-if="block.type === 'text'"
                    class="subagent-text md-body"
                    v-html="mdHtml(block.content)"
                  ></div>
                </template>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <div v-if="subagentPanelData.messages.length === 0" class="subagent-empty">等待 subagent 输出…</div>

          <!-- 流式光标 -->
          <span
            v-if="subagentPanelData.status === 'running'"
            class="cursor"
          >|</span>
        </div>
    </div>
    </div>

    <!-- ═══════════ 输入区域（有子面板时隐藏） ═══════════ -->
    <div v-if="subPanelStack.length === 0" class="chat-input-area">
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
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid var(--c-think);
  transition: transform 0.15s ease;
}
.thinking details[open] > summary::before {
  transform: rotate(90deg);
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
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid var(--c-tool);
  transition: transform 0.15s ease;
}
.tool-call details[open] > .tool-header::before {
  transform: rotate(90deg);
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
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid currentColor;
  transition: transform 0.15s ease;
}
.status-card details[open] > summary::before { transform: rotate(90deg); }

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

/* Task Claimed — emerald */
.task-card {
  background: var(--green-subtle);
  border-left: 3px solid var(--green);
}
.task-card summary { color: var(--green); }

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

/* ======================== Detail Button (in tool card) ======================== */
.tool-summary-right {
  margin-left: auto; display: flex; align-items: center; gap: 6px;
}
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

/* ======================== Sub-Panel Inline ======================== */
.chat-body-wrapper {
  flex: 1; position: relative; overflow: hidden;
  display: flex; flex-direction: column;
}
.sub-panel-view {
  flex: 1; position: relative; display: flex; flex-direction: column; overflow: hidden;
}
.sub-panel-topbar {
  position: absolute; top: 0; left: 0; right: 0; z-index: 10;
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  margin: 6.8px 20px 0;
  padding: 10px 18px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  background: rgba(255, 251, 235, 0.72);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.recall-back-btn {
  display: flex; align-items: center; gap: 4px;
  font-family: 'Space Grotesk', sans-serif; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--fg-muted); cursor: pointer; background: none; border: none;
  padding: 4px 8px; border-radius: var(--radius-sm); transition: 0.15s ease;
}
.recall-back-btn:hover { color: var(--amber); background: var(--amber-subtle); }
.recall-sub-title {
  font-family: 'Space Grotesk', sans-serif; font-size: 12px; font-weight: 600;
  color: var(--fg-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.recall-sub-title span { color: var(--fg-muted); font-weight: 400; }

.recall-panel-body { flex: 1; overflow-y: auto; padding: 68px 20px 16px; background: var(--bg); }
.recall-panel-body::-webkit-scrollbar { width: 5px; }
.recall-panel-body::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}
.recall-panel-body::-webkit-scrollbar-thumb {
  background: var(--border); border-radius: 10px;
}
.recall-panel-body::-webkit-scrollbar-thumb:hover { background: #D4C4AD; }

/* ── Stage Card ── */
.recall-stage {
  margin-bottom: 14px; border-radius: var(--radius-md); border: 1px solid var(--border); overflow: hidden;
  transition: opacity 0.3s ease, border-color 0.3s ease;
}
.recall-stage.pending { opacity: 0.55; }
.recall-stage details > summary {
  display: flex; align-items: center; gap: 8px;
  padding: 9px 14px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em;
  user-select: none; list-style: none;
}
.recall-stage details > summary::-webkit-details-marker { display: none; }
.recall-stage details > summary::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid currentColor; transition: transform 0.15s ease;
}
.recall-stage details[open] > summary::before { transform: rotate(90deg); }
.recall-stage-body {
  padding: 0 14px 12px; font-size: 13px; line-height: 1.6;
  color: var(--fg-secondary); border-top: 1px solid var(--border-light);
  display: none;
}
.recall-stage details[open] > .recall-stage-body { display: block; }

.recall-stage-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--fg-muted);
}
.recall-stage.pending .recall-stage-dot { background: var(--fg-muted); }
.recall-stage.running .recall-stage-dot { animation: recall-pulse 1.2s ease-in-out infinite; }

@keyframes recall-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

.recall-stage-badge {
  margin-left: auto; font-size: 10px; font-weight: 500;
  letter-spacing: 0.04em; padding: 2px 8px; border-radius: 10px;
  color: var(--fg-muted);
}
.recall-stage.running .recall-stage-badge { color: var(--amber); background: var(--amber-subtle); }
.recall-stage.done .recall-stage-badge { color: var(--green); background: var(--green-subtle); }

/* Stage color variants */
.recall-stage-expand   { border-left: 3px solid var(--c-think); background: var(--c-think-subtle); }
.recall-stage-expand   details > summary { color: var(--c-think); }
.recall-stage-expand   .recall-stage-dot { background: var(--c-think); }
.recall-stage-retrieve { border-left: 3px solid var(--c-bg); background: var(--c-bg-subtle); }
.recall-stage-retrieve details > summary { color: var(--c-bg); }
.recall-stage-retrieve .recall-stage-dot { background: var(--c-bg); }
.recall-stage-rerank   { border-left: 3px solid var(--c-compact); background: var(--c-compact-subtle); }
.recall-stage-rerank   details > summary { color: var(--c-compact); }
.recall-stage-rerank   .recall-stage-dot { background: var(--c-compact); }
.recall-stage-synth    { border-left: 3px solid var(--c-inbox); background: var(--c-inbox-subtle); }
.recall-stage-synth    details > summary { color: var(--c-inbox); }
.recall-stage-synth    .recall-stage-dot { background: var(--c-inbox); }

/* ── Explanation ── */
.recall-explain {
  margin: 8px 0; padding: 8px 14px; font-size: 13px;
  background: var(--surface); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); color: var(--fg-secondary); line-height: 1.65;
}

/* ── Think block (in stage body) ── */
.recall-think-block {
  margin: 8px 0; background: var(--amber-ghost); border: 1px solid var(--border);
  border-left: 3px solid var(--amber); border-radius: var(--radius-md); overflow: hidden;
}
.recall-think-block summary {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em; color: var(--amber);
  user-select: none; list-style: none;
}
.recall-think-block summary::-webkit-details-marker { display: none; }
.recall-think-block summary::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid var(--amber); transition: transform 0.15s ease;
}
.recall-think-block details[open] > summary::before { transform: rotate(90deg); }
.recall-think-content {
  padding: 4px 12px 10px; font-size: 12px; color: var(--fg-muted);
  font-style: italic; white-space: pre-wrap; border-top: 1px solid var(--border-light);
}

/* ── Text block (LLM output in stage body) ── */
.recall-text-block {
  margin: 8px 0; background: var(--surface); border: 1px solid var(--border-light);
  border-left: 3px solid var(--c-think); border-radius: var(--radius-md); overflow: hidden;
}
.recall-stage-rerank .recall-text-block { border-left-color: var(--c-compact); }
.recall-stage-synth  .recall-text-block { border-left-color: var(--c-inbox); }
.recall-text-block summary {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em; color: var(--c-think);
  user-select: none; list-style: none;
}
.recall-stage-rerank .recall-text-block summary { color: var(--c-compact); }
.recall-stage-synth  .recall-text-block summary { color: var(--c-inbox); }
.recall-text-block summary::-webkit-details-marker { display: none; }
.recall-text-block summary::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid currentColor; transition: transform 0.15s ease;
}
.recall-text-block details[open] > summary::before { transform: rotate(90deg); }
.recall-text-content {
  padding: 4px 12px 10px; font-size: 12px; color: var(--fg-secondary);
  white-space: pre-wrap; font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid var(--border-light);
}

/* ── Variant list ── */
.recall-variant-list { margin: 8px 0; }
.recall-variant-label { font-size: 11px; color: var(--fg-muted); margin-bottom: 4px; }
.recall-variant-item {
  display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; font-size: 13px;
}
.recall-variant-idx {
  flex-shrink: 0; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  color: var(--c-think); background: var(--c-think-subtle); border-radius: 50%;
}
.recall-variant-original {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 1px 5px;
  background: var(--c-think-subtle); color: var(--c-think); border-radius: 3px; margin-left: 2px;
}

/* ── Query result card ── */
.recall-query-card {
  margin: 8px 0; background: var(--surface); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); overflow: hidden;
}
.recall-query-card details > summary::-webkit-details-marker { display: none; }
.recall-query-card details > summary::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid var(--c-bg); transition: transform 0.15s ease;
  margin-right: 2px;
}
.recall-query-card details[open] > summary::before { transform: rotate(90deg); }
.recall-qr-header {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em; color: var(--fg-muted);
  background: var(--surface-hover); cursor: pointer; user-select: none; list-style: none;
}
.recall-query-card details[open] > .recall-qr-header {
  border-bottom: 1px solid var(--border-light);
}
.recall-qr-header code {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--fg-secondary);
  max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.recall-qr-hits { margin-left: auto; font-size: 10px; font-weight: 500; color: var(--c-bg); }
.recall-qr-error { padding: 7px 12px; font-size: 12px; color: var(--red); }
.recall-qr-item {
  padding: 7px 12px; border-bottom: 1px solid var(--border-light);
  font-size: 12px; color: var(--fg-secondary);
}
.recall-qr-item:last-child { border-bottom: none; }
.recall-qr-id { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--fg-muted); margin-bottom: 2px; }
.recall-qr-dist { font-size: 10px; color: var(--fg-muted); }
.recall-qr-doc { margin-top: 3px; font-size: 12px; line-height: 1.5; max-height: 80px; overflow-y: auto; }
.recall-dup-tag {
  font-family: 'Space Grotesk', sans-serif; font-size: 8px; font-weight: 600;
  text-transform: uppercase; padding: 1px 5px; border-radius: 8px;
  color: var(--fg-muted); background: var(--border-light); margin-left: 6px;
}
.recall-retrieve-summary {
  text-align: center; padding: 4px 0 0; font-size: 11px; color: var(--fg-muted);
}

/* ── Ranked list ── */
.recall-ranked-list { margin: 8px 0; }
.recall-ranked-label { font-size: 11px; color: var(--fg-muted); margin-bottom: 4px; }
.recall-ranked-item {
  display: flex; align-items: flex-start; gap: 8px; padding: 6px 0;
  border-bottom: 1px solid var(--border-light); font-size: 12px; color: var(--fg-secondary);
}
.recall-ranked-item:last-child { border-bottom: none; }
.recall-rank-num {
  flex-shrink: 0; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  color: var(--c-compact); background: var(--c-compact-subtle); border-radius: 50%;
}
.recall-ranked-top .recall-rank-num { color: var(--c-compact); background: var(--c-compact-subtle); }
.recall-ranked-item:not(.recall-ranked-top) .recall-rank-num { color: var(--fg-muted); background: var(--border-light); }
.recall-rank-id { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--fg-muted); }
.recall-rank-skip {
  margin-left: auto; font-size: 9px; font-weight: 500; color: var(--fg-muted);
  font-family: 'Space Grotesk', sans-serif; text-transform: uppercase;
}

/* ── Synthesis input ── */
.recall-synth-input {
  margin: 8px 0; background: var(--surface); border: 1px solid var(--border-light);
  border-left: 3px solid var(--c-inbox);
  border-radius: var(--radius-sm); overflow: hidden;
}
.recall-si-header {
  padding: 6px 12px; font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; color: var(--fg-muted); background: var(--surface-hover);
  border-bottom: 1px solid var(--border-light); cursor: pointer; list-style: none;
  display: flex; align-items: center; gap: 6px;
}
.recall-si-header::-webkit-details-marker { display: none; }
.recall-si-header::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid var(--fg-muted); transition: transform 0.15s ease;
}
.recall-synth-input details[open] > .recall-si-header::before { transform: rotate(90deg); }
.recall-synth-input details[open] > .recall-si-header {
  border-bottom: 1px solid var(--border-light);
}
.recall-si-body {
  padding: 8px 12px; font-size: 12px; color: var(--fg-secondary);
}
.recall-frag-tag {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--c-think);
  font-weight: 500;
}

/* ── Final result ── */
.recall-final-result {
  margin: 8px 0; padding: 10px 14px;
  background: var(--green-subtle); border: 1px solid var(--border);
  border-left: 3px solid var(--green); border-radius: var(--radius-md);
  font-size: 13px; line-height: 1.65; color: var(--fg);
}
.recall-fr-label {
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em; color: var(--green); margin-bottom: 4px;
}

/* ── Blinking cursor ── */
.recall-blink {
  display: inline-block; color: var(--amber);
  animation: blink 0.8s step-end infinite; font-weight: 100; font-size: 1.1em;
}

/* ======================== Subagent Sub-Panel ======================== */
.subagent-panel-body {
  display: flex; flex-direction: column; gap: 16px;
}
.subagent-msg {
  display: flex; flex-direction: column; gap: 6px;
}
.subagent-msg-role {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--fg-muted);
}
.subagent-msg-body { min-width: 0; }
.subagent-text {
  font-family: 'DM Sans', sans-serif;
  font-size: 13px; line-height: 1.65;
  color: var(--fg);
}
.subagent-empty {
  text-align: center; padding: 32px 0;
  font-size: 13px; color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
}
</style>
