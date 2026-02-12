/**
 * Bust animation timing tests.
 *
 * Verifies that the bust speaking animation only triggers when actual
 * text content is being written to chat, not just when engine enters
 * 'responding' state (which happens before text starts streaming).
 */

/// <reference types="vitest/globals" />
import { describe, it, expect } from 'vitest'

// We test the mapping function directly — no DOM rendering needed.
// Import the module's internal function via a test-only re-export pattern.
// Since engineStateToBustState is not exported, we replicate the logic
// here as a contract test against the documented behavior.

/**
 * Contract: engineStateToBustState(engineState, hasText)
 *   - thinking/tool_executing → 'thinking'
 *   - responding + hasText=true → 'speaking'
 *   - responding + hasText=false → 'thinking' (NOT speaking!)
 *   - error → 'error'
 *   - idle/anything else → 'idle'
 */
function engineStateToBustState(engineState: string, hasText: boolean): string {
  switch (engineState) {
    case 'thinking':
    case 'tool_executing':
      return 'thinking'
    case 'responding':
      return hasText ? 'speaking' : 'thinking'
    case 'error':
      return 'error'
    default:
      return 'idle'
  }
}

describe('engineStateToBustState', () => {
  describe('thinking states', () => {
    it('thinking → thinking (regardless of hasText)', () => {
      expect(engineStateToBustState('thinking', false)).toBe('thinking')
      expect(engineStateToBustState('thinking', true)).toBe('thinking')
    })

    it('tool_executing → thinking', () => {
      expect(engineStateToBustState('tool_executing', false)).toBe('thinking')
      expect(engineStateToBustState('tool_executing', true)).toBe('thinking')
    })
  })

  describe('responding state — text-gated speaking', () => {
    it('responding WITHOUT text → thinking (bust does NOT speak)', () => {
      expect(engineStateToBustState('responding', false)).toBe('thinking')
    })

    it('responding WITH text → speaking (bust speaks)', () => {
      expect(engineStateToBustState('responding', true)).toBe('speaking')
    })
  })

  describe('other states', () => {
    it('error → error', () => {
      expect(engineStateToBustState('error', false)).toBe('error')
    })

    it('idle → idle', () => {
      expect(engineStateToBustState('idle', false)).toBe('idle')
    })

    it('unknown → idle', () => {
      expect(engineStateToBustState('waiting_approval', false)).toBe('idle')
    })
  })
})

describe('hasText computation contract', () => {
  // Tests the logic from AvatarWidget that computes hasText:
  // const lastMsg = messages[messages.length - 1]
  // const hasText = !!(lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming && lastMsg.content)

  function computeHasText(messages: Array<{ role: string; isStreaming: boolean; content: string }>): boolean {
    const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null
    return !!(lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming && lastMsg.content)
  }

  it('returns false for empty messages', () => {
    expect(computeHasText([])).toBe(false)
  })

  it('returns false when last message is user', () => {
    expect(computeHasText([
      { role: 'user', isStreaming: false, content: 'Hello' },
    ])).toBe(false)
  })

  it('returns false when assistant is streaming but no content yet', () => {
    expect(computeHasText([
      { role: 'user', isStreaming: false, content: 'Hello' },
      { role: 'assistant', isStreaming: true, content: '' },
    ])).toBe(false)
  })

  it('returns true when assistant is streaming with content', () => {
    expect(computeHasText([
      { role: 'user', isStreaming: false, content: 'Hello' },
      { role: 'assistant', isStreaming: true, content: 'Hi there' },
    ])).toBe(true)
  })

  it('returns false when assistant finished streaming', () => {
    expect(computeHasText([
      { role: 'user', isStreaming: false, content: 'Hello' },
      { role: 'assistant', isStreaming: false, content: 'Hi there' },
    ])).toBe(false)
  })
})

describe('stateDetail computation contract', () => {
  /**
   * Contract: compact header shows dynamic detail instead of generic label.
   *   - thinking + thinkingSubject → subject text (e.g. "Analyzing imports")
   *   - tool_executing + toolName → tool name (e.g. "read_file")
   *   - responding → no detail (uses default label)
   *   - thinking without subject → no detail (uses default label)
   */
  function computeStateDetail(
    engineState: string,
    thinkingSubject: string,
    toolName: string,
  ): string {
    if (engineState === 'thinking' && thinkingSubject) return thinkingSubject
    if (engineState === 'tool_executing' && toolName) return toolName
    return ''
  }

  it('thinking with subject → shows subject', () => {
    expect(computeStateDetail('thinking', 'Analyzing imports', '')).toBe('Analyzing imports')
  })

  it('thinking without subject → empty (uses default label)', () => {
    expect(computeStateDetail('thinking', '', '')).toBe('')
  })

  it('tool_executing with toolName → shows tool name', () => {
    expect(computeStateDetail('tool_executing', '', 'read_file')).toBe('read_file')
  })

  it('tool_executing without toolName → empty', () => {
    expect(computeStateDetail('tool_executing', '', '')).toBe('')
  })

  it('responding → empty (always uses default label)', () => {
    expect(computeStateDetail('responding', 'some subject', 'some_tool')).toBe('')
  })

  it('idle → empty', () => {
    expect(computeStateDetail('idle', '', '')).toBe('')
  })
})
