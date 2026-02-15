import { useCallback, useEffect, useReducer, useRef } from 'react'
import {
  avatarReducer,
  initialAvatarState,
} from '@avatar-engine/core'
import type {
  AvatarState,
  ServerMessage,
  ChatAttachment,
} from '@avatar-engine/core'

export interface UseAvatarWebSocketReturn {
  state: AvatarState
  sendMessage: (message: string, attachments?: ChatAttachment[]) => void
  stopResponse: () => void
  clearHistory: () => void
  switchProvider: (provider: string, model?: string, options?: Record<string, unknown>) => void
  resumeSession: (sessionId: string) => void
  newSession: () => void
  sendPermissionResponse: (requestId: string, optionId: string, cancelled: boolean) => void
  onServerMessage: (handler: (msg: ServerMessage) => void) => () => void
}

export function useAvatarWebSocket(url: string): UseAvatarWebSocketReturn {
  const [state, dispatch] = useReducer(avatarReducer, initialAvatarState)
  const wsRef = useRef<WebSocket | null>(null)
  const handlerRef = useRef<((msg: ServerMessage) => void) | null>(null)
  const reconnectTimeoutRef = useRef<number>()
  const unmountedRef = useRef(false)
  const errorFenceRef = useRef(false)

  const connect = useCallback(() => {
    if (unmountedRef.current) return

    const current = wsRef.current
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) {
      return
    }

    if (current && current.readyState !== WebSocket.CLOSED) {
      current.onclose = null
      current.close()
    }

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      // Connection established — wait for 'connected' message
    }

    ws.onmessage = (event) => {
      if (ws !== wsRef.current) return
      try {
        const msg = JSON.parse(event.data) as ServerMessage

        const fenced = errorFenceRef.current
        if (fenced) {
          if (['engine_state', 'thinking', 'text', 'tool', 'chat_response'].includes(msg.type)) {
            if (msg.type === 'chat_response') {
              errorFenceRef.current = false
              dispatch({ type: 'ENGINE_STATE', state: 'idle' })
              dispatch({ type: 'THINKING_END' })
            }
            handlerRef.current?.(msg)
            return
          }
        }

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
          case 'tool':
            dispatch({
              type: 'TOOL',
              toolName: msg.data.tool_name || '',
              status: msg.data.status || 'started',
            })
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
            dispatch({ type: 'ENGINE_STATE', state: 'idle' })
            dispatch({ type: 'THINKING_END' })
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
            if (msg.data.message) {
              dispatch({ type: 'DIAGNOSTIC', message: msg.data.message, level: msg.data.level || 'info' })
            }
            break
          case 'chat_response':
            if (msg.data.session_id) {
              dispatch({ type: 'SESSION_ID_DISCOVERED', sessionId: msg.data.session_id })
            }
            if (msg.data.error) {
              dispatch({ type: 'ERROR', error: msg.data.error })
              errorFenceRef.current = true
            }
            dispatch({ type: 'ENGINE_STATE', state: 'idle' })
            dispatch({ type: 'THINKING_END' })
            break
        }
        handlerRef.current?.(msg)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      if (ws !== wsRef.current) return
      dispatch({ type: 'DISCONNECTED' })
      if (!unmountedRef.current) {
        reconnectTimeoutRef.current = window.setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => {
      // Handled by onclose
    }
  }, [url])

  useEffect(() => {
    unmountedRef.current = false
    connect()
    return () => {
      unmountedRef.current = true
      clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((message: string, attachments?: ChatAttachment[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
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

  const sendPermissionResponse = useCallback((requestId: string, optionId: string, cancelled: boolean) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'permission_response',
        data: { request_id: requestId, option_id: optionId, cancelled },
      }))
    }
  }, [])

  const onServerMessage = useCallback((handler: (msg: ServerMessage) => void) => {
    handlerRef.current = handler
    return () => { handlerRef.current = null }
  }, [])

  return { state, sendMessage, stopResponse, clearHistory, switchProvider, resumeSession, newSession, sendPermissionResponse, onServerMessage }
}
