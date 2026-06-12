<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { useChat } from './composables/useChat'
import type { RecallMemoryBlock, SubagentBlock } from './composables/useChat'
import ChatView from './components/ChatView.vue'
import MessageBlocks from './components/MessageBlocks.vue'
import SidePanel from './components/SidePanel.vue'
import SessionList from './components/SessionList.vue'

const { sessions, currentSessionId, isStreaming, switchSession, newSession, tokenUsage, todoList, mcpServers, skills, teamInfo, teammateViews, activeTeammate, loadTeammateSession, rightSubPanelStack, openRightRecallDetail, openRightSubagentDetail, closeRightSubPanelTop } = useChat()

const rightSubPanel = computed(() => {
  const top = rightSubPanelStack.value[rightSubPanelStack.value.length - 1]
  return top || null
})
const rightRecallData = computed(() => {
  if (!rightSubPanel.value || rightSubPanel.value.toolName !== 'recall_memory') return null
  return rightSubPanel.value.data as RecallMemoryBlock
})
const rightSubagentData = computed(() => {
  if (!rightSubPanel.value || rightSubPanel.value.toolName !== 'use_subagent') return null
  return rightSubPanel.value.data as SubagentBlock
})

// ── 右边框自动滚动（三种视图共享 teammateBodyEl 滚动容器）──
const teammateBodyEl = ref<HTMLElement | null>(null)

let tmAutoScroll = true
function onTmScroll() {
  if (!teammateBodyEl.value) return
  const { scrollTop, scrollHeight, clientHeight } = teammateBodyEl.value
  tmAutoScroll = scrollHeight - scrollTop - clientHeight < 100
}

// teammate 消息区
watch(() => activeTeammate.value ? teammateViews.value[activeTeammate.value]?.messages : null, () => {
  if (!tmAutoScroll || rightSubPanelStack.value.length > 0) return
  nextTick(() => {
    if (teammateBodyEl.value) {
      teammateBodyEl.value.scrollTop = teammateBodyEl.value.scrollHeight
    }
  })
}, { deep: true })

// recall 子面板
watch(() => rightRecallData.value, () => {
  if (!tmAutoScroll) return
  nextTick(() => {
    if (teammateBodyEl.value) {
      teammateBodyEl.value.scrollTop = teammateBodyEl.value.scrollHeight
    }
  })
}, { deep: true })

// subagent 子面板
watch(() => rightSubagentData.value, () => {
  if (!tmAutoScroll) return
  nextTick(() => {
    if (teammateBodyEl.value) {
      teammateBodyEl.value.scrollTop = teammateBodyEl.value.scrollHeight
    }
  })
}, { deep: true })

const showLeft = ref(false)
const showRight = ref(false)
const rightTab = ref('status')
const rightTabs = [
  { key: 'status', label: '状态' },
  { key: 'mcp', label: '能力' },
  { key: 'team', label: '团队' },
]
const leftWidth = ref(260)
const rightWidth = ref(280)
const dragSide = ref<'left' | 'right' | null>(null)

