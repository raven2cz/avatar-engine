import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChatMessage, ServerMessage, ToolInfo } from '../api/types'
import { useAvatarWebSocket } from './useAvatarWebSocket'

export interface UseAvatarChatReturn {
  messages: ChatMessage[]
  sendMessage: (text: string) => void
  clearHistory: () => void
  isStreaming: boolean
  connected: boolean
  provider: string
  engineState: string
  thinking: { active: boolean; phase: string; subject: string; startedAt: number }
  cost: { totalCostUsd: number; totalInputTokens: number; totalOutputTokens: number }
  capabilities: ReturnType<typeof useAvatarWebSocket>['state']['capabilities']
  error: string | null
}

let messageIdCounter = 0
function nextId(): string {
  return `msg-${++messageIdCounter}-${Date.now()}`
}

function summarizeParams(params: Record<string, unknown>): string {
  const keys = ['file_path', 'path', 'filename', 'command', 'query', 'pattern', 'url']
  for (const key of keys) {
    if (params[key]) {
      const val = String(params[key])
      return val.length > 60 ? val.slice(0, 57) + '...' : val
    }
  }
  for (const val of Object.values(params)) {
    if (typeof val === 'string' && val) {
      return val.length > 60 ? val.slice(0, 57) + '...' : val
    }
  }
  return ''
}

export function useAvatarChat(wsUrl: string): UseAvatarChatReturn {
  const { state, sendMessage: wsSend, clearHistory: wsClear, onServerMessage } =
    useAvatarWebSocket(wsUrl)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const currentAssistantIdRef = useRef<string | null>(null)

  useEffect(() => {
    const cleanup = onServerMessage((msg: ServerMessage) => {
      switch (msg.type) {
        case 'text': {
          // Accumulate text into current assistant message
          setMessages((prev) => {
            const id = currentAssistantIdRef.current
            if (!id) return prev
            return prev.map((m) =>
              m.id === id ? { ...m, content: m.content + msg.data.text } : m
            )
          })
          break
        }

        case 'thinking': {
          // Update thinking info on current assistant message
          if (msg.data.is_complete) break
          setMessages((prev) => {
            const id = currentAssistantIdRef.current
            if (!id) return prev
            return prev.map((m) =>
              m.id === id
                ? {
                    ...m,
                    thinking: {
                      phase: msg.data.phase,
                      subject: msg.data.subject || m.thinking?.subject || '',
                      startedAt: m.thinking?.startedAt || Date.now(),
                      isComplete: false,
                    },
                  }
                : m
            )
          })
          break
        }

        case 'tool': {
          setMessages((prev) => {
            const id = currentAssistantIdRef.current
            if (!id) return prev
            return prev.map((m) => {
              if (m.id !== id) return m
              const tools = [...m.tools]
              const existing = tools.findIndex(
                (t) => t.toolId === (msg.data.tool_id || msg.data.tool_name)
              )
              if (msg.data.status === 'started') {
                if (existing === -1) {
                  tools.push({
                    toolId: msg.data.tool_id || msg.data.tool_name,
                    name: msg.data.tool_name,
                    status: 'started',
                    params: summarizeParams(msg.data.parameters),
                    startedAt: Date.now(),
                  })
                }
              } else if (existing >= 0) {
                tools[existing] = {
                  ...tools[existing],
                  status: msg.data.status as ToolInfo['status'],
                  error: msg.data.error || undefined,
                  completedAt: Date.now(),
                }
              }
              return { ...m, tools }
            })
          })
          break
        }

        case 'chat_response': {
          // Mark current assistant message as complete
          setMessages((prev) => {
            const id = currentAssistantIdRef.current
            if (!id) return prev
            return prev.map((m) =>
              m.id === id
                ? {
                    ...m,
                    content: m.content || msg.data.content,
                    isStreaming: false,
                    durationMs: msg.data.duration_ms,
                    costUsd: msg.data.cost_usd || undefined,
                    thinking: m.thinking ? { ...m.thinking, isComplete: true } : undefined,
                  }
                : m
            )
          })
          currentAssistantIdRef.current = null
          setIsStreaming(false)
          break
        }

        case 'error': {
          // If streaming, add error to current message
          if (currentAssistantIdRef.current) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === currentAssistantIdRef.current
                  ? { ...m, content: m.content || `Error: ${msg.data.error}`, isStreaming: false }
                  : m
              )
            )
            currentAssistantIdRef.current = null
            setIsStreaming(false)
          }
          break
        }

        case 'history_cleared': {
          setMessages([])
          currentAssistantIdRef.current = null
          setIsStreaming(false)
          break
        }
      }
    })
    return cleanup
  }, [onServerMessage])

  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim() || isStreaming) return

      // Add user message
      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        tools: [],
        isStreaming: false,
      }

      // Create placeholder assistant message
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        tools: [],
        isStreaming: true,
      }
      currentAssistantIdRef.current = assistantMsg.id

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)
      wsSend(text)
    },
    [wsSend, isStreaming]
  )

  const clearHistory = useCallback(() => {
    wsClear()
    setMessages([])
    currentAssistantIdRef.current = null
    setIsStreaming(false)
  }, [wsClear])

  return {
    messages,
    sendMessage,
    clearHistory,
    isStreaming,
    connected: state.connected,
    provider: state.provider,
    engineState: state.engineState,
    thinking: state.thinking,
    cost: state.cost,
    capabilities: state.capabilities,
    error: state.error,
  }
}
