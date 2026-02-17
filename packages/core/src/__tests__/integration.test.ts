/**
 * Integration tests — full conversation lifecycle simulation.
 *
 * Simulates the complete flow a consumer (Synapse, web-demo, Vue app) would see
 * through the core state machine:
 *
 *   connect → send chat → thinking → tool → responding → chat_response → idle
 *   error recovery → new session → disconnect
 *
 * Also verifies the re-export chain: everything a consumer needs is
 * importable from a single entry point.
 */

/// <reference types="vitest/globals" />
import { describe, it, expect } from 'vitest'
import {
  // State machine
  avatarReducer,
  initialAvatarState,
  parseServerMessage,

  // Message builders
  createChatMessage,
  createStopMessage,
  createSwitchMessage,
  createPermissionResponse,
  createResumeSessionMessage,
  createNewSessionMessage,
  createClearHistoryMessage,

  // Config
  PROVIDERS,
  getProvider,
  getModelsForProvider,
  isImageModel,
  buildOptionsDict,
  AVATARS,
  DEFAULT_AVATAR_ID,
  getAvatarById,

  // i18n
  initAvatarI18n,
  AVAILABLE_LANGUAGES,

  // Utils
  nextId,
  summarizeParams,

  // localStorage keys
  LS_WIDGET_MODE,
  LS_BUST_VISIBLE,
  LS_SELECTED_AVATAR,
  LS_HINTS_SHOWN,
  LS_DEFAULT_MODE,
  LS_LANGUAGE,
} from '../index'
import type {
  AvatarState,
  AvatarAction,
  ServerMessage,
  ProviderCapabilities,
  ChatMessage,
  WidgetMode,
  SafetyMode,
  EngineState,
} from '../index'

const testCaps: ProviderCapabilities = {
  can_list_sessions: true,
  can_load_session: true,
  can_continue_last: true,
  thinking_supported: true,
  thinking_structured: true,
  cost_tracking: true,
  budget_enforcement: false,
  system_prompt_method: 'system',
  streaming: true,
  parallel_tools: false,
  cancellable: true,
  mcp_supported: true,
}

function msg(type: string, data: Record<string, unknown> = {}): ServerMessage {
  return { type, data } as ServerMessage
}

function dispatch(state: AvatarState, action: AvatarAction): AvatarState {
  return avatarReducer(state, action)
}

/** Simulate full client.ts onmessage logic */
function processMessage(state: AvatarState, serverMsg: ServerMessage, fenced: boolean) {
  let errorFenced = fenced
  const actions: AvatarAction[] = []

  const { action, resetFence } = parseServerMessage(serverMsg, errorFenced)
  if (resetFence) errorFenced = false
  if (action) actions.push(action)

  if (!errorFenced || !['engine_state', 'thinking', 'text', 'tool', 'chat_response'].includes(serverMsg.type)) {
    if (serverMsg.type === 'error') {
      actions.push({ type: 'ENGINE_STATE', state: 'idle' })
      actions.push({ type: 'THINKING_END' })
      errorFenced = true
    }
    if (serverMsg.type === 'chat_response') {
      if (serverMsg.data.error) {
        actions.push({ type: 'ERROR', error: serverMsg.data.error })
        errorFenced = true
      }
      actions.push({ type: 'ENGINE_STATE', state: 'idle' })
      actions.push({ type: 'THINKING_END' })
    }
  }

  const newState = actions.reduce((s, a) => dispatch(s, a), state)
  return { state: newState, errorFenced }
}

