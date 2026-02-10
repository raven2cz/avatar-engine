import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChatAttachment, ChatMessage, ServerMessage, ToolInfo, UploadedFile } from '../api/types'
import { useAvatarWebSocket } from './useAvatarWebSocket'
import { useFileUpload } from './useFileUpload'
import { buildOptionsDict } from '../config/providers'

// REST API base — matches Vite proxy config
const API_BASE =
  import.meta.env.DEV
    ? `http://${window.location.hostname}:5173/api/avatar`
    : `/api/avatar`

export interface UseAvatarChatReturn {
  messages: ChatMessage[]
  sendMessage: (text: string, attachments?: UploadedFile[]) => void
  stopResponse: () => void
  clearHistory: () => void
  switchProvider: (provider: string, model?: string, options?: Record<string, string | number>) => void
  resumeSession: (sessionId: string) => void
  newSession: () => void
  activeOptions: Record<string, string | number>
  pendingFiles: UploadedFile[]
  uploading: boolean
  uploadFile: (file: File) => Promise<UploadedFile | null>
  removeFile: (fileId: string) => void
  isStreaming: boolean
  switching: boolean
  connected: boolean
  wasConnected: boolean
  initDetail: string
  sessionId: string | null
  sessionTitle: string | null
  provider: string
  model: string | null
  version: string
  cwd: string
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
  const { state, sendMessage: wsSend, clearHistory: wsClear, switchProvider: wsSwitch, resumeSession: wsResume, newSession: wsNew, onServerMessage, stopResponse: wsStop } =
    useAvatarWebSocket(wsUrl)
  const { pending: pendingFiles, uploading, upload: uploadFile, remove: removeFile, clear: clearFiles } =
    useFileUpload()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeOptions, setActiveOptions] = useState<Record<string, string | number>>({})
  const currentAssistantIdRef = useRef<string | null>(null)
  const chatTimeoutRef = useRef<number>()

  // Clear chat timeout when we receive any response-related event
  const resetChatTimeout = useCallback(() => {
    if (chatTimeoutRef.current) {
      clearTimeout(chatTimeoutRef.current)
      chatTimeoutRef.current = undefined
    }
  }, [])

  useEffect(() => {
    const cleanup = onServerMessage((msg: ServerMessage) => {
      switch (msg.type) {
        case 'text': {
          resetChatTimeout()
          // Accumulate text into current assistant message
          // Capture ref outside updater to avoid React 18 batching race
          const textId = currentAssistantIdRef.current
          if (!textId) break
          setMessages((prev) =>
            prev.map((m) =>
              m.id === textId
                ? {
                    ...m,
                    content: m.content + msg.data.text,
                    thinking: m.thinking ? { ...m.thinking, isComplete: true } : undefined,
                  }
                : m
            )
          )
          break
        }

        case 'thinking': {
          resetChatTimeout()
          if (msg.data.is_complete) break
          const thinkId = currentAssistantIdRef.current
          if (!thinkId) break
          setMessages((prev) =>
            prev.map((m) =>
              m.id === thinkId
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
          )
          break
        }

        case 'tool': {
          resetChatTimeout()
          const toolId = currentAssistantIdRef.current
          if (!toolId) break
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== toolId) return m
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
          )
          break
        }

        case 'chat_response': {
          resetChatTimeout()
          // Capture ref BEFORE clearing — React 18 batching defers updaters
          const responseId = currentAssistantIdRef.current
          currentAssistantIdRef.current = null
          setIsStreaming(false)
          if (!responseId) break
          setMessages((prev) =>
            prev.map((m) =>
              m.id === responseId
                ? {
                    ...m,
                    content: m.content || msg.data.content || (msg.data.error ? `Error: ${msg.data.error}` : ''),
                    isStreaming: false,
                    durationMs: msg.data.duration_ms,
                    costUsd: msg.data.cost_usd || undefined,
                    thinking: m.thinking ? { ...m.thinking, isComplete: true } : undefined,
                    images: msg.data.images,
                  }
                : m
            )
          )
          break
        }

        case 'error': {
          resetChatTimeout()
          const errorId = currentAssistantIdRef.current
          if (errorId) {
            currentAssistantIdRef.current = null
            setIsStreaming(false)
            setMessages((prev) =>
              prev.map((m) =>
                m.id === errorId
                  ? { ...m, content: m.content || `Error: ${msg.data.error}`, isStreaming: false }
                  : m
              )
            )
          }
          break
        }

        case 'history_cleared': {
          setMessages([])
          currentAssistantIdRef.current = null
          setIsStreaming(false)
          break
        }

        // (connected event handled by useAvatarWebSocket reducer)
      }
    })
    return cleanup
  }, [onServerMessage])

  const sendMessage = useCallback(
    (text: string, attachments?: UploadedFile[]) => {
      if (!text.trim() || isStreaming) return

      // Merge explicit attachments with pending files
      const allFiles = attachments?.length ? attachments : pendingFiles.length ? pendingFiles : undefined

      // Add user message
      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        tools: [],
        isStreaming: false,
        attachments: allFiles,
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

      // Build attachments for WS message
      const wsAttachments: ChatAttachment[] | undefined = allFiles?.map((f) => ({
        file_id: f.fileId,
        filename: f.filename,
        mime_type: f.mimeType,
        path: f.path,
      }))
      wsSend(text, wsAttachments)
      clearFiles()

      // Timeout: if no response event arrives, show error.
      // Dynamic: base 30s + 3s per MB of attachments (large files need more time)
      resetChatTimeout()
      let clientTimeout = 30_000
      if (allFiles?.length) {
        const totalMb = allFiles.reduce((sum, f) => sum + f.size, 0) / (1024 * 1024)
        clientTimeout += Math.round(totalMb * 3_000) // +3s per MB
      }
      chatTimeoutRef.current = window.setTimeout(() => {
        const id = currentAssistantIdRef.current
        if (id) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === id
                ? { ...m, content: m.content || 'No response from engine — request may have timed out.', isStreaming: false }
                : m
            )
          )
          currentAssistantIdRef.current = null
          setIsStreaming(false)
        }
      }, clientTimeout)
    },
    [wsSend, isStreaming, resetChatTimeout, pendingFiles, clearFiles]
  )

  const clearHistory = useCallback(() => {
    wsClear()
    setMessages([])
    currentAssistantIdRef.current = null
    setIsStreaming(false)
  }, [wsClear])

  const switchProvider = useCallback((provider: string, model?: string, flatOptions?: Record<string, string | number>) => {
    setMessages([])
    currentAssistantIdRef.current = null
    setIsStreaming(false)
    setActiveOptions(flatOptions && Object.keys(flatOptions).length > 0 ? flatOptions : {})
    const builtOptions = flatOptions && Object.keys(flatOptions).length > 0
      ? buildOptionsDict(provider, flatOptions)
      : undefined
    wsSwitch(provider, model, builtOptions)
  }, [wsSwitch])

  const resumeSession = useCallback((sessionId: string) => {
    currentAssistantIdRef.current = null
    setIsStreaming(false)
    setActiveOptions({})
    wsResume(sessionId)

    // Fetch session history immediately from REST API (works even during
    // engine restart — the endpoint only needs provider name + working dir)
    fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages`)
      .then((r) => r.json())
      .then((data: Array<{ role: string; content: string }>) => {
        if (!data || !data.length) {
          setMessages([])
          return
        }
        const historyMessages: ChatMessage[] = data.map((m, i) => ({
          id: `history-${i}-${Date.now()}`,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          timestamp: Date.now() - (data.length - i) * 1000,
          tools: [],
          isStreaming: false,
        }))
        setMessages(historyMessages)
      })
      .catch(() => {
        setMessages([])
      })
  }, [wsResume])

  const newSession = useCallback(() => {
    setMessages([])
    currentAssistantIdRef.current = null
    setIsStreaming(false)
    setActiveOptions({})
    wsNew()
  }, [wsNew])

  const stopResponse = useCallback(() => {
    wsStop()
    resetChatTimeout()
    // Immediately mark streaming as done in UI
    if (currentAssistantIdRef.current) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === currentAssistantIdRef.current
            ? { ...m, isStreaming: false, content: m.content || '[Stopped]' }
            : m
        )
      )
      currentAssistantIdRef.current = null
      setIsStreaming(false)
    }
  }, [wsStop, resetChatTimeout])

  return {
    messages,
    sendMessage,
    stopResponse,
    clearHistory,
    switchProvider,
    resumeSession,
    newSession,
    activeOptions,
    pendingFiles,
    uploading,
    uploadFile,
    removeFile,
    isStreaming,
    switching: state.switching,
    connected: state.connected,
    wasConnected: state.wasConnected,
    initDetail: state.initDetail,
    sessionId: state.sessionId,
    sessionTitle: state.sessionTitle
      || messages.find((m) => m.role === 'user')?.content?.slice(0, 80)
      || null,
    provider: state.provider,
    model: state.model,
    version: state.version,
    cwd: state.cwd,
    engineState: state.engineState,
    thinking: state.thinking,
    cost: state.cost,
    capabilities: state.capabilities,
    error: state.error,
  }
}
