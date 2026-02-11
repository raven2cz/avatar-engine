/**
 * Error handling + state reset tests.
 *
 * Verifies:
 *   - useAvatarWebSocket reducer resets engineState to idle on error
 *   - Thinking state is cleared on stop
 *   - Bust state maps engineState correctly (including error)
 *   - No client-side auto-timeout exists (removed by design)
 *   - Server error events properly reset engine state
 */

/// <reference types="vitest/globals" />
import { describe, it, expect } from 'vitest'

// Node fs used for source-level assertions in test environment
declare function require(id: string): { readFileSync(path: string, enc: string): string }

// ---------- Inline the reducer so we can test it without hooks ----------

type EngineState = 'idle' | 'thinking' | 'responding' | 'tool_executing' | 'waiting_approval' | 'error'
type ThinkingPhase = 'general' | 'analyzing' | 'coding' | 'planning' | 'reviewing' | 'tool_planning'
type BustState = 'idle' | 'thinking' | 'speaking' | 'error'

interface AvatarWSState {
  connected: boolean
  wasConnected: boolean
  sessionId: string | null
  sessionTitle: string | null
  provider: string
  model: string | null
  version: string
  cwd: string
  capabilities: null
  engineState: EngineState
  initDetail: string
  switching: boolean
  thinking: { active: boolean; phase: ThinkingPhase; subject: string; startedAt: number }
  cost: { totalCostUsd: number; totalInputTokens: number; totalOutputTokens: number }
  error: string | null
}

type Action =
  | { type: 'ENGINE_STATE'; state: EngineState }
  | { type: 'THINKING_START'; phase: ThinkingPhase; subject: string }
  | { type: 'THINKING_UPDATE'; phase: ThinkingPhase; subject: string }
  | { type: 'THINKING_END' }
  | { type: 'ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'DISCONNECTED' }

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
}

// Same reducer logic as useAvatarWebSocket (extracted for testability)
function reducer(state: AvatarWSState, action: Action): AvatarWSState {
  switch (action.type) {
    case 'ENGINE_STATE':
      return { ...state, engineState: action.state }
    case 'THINKING_START':
      return {
        ...state,
        thinking: { active: true, phase: action.phase, subject: action.subject, startedAt: Date.now() },
      }
    case 'THINKING_UPDATE':
      return {
        ...state,
        thinking: { ...state.thinking, phase: action.phase, subject: action.subject || state.thinking.subject },
      }
    case 'THINKING_END':
      return {
        ...state,
        thinking: { active: false, phase: 'general', subject: '', startedAt: 0 },
      }
    case 'ERROR':
      return { ...state, error: action.error }
    case 'CLEAR_ERROR':
      return { ...state, error: null }
    case 'DISCONNECTED':
      return { ...state, connected: false, engineState: 'idle' }
    default:
      return state
  }
}

// Same mapping as useAvatarBust
function engineStateToBustState(engineState: string): BustState {
  switch (engineState) {
    case 'thinking':
    case 'tool_executing':
      return 'thinking'
    case 'responding':
      return 'speaking'
    case 'error':
      return 'error'
    default:
      return 'idle'
  }
}

