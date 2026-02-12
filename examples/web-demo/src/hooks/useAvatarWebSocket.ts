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
  wasConnected: boolean
  sessionId: string | null
  sessionTitle: string | null
  provider: string
  model: string | null
  version: string
  cwd: string
  capabilities: ProviderCapabilities | null
  engineState: EngineState
  initDetail: string
  switching: boolean
  thinking: {
    active: boolean
    phase: ThinkingPhase
    subject: string
    startedAt: number
  }
  cost: CostInfo
  error: string | null
  diagnostic: string | null
}

type Action =
  | { type: 'CONNECTED'; payload: ServerMessage & { type: 'connected' } }
  | { type: 'DISCONNECTED' }
  | { type: 'ENGINE_STATE'; state: EngineState }
  | { type: 'INITIALIZING'; payload: ServerMessage & { type: 'initializing' } }
  | { type: 'STATE_UPDATE'; detail: string; state: string }
  | { type: 'THINKING_START'; phase: ThinkingPhase; subject: string }
  | { type: 'THINKING_UPDATE'; phase: ThinkingPhase; subject: string }
  | { type: 'THINKING_END' }
  | { type: 'COST'; costUsd: number; inputTokens: number; outputTokens: number }
  | { type: 'ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'SWITCHING' }
  | { type: 'SESSION_TITLE_UPDATED'; sessionId: string; title: string | null; isCurrentSession: boolean }
  | { type: 'SESSION_ID_DISCOVERED'; sessionId: string }
  | { type: 'DIAGNOSTIC'; message: string; level: string }

const initialState: AvatarWSState = {
  connected: false,
  wasConnected: false,
  sessionId: null,
  sessionTitle: null,
  provider: '',
  model: null,
  version: '',
  cwd: '',
  capabilities: null,
  engineState: 'idle',
  initDetail: '',
  switching: false,
  thinking: { active: false, phase: 'general', subject: '', startedAt: 0 },
  cost: { totalCostUsd: 0, totalInputTokens: 0, totalOutputTokens: 0 },
  error: null,
  diagnostic: null,
}

function reducer(state: AvatarWSState, action: Action): AvatarWSState {
  switch (action.type) {
    case 'CONNECTED':
      return {
        ...state,
        connected: true,
        wasConnected: true,
        switching: false,
        initDetail: '',
        sessionId: action.payload.data.session_id,
        sessionTitle: action.payload.data.session_title || null,
        provider: action.payload.data.provider,
        model: action.payload.data.model || null,
        version: action.payload.data.version || '',
        cwd: action.payload.data.cwd || '',
        capabilities: action.payload.data.capabilities,
        engineState: action.payload.data.engine_state,
        error: null,
      }
    case 'INITIALIZING':
      return {
        ...state,
        connected: false,
        initDetail: action.payload.data.detail || '',
        provider: action.payload.data.provider || state.provider,
      }
    case 'STATE_UPDATE':
      return {
        ...state,
        initDetail: action.detail || state.initDetail,
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
    case 'DIAGNOSTIC':
      return { ...state, diagnostic: action.message || null }
    case 'SWITCHING':
      return { ...state, switching: true }
    case 'SESSION_TITLE_UPDATED':
      // Use server-provided is_current_session flag to avoid ID format mismatch
      if (action.isCurrentSession) {
        return { ...state, sessionTitle: action.title }
      }
      return state
    case 'SESSION_ID_DISCOVERED':
      // Backfill session ID from first chat_response (oneshot providers
      // don't emit session_id on startup, only after the first exchange)
      if (!state.sessionId) {
        return { ...state, sessionId: action.sessionId }
      }
      return state
    default:
      return state
  }
}

export interface UseAvatarWebSocketReturn {
  state: AvatarWSState
  sendMessage: (message: string, attachments?: import('../api/types').ChatAttachment[]) => void
  stopResponse: () => void
  clearHistory: () => void
  switchProvider: (provider: string, model?: string, options?: Record<string, unknown>) => void
  resumeSession: (sessionId: string) => void
  newSession: () => void
  onServerMessage: (handler: (msg: ServerMessage) => void) => () => void
}

export function useAvatarWebSocket(url: string): UseAvatarWebSocketReturn {
  const [state, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<WebSocket | null>(null)
  const handlerRef = useRef<((msg: ServerMessage) => void) | null>(null)
  const reconnectTimeoutRef = useRef<number>()
  const unmountedRef = useRef(false)
  // Error fence: when true, ignore engine_state/thinking/text/tool events
  // from a stale (timed-out) request. Cleared on next sendMessage.
  const errorFenceRef = useRef(false)

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

        // Error fence: after an error/timeout, ignore stale events from
        // the old request that the engine is still processing. The fence
        // is cleared when the user sends a new message.
        const fenced = errorFenceRef.current
        if (fenced) {
          // Let through: connected, initializing, state, session_title_updated,
          // error (could be a new error), cost (harmless). Block everything
          // that would change engine state or bust animation.
          if (['engine_state', 'thinking', 'text', 'tool', 'chat_response'].includes(msg.type)) {
            // Still reset to idle if this is chat_response (cleanup)
            if (msg.type === 'chat_response') {
              errorFenceRef.current = false
              dispatch({ type: 'ENGINE_STATE', state: 'idle' })
              dispatch({ type: 'THINKING_END' })
            }
            // Pass to handler so useAvatarChat can ignore gracefully
            handlerRef.current?.(msg)
            return
          }
        }

        // Dispatch state updates based on message type
        switch (msg.type) {
          case 'connected':
            errorFenceRef.current = false
            dispatch({ type: 'CONNECTED', payload: msg })
            break
          case 'initializing':
            dispatch({ type: 'INITIALIZING', payload: msg })
            break
          case 'state':
            if (msg.data.detail) {
              dispatch({ type: 'STATE_UPDATE', detail: msg.data.detail, state: msg.data.new_state || '' })
            }
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
            // Defensive: reset to idle on error (same as chat_response)
            dispatch({ type: 'ENGINE_STATE', state: 'idle' })
            dispatch({ type: 'THINKING_END' })
            // Activate error fence: ignore stale events from the old
            // request until the user sends a new message or reconnects.
            errorFenceRef.current = true
            break
          case 'session_title_updated':
            dispatch({
              type: 'SESSION_TITLE_UPDATED',
              sessionId: msg.data.session_id,
              title: msg.data.title,
              isCurrentSession: !!msg.data.is_current_session,
            })
            break
          case 'diagnostic':
            // Surface CLI diagnostics (stderr, ACP errors) to the user
            if (msg.data.message) {
              dispatch({ type: 'DIAGNOSTIC', message: msg.data.message, level: msg.data.level || 'info' })
            }
            break
          case 'chat_response':
            // Backfill session ID for oneshot providers that don't emit it on startup
            if (msg.data.session_id) {
              dispatch({ type: 'SESSION_ID_DISCOVERED', sessionId: msg.data.session_id })
            }
            // Defensive: ensure engine state returns to idle when response completes.
            dispatch({ type: 'ENGINE_STATE', state: 'idle' })
            dispatch({ type: 'THINKING_END' })
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
      // Only show error if we had a previous connection — initial connect
      // failures are handled gracefully as "Connecting..." state
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

  const sendMessage = useCallback((message: string, attachments?: import('../api/types').ChatAttachment[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Clear error fence + stale diagnostic — user is starting a new request
      errorFenceRef.current = false
      dispatch({ type: 'CLEAR_ERROR' })
      dispatch({ type: 'DIAGNOSTIC', message: '', level: '' })
      const data: Record<string, unknown> = { message }
      if (attachments?.length) data.attachments = attachments
      wsRef.current.send(JSON.stringify({ type: 'chat', data }))
    }
  }, [])

  const stopResponse = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop', data: {} }))
    }
    // Immediately reset engine state on client side — the server may not
    // send engine_state:idle before the connection closes or times out.
    dispatch({ type: 'ENGINE_STATE', state: 'idle' })
    dispatch({ type: 'THINKING_END' })
  }, [])

  const clearHistory = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'clear_history', data: {} }))
    }
  }, [])

  const switchProvider = useCallback((provider: string, model?: string, options?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      dispatch({ type: 'SWITCHING' })
      wsRef.current.send(JSON.stringify({
        type: 'switch',
        data: { provider, model: model || undefined, options: options || undefined },
      }))
    }
  }, [])

  const resumeSession = useCallback((sessionId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      dispatch({ type: 'SWITCHING' })
      wsRef.current.send(JSON.stringify({
        type: 'resume_session',
        data: { session_id: sessionId },
      }))
    }
  }, [])

  const newSession = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      dispatch({ type: 'SWITCHING' })
      wsRef.current.send(JSON.stringify({
        type: 'new_session',
        data: {},
      }))
    }
  }, [])

  const onServerMessage = useCallback((handler: (msg: ServerMessage) => void) => {
    handlerRef.current = handler
    return () => { handlerRef.current = null }
  }, [])

  return { state, sendMessage, stopResponse, clearHistory, switchProvider, resumeSession, newSession, onServerMessage }
}
