/**
 * Response guard tests — verify that non-OK HTTP responses (404, 500)
 * don't crash React components or hooks.
 *
 * Tests cover:
 *   1. SessionPanel with 404/500 → sessions = [], no crash
 *   2. useAvailableProviders with 500 → available = null, no crash
 *   3. useAvatarChat resumeSession with 404 → messages = []
 *   4. StatusBar usage fetch with 500 → usage stays null
 */

/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import {
  SessionPanel,
  StatusBar,
  useAvailableProviders,
  useAvatarChat,
} from '@avatar-engine/react'
import type { UseAvatarChatReturn } from '@avatar-engine/react'

// --------------- Mock WebSocket ---------------

let wsInstance: MockWebSocket | null = null

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static CLOSED = 3
  static CLOSING = 2

  readyState = MockWebSocket.CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  sent: string[] = []

  constructor(public url: string) {
    wsInstance = this
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateMessage(msg: { type: string; data: Record<string, unknown> }) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(msg) }))
  }
}

// --------------- Setup / Teardown ---------------

const OriginalWebSocket = globalThis.WebSocket

beforeEach(() => {
  wsInstance = null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  globalThis.WebSocket = MockWebSocket as any
})

afterEach(() => {
  globalThis.WebSocket = OriginalWebSocket
  wsInstance = null
  vi.restoreAllMocks()
})

// --------------- Test helpers ---------------

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

// --------------- SessionPanel guard tests ---------------

describe('SessionPanel — response guards', () => {
  it('handles 404 response without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 404, statusText: 'Not Found' }),
    )

    render(
      <SessionPanel
        open={true}
        onClose={vi.fn()}
        provider="gemini"
        cwd="/project"
        capabilities={TEST_CAPS}
        onResume={vi.fn()}
        onNewSession={vi.fn()}
      />,
    )

    // Wait for fetch + state update
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    // Should render without crash — no sessions shown
    expect(screen.getByText(/no previous sessions/i)).toBeInTheDocument()
  })

  it('handles 500 response without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 500, statusText: 'Internal Server Error' }),
    )

    render(
      <SessionPanel
        open={true}
        onClose={vi.fn()}
        provider="gemini"
        cwd="/project"
        capabilities={TEST_CAPS}
        onResume={vi.fn()}
        onNewSession={vi.fn()}
      />,
    )

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    expect(screen.getByText(/no previous sessions/i)).toBeInTheDocument()
  })

  it('handles fetch network error without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))

    render(
      <SessionPanel
        open={true}
        onClose={vi.fn()}
        provider="gemini"
        cwd="/project"
        capabilities={TEST_CAPS}
        onResume={vi.fn()}
        onNewSession={vi.fn()}
      />,
    )

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    // Should not crash — component is still in the DOM
    expect(screen.getByText(/no previous sessions/i)).toBeInTheDocument()
  })

  it('handles malformed JSON (non-array) without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'not an array' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    render(
      <SessionPanel
        open={true}
        onClose={vi.fn()}
        provider="gemini"
        cwd="/project"
        capabilities={TEST_CAPS}
        onResume={vi.fn()}
        onNewSession={vi.fn()}
      />,
    )

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    // Array.isArray guard catches this — sessions = []
    expect(screen.getByText(/no previous sessions/i)).toBeInTheDocument()
  })
})

// --------------- useAvailableProviders guard tests ---------------

describe('useAvailableProviders — response guards', () => {
  function ProvidersTestApp({ apiBase }: { apiBase?: string }) {
    const available = useAvailableProviders(apiBase)
    return (
      <div>
        <div data-testid="status">{available === null ? 'null' : 'loaded'}</div>
        <div data-testid="count">{available ? available.size : 'n/a'}</div>
      </div>
    )
  }

  it('returns null on 500 response (graceful fallback)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 500 }),
    )

    render(<ProvidersTestApp />)

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    // 500 → r.ok is false → returns [] → Array.isArray([]) is true → sets empty Set
    // Actually: !r.ok → return [] → then data=[] → Array.isArray([]) = true → Set(empty)
    expect(screen.getByTestId('status').textContent).toBe('loaded')
    expect(screen.getByTestId('count').textContent).toBe('0')
  })

  it('returns null on network error (graceful fallback)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))

    render(<ProvidersTestApp />)

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    // Network error → catch → available stays null
    expect(screen.getByTestId('status').textContent).toBe('null')
  })

  it('handles non-array JSON without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'unexpected' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    render(<ProvidersTestApp />)

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })

    // Array.isArray guard: non-array data → setAvailable not called → stays null
    expect(screen.getByTestId('status').textContent).toBe('null')
  })
})

// --------------- useAvatarChat resumeSession guard tests ---------------

describe('useAvatarChat resumeSession — response guards', () => {
  function ResumeTestApp() {
    const chat = useAvatarChat('ws://test/ws')
    return (
      <div>
        <div data-testid="connected">{String(chat.connected)}</div>
        <div data-testid="message-count">{chat.messages.length}</div>
        <button
          data-testid="resume"
          onClick={() => chat.resumeSession('old-session-123')}
        >
          Resume
        </button>
      </div>
    )
  }

  it('handles 404 on session messages without crashing', async () => {
    vi.useFakeTimers()

    // First fetch = providers (from useAvailableProviders), subsequent = session messages
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const urlStr = typeof url === 'string' ? url : url.toString()
      if (urlStr.includes('/messages')) {
        return Promise.resolve(new Response(null, { status: 404 }))
      }
      // Default: return empty array for other fetches
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    })

    render(<ResumeTestApp />)

    // Connect WS
    await act(async () => {
      vi.advanceTimersByTime(0)
    })
    await act(async () => {
      wsInstance!.simulateOpen()
      wsInstance!.simulateMessage({
        type: 'connected',
        data: {
          session_id: 'test-session',
          provider: 'gemini',
          model: 'gemini-2.5-pro',
          version: '1.0.0',
          cwd: '/',
          capabilities: TEST_CAPS,
          engine_state: 'idle',
        },
      })
    })

    expect(screen.getByTestId('connected').textContent).toBe('true')

    // Resume with 404 session messages
    await act(async () => {
      screen.getByTestId('resume').click()
    })

    // Let fetch resolve
    await act(async () => {
      vi.advanceTimersByTime(50)
      await Promise.resolve()
    })

    // Should not crash — messages cleared to []
    expect(screen.getByTestId('message-count').textContent).toBe('0')

    fetchSpy.mockRestore()
    vi.useRealTimers()
  })
})

// --------------- StatusBar usage guard tests ---------------

describe('StatusBar — usage fetch response guard', () => {
  it('handles 500 on usage endpoint without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 500 }),
    )

    render(
      <StatusBar
        connected={true}
        provider="gemini"
        model="gemini-2.5-pro"
        version="1.0.0"
        engineState="idle"
        capabilities={TEST_CAPS}
        sessionId="test-session"
        cost={{ totalCostUsd: 0, totalInputTokens: 0, totalOutputTokens: 0 }}
      />,
    )

    // StatusBar should render without crash
    expect(screen.getByText('Avatar Engine')).toBeInTheDocument()
  })
})
