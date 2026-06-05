import { ref, type Ref } from 'vue'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  blocks: MessageBlock[]
}

export type MessageBlock =
  | { type: 'text'; content: string }
  | { type: 'thinking'; content: string; active: boolean }
  | { type: 'tool'; id: string; name: string; input: Record<string, unknown>; status: 'running' | 'done'; result?: string }
  | { type: 'micro_compact'; content: string }
  | { type: 'auto_compact'; content: string; thinking: string; summary: string; compactStatus: 'running' | 'done'; result?: string }
  | { type: 'background_notification'; content: string }
  | { type: 'inbox_message'; content: string }
  | { type: 'todo_reminder'; content: string }

export interface SessionInfo {
  session_id: string
  title: string
  turns: number
  created_at: string
  updated_at: string
}

// 单例：确保所有组件共享同一个 WebSocket 连接和状态
let _instance: ReturnType<typeof _createChat> | null = null

export function useChat() {
  if (!_instance) {
    _instance = _createChat()
  }
  return _instance
}

function _createChat() {
  const messages: Ref<ChatMessage[]> = ref([])
  const isStreaming = ref(false)
  const wsStatus = ref<'disconnected' | 'connecting' | 'connected'>('disconnected')

  // 会话管理
  const sessions: Ref<SessionInfo[]> = ref([])
  const currentSessionId: Ref<string | null> = ref(null)
  const hasSession = ref(false) // 是否有活跃会话（已发送过消息）

  let ws: WebSocket | null = null

  function _lastAssistant(): ChatMessage | undefined {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') return messages.value[i]
    }
    return undefined
  }

  function _applyDelta(type: 'text' | 'thinking', delta: string) {
    if (!isStreaming.value) return
    const last = _lastAssistant()
    if (!last) return

    const lastBlock = last.blocks[last.blocks.length - 1]

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

  // ---- 事件分发 ----
  function handleEvent(data: any) {
    const type = data.type as string

    // === 会话管理事件 ===

    if (type === 'session_list') {
      sessions.value = data.sessions || []
      return
    }

    if (type === 'session_created') {
      currentSessionId.value = data.session_id
      hasSession.value = true
      return
    }

    if (type === 'session_state') {
      currentSessionId.value = data.session_id
      hasSession.value = !!data.session_id
      messages.value = rebuildFromTranscript(data.transcript || [])
      isStreaming.value = false
      return
    }

    // === 对话事件 ===

    if (type === 'text') {
      if (isStreaming.value) _applyDelta('text', data.delta)
    } else if (type === 'thinking') {
      if (isStreaming.value) _applyDelta('thinking', data.delta)
    } else if (type === 'tool_start') {
      if (isStreaming.value) {
        const last = _lastAssistant()
        if (last) {
          const lastBlock = last.blocks[last.blocks.length - 1]
          if (lastBlock?.type === 'thinking') lastBlock.active = false
          last.blocks.push({
            type: 'tool', id: data.tool_id, name: data.tool_name,
            input: data.tool_input ?? {}, status: 'running',
          })
        }
      }
    } else if (type === 'tool_result') {
      if (isStreaming.value) {
        const last = _lastAssistant()
        if (last) {
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
      const last = _lastAssistant()
      if (last) {
        for (const b of last.blocks) {
          if (b.type === 'thinking') b.active = false
        }
      }
      isStreaming.value = false
    } else if (type === 'error') {
      if (isStreaming.value) {
        const last = _lastAssistant()
        if (last) {
          last.blocks.push({ type: 'text', content: `\n❌ ${data.error_msg}` } as MessageBlock)
        }
        isStreaming.value = false
      }

    // === 状态事件 — 作为 block 插入当前 assistant 消息 ===

    } else if (type === 'micro_compact') {
      const last = _lastAssistant()
      if (last) last.blocks.push({ type: 'micro_compact', content: data.content || '' })

    } else if (type === 'inbox_message') {
      const last = _lastAssistant()
      if (last) last.blocks.push({ type: 'inbox_message', content: data.content || '' })

    } else if (type === 'background_notification') {
      const last = _lastAssistant()
      if (last) last.blocks.push({ type: 'background_notification', content: data.content || '' })

    } else if (type === 'todo_reminder') {
      const last = _lastAssistant()
      if (last) last.blocks.push({ type: 'todo_reminder', content: data.content || '' })

    } else if (type === 'auto_compact_start') {
      const last = _lastAssistant()
      if (last) last.blocks.push({ type: 'auto_compact', content: data.content || '', thinking: '', summary: '', compactStatus: 'running' })

    } else if (type === 'auto_compact_thinking') {
      const last = _lastAssistant()
      if (last) {
        const ac = last.blocks[last.blocks.length - 1]
        if (ac?.type === 'auto_compact') ac.thinking += (data.delta || '')
      }

    } else if (type === 'auto_compact_text') {
      const last = _lastAssistant()
      if (last) {
        const ac = last.blocks[last.blocks.length - 1]
        if (ac?.type === 'auto_compact') ac.summary += (data.delta || '')
      }

    } else if (type === 'auto_compact_done') {
      const last = _lastAssistant()
      if (last) {
        const ac = last.blocks[last.blocks.length - 1]
        if (ac?.type === 'auto_compact') {
          ac.compactStatus = 'done'
          if (data.content) ac.result = data.content
        }
      }
    }
  }

  // ---- 发送 ----
  function send(content: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    messages.value.push({ role: 'user', content, blocks: [] })
    ws.send(JSON.stringify({ type: 'send', content }))
  }

  // ---- 会话操作 ----
  function switchSession(sessionId: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    if (isStreaming.value) return
    messages.value = []
    ws.send(JSON.stringify({ type: 'switch_session', session_id: sessionId }))
  }

  function newSession() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    if (isStreaming.value) return
    messages.value = []
    isStreaming.value = false
    currentSessionId.value = null
    hasSession.value = false
    ws.send(JSON.stringify({ type: 'new_session' }))
  }

  function rewindToTurn(turn: number) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'rewind', turn }))
  }

  // ---- 从 transcript 重建历史消息 ----
  function rebuildFromTranscript(transcript: any[]): ChatMessage[] {
    const rebuilt: ChatMessage[] = []
    let curAssistant: ChatMessage | null = null

    for (const entry of transcript) {
      const et = entry.type as string

      // 用户消息 → 创建 user ChatMessage
      if (et === 'user_message') {
        curAssistant = null
        rebuilt.push({ role: 'user', content: entry.content || '', blocks: [] })
        continue
      }

      // 状态事件 → 作为 block 插入当前 assistant 消息
      if (et === 'micro_compact') {
        if (curAssistant) curAssistant.blocks.push({ type: 'micro_compact', content: entry.content || '' })
        continue
      }

      if (et === 'inbox_message') {
        if (curAssistant) curAssistant.blocks.push({ type: 'inbox_message', content: entry.content || '' })
        continue
      }

      if (et === 'background_notification') {
        if (curAssistant) curAssistant.blocks.push({ type: 'background_notification', content: entry.content || '' })
        continue
      }

      if (et === 'todo_reminder') {
        if (curAssistant) curAssistant.blocks.push({ type: 'todo_reminder', content: entry.content || '' })
        continue
      }

      if (et === 'auto_compact_start') {
        if (curAssistant) curAssistant.blocks.push({ type: 'auto_compact', content: entry.content || '', thinking: '', summary: '', compactStatus: 'running' })
        continue
      }

      if (et === 'auto_compact_thinking') {
        if (curAssistant) {
          const ac = curAssistant.blocks[curAssistant.blocks.length - 1]
          if (ac?.type === 'auto_compact') ac.thinking += (entry.content || '')
        }
        continue
      }

      if (et === 'auto_compact_text') {
        if (curAssistant) {
          const ac = curAssistant.blocks[curAssistant.blocks.length - 1]
          if (ac?.type === 'auto_compact') ac.summary += (entry.content || '')
        }
        continue
      }

      if (et === 'auto_compact_done') {
        if (curAssistant) {
          const ac = curAssistant.blocks[curAssistant.blocks.length - 1]
          if (ac?.type === 'auto_compact') {
            ac.compactStatus = 'done'
            if (entry.content) ac.result = entry.content
          }
        }
        continue
      }

      // 上下文入口 / 统计信息 → 跳过
      if (et === 'context_entry' || et === 'token_usage' || et === 'context_patch') {
        continue
      }

      // thought / text / tool_start → 需要 assistant 容器
      if (et === 'thinking' || et === 'text' || et === 'tool_start') {
        if (!curAssistant) {
          curAssistant = { role: 'assistant', content: '', blocks: [] }
          rebuilt.push(curAssistant)
        }

        if (et === 'thinking') {
          curAssistant.blocks.push({
            type: 'thinking',
            content: entry.content || '',
            active: false, // 历史思考默认折叠
          })
        } else if (et === 'text') {
          curAssistant.blocks.push({
            type: 'text',
            content: entry.content || '',
          })
        } else if (et === 'tool_start') {
          curAssistant.blocks.push({
            type: 'tool',
            id: entry.tool_id || '',
            name: entry.tool_name || '',
            input: entry.tool_input ?? {},
            status: 'running',
          })
        }
        continue
      }

      // tool_result → 更新匹配的 tool block
      if (et === 'tool_result') {
        if (curAssistant) {
          // 逆序查找最后一个匹配的 tool block（同 tool_use_id 可能有多个 subagent 调用）
          let idx = -1
          for (let i = curAssistant.blocks.length - 1; i >= 0; i--) {
            const b = curAssistant.blocks[i]
            if (b.type === 'tool' && b.id === entry.tool_id) {
              idx = i
              break
            }
          }
          if (idx !== -1) {
            const block = curAssistant.blocks[idx] as Extract<MessageBlock, { type: 'tool' }>
            curAssistant.blocks.splice(idx, 1, {
              ...block,
              status: 'done',
              result: entry.content || '',
            })
          }
        }
        continue
      }

      // assistant_done → 折叠全部 thinking
      if (et === 'assistant_done') {
        if (curAssistant) {
          for (const b of curAssistant.blocks) {
            if (b.type === 'thinking') b.active = false
          }
        }
        curAssistant = null
        continue
      }

      // error → 追加文本块
      if (et === 'error') {
        if (!curAssistant) {
          curAssistant = { role: 'assistant', content: '', blocks: [] }
          rebuilt.push(curAssistant)
        }
        curAssistant.blocks.push({
          type: 'text',
          content: `\n❌ ${entry.error_msg || entry.content || '未知错误'}`,
        })
        continue
      }

      // sub_panel_enter / sub_panel_exit / background_notification / todo_reminder / auto_compact_* → 忽略
    }

    return rebuilt
  }

  return { messages, isStreaming, wsStatus, sessions, currentSessionId, hasSession, connect, send, switchSession, newSession, rewindToTurn }
}