describe('full conversation lifecycle', () => {
  it('connect → chat → thinking → responding → chat_response → idle', () => {
    let state = initialAvatarState
    let fenced = false

    // 1. Connect
    ;({ state, errorFenced: fenced } = processMessage(state, msg('connected', {
      session_id: 'sess-001',
      provider: 'gemini',
      model: 'gemini-2.5-pro',
      version: '1.0.0',
      cwd: '/project',
      capabilities: testCaps,
      engine_state: 'idle',
      safety_mode: 'ask',
    }), fenced))

    expect(state.connected).toBe(true)
    expect(state.provider).toBe('gemini')
    expect(state.sessionId).toBe('sess-001')
    expect(state.safetyMode).toBe('ask')
    expect(state.engineState).toBe('idle')
    expect(fenced).toBe(false)

    // 2. User sends message (client side)
    const chatMsg = createChatMessage('Explain this code')
    expect(JSON.parse(chatMsg).type).toBe('chat')
    expect(JSON.parse(chatMsg).data.message).toBe('Explain this code')

    // 3. Engine starts thinking
    ;({ state } = processMessage(state, msg('engine_state', { state: 'thinking' }), fenced))
    expect(state.engineState).toBe('thinking')

    ;({ state } = processMessage(state, msg('thinking', {
      is_start: true, phase: 'analyzing', subject: 'code structure',
    }), fenced))
    expect(state.thinking.active).toBe(true)
    expect(state.thinking.phase).toBe('analyzing')

    // 4. Tool execution
    ;({ state } = processMessage(state, msg('engine_state', { state: 'tool_executing' }), fenced))
    ;({ state } = processMessage(state, msg('tool', {
      tool_name: 'read_file', status: 'started',
    }), fenced))
    expect(state.engineState).toBe('tool_executing')
    expect(state.toolName).toBe('read_file')

    ;({ state } = processMessage(state, msg('tool', {
      tool_name: 'read_file', status: 'completed',
    }), fenced))
    expect(state.toolName).toBe('') // cleared on non-started

    // 5. Responding
    ;({ state } = processMessage(state, msg('engine_state', { state: 'responding' }), fenced))
    ;({ state } = processMessage(state, msg('thinking', { is_complete: true }), fenced))
    expect(state.engineState).toBe('responding')
    expect(state.thinking.active).toBe(false)

    // 6. Cost update
    ;({ state } = processMessage(state, msg('cost', {
      cost_usd: 0.003, input_tokens: 1500, output_tokens: 500,
    }), fenced))
    expect(state.cost.totalCostUsd).toBeCloseTo(0.003)
    expect(state.cost.totalInputTokens).toBe(1500)

    // 7. Chat response (end of turn)
    ;({ state } = processMessage(state, msg('chat_response', {
      session_id: 'sess-001',
    }), fenced))
    expect(state.engineState).toBe('idle')
    expect(state.thinking.active).toBe(false)
  })

  it('error recovery: error → fence → new chat clears fence', () => {
    let state = dispatch(initialAvatarState, {
      type: 'CONNECTED',
      payload: msg('connected', {
        session_id: 's1', provider: 'gemini', model: 'm', version: '1',
        cwd: '/', capabilities: testCaps, engine_state: 'idle',
      }) as any,
    })
    let fenced = false

    // Start thinking
    ;({ state } = processMessage(state, msg('engine_state', { state: 'thinking' }), fenced))
    ;({ state } = processMessage(state, msg('thinking', {
      is_start: true, phase: 'general', subject: '',
    }), fenced))

    // Error!
    ;({ state, errorFenced: fenced } = processMessage(state, msg('error', {
      error: 'Rate limit exceeded',
    }), fenced))
    expect(state.error).toBe('Rate limit exceeded')
    expect(state.engineState).toBe('idle')
    expect(fenced).toBe(true)

    // Stale events are fenced
    ;({ state } = processMessage(state, msg('engine_state', { state: 'responding' }), fenced))
    expect(state.engineState).toBe('idle') // stayed idle, not responding

    // chat_response resets fence
    ;({ state, errorFenced: fenced } = processMessage(state, msg('chat_response', {}), fenced))
    expect(fenced).toBe(false)
    expect(state.engineState).toBe('idle')
  })

  it('disconnect and reconnect preserves wasConnected', () => {
    let state = dispatch(initialAvatarState, {
      type: 'CONNECTED',
      payload: msg('connected', {
        session_id: 's1', provider: 'claude', model: 'claude-4', version: '1',
        cwd: '/', capabilities: testCaps, engine_state: 'idle',
      }) as any,
    })
    expect(state.wasConnected).toBe(true)

    state = dispatch(state, { type: 'DISCONNECTED' })
    expect(state.connected).toBe(false)
    expect(state.wasConnected).toBe(true) // preserved
    expect(state.engineState).toBe('idle')
  })

  it('provider switch lifecycle', () => {
    let state = dispatch(initialAvatarState, {
      type: 'CONNECTED',
      payload: msg('connected', {
        session_id: 's1', provider: 'gemini', model: 'm', version: '1',
        cwd: '/', capabilities: testCaps, engine_state: 'idle',
      }) as any,
    })

    // Client sends switch
    const switchMsg = createSwitchMessage('claude', 'claude-4', { thinking: true })
    const parsed = JSON.parse(switchMsg)
    expect(parsed.type).toBe('switch')
    expect(parsed.data.provider).toBe('claude')

    // Mark switching
    state = dispatch(state, { type: 'SWITCHING' })
    expect(state.switching).toBe(true)

    // Initializing event
    ;({ state } = processMessage(state, msg('initializing', {
      detail: 'Starting Claude...', provider: 'claude',
    }), false))
    expect(state.initDetail).toBe('Starting Claude...')

    // New connected event
    ;({ state } = processMessage(state, msg('connected', {
      session_id: 's2', provider: 'claude', model: 'claude-4', version: '1',
      cwd: '/', capabilities: testCaps, engine_state: 'idle',
    }), false))
    expect(state.provider).toBe('claude')
    expect(state.sessionId).toBe('s2')
    expect(state.switching).toBe(false)
  })
})