function startDrag(side: 'left' | 'right', e: MouseEvent) {
  dragSide.value = side
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onDrag(e: MouseEvent) {
  if (dragSide.value === 'left') {
    leftWidth.value = Math.max(180, e.clientX - 4)
  } else if (dragSide.value === 'right') {
    rightWidth.value = Math.max(180, window.innerWidth - e.clientX - 4)
  }
}

function stopDrag() {
  dragSide.value = null
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

onUnmounted(() => stopDrag())
</script>

<template>
  <div class="app-shell">
    <!-- Left Panel: Session List -->
    <SidePanel
      v-if="showLeft"
      side="left"
      :width="leftWidth"
      title="会话"
      @close="showLeft = false"
    >
      <SessionList
        :sessions="sessions"
        :current-session-id="currentSessionId"
        :streaming="isStreaming"
        @select="switchSession"
        @new-session="newSession"
      />
    </SidePanel>

    <!-- Left Resize Handle -->
    <div
      v-if="showLeft"
      class="drag-handle"
      :class="{ active: dragSide === 'left' }"
      @mousedown="startDrag('left', $event)"
    ></div>

    <!-- Center: ChatView -->
    <div class="center-area">
      <ChatView
        :left-panel-open="showLeft"
        :right-panel-open="showRight"
        @toggle-left="showLeft = !showLeft"
        @toggle-right="showRight = !showRight"
      />
    </div>

    <!-- Right Resize Handle -->
    <div
      v-if="showRight"
      class="drag-handle"
      :class="{ active: dragSide === 'right' }"
      @mousedown="startDrag('right', $event)"
    ></div>

    <!-- Right Panel: Status -->
    <SidePanel
      v-if="showRight"
      side="right"
      :width="rightWidth"
      title="状态"
      :tabs="rightTabs"
      :active-tab="rightTab"
      @close="showRight = false"
      @tab-change="rightTab = $event"
    >
      <!-- Tab: 状态（Token + Todo） -->
      <template v-if="rightTab === 'status'">
      <!-- Token 用量 -->
      <div class="token-section">
        <div class="token-section-title">Token 用量</div>
        <div v-if="tokenUsage" class="token-bar-wrap">
          <div class="token-bar">
            <div
              class="token-bar-fill"
              :style="{ width: Math.min(100, (tokenUsage.used / tokenUsage.total) * 100) + '%' }"
              :class="{ warn: tokenUsage.used / tokenUsage.total > 0.8 }"
            ></div>
          </div>
          <div class="token-stats">
            <span>{{ tokenUsage.used.toLocaleString() }} / {{ tokenUsage.total.toLocaleString() }}</span>
            <span class="token-pct">{{ Math.round((tokenUsage.used / tokenUsage.total) * 100) }}%</span>
          </div>
        </div>
        <div v-else class="token-empty">等待用量数据…</div>
      </div>

      <!-- Todo 列表 -->
      <div class="todo-section">
        <div class="todo-section-title">Todo</div>
        <div v-if="todoList.length" class="todo-items">
          <div
            v-for="(item, i) in todoList"
            :key="i"
            class="todo-item"
            :class="item.status"
          >
            <span class="todo-status-dot" :class="item.status"></span>
            <span class="todo-content">{{ item.content }}</span>
          </div>
        </div>
        <div v-else class="todo-empty">暂无 todo 项</div>
      </div>
      </template>

      <!-- Tab: 能力（MCP + Skill） -->
      <div v-else-if="rightTab === 'mcp'" class="cap-section">
        <!-- MCP 服务器 -->
        <details class="cap-group" open>
          <summary class="cap-group-title">MCP 服务器</summary>
          <div v-if="mcpServers.length" class="cap-items">
            <div v-for="s in mcpServers" :key="s.name" class="cap-item">
              <span class="cap-dot" :class="s.connected ? 'on' : 'off'"></span>
              <span class="cap-name">{{ s.name }}</span>
              <span class="cap-tag" :class="s.connected ? 'on' : 'off'">{{ s.connected ? '已连接' : '未连接' }}</span>
            </div>
          </div>
          <div v-else class="cap-empty">无 MCP 服务器</div>
        </details>

        <!-- Skill 列表 -->
        <details class="cap-group" open>
          <summary class="cap-group-title">Skills</summary>
          <div v-if="skills.length" class="cap-items">
            <div v-for="s in skills" :key="s.name" class="cap-item skill-item">
              <span class="cap-name">{{ s.name }}</span>
              <span v-if="s.description" class="cap-desc">{{ s.description }}</span>
            </div>
          </div>
          <div v-else class="cap-empty">无 Skill</div>
        </details>
      </div>

      <!-- Tab: 团队 -->
      <div v-else class="team-tab-content">
        <!-- 队员列表 -->
        <div v-if="!activeTeammate">
          <div v-if="teamInfo" class="team-items">
            <div v-for="m in teamInfo.members" :key="m.name" class="team-item">
              <span class="team-dot" :class="m.status"></span>
              <div class="team-info">
                <span class="team-name">{{ m.name }}</span>
                <span class="team-role">{{ m.role }}</span>
              </div>
              <span v-if="m.name !== 'lead'" class="team-view-btn" @click="activeTeammate = m.name; loadTeammateSession(m.name)">
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="5.5" cy="5.5" r="4"/><line x1="9" y1="9" x2="11" y2="11"/></svg>
                运行查看
              </span>
              <span class="team-status-tag" :class="m.status">
                {{ m.status === 'working' ? '工作中' : m.status === 'idle' ? '空闲' : '已关闭' }}
              </span>
            </div>
          </div>
          <div v-else class="team-empty">等待团队数据…</div>
        </div>

        <!-- Teammate 输出 -->
        <div v-else class="teammate-output">
          <!-- 固定顶栏 -->
          <div class="teammate-topbar">
            <button class="teammate-back" @click="rightSubPanelStack.length > 0 ? closeRightSubPanelTop() : activeTeammate = null">
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="7.5,2 3.5,6 7.5,10"/>
              </svg>
              {{ rightSubPanelStack.length > 0 ? '返回' : '返回团队' }}
            </button>
            <div class="teammate-name">
              <template v-if="!rightSubPanel">{{ activeTeammate }}</template>
              <template v-else-if="rightRecallData">Memory Recall<span v-if="rightRecallData.synth.query"> · {{ rightRecallData.synth.query }}</span></template>
              <template v-else-if="rightSubagentData">Subagent · {{ rightSubagentData.agentType }}<span v-if="rightSubagentData.name"> · {{ rightSubagentData.name }}</span></template>
            </div>
          </div>

          <!-- 可滚动内容区 -->
          <div ref="teammateBodyEl" class="teammate-body" @scroll="onTmScroll">
            <!-- 子面板 -->
            <template v-if="rightSubPanelStack.length > 0">
              <!-- Recall Memory 子面板 -->
              <div v-if="rightRecallData" class="right-recall-body">
                <!-- Stage 1: Expand -->
                <div class="right-recall-stage" :class="rightRecallData.expand.status">
                  <details :open="rightRecallData.expand.status !== 'pending'">
                    <summary>
                      <span class="right-stage-dot"></span>STAGE 1 · Query Expansion
                      <span class="right-stage-badge">{{ rightRecallData.expand.status === 'running' ? '执行中' : rightRecallData.expand.status === 'done' ? '完成' : '等待中' }}</span>
                    </summary>
                    <div class="right-stage-body">
                      <div v-if="rightRecallData.expand.status !== 'pending'" class="right-stage-explain">将原始查询发给 LLM，生成 3–10 条不同角度表述的变体查询，提高召回覆盖度。</div>
                      <div v-if="rightRecallData.expand.thinking" class="right-think-block">
                        <details :open="rightRecallData.active && rightRecallData.expand.status === 'running' && !rightRecallData.expand.text"><summary>EXPANSION THINKING</summary><div class="right-think-content">{{ rightRecallData.expand.thinking }}</div></details>
                      </div>
                      <div v-if="rightRecallData.expand.text" class="right-text-block">
                        <details :open="rightRecallData.active && rightRecallData.expand.status === 'running' && !!rightRecallData.expand.text"><summary>EXPANSION OUTPUT</summary><div class="right-text-content">{{ rightRecallData.expand.text }}</div></details>
                      </div>
                      <div v-if="rightRecallData.expand.variants.length" class="right-variant-list">
                        <div class="right-variant-label">生成变体查询（含原始查询共 {{ rightRecallData.expand.count }} 条）：</div>
                        <div v-for="(v, vi) in rightRecallData.expand.variants" :key="vi" class="right-variant-item">
                          <span class="right-variant-idx">{{ vi + 1 }}</span><span>{{ v }}<span v-if="vi === 0" class="right-variant-original">原始</span></span>
                        </div>
                      </div>
                      <span v-if="rightRecallData.expand.status === 'running'" class="recall-blink">|</span>
                    </div>
                  </details>
                </div>

                <!-- Stage 2: Retrieve -->
                <div class="right-recall-stage" :class="rightRecallData.retrieve.status">
                  <details :open="rightRecallData.retrieve.status !== 'pending'">
                    <summary>
                      <span class="right-stage-dot"></span>STAGE 2 · Multi-Query Retrieval
                      <span class="right-stage-badge">{{ rightRecallData.retrieve.status === 'running' ? '执行中' : rightRecallData.retrieve.status === 'done' ? '完成' : '等待中' }}</span>
                    </summary>
                    <div class="right-stage-body">
                      <div v-if="rightRecallData.retrieve.status !== 'pending'" class="right-stage-explain">将每条变体查询转为向量，分别检索 Chroma 向量数据库，去重合并候选记忆。</div>
                      <div v-for="(qr, qri) in rightRecallData.retrieve.queries" :key="qri" class="right-query-card">
                        <details :open="qr.active">
                          <summary>查询 <code>{{ qr.query }}</code><span class="right-qr-hits">{{ qr.error ? '失败' : qr.active ? '查询中…' : qr.hit_count + ' 条命中' }}</span></summary>
                          <div v-if="qr.error" style="color:var(--red);padding:4px 8px;font-size:10px;">{{ qr.error }}</div>
                          <div v-for="(hit, hi) in qr.hits" :key="hi" class="right-query-hit">
                            <div class="right-query-hit-id">{{ hit.id }}<span v-if="hit.duplicate" class="right-dup-tag">重复</span></div>
                            <div class="right-query-hit-dist">distance: {{ hit.distance }} · access: {{ hit.access_count }}</div>
                            <div class="right-query-hit-doc">{{ hit.doc }}</div>
                          </div>
                        </details>
                      </div>
                      <div v-if="rightRecallData.retrieve.status === 'done'" style="text-align:center;font-size:10px;color:var(--fg-muted);padding-top:4px;">去重后共 <strong>{{ rightRecallData.retrieve.total_candidates }}</strong> 条候选记忆</div>
                    </div>
                  </details>
                </div>

                <!-- Stage 3: Rerank -->
                <div class="right-recall-stage" :class="rightRecallData.rerank.status">
                  <details :open="rightRecallData.rerank.status !== 'pending'">
                    <summary>
                      <span class="right-stage-dot"></span>STAGE 3 · LLM Reranking
                      <span class="right-stage-badge">{{ rightRecallData.rerank.status === 'running' ? '执行中' : rightRecallData.rerank.status === 'done' ? '完成' : '等待中' }}</span>
                    </summary>
                    <div class="right-stage-body">
                      <div v-if="rightRecallData.rerank.status !== 'pending'" class="right-stage-explain">将去重后的候选记忆送给重排序 LLM，按语义匹配度、向量距离、历史访问频率综合打分，输出降序排列。</div>
                      <div v-if="rightRecallData.rerank.thinking" class="right-think-block">
                        <details :open="rightRecallData.active && rightRecallData.rerank.status === 'running' && !rightRecallData.rerank.text"><summary>RERANK THINKING</summary><div class="right-think-content">{{ rightRecallData.rerank.thinking }}</div></details>
                      </div>
                      <div v-if="rightRecallData.rerank.text" class="right-text-block">
                        <details :open="rightRecallData.active && rightRecallData.rerank.status === 'running' && !!rightRecallData.rerank.text"><summary>RERANK OUTPUT</summary><div class="right-text-content">{{ rightRecallData.rerank.text }}</div></details>
                      </div>
                      <div v-if="rightRecallData.rerank.ranked_ids.length" class="right-ranked-list">
                        <div class="right-ranked-label">排序结果（top {{ rightRecallData.rerank.top_k }} 送入合成）：</div>
                        <div v-for="(rid, ri) in rightRecallData.rerank.ranked_ids" :key="ri" class="right-ranked-item" :class="{ 'right-ranked-top': ri < rightRecallData.rerank.top_k }">
                          <span class="right-rank-num">{{ ri + 1 }}</span>
                          <span class="right-rank-id">{{ rid }}</span>
                          <span v-if="ri >= rightRecallData.rerank.top_k" class="right-rank-skip">舍弃</span>
                        </div>
                      </div>
                      <span v-if="rightRecallData.rerank.status === 'running'" class="recall-blink">|</span>
                    </div>
                  </details>
                </div>

                <!-- Stage 4: Synthesize -->
                <div class="right-recall-stage" :class="rightRecallData.synth.status">
                  <details :open="rightRecallData.synth.status !== 'pending'">
                    <summary>
                      <span class="right-stage-dot"></span>STAGE 4 · LLM Synthesis
                      <span class="right-stage-badge">{{ rightRecallData.synth.status === 'running' ? '执行中' : rightRecallData.synth.status === 'done' ? '完成' : '等待中' }}</span>
                    </summary>
                    <div class="right-stage-body">
                      <div v-if="rightRecallData.synth.status !== 'pending'" class="right-stage-explain">将重排结果组装为记忆片段列表，送合成 LLM 生成面向原始查询的最终回答。如有矛盾以索引小的片段为准。</div>
                      <div v-if="rightRecallData.synth.fragments.length" class="right-synth-input">
                        <details :open="rightRecallData.active && rightRecallData.synth.status === 'running' && !rightRecallData.synth.thinking && !rightRecallData.synth.text"><summary>合成输入 · {{ rightRecallData.synth.fragments.length }} 条记忆片段</summary>
                          <div class="right-synth-body">
                            <div v-for="(f, fi) in rightRecallData.synth.fragments" :key="fi">
                              <span class="right-frag-tag">[{{ f.index }}]</span> {{ f.content }}
                            </div>
                          </div>
                        </details>
                      </div>
                      <div v-if="rightRecallData.synth.thinking" class="right-think-block">
                        <details :open="rightRecallData.active && rightRecallData.synth.status === 'running' && !rightRecallData.synth.text"><summary>SYNTHESIS THINKING</summary><div class="right-think-content">{{ rightRecallData.synth.thinking }}</div></details>
                      </div>
                      <div v-if="rightRecallData.synth.text" class="right-text-block">
                        <details :open="rightRecallData.active && rightRecallData.synth.status === 'running' && !!rightRecallData.synth.text"><summary>SYNTHESIS OUTPUT</summary><div class="right-text-content">{{ rightRecallData.synth.text }}</div></details>
                      </div>
                      <div v-if="rightRecallData.synth.result" class="right-final-result">
                        <div class="right-fr-label">合成结果</div>
                        <div>{{ rightRecallData.synth.result }}</div>
                      </div>
                      <span v-if="rightRecallData.synth.status === 'running'" class="recall-blink">|</span>
                    </div>
                  </details>
                </div>
              </div>

              <!-- Subagent 子面板 -->
              <div v-else-if="rightSubagentData" class="right-subagent-body">
                <template v-for="(msg, mi) in rightSubagentData.messages" :key="mi">
                  <div class="right-sa-msg">
                    <MessageBlocks
                      :blocks="msg.blocks"
                      :streaming="rightSubagentData.status === 'running'"
                      :is-last="mi === rightSubagentData.messages.length - 1"
                      @open-recall-detail="openRightRecallDetail"
                      @open-subagent-detail="openRightSubagentDetail"
                    />
                  </div>
                </template>
                <div v-if="rightSubagentData.messages.length === 0" class="right-sa-empty">等待 subagent 输出…</div>
                <span v-if="rightSubagentData.status === 'running'" class="cursor">|</span>
              </div>
            </template>

            <!-- 消息列表（无子面板时） -->
            <div v-else-if="teammateViews[activeTeammate]" class="teammate-msgs">
              <div v-for="(msg, mi) in teammateViews[activeTeammate].messages" :key="mi" class="tm-msg">
                <MessageBlocks
                  :blocks="msg.blocks"
                  :streaming="teammateViews[activeTeammate].isActive"
                  :is-last="mi === teammateViews[activeTeammate].messages.length - 1"
                  @open-recall-detail="openRightRecallDetail"
                  @open-subagent-detail="openRightSubagentDetail"
                />
              </div>
            </div>
            <div v-else class="teammate-loading">加载中…</div>
          </div>
        </div>
      </div>
    </SidePanel>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex; align-items: stretch;
  height: 100vh; width: 100vw;
  background: var(--bg);
  overflow: hidden;
  padding: 12px 4px;
}

.center-area {
  flex: 1; min-width: 0;
  height: 100%;
}

/* ======================== Drag Handle ======================== */
.drag-handle {
  width: 8px; flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s ease;
  position: relative;
}
.drag-handle::after {
  content: '';
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 2px; height: 40px;
  border-radius: 1px;
  background: var(--border);
  transition: background 0.15s ease, height 0.15s ease;
}
.drag-handle:hover::after,
.drag-handle.active::after {
  background: var(--amber);
  height: 60px;
}

/* ======================== Token Usage ======================== */
.token-section {
  margin-bottom: 16px;
}
.token-section-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--fg-muted);
  margin-bottom: 8px;
}
.token-bar-wrap {
  display: flex; flex-direction: column; gap: 4px;
}
.token-bar {
  width: 100%; height: 6px;
  background: var(--border-light);
  border-radius: 3px;
  overflow: hidden;
}
.token-bar-fill {
  height: 100%;
  background: var(--amber);
  border-radius: 3px;
  transition: width 0.3s ease;
}
.token-bar-fill.warn {
  background: var(--red);
}
.token-stats {
  display: flex; justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: var(--fg-muted);
}
.token-pct {
  font-weight: 500; color: var(--fg-secondary);
}
.token-empty {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 12px;
}