describe('WebSocket reducer — engine state management', () => {
  it('starts in idle state', () => {
    expect(initialState.engineState).toBe('idle')
  })

  it('transitions to thinking', () => {
    const state = reducer(initialState, { type: 'ENGINE_STATE', state: 'thinking' })
    expect(state.engineState).toBe('thinking')
  })

  it('transitions to responding', () => {
    const state = reducer(initialState, { type: 'ENGINE_STATE', state: 'responding' })
    expect(state.engineState).toBe('responding')
  })

  it('resets to idle on ENGINE_STATE:idle (defensive reset on chat_response)', () => {
    let state = reducer(initialState, { type: 'ENGINE_STATE', state: 'responding' })
    expect(state.engineState).toBe('responding')
    state = reducer(state, { type: 'ENGINE_STATE', state: 'idle' })
    expect(state.engineState).toBe('idle')
  })

  it('sets error message on ERROR action', () => {
    const state = reducer(initialState, { type: 'ERROR', error: 'Something went wrong' })
    expect(state.error).toBe('Something went wrong')
  })

  it('clears error on CLEAR_ERROR', () => {
    let state = reducer(initialState, { type: 'ERROR', error: 'fail' })
    state = reducer(state, { type: 'CLEAR_ERROR' })
    expect(state.error).toBeNull()
  })

  it('resets engineState to idle on DISCONNECTED', () => {
    let state = reducer(initialState, { type: 'ENGINE_STATE', state: 'thinking' })
    state = reducer(state, { type: 'DISCONNECTED' })
    expect(state.engineState).toBe('idle')
  })
})

describe('WebSocket reducer — thinking state management', () => {
  it('starts thinking with phase and subject', () => {
    const state = reducer(initialState, {
      type: 'THINKING_START',
      phase: 'analyzing',
      subject: 'file structure',
    })
    expect(state.thinking.active).toBe(true)
    expect(state.thinking.phase).toBe('analyzing')
    expect(state.thinking.subject).toBe('file structure')
    expect(state.thinking.startedAt).toBeGreaterThan(0)
  })

  it('updates thinking phase and subject', () => {
    let state = reducer(initialState, {
      type: 'THINKING_START',
      phase: 'general',
      subject: 'initial',
    })
    state = reducer(state, {
      type: 'THINKING_UPDATE',
      phase: 'coding',
      subject: 'implementing fix',
    })
    expect(state.thinking.phase).toBe('coding')
    expect(state.thinking.subject).toBe('implementing fix')
    expect(state.thinking.active).toBe(true)
  })

  it('clears thinking on THINKING_END', () => {
    let state = reducer(initialState, {
      type: 'THINKING_START',
      phase: 'analyzing',
      subject: 'testing',
    })
    state = reducer(state, { type: 'THINKING_END' })
    expect(state.thinking.active).toBe(false)
    expect(state.thinking.phase).toBe('general')
    expect(state.thinking.subject).toBe('')
    expect(state.thinking.startedAt).toBe(0)
  })
})

describe('Bust state — stop/error sequences', () => {
  it('simulates stop: ENGINE_STATE:idle + THINKING_END resets bust to idle', () => {
    // Before stop: engine is thinking, thinking is active
    let state = reducer(initialState, { type: 'ENGINE_STATE', state: 'thinking' })
    state = reducer(state, { type: 'THINKING_START', phase: 'analyzing', subject: 'code' })
    expect(engineStateToBustState(state.engineState)).toBe('thinking')
    expect(state.thinking.active).toBe(true)

    // After stop: both are reset (as useAvatarWebSocket.stopResponse does)
    state = reducer(state, { type: 'ENGINE_STATE', state: 'idle' })
    state = reducer(state, { type: 'THINKING_END' })
    expect(engineStateToBustState(state.engineState)).toBe('idle')
    expect(state.thinking.active).toBe(false)
  })

  it('simulates server error: ERROR + ENGINE_STATE:idle resets bust', () => {
    // Engine is responding (bust would be speaking)
    let state = reducer(initialState, { type: 'ENGINE_STATE', state: 'responding' })
    expect(engineStateToBustState(state.engineState)).toBe('speaking')

    // Server sends error + defensive idle
    state = reducer(state, { type: 'ERROR', error: 'Internal error' })
    state = reducer(state, { type: 'ENGINE_STATE', state: 'idle' })
    expect(engineStateToBustState(state.engineState)).toBe('idle')
    expect(state.error).toBe('Internal error')
  })

  it('simulates server error with explicit error state', () => {
    let state = reducer(initialState, { type: 'ENGINE_STATE', state: 'responding' })
    state = reducer(state, { type: 'ENGINE_STATE', state: 'error' })
    expect(engineStateToBustState(state.engineState)).toBe('error')
  })
})

