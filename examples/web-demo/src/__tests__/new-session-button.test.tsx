/**
 * New Session button tests — CompactHeader and StatusBar.
 *
 * Verifies:
 *   1. Button renders when onNewSession prop is provided
 *   2. Button hidden when onNewSession is not provided
 *   3. Button disabled when !connected or isStreaming
 *   4. Click calls onNewSession callback
 */

/// <reference types="vitest/globals" />
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CompactHeader, StatusBar } from '@avatar-engine/react'

const TEST_CAPS = {
  can_list_sessions: true,
  can_load_session: true,
  can_continue_last: true,
  thinking_supported: true,
  thinking_structured: false,
  cost_tracking: false,
  budget_enforcement: false,
  system_prompt_method: 'system' as const,
  streaming: true,
  parallel_tools: false,
  cancellable: false,
  mcp_supported: false,
}

// --------------- CompactHeader tests ---------------

describe('CompactHeader — New Session button', () => {
  const baseProps = {
    provider: 'gemini',
    model: 'gemini-2.5-pro',
    connected: true,
    engineState: 'idle' as const,
    onFullscreen: vi.fn(),
    onClose: vi.fn(),
  }

  it('renders + button when onNewSession is provided', () => {
    render(<CompactHeader {...baseProps} onNewSession={vi.fn()} />)
    expect(screen.getByRole('button', { name: /new session/i })).toBeInTheDocument()
  })

  it('does not render + button when onNewSession is not provided', () => {
    render(<CompactHeader {...baseProps} />)
    expect(screen.queryByRole('button', { name: /new session/i })).not.toBeInTheDocument()
  })

  it('button is disabled when not connected', () => {
    render(
      <CompactHeader {...baseProps} connected={false} onNewSession={vi.fn()} />,
    )
    const btn = screen.getByRole('button', { name: /new session/i })
    expect(btn).toBeDisabled()
  })

  it('button is disabled when streaming', () => {
    render(
      <CompactHeader {...baseProps} isStreaming={true} onNewSession={vi.fn()} />,
    )
    const btn = screen.getByRole('button', { name: /new session/i })
    expect(btn).toBeDisabled()
  })

  it('button is enabled when connected and not streaming', () => {
    render(
      <CompactHeader
        {...baseProps}
        connected={true}
        isStreaming={false}
        onNewSession={vi.fn()}
      />,
    )
    const btn = screen.getByRole('button', { name: /new session/i })
    expect(btn).not.toBeDisabled()
  })

  it('click calls onNewSession callback', () => {
    const onNewSession = vi.fn()
    render(<CompactHeader {...baseProps} onNewSession={onNewSession} />)
    fireEvent.click(screen.getByRole('button', { name: /new session/i }))
    expect(onNewSession).toHaveBeenCalledOnce()
  })
})

// --------------- StatusBar tests ---------------

describe('StatusBar — New Session button', () => {
  const baseProps = {
    connected: true,
    provider: 'gemini',
    model: 'gemini-2.5-pro',
    version: '1.3.0',
    engineState: 'idle' as const,
    capabilities: TEST_CAPS,
    sessionId: 'test-session',
    cost: { totalCostUsd: 0, totalInputTokens: 0, totalOutputTokens: 0 },
  }

  it('renders + button when onNewSession is provided', () => {
    render(<StatusBar {...baseProps} onNewSession={vi.fn()} />)
    expect(screen.getByRole('button', { name: /new session/i })).toBeInTheDocument()
  })

  it('does not render + button when onNewSession is not provided', () => {
    render(<StatusBar {...baseProps} />)
    expect(screen.queryByRole('button', { name: /new session/i })).not.toBeInTheDocument()
  })

  it('button is disabled when not connected', () => {
    render(
      <StatusBar {...baseProps} connected={false} onNewSession={vi.fn()} />,
    )
    const btn = screen.getByRole('button', { name: /new session/i })
    expect(btn).toBeDisabled()
  })

  it('button is disabled when streaming', () => {
    render(
      <StatusBar {...baseProps} isStreaming={true} onNewSession={vi.fn()} />,
    )
    const btn = screen.getByRole('button', { name: /new session/i })
    expect(btn).toBeDisabled()
  })

  it('button is enabled when connected and not streaming', () => {
    render(
      <StatusBar
        {...baseProps}
        isStreaming={false}
        onNewSession={vi.fn()}
      />,
    )
    const btn = screen.getByRole('button', { name: /new session/i })
    expect(btn).not.toBeDisabled()
  })

  it('click calls onNewSession callback', () => {
    const onNewSession = vi.fn()
    render(<StatusBar {...baseProps} onNewSession={onNewSession} />)
    fireEvent.click(screen.getByRole('button', { name: /new session/i }))
    expect(onNewSession).toHaveBeenCalledOnce()
  })
})
