<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useChat } from './composables/useChat'
import ChatView from './components/ChatView.vue'
import SidePanel from './components/SidePanel.vue'
import SessionList from './components/SessionList.vue'

const { sessions, currentSessionId, isStreaming, tokenUsage, todoList, mcpServers, skills, switchSession, newSession } = useChat()

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

      <!-- Tab: Team -->
      <div v-else class="placeholder">
        Team 信息（占位）
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

/* ======================== Placeholder ======================== */
.placeholder {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  line-height: 1.6;
}
</style>