describe('config and utils export verification', () => {
  it('PROVIDERS has at least gemini, claude, codex', () => {
    const ids = PROVIDERS.map((p) => p.id)
    expect(ids).toContain('gemini')
    expect(ids).toContain('claude')
    expect(ids).toContain('codex')
  })

  it('getProvider returns config for known providers', () => {
    const gemini = getProvider('gemini')
    expect(gemini).toBeTruthy()
    expect(gemini!.label).toBeTruthy()
  })

  it('getModelsForProvider returns array', () => {
    const models = getModelsForProvider('gemini')
    expect(Array.isArray(models)).toBe(true)
    expect(models.length).toBeGreaterThan(0)
  })

  it('AVATARS has entries', () => {
    expect(AVATARS.length).toBeGreaterThan(0)
  })

  it('getAvatarById returns default avatar', () => {
    const avatar = getAvatarById(DEFAULT_AVATAR_ID)
    expect(avatar).toBeTruthy()
    expect(avatar!.id).toBe(DEFAULT_AVATAR_ID)
  })

  it('nextId generates unique IDs', () => {
    const ids = new Set(Array.from({ length: 100 }, () => nextId()))
    expect(ids.size).toBe(100)
  })

  it('summarizeParams truncates long values', () => {
    const result = summarizeParams({ key: 'a'.repeat(200) })
    expect(result.length).toBeLessThan(200)
  })

  it('AVAILABLE_LANGUAGES includes en and cs', () => {
    const codes = AVAILABLE_LANGUAGES.map((l) => l.code)
    expect(codes).toContain('en')
    expect(codes).toContain('cs')
  })

  it('localStorage key constants are strings', () => {
    expect(typeof LS_WIDGET_MODE).toBe('string')
    expect(typeof LS_BUST_VISIBLE).toBe('string')
    expect(typeof LS_SELECTED_AVATAR).toBe('string')
    expect(typeof LS_HINTS_SHOWN).toBe('string')
    expect(typeof LS_DEFAULT_MODE).toBe('string')
    expect(typeof LS_LANGUAGE).toBe('string')
  })
})

describe('type safety — compile-time verification', () => {
  it('AvatarState fields are typed', () => {
    const state: AvatarState = initialAvatarState
    const _engine: EngineState = state.engineState
    const _safety: SafetyMode = state.safetyMode
    const _mode: WidgetMode = 'fab' // WidgetMode is importable
    expect(_engine).toBe('idle')
    expect(_safety).toBe('safe')
    expect(_mode).toBe('fab')
  })

  it('ChatMessage type is usable', () => {
    const msg: ChatMessage = {
      id: '1',
      role: 'user',
      content: 'hello',
      timestamp: Date.now(),
      tools: [],
      isStreaming: false,
    }
    expect(msg.role).toBe('user')
  })
})
