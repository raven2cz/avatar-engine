/**
 * Avatar Engine protocol — state machine (reducer), message parser, message builders.
 *
 * Pure functions with zero framework dependencies.
 */

import type {
  EngineState,
  ThinkingPhase,
  SafetyMode,
  ProviderCapabilities,
  CostInfo,
  ConnectedMessage,
  ServerMessage,
  ChatAttachment,
} from './types'

// === State machine ===

/**
 * Complete avatar state managed by the reducer.
 *
 * @property connected - Whether the WebSocket connection is currently open.
 * @property wasConnected - Whether the client has connected at least once (survives reconnects).
 * @property sessionId - Current session identifier, or null before the first connection.
 * @property sessionTitle - Human-readable session title, or null if unnamed.
 * @property provider - Active provider identifier (e.g. "gemini", "claude").
 * @property model - Active model name, or null when the server hasn't reported one.
 * @property version - Server/engine version string.
 * @property cwd - Server working directory.
 * @property capabilities - Provider-specific capability flags, or null before connection.
 * @property engineState - Current engine lifecycle state (idle, thinking, etc.).
 * @property initDetail - Human-readable detail string shown during initialization.
 * @property switching - Whether a provider/session switch is in progress.
 * @property safetyMode - Active safety mode (safe, ask, or unrestricted).
 * @property thinking - Thinking-indicator state (active flag, phase, subject, timestamp).
 * @property toolName - Name of the currently executing tool, or empty string when idle.
 * @property cost - Accumulated cost and token usage for the session.
 * @property error - Most recent error message, or null.
 * @property diagnostic - Most recent diagnostic message, or null.
 */
export interface AvatarState {
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
  safetyMode: SafetyMode
  thinking: {
    active: boolean
    phase: ThinkingPhase
    subject: string
    startedAt: number
  }
  toolName: string
  cost: CostInfo
  error: string | null
  diagnostic: string | null
}

/** Discriminated union of all actions dispatched to {@link avatarReducer}. */
export type AvatarAction =
  | { type: 'CONNECTED'; payload: ConnectedMessage }
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
  | { type: 'TOOL'; toolName: string; status: string }
  | { type: 'DIAGNOSTIC'; message: string; level: string }

/** Default starting state for a fresh avatar session. */
export const initialAvatarState: AvatarState = {
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
  safetyMode: 'safe',
  thinking: { active: false, phase: 'general', subject: '', startedAt: 0 },
  toolName: '',
  cost: { totalCostUsd: 0, totalInputTokens: 0, totalOutputTokens: 0 },
  error: null,
  diagnostic: null,
}

/**
 * Pure reducer — no React, no side-effects.
 * Maps AvatarAction to a new AvatarState.
 */
export function avatarReducer(state: AvatarState, action: AvatarAction): AvatarState {
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
        safetyMode: action.payload.data.safety_mode ?? 'safe',
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
    case 'TOOL':
      return {
        ...state,
        toolName: action.status === 'started' ? action.toolName : '',
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
      if (action.isCurrentSession) {
        return { ...state, sessionTitle: action.title }
      }
      return state
    case 'SESSION_ID_DISCOVERED':
      if (!state.sessionId) {
        return { ...state, sessionId: action.sessionId }
      }
      return state
    default:
      return state
  }
}

/**
 * Parse a raw WebSocket server message into an AvatarAction (or null for ignored messages).
 *
 * The `errorFenced` flag controls whether stale events from a timed-out request
 * should be suppressed. When true, engine_state/thinking/text/tool events are ignored
 * unless the message is a chat_response (which resets the fence).
 *
 * Returns `{ action, resetFence }` where `resetFence` signals that the error fence
 * should be cleared.
 */
