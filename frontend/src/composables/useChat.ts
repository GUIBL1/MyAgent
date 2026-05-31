import { ref, nextTick, type Ref } from 'vue'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  blocks: MessageBlock[]
}

export type MessageBlock =
  | { type: 'text'; content: string }
  | { type: 'thinking'; content: string; active: boolean }
  | { type: 'tool'; id: string; name: string; input: Record<string, unknown>; status: 'running' | 'done'; result?: string }

export function useChat() {
  const messages: Ref<ChatMessage[]> = ref([])
  const isStreaming = ref(false)
  const wsStatus = ref<'disconnected' | 'connecting' | 'connected'>('disconnected')

  let ws: WebSocket | null = null

  function _applyDelta(type: 'text' | 'thinking', delta: string) {
    if (!isStreaming.value) return
    const last = messages.value[messages.value.length - 1]
    if (!last || last.role !== 'assistant') return

    const lastBlock = last.blocks[last.blocks.length - 1]

    // 类型切换时，标记上一个 thinking 块为非活跃（自动折叠）
    if (lastBlock && lastBlock.type !== type && lastBlock.type === 'thinking') {
      lastBlock.active = false
    }

    if (lastBlock && lastBlock.type === type) {
      lastBlock.content += delta
    } else if (type === 'thinking') {
      last.blocks.push({ type: 'thinking', content: delta, active: true })
    } else {
      last.blocks.push({ type: 'text', content: delta })
    }
  }

  // ---- WebSocket 连接 ----
  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws/chat`
    wsStatus.value = 'connecting'
    ws = new WebSocket(url)

    ws.onopen = () => { wsStatus.value = 'connected' }
    ws.onclose = () => { wsStatus.value = 'disconnected' }
    ws.onerror = () => { wsStatus.value = 'disconnected' }

    ws.onmessage = (evt) => {
      handleEvent(JSON.parse(evt.data))
    }
  }

  // ---- 事件分发：收到即写，不缓冲 ----
  function handleEvent(data: any) {
    const type = data.type as string

    if (type === 'text') {
      if (isStreaming.value) _applyDelta('text', data.delta)
    } else if (type === 'thinking') {
      if (isStreaming.value) _applyDelta('thinking', data.delta)
    } else if (type === 'tool_start') {
      if (isStreaming.value) {
        const last = messages.value[messages.value.length - 1]
        if (last?.role === 'assistant') {
          // 上一个 thinking 块结束 → 折叠
          const lastBlock = last.blocks[last.blocks.length - 1]
          if (lastBlock?.type === 'thinking') lastBlock.active = false

          last.blocks.push({
            type: 'tool', id: data.tool_id, name: data.tool_name,
            input: data.tool_input ?? {}, status: 'running',
          })
          nextTick()
        }
      }
    } else if (type === 'tool_result') {
      if (isStreaming.value) {
        const last = messages.value[messages.value.length - 1]
        if (last?.role === 'assistant') {
          const idx = last.blocks.findIndex(
            (b) => b.type === 'tool' && b.id === data.tool_id
          )
          if (idx !== -1) {
            const block = last.blocks[idx] as Extract<MessageBlock, { type: 'tool' }>
            last.blocks.splice(idx, 1, {
              ...block, status: 'done', result: data.content,
            })
          }
        }
      }
    } else if (type === 'user_message') {
      messages.value.push({ role: 'assistant', content: '', blocks: [] })
      isStreaming.value = true
    } else if (type === 'assistant_done') {
      // 结束所有 thinking 块
      const lastDone = messages.value[messages.value.length - 1]
      if (lastDone?.role === 'assistant') {
        for (const b of lastDone.blocks) {
          if (b.type === 'thinking') b.active = false
        }
      }
      isStreaming.value = false
    } else if (type === 'error') {
      if (isStreaming.value) {
        const last = messages.value[messages.value.length - 1]
        if (last?.role === 'assistant') {
          last.blocks.push({ type: 'text', content: `\n❌ ${data.error_msg}` } as MessageBlock)
        }
        isStreaming.value = false
      }
    }
  }

  // ---- 发送 ----
  function send(content: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    messages.value.push({ role: 'user', content, blocks: [] })
    ws.send(JSON.stringify({ type: 'send', content }))
  }

  return { messages, isStreaming, wsStatus, connect, send }
}
