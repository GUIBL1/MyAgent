<script setup lang="ts">
defineProps<{
  title: string
  width: number
  side: 'left' | 'right'
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <div class="side-panel" :style="{ width: width + 'px' }">
    <header class="panel-header">
      <span class="panel-title">{{ title }}</span>
      <button class="panel-close" @click="emit('close')" title="关闭面板">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="3" x2="11" y2="11" />
          <line x1="11" y1="3" x2="3" y2="11" />
        </svg>
      </button>
    </header>
    <div class="panel-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.side-panel {
  display: flex; flex-direction: column;
  height: 100%;
  background: var(--glass);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  margin: 0 8px;
  overflow: hidden;
  flex-shrink: 0;
}

.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}
.panel-title {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600; font-size: 13px;
  color: var(--fg);
  letter-spacing: -0.2px;
}
.panel-close {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  background: none; border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-muted); cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.panel-close:hover { background: var(--amber-subtle); color: var(--amber); }

.panel-body {
  flex: 1; overflow-y: auto;
  padding: 8px 16px;
}

.panel-body::-webkit-scrollbar { width: 5px; }
.panel-body::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}
.panel-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
.panel-body::-webkit-scrollbar-thumb:hover { background: #D4C4AD; }
</style>
