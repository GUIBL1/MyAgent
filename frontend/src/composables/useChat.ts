import { ref, type Ref } from 'vue'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  blocks: MessageBlock[]
}

// ── Recall Memory 子面板数据结构 ──

export interface RecallQueryHit {
  id: string
  doc: string
  distance: number
  access_count: number
  duplicate?: boolean
}

export interface RecallQueryResult {
  query: string
  hit_count: number
  hits: RecallQueryHit[]
  error?: string
  active: boolean  // true while this query is being executed (result not yet received)
}

export interface RecallMemoryBlock {
  type: 'recall_memory'
  toolId: string
  active: boolean
  expand: {
    status: 'pending' | 'running' | 'done'
    thinking: string
    text: string
    variants: string[]
    count: number
  }
  retrieve: {
    status: 'pending' | 'running' | 'done'
    queries: RecallQueryResult[]
    total_candidates: number
  }
  rerank: {
    status: 'pending' | 'running' | 'done'
    thinking: string
    text: string
    ranked_ids: string[]
    top_k: number
    total: number
  }
  synth: {
    status: 'pending' | 'running' | 'done'
    thinking: string
    text: string
    fragments: { index: number; id: string; content: string }[]
    query: string
    result?: string
  }
}

function _emptyRecallBlock(toolId: string, active: boolean): RecallMemoryBlock {
  return {
    type: 'recall_memory', toolId, active,
    expand:  { status: 'pending', thinking: '', text: '', variants: [], count: 0 },
    retrieve:{ status: 'pending', queries: [], total_candidates: 0 },
    rerank:  { status: 'pending', thinking: '', text: '', ranked_ids: [], top_k: 0, total: 0 },
    synth:   { status: 'pending', thinking: '', text: '', fragments: [], query: '', result: undefined },
  }
}

// ── MessageBlock union ──