/* ======================== Todo List ======================== */
.todo-section {
  margin-bottom: 16px;
}
.todo-section-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--fg-muted);
  margin-bottom: 8px;
}
.todo-items {
  display: flex; flex-direction: column; gap: 6px;
}
.todo-item {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-light);
  font-family: 'DM Sans', sans-serif; font-size: 12px; line-height: 1.5;
  color: var(--fg-secondary);
}
.todo-item.in_progress {
  background: var(--amber-subtle);
  border-color: rgba(217, 119, 6, 0.15);
  color: var(--fg);
}
.todo-item.completed {
  opacity: 0.55;
}
.todo-item.completed .todo-content {
  text-decoration: line-through;
}
.todo-status-dot {
  flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%;
  margin-top: 4px;
  background: var(--border);
}
.todo-status-dot.in_progress { background: var(--amber); }
.todo-status-dot.completed { background: var(--green); }
.todo-empty {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 12px;
}

/* ======================== MCP / Skill ======================== */
.cap-section {
  display: flex; flex-direction: column; gap: 12px;
}
.cap-group {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.cap-group-title {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--fg-muted);
  background: var(--surface-hover);
  user-select: none; list-style: none;
}
.cap-group-title::-webkit-details-marker { display: none; }
.cap-group-title::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid var(--fg-muted); transition: transform 0.15s ease;
}
.cap-group[open] > .cap-group-title::before { transform: rotate(90deg); }
.cap-items {
  display: flex; flex-direction: column;
}
.cap-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; border-bottom: 1px solid var(--border-light);
  font-family: 'DM Sans', sans-serif; font-size: 12px; color: var(--fg-secondary);
}
.cap-item:last-child { border-bottom: none; }
.skill-item {
  flex-wrap: wrap;
}
.cap-dot {
  flex-shrink: 0; width: 7px; height: 7px; border-radius: 50%;
}
.cap-dot.on  { background: var(--green); }
.cap-dot.off { background: var(--red); }
.cap-name {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg);
}
.cap-desc {
  width: 100%; margin-top: 2px;
  font-size: 11px; color: var(--fg-muted); line-height: 1.4;
}
.cap-tag {
  margin-left: auto;
  font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em;
  padding: 2px 6px; border-radius: 8px;
}
.cap-tag.on  { color: var(--green); background: var(--green-subtle); }
.cap-tag.off { color: var(--red);  background: var(--red-subtle); }
.cap-empty {
  padding: 10px 12px;
  font-family: 'DM Sans', sans-serif; font-size: 12px; color: var(--fg-muted);
}

