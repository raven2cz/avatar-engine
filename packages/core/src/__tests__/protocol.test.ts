/**
 * Protocol tests — avatarReducer, parseServerMessage, message builders.
 *
 * Covers:
 *   - Reducer state transitions
 *   - parseServerMessage mapping from raw server messages
 *   - Error fence behavior (suppresses stale events, resets on chat_response)
 *   - No double-dispatch of ENGINE_STATE:idle for chat_response
 *   - Message builder output format
 */

/// <reference types="vitest/globals" />
import { describe, it, expect } from 'vitest'
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
  createPingMessage,
} from '../protocol'
import type { AvatarState, AvatarAction } from '../protocol'
import type { ServerMessage, ProviderCapabilities } from '../types'

const nullCaps: ProviderCapabilities = {
  can_list_sessions: false,
  can_load_session: false,
  can_continue_last: false,
  thinking_supported: false,
  thinking_structured: false,
  cost_tracking: false,
  budget_enforcement: false,
  system_prompt_method: 'none',
  streaming: false,
  parallel_tools: false,
  cancellable: false,
  mcp_supported: false,
}

// Helper: apply a sequence of actions
function applyActions(state: AvatarState, actions: AvatarAction[]): AvatarState {
  return actions.reduce((s, a) => avatarReducer(s, a), state)
}

// Helper: make a ServerMessage
function msg(type: string, data: Record<string, unknown> = {}): ServerMessage {
  return { type, data } as ServerMessage
}

describe('avatarReducer', () => {
  it('starts in idle with defaults', () => {
    expect(initialAvatarState.engineState).toBe('idle')
    expect(initialAvatarState.connected).toBe(false)
    expect(initialAvatarState.error).toBeNull()
    expect(initialAvatarState.thinking.active).toBe(false)
  })

  it('CONNECTED sets all fields', () => {
    const state = avatarReducer(initialAvatarState, {
      type: 'CONNECTED',
      payload: {
        type: 'connected',
        data: {
          session_id: 's1',
          session_title: 'Test',
          provider: 'gemini',
          model: 'gemini-2.5-pro',
          version: '1.0.0',
          cwd: '/tmp',
          capabilities: nullCaps,
          engine_state: 'idle',
          safety_mode: 'ask',
        },
      },
    })

    expect(state.connected).toBe(true)
    expect(state.wasConnected).toBe(true)
    expect(state.sessionId).toBe('s1')
    expect(state.provider).toBe('gemini')
    expect(state.model).toBe('gemini-2.5-pro')
    expect(state.safetyMode).toBe('ask')
    expect(state.error).toBeNull()
  })

  it('DISCONNECTED resets to idle', () => {
    const thinking = avatarReducer(initialAvatarState, { type: 'ENGINE_STATE', state: 'thinking' })
    const disconnected = avatarReducer(thinking, { type: 'DISCONNECTED' })
    expect(disconnected.connected).toBe(false)
    expect(disconnected.engineState).toBe('idle')
  })

  it('ENGINE_STATE transitions', () => {
    let state = avatarReducer(initialAvatarState, { type: 'ENGINE_STATE', state: 'thinking' })
    expect(state.engineState).toBe('thinking')
    state = avatarReducer(state, { type: 'ENGINE_STATE', state: 'responding' })
    expect(state.engineState).toBe('responding')
    state = avatarReducer(state, { type: 'ENGINE_STATE', state: 'idle' })
    expect(state.engineState).toBe('idle')
  })

  it('thinking lifecycle', () => {
    let state = avatarReducer(initialAvatarState, {
      type: 'THINKING_START', phase: 'analyzing', subject: 'code',
    })
    expect(state.thinking.active).toBe(true)
    expect(state.thinking.phase).toBe('analyzing')
    expect(state.thinking.subject).toBe('code')
    expect(state.thinking.startedAt).toBeGreaterThan(0)

    state = avatarReducer(state, {
      type: 'THINKING_UPDATE', phase: 'coding', subject: 'fix',
    })
    expect(state.thinking.phase).toBe('coding')
    expect(state.thinking.subject).toBe('fix')

    state = avatarReducer(state, { type: 'THINKING_END' })
    expect(state.thinking.active).toBe(false)
    expect(state.thinking.phase).toBe('general')
    expect(state.thinking.startedAt).toBe(0)
  })

  it('COST accumulates', () => {
    let state = avatarReducer(initialAvatarState, {
      type: 'COST', costUsd: 0.01, inputTokens: 100, outputTokens: 50,
    })
    state = avatarReducer(state, {
      type: 'COST', costUsd: 0.02, inputTokens: 200, outputTokens: 100,
    })
    expect(state.cost.totalCostUsd).toBeCloseTo(0.03)
    expect(state.cost.totalInputTokens).toBe(300)
    expect(state.cost.totalOutputTokens).toBe(150)
  })

  it('ERROR/CLEAR_ERROR', () => {
    let state = avatarReducer(initialAvatarState, { type: 'ERROR', error: 'oops' })
    expect(state.error).toBe('oops')
    state = avatarReducer(state, { type: 'CLEAR_ERROR' })
    expect(state.error).toBeNull()
  })

  it('SESSION_ID_DISCOVERED only if empty', () => {
    let state = avatarReducer(initialAvatarState, {
      type: 'SESSION_ID_DISCOVERED', sessionId: 's1',
    })
    expect(state.sessionId).toBe('s1')
    state = avatarReducer(state, {
      type: 'SESSION_ID_DISCOVERED', sessionId: 's2',
    })
    expect(state.sessionId).toBe('s1') // unchanged
  })
})