export function parseServerMessage(
  msg: ServerMessage,
  errorFenced: boolean = false,
): { action: AvatarAction | null; resetFence: boolean } {
  // Error fence: suppress stale events
  if (errorFenced) {
    if (['engine_state', 'thinking', 'text', 'tool', 'chat_response'].includes(msg.type)) {
      if (msg.type === 'chat_response') {
        // Reset fence so compound handler in caller can run;
        // caller dispatches ENGINE_STATE:idle + THINKING_END.
        return { action: null, resetFence: true }
      }
      return { action: null, resetFence: false }
    }
  }

  switch (msg.type) {
    case 'connected':
      return {
        action: { type: 'CONNECTED', payload: msg },
        resetFence: true,
      }
    case 'initializing':
      return {
        action: { type: 'INITIALIZING', payload: msg },
        resetFence: false,
      }
    case 'state':
      if (msg.data.detail) {
        return {
          action: { type: 'STATE_UPDATE', detail: msg.data.detail, state: msg.data.new_state || '' },
          resetFence: false,
        }
      }
      return { action: null, resetFence: false }
    case 'engine_state':
      return {
        action: { type: 'ENGINE_STATE', state: msg.data.state },
        resetFence: false,
      }
    case 'thinking':
      if (msg.data.is_complete) {
        return { action: { type: 'THINKING_END' }, resetFence: false }
      } else if (msg.data.is_start) {
        return {
          action: { type: 'THINKING_START', phase: msg.data.phase, subject: msg.data.subject },
          resetFence: false,
        }
      } else {
        return {
          action: { type: 'THINKING_UPDATE', phase: msg.data.phase, subject: msg.data.subject },
          resetFence: false,
        }
      }
    case 'tool':
      return {
        action: { type: 'TOOL', toolName: msg.data.tool_name || '', status: msg.data.status || 'started' },
        resetFence: false,
      }
    case 'cost':
      return {
        action: {
          type: 'COST',
          costUsd: msg.data.cost_usd,
          inputTokens: msg.data.input_tokens,
          outputTokens: msg.data.output_tokens,
        },
        resetFence: false,
      }
    case 'error':
      return {
        action: { type: 'ERROR', error: msg.data.error },
        resetFence: false,
      }
    case 'session_title_updated':
      return {
        action: {
          type: 'SESSION_TITLE_UPDATED',
          sessionId: msg.data.session_id,
          title: msg.data.title,
          isCurrentSession: !!msg.data.is_current_session,
        },
        resetFence: false,
      }
    case 'diagnostic':
      if (msg.data.message) {
        return {
          action: { type: 'DIAGNOSTIC', message: msg.data.message, level: msg.data.level || 'info' },
          resetFence: false,
        }
      }
      return { action: null, resetFence: false }
    case 'chat_response':
      // Multiple actions needed — compound handler in caller dispatches
      // ENGINE_STATE:idle and THINKING_END; we only handle session ID discovery.
      return {
        action: msg.data.session_id
          ? { type: 'SESSION_ID_DISCOVERED', sessionId: msg.data.session_id }
          : null,
        resetFence: false,
      }
    default:
      return { action: null, resetFence: false }
  }
}

// === Message builders ===

/**
 * Build a JSON-encoded chat message for the WebSocket server.
 *
 * @param text - The user's chat text.
 * @param attachments - Optional file or image attachments to include.
 * @param context - Optional opaque metadata (e.g. page context) forwarded to the AI.
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createChatMessage(text: string, attachments?: ChatAttachment[], context?: Record<string, unknown>): string {
  const data: Record<string, unknown> = { message: text }
  if (attachments?.length) data.attachments = attachments
  if (context && Object.keys(context).length > 0) data.context = context
  return JSON.stringify({ type: 'chat', data })
}

/**
 * Build a JSON-encoded stop message to abort the current generation.
 *
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createStopMessage(): string {
  return JSON.stringify({ type: 'stop', data: {} })
}

/**
 * Build a JSON-encoded provider/model switch message.
 *
 * @param provider - Target provider identifier (e.g. "gemini", "claude").
 * @param model - Optional model name to select within the provider.
 * @param options - Optional provider-specific configuration overrides.
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createSwitchMessage(
  provider: string,
  model?: string,
  options?: Record<string, unknown>,
): string {
  return JSON.stringify({
    type: 'switch',
    data: { provider, model: model || undefined, options: options || undefined },
  })
}

/**
 * Build a JSON-encoded permission response for the safety system.
 *
 * @param requestId - Identifier of the original permission request.
 * @param optionId - Selected permission option (e.g. "allow", "deny").
 * @param cancelled - Whether the user dismissed the prompt without choosing.
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createPermissionResponse(
  requestId: string,
  optionId: string,
  cancelled: boolean,
): string {
  return JSON.stringify({
    type: 'permission_response',
    data: { request_id: requestId, option_id: optionId, cancelled },
  })
}

/**
 * Build a JSON-encoded message to resume an existing session.
 *
 * @param sessionId - Identifier of the session to resume.
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createResumeSessionMessage(sessionId: string): string {
  return JSON.stringify({ type: 'resume_session', data: { session_id: sessionId } })
}

/**
 * Build a JSON-encoded message to start a new session.
 *
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createNewSessionMessage(): string {
  return JSON.stringify({ type: 'new_session', data: {} })
}

/**
 * Build a JSON-encoded message to clear conversation history.
 *
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createClearHistoryMessage(): string {
  return JSON.stringify({ type: 'clear_history', data: {} })
}

/**
 * Build a JSON-encoded ping/keepalive message.
 *
 * @returns Serialized JSON string ready to send over the WebSocket.
 */
export function createPingMessage(): string {
  return JSON.stringify({ type: 'ping', data: {} })
}