/* ======================== Team ======================== */
.team-items { display: flex; flex-direction: column; gap: 6px; }
.team-item { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border: 1px solid var(--border-light); border-radius: var(--radius-sm); font-family: 'DM Sans', sans-serif; font-size: 12px; }
.team-dot { flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%; }
.team-dot.working { background: var(--green); } .team-dot.idle { background: var(--amber); } .team-dot.shutdown { background: var(--fg-muted); }
.team-info { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.team-name { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg); }
.team-role { font-size: 10px; color: var(--fg-muted); }
.team-status-tag { flex-shrink: 0; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 6px; border-radius: 8px; }
.team-status-tag.working { color: var(--green); background: var(--green-subtle); }
.team-status-tag.idle { color: var(--amber); background: var(--amber-subtle); }
.team-status-tag.shutdown { color: var(--fg-muted); background: var(--border-light); }
.team-view-btn { flex-shrink: 0; display: inline-flex; align-items: center; gap: 3px; padding: 3px 8px; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--amber); background: var(--amber-subtle); border: 1px solid rgba(217,119,6,0.2); border-radius: var(--radius-sm); cursor: pointer; transition: 0.15s ease; }
.team-view-btn:hover { background: rgba(217,119,6,0.15); }
.team-empty { font-family: 'DM Sans', sans-serif; font-size: 12px; color: var(--fg-muted); }

