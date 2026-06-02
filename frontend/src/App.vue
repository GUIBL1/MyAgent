<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import ChatView from './components/ChatView.vue'
import SidePanel from './components/SidePanel.vue'

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
    <!-- Left Panel -->
    <SidePanel
      v-if="showLeft"
      side="left"
      :width="leftWidth"
      title="会话"
      @close="showLeft = false"
    >
      <div class="placeholder">会话列表（占位）</div>
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

    <!-- Right Panel -->
    <SidePanel
      v-if="showRight"
      side="right"
      :width="rightWidth"
      title="状态"
      @close="showRight = false"
    >
      <div class="placeholder">Todo / Skill / MCP / Teammate（占位）</div>
    </SidePanel>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex; align-items: stretch;
  height: 100vh; width: 100vw;
  background: var(--bg);
  overflow: hidden;
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

/* ======================== Placeholder ======================== */
.placeholder {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  line-height: 1.6;
}
</style>
