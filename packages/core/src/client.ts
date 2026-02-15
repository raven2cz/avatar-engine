/**
 * AvatarClient — framework-agnostic WebSocket client.
 *
 * Uses avatarReducer and parseServerMessage internally.
 * Emits state changes via callbacks (no React dependency).
 */

import type { AvatarState, AvatarAction } from './protocol'
import type { ServerMessage, ChatAttachment } from './types'
import {
  avatarReducer,
  initialAvatarState,
  parseServerMessage,
  createChatMessage,
  createStopMessage,
  createSwitchMessage,
  createPermissionResponse,
  createResumeSessionMessage,
  createNewSessionMessage,
  createClearHistoryMessage,
} from './protocol'

export interface AvatarClientOptions {
  /** Reconnect delay in ms (default 3000) */
  reconnectDelay?: number
  /** Called whenever the internal AvatarState changes */
  onStateChange?: (state: Readonly<AvatarState>) => void
  /** Called for every raw server message */
  onMessage?: (msg: ServerMessage) => void
}

export class AvatarClient {
  private state: AvatarState
  private ws: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private destroyed = false
  private errorFenced = false

  constructor(
    private url: string,
    private options: AvatarClientOptions = {},
  ) {
    this.state = { ...initialAvatarState }
  }

  /** Connect to the WebSocket server. */
  connect(): void {
    this.destroyed = false
    this._connect()
  }

  /** Disconnect and prevent reconnection. */
  disconnect(): void {
    this.destroyed = true
    this._clearReconnect()
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
  }

  /** Get a readonly snapshot of the current state. */
  getState(): Readonly<AvatarState> {
    return this.state
  }

  // === Actions ===

  sendChat(text: string, attachments?: ChatAttachment[]): void {
    this.errorFenced = false
    this._dispatch({ type: 'CLEAR_ERROR' })
    this._dispatch({ type: 'DIAGNOSTIC', message: '', level: '' })
    this._send(createChatMessage(text, attachments))
  }

  stop(): void {
    this._send(createStopMessage())
    this._dispatch({ type: 'ENGINE_STATE', state: 'idle' })
    this._dispatch({ type: 'THINKING_END' })
  }

  switchProvider(provider: string, model?: string, options?: Record<string, unknown>): void {
    this._dispatch({ type: 'SWITCHING' })
    this._send(createSwitchMessage(provider, model, options))
  }

  resumeSession(sessionId: string): void {
    this._dispatch({ type: 'SWITCHING' })
    this._send(createResumeSessionMessage(sessionId))
  }

  newSession(): void {
    this._dispatch({ type: 'SWITCHING' })
    this._send(createNewSessionMessage())
  }

  sendPermissionResponse(requestId: string, optionId: string, cancelled: boolean): void {
    this._send(createPermissionResponse(requestId, optionId, cancelled))
  }

  clearHistory(): void {
    this._send(createClearHistoryMessage())
  }

  // === Internals ===

  private _connect(): void {
    if (this.destroyed) return

    const current = this.ws
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) {
      return
    }
    if (current && current.readyState !== WebSocket.CLOSED) {
      current.onclose = null
      current.close()
    }

    const ws = new WebSocket(this.url)
    this.ws = ws

    ws.onmessage = (event) => {
      if (ws !== this.ws) return
      try {
        const msg = JSON.parse(event.data) as ServerMessage

        const { action, resetFence } = parseServerMessage(msg, this.errorFenced)
        if (resetFence) this.errorFenced = false

        if (action) this._dispatch(action)

        // Handle compound actions for specific message types
        if (!this.errorFenced || !['engine_state', 'thinking', 'text', 'tool', 'chat_response'].includes(msg.type)) {
          if (msg.type === 'error') {
            this._dispatch({ type: 'ENGINE_STATE', state: 'idle' })
            this._dispatch({ type: 'THINKING_END' })
            this.errorFenced = true
          }
          if (msg.type === 'chat_response') {
            if (msg.data.error) {
              this._dispatch({ type: 'ERROR', error: msg.data.error })
              this.errorFenced = true
            }
            this._dispatch({ type: 'ENGINE_STATE', state: 'idle' })
            this._dispatch({ type: 'THINKING_END' })
          }
        }

        this.options.onMessage?.(msg)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      if (ws !== this.ws) return
      this._dispatch({ type: 'DISCONNECTED' })
      if (!this.destroyed) {
        this.reconnectTimer = setTimeout(
          () => this._connect(),
          this.options.reconnectDelay ?? 3000,
        )
      }
    }

    ws.onerror = () => {
      // Handled by onclose
    }
  }

  private _send(data: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data)
    }
  }

  private _dispatch(action: AvatarAction): void {
    this.state = avatarReducer(this.state, action)
    this.options.onStateChange?.(this.state)
  }

  private _clearReconnect(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}
