import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react'
import { useTranslation } from 'react-i18next'
import type {
  ChatAttachment,
  ChatMessage,
  SafetyMode,
  ServerMessage,
  ToolInfo,
  UploadedFile,
  PermissionRequest,
} from '@avatar-engine/core'
import { buildOptionsDict, isImageModel, nextId, summarizeParams } from '@avatar-engine/core'
import { useAvatarWebSocket } from './useAvatarWebSocket'
import { useFileUpload } from './useFileUpload'

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
  safetyMode: SafetyMode
  permissionRequest: PermissionRequest | null
  sendPermissionResponse: (requestId: string, optionId: string, cancelled: boolean) => void
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
  toolName: string | undefined
  error: string | null
  diagnostic: string | null
}

export function useAvatarChat(wsUrl: string, apiBase?: string): UseAvatarChatReturn {
  const { t } = useTranslation()

  // Derive REST API base — relative URL works with Vite proxy and production
  const resolvedApiBase = apiBase ?? '/api/avatar'

  const { state, sendMessage: wsSend, clearHistory: wsClear, switchProvider: wsSwitch, resumeSession: wsResume, newSession: wsNew, sendPermissionResponse: wsPermission, onServerMessage, stopResponse: wsStop } =
    useAvatarWebSocket(wsUrl)
  const { pending: pendingFiles, uploading, upload: uploadFile, remove: removeFile, clear: clearFiles } =
    useFileUpload(resolvedApiBase)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeOptions, setActiveOptions] = useState<Record<string, string | number>>({})
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequest | null>(null)
  const currentAssistantIdRef = useRef<string | null>(null)
  const resumeAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const cleanup = onServerMessage((msg: ServerMessage) => {
      switch (msg.type) {
        case 'text': {
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
          const responseId = currentAssistantIdRef.current
          currentAssistantIdRef.current = null
          setIsStreaming(false)
          setPermissionRequest(null)
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

        case 'permission_request': {
          setPermissionRequest({
            requestId: msg.data.request_id,
            toolName: msg.data.tool_name,
            toolInput: msg.data.tool_input,
            options: msg.data.options,
          })
          break
        }
      }
    })
    return cleanup
  }, [onServerMessage])

  const sendMessage = useCallback(
    (text: string, attachments?: UploadedFile[]) => {
      if (!text.trim() || isStreaming) return

      const allFiles = attachments?.length ? attachments : pendingFiles.length ? pendingFiles : undefined

      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        tools: [],
        isStreaming: false,
        attachments: allFiles,
      }

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

      const wsAttachments: ChatAttachment[] | undefined = allFiles?.map((f) => ({
        file_id: f.fileId,
        filename: f.filename,
        mime_type: f.mimeType,
        path: f.path,
      }))
      wsSend(text, wsAttachments)
      clearFiles()
    },
    [wsSend, isStreaming, pendingFiles, clearFiles]
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
    setPermissionRequest(null)
    setActiveOptions(flatOptions && Object.keys(flatOptions).length > 0 ? flatOptions : {})

    const safetyValue = flatOptions?.safety_mode
    const providerFlatOptions = flatOptions ? { ...flatOptions } : undefined
    if (providerFlatOptions) delete providerFlatOptions.safety_mode

    let builtOptions: Record<string, unknown> | undefined =
      providerFlatOptions && Object.keys(providerFlatOptions).length > 0
        ? buildOptionsDict(provider, providerFlatOptions)
        : undefined

    if (safetyValue !== undefined) {
      builtOptions = { ...(builtOptions ?? {}), safety_mode: safetyValue }
    }

    if (model && isImageModel(model)) {
      const genCfg = ((builtOptions?.generation_config ?? {}) as Record<string, unknown>)
      builtOptions = {
        ...(builtOptions ?? {}),
        generation_config: { ...genCfg, response_modalities: 'TEXT,IMAGE' },
      }
    }

    wsSwitch(provider, model, builtOptions)
  }, [wsSwitch])

  const resumeSession = useCallback((sessionId: string) => {
    // Abort any in-flight history fetch
    resumeAbortRef.current?.abort()
    const controller = new AbortController()
    resumeAbortRef.current = controller

    currentAssistantIdRef.current = null
    setIsStreaming(false)
    setActiveOptions({})
    wsResume(sessionId)

    fetch(`${resolvedApiBase}/sessions/${encodeURIComponent(sessionId)}/messages`, {
      signal: controller.signal,
    })
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
      .catch((e) => {
        if (e?.name !== 'AbortError') setMessages([])
      })
  }, [wsResume, resolvedApiBase])

  const newSession = useCallback(() => {
    setMessages([])
    currentAssistantIdRef.current = null
    setIsStreaming(false)
    setActiveOptions({})
    wsNew()
  }, [wsNew])

  const sendPermissionResponse = useCallback((requestId: string, optionId: string, cancelled: boolean) => {
    wsPermission(requestId, optionId, cancelled)
    setPermissionRequest(null)
  }, [wsPermission])

  const stopResponse = useCallback(() => {
    wsStop()
    setPermissionRequest(null)
    if (currentAssistantIdRef.current) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === currentAssistantIdRef.current
            ? { ...m, isStreaming: false, content: m.content || t('chat.stopped') }
            : m
        )
      )
      currentAssistantIdRef.current = null
      setIsStreaming(false)
    }
  }, [wsStop, t])

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
    safetyMode: state.safetyMode,
    permissionRequest,
    sendPermissionResponse,
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
    toolName: state.toolName,
    cost: state.cost,
    capabilities: state.capabilities,
    error: state.error,
    diagnostic: state.diagnostic,
  }
}
