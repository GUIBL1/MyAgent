<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useChat } from './composables/useChat'
import ChatView from './components/ChatView.vue'
import SidePanel from './components/SidePanel.vue'
import SessionList from './components/SessionList.vue'

const { sessions, currentSessionId, isStreaming, tokenUsage, switchSession, newSession } = useChat()

const showLeft = ref(false)
const showRight = ref(false)
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
      @close="showRight = false"
    >
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

/* ======================== Placeholder ======================== */
.placeholder {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  line-height: 1.6;
}
</style>