/* Team tab wrapper — 100% 高度继承自 panel-body (flex:1)，给子元素提供确定的包含块 */
.team-tab-content { height: 100%; overflow-y: auto; }

/* Teammate 输出 — 固定顶栏 + 可滚动内容 (same pattern as ChatView sub-panel) */
.teammate-output { height: 100%; position: relative; overflow: hidden; }
.teammate-topbar {
  position: absolute; top: 0; left: 0; right: 0; z-index: 10;
  display: flex; align-items: center; gap: 8px;
  padding: 8px 0 8px; border-bottom: 1px solid var(--border-light);
  background: var(--bg);
}
.teammate-back { display: inline-flex; align-items: center; gap: 4px; font-family: 'Space Grotesk', sans-serif; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--fg-muted); background: none; border: none; cursor: pointer; padding: 4px 8px; border-radius: var(--radius-sm); transition: 0.15s ease; flex-shrink: 0; }
.teammate-back:hover { color: var(--amber); background: var(--amber-subtle); }
.teammate-name { font-family: 'Space Grotesk', sans-serif; font-size: 12px; font-weight: 600; color: var(--fg-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.teammate-body { height: 100%; overflow-y: auto; padding: 42px 0 16px; }
.teammate-body::-webkit-scrollbar { width: 5px; }
.teammate-body::-webkit-scrollbar-track { background: transparent; margin: 8px 0; }
.teammate-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
.teammate-body::-webkit-scrollbar-thumb:hover { background: #D4C4AD; }
.teammate-msgs { display: flex; flex-direction: column; gap: 12px; }
.teammate-loading { font-size: 12px; color: var(--fg-muted); }

/* ── Right Panel Recall Memory Stages (仿 ChatView 样式) ── */
.right-recall-body { display: flex; flex-direction: column; gap: 10px; }
.right-recall-stage {
  margin-bottom: 2px; border-radius: var(--radius-md); border: 1px solid var(--border); overflow: hidden;
  transition: opacity 0.3s ease;
}
.right-recall-stage.pending { opacity: 0.55; }
.right-recall-stage details > summary {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 10px; cursor: pointer;
  font-family: 'Space Grotesk', sans-serif; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em;
  user-select: none; list-style: none;
}
.right-recall-stage details > summary::-webkit-details-marker { display: none; }
.right-recall-stage details > summary::before {
  content: ''; display: inline-block; flex-shrink: 0;
  width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  border-left: 5px solid currentColor; transition: transform 0.15s ease;
}
.right-recall-stage details[open] > summary::before { transform: rotate(90deg); }
.right-stage-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.right-recall-stage.running .right-stage-dot { animation: recall-pulse 1.2s ease-in-out infinite; }
@keyframes recall-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.right-stage-badge {
  margin-left: auto; font-size: 9px; font-weight: 500;
  letter-spacing: 0.03em; padding: 1px 6px; border-radius: 8px;
}
.right-recall-stage.running .right-stage-badge { color: var(--amber); background: var(--amber-subtle); }
.right-recall-stage.done .right-stage-badge { color: var(--green); background: var(--green-subtle); }
/* Stage colors — nth-child match ChatView */
.right-recall-stage:nth-child(1) { border-left: 3px solid var(--c-think); background: var(--c-think-subtle); }
.right-recall-stage:nth-child(1) details > summary { color: var(--c-think); }
.right-recall-stage:nth-child(1) .right-stage-dot { background: var(--c-think); }
.right-recall-stage:nth-child(2) { border-left: 3px solid var(--c-bg); background: var(--c-bg-subtle); }
.right-recall-stage:nth-child(2) details > summary { color: var(--c-bg); }
.right-recall-stage:nth-child(2) .right-stage-dot { background: var(--c-bg); }
.right-recall-stage:nth-child(3) { border-left: 3px solid var(--c-compact); background: var(--c-compact-subtle); }
.right-recall-stage:nth-child(3) details > summary { color: var(--c-compact); }
.right-recall-stage:nth-child(3) .right-stage-dot { background: var(--c-compact); }
.right-recall-stage:nth-child(4) { border-left: 3px solid var(--c-inbox); background: var(--c-inbox-subtle); }
.right-recall-stage:nth-child(4) details > summary { color: var(--c-inbox); }
.right-recall-stage:nth-child(4) .right-stage-dot { background: var(--c-inbox); }

.right-stage-body {
  padding: 0 10px 8px; font-size: 11px; line-height: 1.5;
  color: var(--fg-secondary); border-top: 1px solid var(--border-light);
}
/* Explanation */
.right-stage-explain { font-size: 11px; color: var(--fg-muted); padding: 6px 8px; margin: 4px 0; background: var(--surface); border: 1px solid var(--border-light); border-radius: var(--radius-sm); line-height: 1.5; }
/* Thinking block */
.right-think-block { margin: 4px 0; background: var(--amber-ghost); border: 1px solid var(--border); border-left: 3px solid var(--amber); border-radius: var(--radius-sm); overflow: hidden; }
.right-think-block summary { padding: 4px 8px; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; color: var(--amber); cursor: pointer; list-style: none; display: flex; align-items: center; gap: 4px; }
.right-think-block summary::-webkit-details-marker { display: none; }
.right-think-block summary::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 3px solid transparent; border-bottom: 3px solid transparent; border-left: 4px solid var(--amber); transition: transform 0.15s ease; }
.right-think-block details[open] > summary::before { transform: rotate(90deg); }
.right-think-content { padding: 2px 8px 6px; font-size: 10px; color: var(--fg-muted); font-style: italic; white-space: pre-wrap; border-top: 1px solid var(--border-light); }
/* Text block */
.right-text-block { margin: 4px 0; background: var(--surface); border: 1px solid var(--border-light); border-left: 3px solid var(--c-think); border-radius: var(--radius-sm); overflow: hidden; }
.right-text-block summary { padding: 4px 8px; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; color: var(--c-think); cursor: pointer; list-style: none; display: flex; align-items: center; gap: 4px; }
.right-text-block summary::-webkit-details-marker { display: none; }
.right-text-block summary::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 3px solid transparent; border-bottom: 3px solid transparent; border-left: 4px solid var(--c-think); transition: transform 0.15s ease; }
.right-text-block details[open] > summary::before { transform: rotate(90deg); }
.right-text-content { padding: 2px 8px 6px; font-size: 10px; color: var(--fg-secondary); font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; border-top: 1px solid var(--border-light); }
/* Variants */
.right-variant-list { margin: 4px 0; }
.right-variant-label { font-size: 10px; color: var(--fg-muted); margin-bottom: 2px; }
.right-variant-item { display: flex; align-items: flex-start; gap: 6px; padding: 2px 0; font-size: 11px; }
.right-variant-idx { flex-shrink: 0; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; color: var(--c-think); background: var(--c-think-subtle); border-radius: 50%; }
.right-variant-original { font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 0 4px; background: var(--c-think-subtle); color: var(--c-think); border-radius: 2px; margin-left: 2px; }
/* Query cards in Stage 2 */
.right-query-card { margin: 4px 0; background: var(--surface); border: 1px solid var(--border-light); border-radius: var(--radius-sm); overflow: hidden; }
.right-query-card summary { padding: 5px 8px; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; color: var(--fg-muted); cursor: pointer; list-style: none; display: flex; align-items: center; gap: 6px; background: var(--surface-hover); }
.right-query-card summary::-webkit-details-marker { display: none; }
.right-query-card summary::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 3px solid transparent; border-bottom: 3px solid transparent; border-left: 4px solid var(--c-bg); transition: transform 0.15s ease; }
.right-query-card details[open] > summary::before { transform: rotate(90deg); }
.right-qr-hits { margin-left: auto; font-size: 9px; font-weight: 500; color: var(--c-bg); }
.right-query-hit { padding: 4px 8px; border-bottom: 1px solid var(--border-light); font-size: 10px; color: var(--fg-secondary); }
.right-query-hit:last-child { border-bottom: none; }
.right-query-hit-id { font-family: 'JetBrains Mono', monospace; font-size: 8px; color: var(--fg-muted); }
.right-query-hit-dist { font-size: 9px; color: var(--fg-muted); }
.right-query-hit-doc { font-size: 10px; line-height: 1.4; margin-top: 2px; max-height: 60px; overflow-y: auto; }
.right-dup-tag { font-family: 'Space Grotesk', sans-serif; font-size: 7px; font-weight: 600; text-transform: uppercase; padding: 0 4px; border-radius: 6px; color: var(--fg-muted); background: var(--border-light); margin-left: 4px; }
/* Ranked list in Stage 3 */
.right-ranked-list { margin: 4px 0; }
.right-ranked-label { font-size: 10px; color: var(--fg-muted); margin-bottom: 2px; }
.right-ranked-item { display: flex; align-items: flex-start; gap: 6px; padding: 3px 0; border-bottom: 1px solid var(--border-light); font-size: 11px; color: var(--fg-secondary); }
.right-ranked-item:last-child { border-bottom: none; }
.right-rank-num { flex-shrink: 0; width: 16px; height: 16px; display: flex; align-items: center; justify-content: center; font-family: 'Space Grotesk', sans-serif; font-size: 8px; font-weight: 600; color: var(--c-compact); background: var(--c-compact-subtle); border-radius: 50%; }
.right-ranked-item:not(.right-ranked-top) .right-rank-num { color: var(--fg-muted); background: var(--border-light); }
.right-rank-id { font-family: 'JetBrains Mono', monospace; font-size: 8px; color: var(--fg-muted); }
.right-rank-skip { margin-left: auto; font-size: 8px; font-weight: 500; color: var(--fg-muted); font-family: 'Space Grotesk', sans-serif; text-transform: uppercase; }
/* Synthesis input fragments in Stage 4 */
.right-synth-input { margin: 4px 0; background: var(--surface); border: 1px solid var(--border-light); border-left: 3px solid var(--c-inbox); border-radius: var(--radius-sm); overflow: hidden; }
.right-synth-input summary { padding: 5px 8px; font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; color: var(--fg-muted); cursor: pointer; list-style: none; display: flex; align-items: center; gap: 6px; background: var(--surface-hover); }
.right-synth-input summary::-webkit-details-marker { display: none; }
.right-synth-input summary::before { content: ''; display: inline-block; flex-shrink: 0; width: 0; height: 0; border-top: 3px solid transparent; border-bottom: 3px solid transparent; border-left: 4px solid var(--fg-muted); transition: transform 0.15s ease; }
.right-synth-input details[open] > summary::before { transform: rotate(90deg); }
.right-synth-body { padding: 4px 8px 6px; font-size: 10px; color: var(--fg-secondary); max-height: 160px; overflow-y: auto; }
.right-frag-tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--c-think); font-weight: 500; }
/* Final result */
.right-final-result { padding: 6px 8px; margin-top: 4px; background: var(--green-subtle); border: 1px solid var(--border); border-left: 3px solid var(--green); border-radius: var(--radius-sm); font-size: 11px; line-height: 1.5; color: var(--fg); }
.right-fr-label { font-family: 'Space Grotesk', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--green); margin-bottom: 2px; }
/* Blinking cursor */
.recall-blink { display: inline-block; color: var(--amber); animation: blink 0.8s step-end infinite; font-weight: 100; }

.right-subagent-body { display: flex; flex-direction: column; gap: 12px; }
.right-sa-empty { text-align: center; padding: 24px 0; font-size: 12px; color: var(--fg-muted); font-family: 'DM Sans', sans-serif; }
.cursor { display: inline-block; color: var(--amber); animation: blink 0.8s step-end infinite; font-weight: 100; font-size: 1.1em; line-height: 1; margin-left: 1px; }
@keyframes blink { 50% { opacity: 0; } }

/* ======================== Placeholder ======================== */
.placeholder {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  line-height: 1.6;
}
</style>