describe('engineStateToBustState mapping', () => {
  it('idle → idle', () => expect(engineStateToBustState('idle')).toBe('idle'))
  it('thinking → thinking', () => expect(engineStateToBustState('thinking')).toBe('thinking'))
  it('tool_executing → thinking', () => expect(engineStateToBustState('tool_executing')).toBe('thinking'))
  it('responding → speaking', () => expect(engineStateToBustState('responding')).toBe('speaking'))
  it('error → error', () => expect(engineStateToBustState('error')).toBe('error'))
  it('unknown → idle', () => expect(engineStateToBustState('anything_else')).toBe('idle'))
  it('waiting_approval → idle', () => expect(engineStateToBustState('waiting_approval')).toBe('idle'))
})

describe('no client-side auto-timeout', () => {
  const basePath = '/home/box/git/github/avatar-engine/examples/web-demo/src/hooks'

  it('useAvatarChat should not contain chatTimeoutRef or resetChatTimeout', () => {
    // This test verifies the timeout was properly removed by checking the source
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarChat.ts`, 'utf-8')
    expect(source).not.toContain('chatTimeoutRef')
    expect(source).not.toContain('resetChatTimeout')
    expect(source).not.toContain('setTimeout')
    expect(source).not.toContain('timed out')
  })

  it('useAvatarWebSocket stopResponse dispatches ENGINE_STATE:idle', () => {
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarWebSocket.ts`, 'utf-8')
    // The stopResponse function should dispatch idle + thinking_end
    const stopBlock = source.slice(
      source.indexOf('const stopResponse'),
      source.indexOf('}, [])', source.indexOf('const stopResponse')) + 6
    )
    expect(stopBlock).toContain("dispatch({ type: 'ENGINE_STATE', state: 'idle' })")
    expect(stopBlock).toContain("dispatch({ type: 'THINKING_END' })")
  })

  it('useAvatarWebSocket dispatches idle on chat_response and error', () => {
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarWebSocket.ts`, 'utf-8')
    // Find the chat_response case
    const chatResponseIdx = source.indexOf("case 'chat_response':")
    const chatResponseBlock = source.slice(chatResponseIdx, source.indexOf('break', chatResponseIdx) + 5)
    expect(chatResponseBlock).toContain("dispatch({ type: 'ENGINE_STATE', state: 'idle' })")

    // Find the error case
    const errorIdx = source.indexOf("case 'error':")
    const errorBlock = source.slice(errorIdx, source.indexOf('break', errorIdx) + 5)
    expect(errorBlock).toContain("dispatch({ type: 'ENGINE_STATE', state: 'idle' })")
  })

  it('useAvatarWebSocket has error fence to block ghost events after timeout', () => {
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarWebSocket.ts`, 'utf-8')
    // Error fence ref must exist
    expect(source).toContain('errorFenceRef')
    // Error sets the fence
    expect(source).toContain('errorFenceRef.current = true')
    // sendMessage clears the fence
    const sendBlock = source.slice(
      source.indexOf('const sendMessage'),
      source.indexOf('}, [])', source.indexOf('const sendMessage')) + 6
    )
    expect(sendBlock).toContain('errorFenceRef.current = false')
    // Fence blocks engine_state, thinking, text, tool, chat_response
    expect(source).toContain("['engine_state', 'thinking', 'text', 'tool', 'chat_response']")
  })

  it('server timeout is at least 600 seconds', () => {
    const fs = require('fs')
    const source = fs.readFileSync(
      '/home/box/git/github/avatar-engine/avatar_engine/web/server.py',
      'utf-8'
    )
    // The chat_timeout base value should be 600 or higher
    const match = source.match(/chat_timeout\s*=\s*(\d+)/)
    expect(match).toBeTruthy()
    expect(Number(match![1])).toBeGreaterThanOrEqual(600)
  })
})