describe('parseServerMessage', () => {
  it('connected → CONNECTED + resetFence', () => {
    const result = parseServerMessage(msg('connected', {
      session_id: 's1', provider: 'gemini', model: 'm', version: '1',
      cwd: '/', capabilities: nullCaps, engine_state: 'idle',
    }))
    expect(result.action?.type).toBe('CONNECTED')
    expect(result.resetFence).toBe(true)
  })

  it('engine_state → ENGINE_STATE', () => {
    const result = parseServerMessage(msg('engine_state', { state: 'thinking' }))
    expect(result.action).toEqual({ type: 'ENGINE_STATE', state: 'thinking' })
    expect(result.resetFence).toBe(false)
  })

  it('thinking start → THINKING_START', () => {
    const result = parseServerMessage(msg('thinking', {
      is_start: true, phase: 'analyzing', subject: 'code',
    }))
    expect(result.action).toEqual({
      type: 'THINKING_START', phase: 'analyzing', subject: 'code',
    })
  })

  it('thinking end → THINKING_END', () => {
    const result = parseServerMessage(msg('thinking', { is_complete: true }))
    expect(result.action).toEqual({ type: 'THINKING_END' })
  })

  it('error → ERROR (no fence set)', () => {
    const result = parseServerMessage(msg('error', { error: 'fail' }))
    expect(result.action).toEqual({ type: 'ERROR', error: 'fail' })
    expect(result.resetFence).toBe(false)
  })

  it('chat_response with session_id → SESSION_ID_DISCOVERED', () => {
    const result = parseServerMessage(msg('chat_response', { session_id: 's1' }))
    expect(result.action).toEqual({ type: 'SESSION_ID_DISCOVERED', sessionId: 's1' })
    expect(result.resetFence).toBe(false)
  })

  it('chat_response without session_id → null action (no double-dispatch)', () => {
    const result = parseServerMessage(msg('chat_response', {}))
    expect(result.action).toBeNull()
    expect(result.resetFence).toBe(false)
  })

  it('unknown message types → null action', () => {
    const result = parseServerMessage(msg('text', { content: 'hello' }))
    expect(result.action).toBeNull()
  })

  it('cost → COST', () => {
    const result = parseServerMessage(msg('cost', {
      cost_usd: 0.05, input_tokens: 500, output_tokens: 200,
    }))
    expect(result.action).toEqual({
      type: 'COST', costUsd: 0.05, inputTokens: 500, outputTokens: 200,
    })
  })

  it('diagnostic with message → DIAGNOSTIC', () => {
    const result = parseServerMessage(msg('diagnostic', { message: 'info', level: 'warn' }))
    expect(result.action).toEqual({ type: 'DIAGNOSTIC', message: 'info', level: 'warn' })
  })

  it('diagnostic without message → null', () => {
    const result = parseServerMessage(msg('diagnostic', {}))
    expect(result.action).toBeNull()
  })
})

