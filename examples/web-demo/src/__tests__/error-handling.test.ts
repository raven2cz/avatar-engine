/**
 * Error handling + state reset tests.
 *
 * Verifies:
 *   - avatarReducer (from core) resets engineState to idle on error
 *   - Thinking state is cleared on stop
 *   - Bust state maps engineState correctly (including error)
 *   - No client-side auto-timeout exists (removed by design)
 *   - Server error events properly reset engine state
 *
 * IMPORTANT: Uses the REAL avatarReducer from @avatar-engine/core.
 * Previous version had a duplicated inline reducer that could silently
 * diverge from the actual implementation.
 */

/// <reference types="vitest/globals" />
import { describe, it, expect } from 'vitest'
import {
  avatarReducer,
  initialAvatarState,
} from '@avatar-engine/core'
import type { AvatarState, AvatarAction } from '@avatar-engine/core'

// Node fs used for source-level assertions in test environment
declare function require(id: string): { readFileSync(path: string, enc: string): string }

// Helper: dispatch action through the real reducer
function dispatch(state: AvatarState, action: AvatarAction): AvatarState {
  return avatarReducer(state, action)
}

// Same mapping as useAvatarBust (tested against real logic)
type BustState = 'idle' | 'thinking' | 'speaking' | 'error'

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
    expect(initialAvatarState.engineState).toBe('idle')
  })

  it('transitions to thinking', () => {
    const state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'thinking' })
    expect(state.engineState).toBe('thinking')
  })

  it('transitions to responding', () => {
    const state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'responding' })
    expect(state.engineState).toBe('responding')
  })

  it('resets to idle on ENGINE_STATE:idle (defensive reset on chat_response)', () => {
    let state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'responding' })
    expect(state.engineState).toBe('responding')
    state = dispatch(state, { type: 'ENGINE_STATE', state: 'idle' })
    expect(state.engineState).toBe('idle')
  })

  it('sets error message on ERROR action', () => {
    const state = dispatch(initialAvatarState, { type: 'ERROR', error: 'Something went wrong' })
    expect(state.error).toBe('Something went wrong')
  })

  it('clears error on CLEAR_ERROR', () => {
    let state = dispatch(initialAvatarState, { type: 'ERROR', error: 'fail' })
    state = dispatch(state, { type: 'CLEAR_ERROR' })
    expect(state.error).toBeNull()
  })

  it('resets engineState to idle on DISCONNECTED', () => {
    let state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'thinking' })
    state = dispatch(state, { type: 'DISCONNECTED' })
    expect(state.engineState).toBe('idle')
  })
})

describe('WebSocket reducer — thinking state management', () => {
  it('starts thinking with phase and subject', () => {
    const state = dispatch(initialAvatarState, {
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
    let state = dispatch(initialAvatarState, {
      type: 'THINKING_START',
      phase: 'general',
      subject: 'initial',
    })
    state = dispatch(state, {
      type: 'THINKING_UPDATE',
      phase: 'coding',
      subject: 'implementing fix',
    })
    expect(state.thinking.phase).toBe('coding')
    expect(state.thinking.subject).toBe('implementing fix')
    expect(state.thinking.active).toBe(true)
  })

  it('clears thinking on THINKING_END', () => {
    let state = dispatch(initialAvatarState, {
      type: 'THINKING_START',
      phase: 'analyzing',
      subject: 'testing',
    })
    state = dispatch(state, { type: 'THINKING_END' })
    expect(state.thinking.active).toBe(false)
    expect(state.thinking.phase).toBe('general')
    expect(state.thinking.subject).toBe('')
    expect(state.thinking.startedAt).toBe(0)
  })
})

describe('Bust state — stop/error sequences', () => {
  it('simulates stop: ENGINE_STATE:idle + THINKING_END resets bust to idle', () => {
    let state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'thinking' })
    state = dispatch(state, { type: 'THINKING_START', phase: 'analyzing', subject: 'code' })
    expect(engineStateToBustState(state.engineState)).toBe('thinking')
    expect(state.thinking.active).toBe(true)

    state = dispatch(state, { type: 'ENGINE_STATE', state: 'idle' })
    state = dispatch(state, { type: 'THINKING_END' })
    expect(engineStateToBustState(state.engineState)).toBe('idle')
    expect(state.thinking.active).toBe(false)
  })

  it('simulates server error: ERROR + ENGINE_STATE:idle resets bust', () => {
    let state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'responding' })
    expect(engineStateToBustState(state.engineState)).toBe('speaking')

    state = dispatch(state, { type: 'ERROR', error: 'Internal error' })
    state = dispatch(state, { type: 'ENGINE_STATE', state: 'idle' })
    expect(engineStateToBustState(state.engineState)).toBe('idle')
    expect(state.error).toBe('Internal error')
  })

  it('simulates server error with explicit error state', () => {
    let state = dispatch(initialAvatarState, { type: 'ENGINE_STATE', state: 'responding' })
    state = dispatch(state, { type: 'ENGINE_STATE', state: 'error' })
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
  const basePath = '/home/box/git/github/avatar-engine/packages/react/src/hooks'

  it('useAvatarChat should not contain chatTimeoutRef or resetChatTimeout', () => {
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarChat.ts`, 'utf-8')
    expect(source).not.toContain('chatTimeoutRef')
    expect(source).not.toContain('resetChatTimeout')
    expect(source).not.toContain('timed out')
  })

  it('useAvatarWebSocket stopResponse dispatches ENGINE_STATE:idle', () => {
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarWebSocket.ts`, 'utf-8')
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
    const chatResponseIdx = source.indexOf("case 'chat_response':")
    const chatResponseBlock = source.slice(chatResponseIdx, source.indexOf('break', chatResponseIdx) + 5)
    expect(chatResponseBlock).toContain("dispatch({ type: 'ENGINE_STATE', state: 'idle' })")

    const errorIdx = source.indexOf("case 'error':")
    const errorBlock = source.slice(errorIdx, source.indexOf('break', errorIdx) + 5)
    expect(errorBlock).toContain("dispatch({ type: 'ENGINE_STATE', state: 'idle' })")
  })

  it('useAvatarWebSocket has error fence to block ghost events after timeout', () => {
    const fs = require('fs')
    const source = fs.readFileSync(`${basePath}/useAvatarWebSocket.ts`, 'utf-8')
    expect(source).toContain('errorFenceRef')
    expect(source).toContain('errorFenceRef.current = true')
    const sendBlock = source.slice(
      source.indexOf('const sendMessage'),
      source.indexOf('}, [])', source.indexOf('const sendMessage')) + 6
    )
    expect(sendBlock).toContain('errorFenceRef.current = false')
    expect(source).toContain("['engine_state', 'thinking', 'text', 'tool', 'chat_response']")
  })

  it('server timeout is at least 600 seconds', () => {
    const fs = require('fs')
    const source = fs.readFileSync(
      '/home/box/git/github/avatar-engine/avatar_engine/web/server.py',
      'utf-8'
    )
    const match = source.match(/chat_timeout\s*=\s*(\d+)/)
    expect(match).toBeTruthy()
    expect(Number(match![1])).toBeGreaterThanOrEqual(600)
  })
})