export type MessageBlock =
  | { type: 'text'; content: string }
  | { type: 'thinking'; content: string; active: boolean }
  | { type: 'tool'; id: string; name: string; input: Record<string, unknown>; status: 'running' | 'done'; result?: string }
  | RecallMemoryBlock
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

  // 子面板栈：支持嵌套（subagent 内调用 recall_memory 等场景）
  // 栈顶为当前可见的子面板；未来扩展其他 tool_name 时，在 .data 上做 union
  interface SubPanelEntry {
    toolId: string
    toolName: string
    data: RecallMemoryBlock  // 未来: RecallMemoryBlock | SubagentBlock | ...
  }
  const subPanelStack: Ref<SubPanelEntry[]> = ref([])

  let ws: WebSocket | null = null

  function _lastAssistant(): ChatMessage | undefined {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') return messages.value[i]
    }
    return undefined
  }

  function _lastRecallBlock(): RecallMemoryBlock | undefined {
    const last = _lastAssistant()
    if (!last) return undefined
    const b = last.blocks[last.blocks.length - 1]
    return b?.type === 'recall_memory' ? (b as RecallMemoryBlock) : undefined
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

  // ---- WebSocket 连接与断线重连 ----
  let _reconnectTimer: ReturnType<typeof setInterval> | null = null
  let _reconnectDeadline = 0           // 重连截止时间戳 (ms)
  const _reconnectInterval = 3000      // 固定重连间隔 3s
  const _reconnectWindow = 600_000     // 重连窗口 10min
  let _keepaliveTimer: ReturnType<typeof setInterval> | null = null

  function _startKeepalive() {
    _stopKeepalive()
    _keepaliveTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30_000)
  }

  function _stopKeepalive() {
    if (_keepaliveTimer) { clearInterval(_keepaliveTimer); _keepaliveTimer = null }
  }

  function _startReconnect() {
    if (_reconnectTimer) return  // 已在重连中
    _stopKeepalive()
    _reconnectDeadline = Date.now() + _reconnectWindow
    wsStatus.value = 'connecting'
    _reconnectTimer = setInterval(() => {
      if (Date.now() > _reconnectDeadline) {
        _stopReconnect()
        wsStatus.value = 'disconnected'
        return
      }
      _doConnect()
    }, _reconnectInterval)
    _doConnect() // 立即尝试第一次
  }

  function _stopReconnect() {
    if (_reconnectTimer) { clearInterval(_reconnectTimer); _reconnectTimer = null }
  }

  function _doConnect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws/chat`
    ws = new WebSocket(url)

    ws.onopen = () => {
      _stopReconnect()
      wsStatus.value = 'connected'
      _startKeepalive()
      // 重连成功后恢复会话状态
      if (currentSessionId.value) {
        ws!.send(JSON.stringify({ type: 'switch_session', session_id: currentSessionId.value }))
      }
    }
    ws.onclose = () => {
      if (!_reconnectTimer) _startReconnect()
    }
    ws.onerror = () => {
      // 不立即变 disconnected，让重连逻辑接管
    }
    ws.onmessage = (evt) => {
      handleEvent(JSON.parse(evt.data))
    }
  }

  function connect() {
    _reconnectDeadline = Date.now() + _reconnectWindow
    _doConnect()
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

    // === Recall Memory 子面板事件 ===

    } else if (type === 'sub_panel_enter') {
      if (data.tool_name === 'recall_memory' && data.tool_id) {
        const last = _lastAssistant()
        if (last) {
          const block = _emptyRecallBlock(data.tool_id, true)
          last.blocks.push(block)
          // 不自动展开子面板，等用户点击"查看详情"
        }
      }

    } else if (type === 'sub_panel_exit') {
      const rb = _lastRecallBlock()
      if (rb) rb.active = false
      // 不弹栈 — 用户通过"返回对话"按钮或点击空白区域手动退出子面板

    // ── Stage 1: Expand ──

    } else if (type === 'recall_expand_start') {
      const rb = _lastRecallBlock()
      if (rb) { rb.expand.status = 'running'; rb.expand.thinking = ''; rb.expand.text = '' }

    } else if (type === 'recall_expand_thinking') {
      const rb = _lastRecallBlock()
      if (rb) rb.expand.thinking += (data.delta || '')

    } else if (type === 'recall_expand_text') {
      const rb = _lastRecallBlock()
      if (rb) rb.expand.text += (data.delta || '')

    } else if (type === 'recall_expand_done') {
      const rb = _lastRecallBlock()
      if (rb) {
        rb.expand.status = 'done'
        try {
          const d = JSON.parse(data.content || '{}')
          rb.expand.variants = d.variants || []
          rb.expand.count = d.count || 0
        } catch { /* ignore parse error */ }
      }

    // ── Stage 2: Retrieve ──

    } else if (type === 'recall_query_start') {
      const rb = _lastRecallBlock()
      if (rb) {
        rb.retrieve.status = 'running'
        // 添加占位条目，卡片在结果到达前保持展开
        try {
          const d = JSON.parse(data.content || '{}')
          rb.retrieve.queries.push({ query: d.query || '', hit_count: 0, hits: [], active: true })
        } catch { /* ignore */ }
      }

    } else if (type === 'recall_query_result') {
      const rb = _lastRecallBlock()
      if (rb) {
        try {
          const d = JSON.parse(data.content || '{}')
          // 找到匹配的占位条目并填充
          const idx = rb.retrieve.queries.findIndex(q => q.query === (d.query || '') && q.active)
          const filled = {
            query: d.query || '',
            hit_count: d.hit_count || 0,
            hits: d.hits || [],
            error: d.error,
            active: false,
          }
          if (idx !== -1) {
            rb.retrieve.queries.splice(idx, 1, filled)
          } else {
            rb.retrieve.queries.push(filled)
          }
        } catch { /* ignore */ }
      }

    } else if (type === 'recall_retrieve_done') {
      const rb = _lastRecallBlock()
      if (rb) {
        rb.retrieve.status = 'done'
        try {
          const d = JSON.parse(data.content || '{}')
          rb.retrieve.total_candidates = d.total_candidates || 0
        } catch { /* ignore */ }
      }

    // ── Stage 3: Rerank ──

    } else if (type === 'recall_rerank_start') {
      const rb = _lastRecallBlock()
      if (rb) { rb.rerank.status = 'running'; rb.rerank.thinking = ''; rb.rerank.text = '' }

    } else if (type === 'recall_rerank_thinking') {
      const rb = _lastRecallBlock()
      if (rb) rb.rerank.thinking += (data.delta || '')

    } else if (type === 'recall_rerank_text') {
      const rb = _lastRecallBlock()
      if (rb) rb.rerank.text += (data.delta || '')

    } else if (type === 'recall_rerank_done') {
      const rb = _lastRecallBlock()
      if (rb) {
        rb.rerank.status = 'done'
        try {
          const d = JSON.parse(data.content || '{}')
          rb.rerank.ranked_ids = d.ranked_ids || []
          rb.rerank.top_k = d.top_k || 0
          rb.rerank.total = d.total || 0
        } catch { /* ignore */ }
      }

    // ── Stage 4: Synthesize ──

    } else if (type === 'recall_synth_start') {
      const rb = _lastRecallBlock()
      if (rb) { rb.synth.status = 'running'; rb.synth.thinking = ''; rb.synth.text = '' }

    } else if (type === 'recall_synth_input') {
      const rb = _lastRecallBlock()
      if (rb) {
        try {
          const d = JSON.parse(data.content || '{}')
          rb.synth.fragments = d.fragments || []
          rb.synth.query = d.query || ''
        } catch { /* ignore */ }
      }

    } else if (type === 'recall_synth_thinking') {
      const rb = _lastRecallBlock()
      if (rb) rb.synth.thinking += (data.delta || '')

    } else if (type === 'recall_synth_text') {
      const rb = _lastRecallBlock()
      if (rb) rb.synth.text += (data.delta || '')

    } else if (type === 'recall_synth_done') {
      const rb = _lastRecallBlock()
      if (rb) {
        rb.synth.status = 'done'
        rb.synth.result = data.content || ''
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

  // ---- Recall transcript replay helper ----
  function _applyRecallTranscript(rb: RecallMemoryBlock, entry: any) {
    const et = entry.type as string; const content = entry.content || ''
    // Stage 1
    if (et === 'recall_expand_start') { rb.expand.status = 'running' }
    else if (et === 'recall_expand_thinking') { rb.expand.thinking += content }
    else if (et === 'recall_expand_text') { rb.expand.text += content }
    else if (et === 'recall_expand_done') {
      rb.expand.status = 'done'; try { const d = JSON.parse(content); rb.expand.variants = d.variants || []; rb.expand.count = d.count || 0 } catch {}
    }
    // Stage 2
    else if (et === 'recall_query_start') {
      rb.retrieve.status = 'running'
      try { const d = JSON.parse(content); rb.retrieve.queries.push({ query: d.query || '', hit_count: 0, hits: [], active: true }) } catch {}
    }
    else if (et === 'recall_query_result') {
      try {
        const d = JSON.parse(content)
        const idx = rb.retrieve.queries.findIndex((q: any) => q.query === (d.query || '') && q.active)
        const filled = { query: d.query || '', hit_count: d.hit_count || 0, hits: d.hits || [], error: d.error, active: false }
        if (idx !== -1) { rb.retrieve.queries.splice(idx, 1, filled) }
        else { rb.retrieve.queries.push(filled) }
      } catch {}
    }
    else if (et === 'recall_retrieve_done') {
      rb.retrieve.status = 'done'; try { const d = JSON.parse(content); rb.retrieve.total_candidates = d.total_candidates || 0 } catch {}
    }
    // Stage 3
    else if (et === 'recall_rerank_start') { rb.rerank.status = 'running' }
    else if (et === 'recall_rerank_thinking') { rb.rerank.thinking += content }
    else if (et === 'recall_rerank_text') { rb.rerank.text += content }
    else if (et === 'recall_rerank_done') {
      rb.rerank.status = 'done'; try { const d = JSON.parse(content); rb.rerank.ranked_ids = d.ranked_ids || []; rb.rerank.top_k = d.top_k || 0; rb.rerank.total = d.total || 0 } catch {}
    }
    // Stage 4
    else if (et === 'recall_synth_start') { rb.synth.status = 'running' }
    else if (et === 'recall_synth_input') {
      try { const d = JSON.parse(content); rb.synth.fragments = d.fragments || []; rb.synth.query = d.query || '' } catch {}
    }
    else if (et === 'recall_synth_thinking') { rb.synth.thinking += content }
    else if (et === 'recall_synth_text') { rb.synth.text += content }
    else if (et === 'recall_synth_done') { rb.synth.status = 'done'; rb.synth.result = content }
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

      // sub_panel_enter → 创建 recall_memory block
      if (et === 'sub_panel_enter') {
        if (entry.tool_name === 'recall_memory' && entry.tool_id) {
          if (!curAssistant) { curAssistant = { role: 'assistant', content: '', blocks: [] }; rebuilt.push(curAssistant) }
          const block = _emptyRecallBlock(entry.tool_id, false)
          curAssistant.blocks.push(block)
        }
        continue
      }

      // Recall events → 追加到当前 recall_memory block
      if (et.startsWith('recall_')) {
        const rb = curAssistant?.blocks[curAssistant.blocks.length - 1]
        if (rb?.type !== 'recall_memory') continue
        _applyRecallTranscript(rb, entry)
        continue
      }

      // sub_panel_exit → 折叠 recall block
      if (et === 'sub_panel_exit') {
        const rb = curAssistant?.blocks[curAssistant.blocks.length - 1]
        if (rb?.type === 'recall_memory') rb.active = false
        continue
      }

      // sub_panel_enter / sub_panel_exit / background_notification / todo_reminder / auto_compact_* → 忽略
    }

    return rebuilt
  }

  return { messages, isStreaming, wsStatus, sessions, currentSessionId, hasSession, subPanelStack, connect, send, switchSession, newSession, rewindToTurn }
}