describe('parseServerMessage — error fence', () => {
  it('fenced engine_state is suppressed', () => {
    const result = parseServerMessage(msg('engine_state', { state: 'thinking' }), true)
    expect(result.action).toBeNull()
    expect(result.resetFence).toBe(false)
  })

  it('fenced thinking is suppressed', () => {
    const result = parseServerMessage(msg('thinking', { is_start: true, phase: 'general', subject: '' }), true)
    expect(result.action).toBeNull()
  })

  it('fenced text is suppressed', () => {
    const result = parseServerMessage(msg('text', { content: 'hello' }), true)
    expect(result.action).toBeNull()
  })

  it('fenced tool is suppressed', () => {
    const result = parseServerMessage(msg('tool', { tool_name: 'bash', status: 'started' }), true)
    expect(result.action).toBeNull()
  })

  it('fenced chat_response resets fence with null action', () => {
    const result = parseServerMessage(msg('chat_response', {}), true)
    expect(result.action).toBeNull()
    expect(result.resetFence).toBe(true)
  })

  it('fenced error is NOT suppressed (error not in fence list)', () => {
    const result = parseServerMessage(msg('error', { error: 'new error' }), true)
    expect(result.action).toEqual({ type: 'ERROR', error: 'new error' })
  })

  it('fenced connected resets fence', () => {
    const result = parseServerMessage(msg('connected', {
      session_id: 's1', provider: 'gemini', model: 'm', version: '1',
      cwd: '/', capabilities: nullCaps, engine_state: 'idle',
    }), true)
    expect(result.action?.type).toBe('CONNECTED')
    expect(result.resetFence).toBe(true)
  })
})

