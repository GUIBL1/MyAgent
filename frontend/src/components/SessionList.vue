<script setup lang="ts">
import type { SessionInfo } from '../composables/useChat'

defineProps<{
  sessions: SessionInfo[]
  currentSessionId: string | null
  streaming: boolean
}>()

const emit = defineEmits<{
  (e: 'select', sessionId: string): void
  (e: 'new-session'): void
}>()

function fmtTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 86400000) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="session-list">
    <button class="new-session-btn" :class="{ disabled: streaming }" :disabled="streaming" @click="emit('new-session')">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
        <line x1="7" y1="1" x2="7" y2="13" />
        <line x1="1" y1="7" x2="13" y2="7" />
      </svg>
      <span>新建会话</span>
    </button>
    <div v-if="sessions.length === 0" class="empty">暂无会话</div>
    <div
      v-for="s in sessions"
      :key="s.session_id"
      class="session-item"
      :class="{ active: s.session_id === currentSessionId, disabled: streaming }"
      @click="!streaming && emit('select', s.session_id)"
    >
      <div class="session-title">{{ s.title || '新会话' }}</div>
      <div class="session-meta">
        <span>{{ s.turns }} 轮</span>
        <span>{{ fmtTime(s.updated_at) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-list {
  display: flex; flex-direction: column; gap: 4px;
}

.new-session-btn {
  display: flex; align-items: center; justify-content: center; gap: 7px;
  width: 100%; padding: 9px 12px;
  background: none; border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--amber); cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 12px; font-weight: 600;
  letter-spacing: 0.03em;
  transition: background 0.15s ease, border-color 0.15s ease;
  margin-bottom: 6px;
}
.new-session-btn:hover {
  background: var(--amber-subtle);
  border-color: var(--amber);
}
.new-session-btn.disabled {
  opacity: 0.35; cursor: not-allowed;
}
.new-session-btn.disabled:hover {
  background: none;
  border-color: var(--border);
}

.empty {
  color: var(--fg-muted);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}

.session-item {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s ease;
}
.session-item:hover {
  background: var(--amber-subtle);
}
.session-item.active {
  background: var(--amber-subtle);
}
.session-item.disabled {
  cursor: not-allowed; opacity: 0.5;
}

.session-title {
  font-family: 'DM Sans', sans-serif;
  font-size: 13px; font-weight: 500;
  color: var(--fg);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 100%;
}

.session-meta {
  display: flex; justify-content: space-between;
  margin-top: 4px;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--fg-muted);
}
</style>
