import { useCallback, useEffect, useReducer, useRef } from 'react'
import type {
  ServerMessage,
  EngineState,
  ProviderCapabilities,
  CostInfo,
  ThinkingPhase,
} from '../api/types'

interface AvatarWSState {
  connected: boolean
  sessionId: string | null
  provider: string
  capabilities: ProviderCapabilities | null
  engineState: EngineState
  thinking: {
    active: boolean
    phase: ThinkingPhase
    subject: string
    startedAt: number
  }
  cost: CostInfo
  error: string | null
}

type Action =
  | { type: 'CONNECTED'; payload: ServerMessage & { type: 'connected' } }
  | { type: 'DISCONNECTED' }
  | { type: 'ENGINE_STATE'; state: EngineState }
  | { type: 'THINKING_START'; phase: ThinkingPhase; subject: string }
  | { type: 'THINKING_UPDATE'; phase: ThinkingPhase; subject: string }
  | { type: 'THINKING_END' }
  | { type: 'COST'; costUsd: number; inputTokens: number; outputTokens: number }
  | { type: 'ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }

const initialState: AvatarWSState = {
  connected: false,
  sessionId: null,
  provider: '',
  capabilities: null,
  engineState: 'idle',
  thinking: { active: false, phase: 'general', subject: '', startedAt: 0 },
  cost: { totalCostUsd: 0, totalInputTokens: 0, totalOutputTokens: 0 },
  error: null,
}

function reducer(state: AvatarWSState, action: Action): AvatarWSState {
  switch (action.type) {
    case 'CONNECTED':
      return {
        ...state,
        connected: true,
        sessionId: action.payload.data.session_id,
        provider: action.payload.data.provider,
        capabilities: action.payload.data.capabilities,
        engineState: action.payload.data.engine_state,
        error: null,
      }
    case 'DISCONNECTED':
      return { ...state, connected: false, engineState: 'idle' }
    case 'ENGINE_STATE':
      return { ...state, engineState: action.state }
    case 'THINKING_START':
      return {
        ...state,
        thinking: {
          active: true,
          phase: action.phase,
          subject: action.subject,
          startedAt: Date.now(),
        },
      }
    case 'THINKING_UPDATE':
      return {
        ...state,
        thinking: {
          ...state.thinking,
          phase: action.phase,
          subject: action.subject || state.thinking.subject,
        },
      }
    case 'THINKING_END':
      return {
        ...state,
        thinking: { active: false, phase: 'general', subject: '', startedAt: 0 },
      }
    case 'COST':
      return {
        ...state,
        cost: {
          totalCostUsd: state.cost.totalCostUsd + action.costUsd,
          totalInputTokens: state.cost.totalInputTokens + action.inputTokens,
          totalOutputTokens: state.cost.totalOutputTokens + action.outputTokens,
        },
      }
    case 'ERROR':
      return { ...state, error: action.error }
    case 'CLEAR_ERROR':
      return { ...state, error: null }
    default:
      return state
  }
}

export interface UseAvatarWebSocketReturn {
  state: AvatarWSState
  sendMessage: (message: string) => void
  clearHistory: () => void
  onServerMessage: (handler: (msg: ServerMessage) => void) => () => void
}

export function useAvatarWebSocket(url: string): UseAvatarWebSocketReturn {
  const [state, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<WebSocket | null>(null)
  const handlerRef = useRef<((msg: ServerMessage) => void) | null>(null)
  const reconnectTimeoutRef = useRef<number>()
  const unmountedRef = useRef(false)

  const connect = useCallback(() => {
    // Don't connect after unmount (prevents StrictMode zombie reconnects)
    if (unmountedRef.current) return

    // Don't create another if already open or still connecting
    const current = wsRef.current
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) {
      return
    }

    // Close any lingering connection in CLOSING state
    if (current && current.readyState !== WebSocket.CLOSED) {
      current.onclose = null  // prevent its onclose from scheduling reconnect
      current.close()
    }

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      // Connection established — wait for 'connected' message
    }

    ws.onmessage = (event) => {
      // Only process messages from the current WebSocket
      if (ws !== wsRef.current) return
      try {
        const msg = JSON.parse(event.data) as ServerMessage
        // Dispatch state updates based on message type
        switch (msg.type) {
          case 'connected':
            dispatch({ type: 'CONNECTED', payload: msg })
            break
          case 'engine_state':
            dispatch({ type: 'ENGINE_STATE', state: msg.data.state })
            break
          case 'thinking':
            if (msg.data.is_complete) {
              dispatch({ type: 'THINKING_END' })
            } else if (msg.data.is_start) {
              dispatch({
                type: 'THINKING_START',
                phase: msg.data.phase,
                subject: msg.data.subject,
              })
            } else {
              dispatch({
                type: 'THINKING_UPDATE',
                phase: msg.data.phase,
                subject: msg.data.subject,
              })
            }
            break
          case 'cost':
            dispatch({
              type: 'COST',
              costUsd: msg.data.cost_usd,
              inputTokens: msg.data.input_tokens,
              outputTokens: msg.data.output_tokens,
            })
            break
          case 'error':
            dispatch({ type: 'ERROR', error: msg.data.error })
            break
        }
        // Notify registered handler
        handlerRef.current?.(msg)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      // Only handle close for the current WebSocket
      if (ws !== wsRef.current) return
      dispatch({ type: 'DISCONNECTED' })
      // Auto-reconnect after 3s (unless unmounted)
      if (!unmountedRef.current) {
        reconnectTimeoutRef.current = window.setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => {
      dispatch({ type: 'ERROR', error: 'WebSocket connection failed' })
    }
  }, [url])

  useEffect(() => {
    unmountedRef.current = false
    connect()
    return () => {
      unmountedRef.current = true
      clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) {
        wsRef.current.onclose = null  // prevent reconnect from cleanup close
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'chat', data: { message } }))
    }
  }, [])

  const clearHistory = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'clear_history', data: {} }))
    }
  }, [])

  const onServerMessage = useCallback((handler: (msg: ServerMessage) => void) => {
    handlerRef.current = handler
    return () => { handlerRef.current = null }
  }, [])

  return { state, sendMessage, clearHistory, onServerMessage }
}