describe('AvatarClient compound dispatch simulation', () => {
  // Simulates what client.ts does with parseServerMessage + compound handler
  // to verify no double-dispatch of ENGINE_STATE:idle

  function simulateClientOnMessage(state: AvatarState, serverMsg: ServerMessage, fenced: boolean) {
    let errorFenced = fenced
    const dispatches: AvatarAction[] = []

    // Step 1: parseServerMessage
    const { action, resetFence } = parseServerMessage(serverMsg, errorFenced)
    if (resetFence) errorFenced = false
    if (action) dispatches.push(action)

    // Step 2: compound handler (mirrors client.ts logic)
    if (!errorFenced || !['engine_state', 'thinking', 'text', 'tool', 'chat_response'].includes(serverMsg.type)) {
      if (serverMsg.type === 'error') {
        dispatches.push({ type: 'ENGINE_STATE', state: 'idle' })
        dispatches.push({ type: 'THINKING_END' })
        errorFenced = true
      }
      if (serverMsg.type === 'chat_response') {
        if (serverMsg.data.error) {
          dispatches.push({ type: 'ERROR', error: serverMsg.data.error })
          errorFenced = true
        }
        dispatches.push({ type: 'ENGINE_STATE', state: 'idle' })
        dispatches.push({ type: 'THINKING_END' })
      }
    }

    const newState = applyActions(state, dispatches)
    return { newState, dispatches, errorFenced }
  }

  it('chat_response without session_id dispatches ENGINE_STATE:idle exactly once', () => {
    const { dispatches } = simulateClientOnMessage(
      initialAvatarState, msg('chat_response', {}), false,
    )
    const idleDispatches = dispatches.filter(
      (d) => d.type === 'ENGINE_STATE' && (d as { state: string }).state === 'idle',
    )
    expect(idleDispatches).toHaveLength(1)
  })

  it('chat_response with session_id dispatches SESSION_ID + ENGINE_STATE:idle', () => {
    const { dispatches, newState } = simulateClientOnMessage(
      initialAvatarState, msg('chat_response', { session_id: 's1' }), false,
    )
    expect(dispatches.find((d) => d.type === 'SESSION_ID_DISCOVERED')).toBeTruthy()
    expect(dispatches.filter((d) => d.type === 'ENGINE_STATE')).toHaveLength(1)
    expect(newState.sessionId).toBe('s1')
    expect(newState.engineState).toBe('idle')
  })

  it('chat_response with error dispatches ERROR + ENGINE_STATE:idle + sets fence', () => {
    const { dispatches, errorFenced } = simulateClientOnMessage(
      initialAvatarState, msg('chat_response', { error: 'rate limit' }), false,
    )
    expect(dispatches.find((d) => d.type === 'ERROR')).toBeTruthy()
    expect(dispatches.filter((d) => d.type === 'ENGINE_STATE')).toHaveLength(1)
    expect(errorFenced).toBe(true)
  })

  it('error dispatches ERROR + ENGINE_STATE:idle + THINKING_END', () => {
    const thinking = avatarReducer(initialAvatarState, { type: 'ENGINE_STATE', state: 'thinking' })
    const { dispatches, newState, errorFenced } = simulateClientOnMessage(
      thinking, msg('error', { error: 'oops' }), false,
    )
    expect(dispatches).toEqual([
      { type: 'ERROR', error: 'oops' },
      { type: 'ENGINE_STATE', state: 'idle' },
      { type: 'THINKING_END' },
    ])
    expect(newState.engineState).toBe('idle')
    expect(newState.error).toBe('oops')
    expect(newState.thinking.active).toBe(false)
    expect(errorFenced).toBe(true)
  })

  it('fenced chat_response resets fence and dispatches ENGINE_STATE:idle once', () => {
    const { dispatches, errorFenced } = simulateClientOnMessage(
      initialAvatarState, msg('chat_response', {}), true,
    )
    // parseServerMessage returns null + resetFence=true
    // compound handler runs because fence was just reset
    const idleDispatches = dispatches.filter(
      (d) => d.type === 'ENGINE_STATE' && (d as { state: string }).state === 'idle',
    )
    expect(idleDispatches).toHaveLength(1)
    expect(errorFenced).toBe(false)
  })
})

describe('message builders', () => {
  it('createChatMessage', () => {
    const m = JSON.parse(createChatMessage('hello'))
    expect(m.type).toBe('chat')
    expect(m.data.message).toBe('hello')
    expect(m.data.attachments).toBeUndefined()
  })

  it('createChatMessage with attachments', () => {
    const m = JSON.parse(createChatMessage('hi', [{ type: 'file', name: 'a.txt', content: 'x' } as any]))
    expect(m.data.attachments).toHaveLength(1)
  })

  it('createStopMessage', () => {
    const m = JSON.parse(createStopMessage())
    expect(m.type).toBe('stop')
  })

  it('createSwitchMessage', () => {
    const m = JSON.parse(createSwitchMessage('claude', 'claude-4', { temp: 0.5 }))
    expect(m.type).toBe('switch')
    expect(m.data.provider).toBe('claude')
    expect(m.data.model).toBe('claude-4')
    expect(m.data.options.temp).toBe(0.5)
  })

  it('createPermissionResponse', () => {
    const m = JSON.parse(createPermissionResponse('r1', 'allow', false))
    expect(m.type).toBe('permission_response')
    expect(m.data.request_id).toBe('r1')
    expect(m.data.option_id).toBe('allow')
    expect(m.data.cancelled).toBe(false)
  })

  it('createResumeSessionMessage', () => {
    const m = JSON.parse(createResumeSessionMessage('sess-123'))
    expect(m.type).toBe('resume_session')
    expect(m.data.session_id).toBe('sess-123')
  })

  it('createNewSessionMessage', () => {
    const m = JSON.parse(createNewSessionMessage())
    expect(m.type).toBe('new_session')
  })

  it('createClearHistoryMessage', () => {
    const m = JSON.parse(createClearHistoryMessage())
    expect(m.type).toBe('clear_history')
  })

  it('createPingMessage', () => {
    const m = JSON.parse(createPingMessage())
    expect(m.type).toBe('ping')
  })
})
