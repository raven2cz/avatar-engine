/**
 * TypeScript types mirroring avatar_engine/events.py + web/protocol.py
 */

// Engine state (mirrors EngineState enum)
export type EngineState = 'idle' | 'thinking' | 'responding' | 'tool_executing' | 'waiting_approval' | 'error'

// Thinking phase (mirrors ThinkingPhase enum)
export type ThinkingPhase = 'general' | 'analyzing' | 'planning' | 'coding' | 'reviewing' | 'tool_planning'

// Activity status
export type ActivityStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

// Bridge state
export type BridgeState = 'disconnected' | 'warming_up' | 'ready' | 'busy' | 'error'

// Provider capabilities
export interface ProviderCapabilities {
  can_list_sessions: boolean
  can_load_session: boolean
  can_continue_last: boolean
  thinking_supported: boolean
  thinking_structured: boolean
  cost_tracking: boolean
  budget_enforcement: boolean
  system_prompt_method: string
  streaming: boolean
  parallel_tools: boolean
  cancellable: boolean
  mcp_supported: boolean
}

// === Server → Client messages ===

export interface ConnectedMessage {
  type: 'connected'
  data: {
    session_id: string | null
    provider: string
    capabilities: ProviderCapabilities
    engine_state: EngineState
  }
}

export interface TextMessage {
  type: 'text'
  data: {
    text: string
    is_complete: boolean
    timestamp: number
    provider: string
  }
}

export interface ThinkingMessage {
  type: 'thinking'
  data: {
    thought: string
    phase: ThinkingPhase
    subject: string
    is_start: boolean
    is_complete: boolean
    block_id: string
    token_count: number
    category: string
    timestamp: number
    provider: string
  }
}

export interface ToolMessage {
  type: 'tool'
  data: {
    tool_name: string
    tool_id: string
    parameters: Record<string, unknown>
    status: 'started' | 'completed' | 'failed'
    result: string | null
    error: string | null
    timestamp: number
    provider: string
  }
}

export interface StateMessage {
  type: 'state'
  data: {
    old_state: BridgeState | null
    new_state: BridgeState | null
    timestamp: number
    provider: string
  }
}

export interface EngineStateMessage {
  type: 'engine_state'
  data: {
    state: EngineState
  }
}

export interface CostMessage {
  type: 'cost'
  data: {
    cost_usd: number
    input_tokens: number
    output_tokens: number
    timestamp: number
    provider: string
  }
}

export interface ErrorMessage {
  type: 'error'
  data: {
    error: string
    recoverable?: boolean
    timestamp?: number
    provider?: string
  }
}

export interface DiagnosticMessage {
  type: 'diagnostic'
  data: {
    message: string
    level: string
    source: string
    timestamp: number
    provider: string
  }
}

export interface ActivityMessage {
  type: 'activity'
  data: {
    activity_id: string
    parent_activity_id: string
    activity_type: string
    name: string
    status: ActivityStatus
    progress: number
    detail: string
    concurrent_group: string
    is_cancellable: boolean
    started_at: number
    completed_at: number
    timestamp: number
    provider: string
  }
}

export interface ChatResponseMessage {
  type: 'chat_response'
  data: {
    content: string
    success: boolean
    error: string | null
    duration_ms: number
    session_id: string | null
    cost_usd: number | null
    tool_calls: unknown[]
  }
}

export interface PongMessage {
  type: 'pong'
  data: { ts: number }
}

export interface HistoryClearedMessage {
  type: 'history_cleared'
  data: Record<string, never>
}

export type ServerMessage =
  | ConnectedMessage
  | TextMessage
  | ThinkingMessage
  | ToolMessage
  | StateMessage
  | EngineStateMessage
  | CostMessage
  | ErrorMessage
  | DiagnosticMessage
  | ActivityMessage
  | ChatResponseMessage
  | PongMessage
  | HistoryClearedMessage

// === Client → Server messages ===

export interface ChatRequest {
  type: 'chat'
  data: { message: string }
}

export interface StopRequest {
  type: 'stop'
  data: Record<string, never>
}

export interface PingRequest {
  type: 'ping'
  data: Record<string, never>
}

export interface ClearHistoryRequest {
  type: 'clear_history'
  data: Record<string, never>
}

export type ClientMessage = ChatRequest | StopRequest | PingRequest | ClearHistoryRequest

// === UI State ===

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  tools: ToolInfo[]
  thinking?: ThinkingInfo
  isStreaming: boolean
  durationMs?: number
  costUsd?: number
}

export interface ToolInfo {
  toolId: string
  name: string
  status: 'started' | 'completed' | 'failed'
  params: string
  error?: string
  startedAt: number
  completedAt?: number
}

export interface ThinkingInfo {
  phase: ThinkingPhase
  subject: string
  startedAt: number
  isComplete: boolean
}

export interface CostInfo {
  totalCostUsd: number
  totalInputTokens: number
  totalOutputTokens: number
}
