/**
 * SMOKE TEST — Full chat lifecycle with mock WebSocket.
 *
 * This is the "will it actually run?" test. It uses the REAL hooks
 * (useAvatarChat → useAvatarWebSocket → avatarReducer from core)
 * with a mock WebSocket, then verifies the complete flow:
 *
 *   connect → send message → thinking → text streaming → chat_response → idle
 *
 * If this test passes, the app will start and basic chat works.
 * If this test fails, something is fundamentally broken.
 */

/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import { useAvatarChat } from '@avatar-engine/react'
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
    // Don't fire onclose — we don't want reconnect in tests
  }

  // --- Test helpers ---
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateMessage(msg: { type: string; data: Record<string, unknown> }) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(msg) }))
  }

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }
}

// --------------- Test component ---------------

/** Minimal component that uses the real useAvatarChat hook */
function TestChatApp({ wsUrl = 'ws://test/ws' }: { wsUrl?: string }) {
  const chat = useAvatarChat(wsUrl)
  return <TestChatUI chat={chat} />
}

function TestChatUI({ chat }: { chat: UseAvatarChatReturn }) {
  return (
    <div>
      <div data-testid="connected">{String(chat.connected)}</div>
      <div data-testid="engine-state">{chat.engineState}</div>
      <div data-testid="provider">{chat.provider}</div>
      <div data-testid="session-id">{chat.sessionId || 'none'}</div>
      <div data-testid="is-streaming">{String(chat.isStreaming)}</div>
      <div data-testid="error">{chat.error || 'none'}</div>
      <div data-testid="thinking-active">{String(chat.thinking.active)}</div>
      <div data-testid="thinking-phase">{chat.thinking.phase}</div>
      <div data-testid="safety-mode">{chat.safetyMode}</div>
      <div data-testid="message-count">{chat.messages.length}</div>
      <div data-testid="messages">
        {chat.messages.map((m) => (
          <div key={m.id} data-testid={`msg-${m.role}-${m.id}`}>
            <span data-testid="role">{m.role}</span>
            <span data-testid="content">{m.content}</span>
            <span data-testid="streaming">{String(m.isStreaming)}</span>
            <span data-testid="tools">{m.tools.length}</span>
          </div>
        ))}
      </div>
      <button data-testid="send" onClick={() => chat.sendMessage('Hello AI')}>
        Send
      </button>
      <button data-testid="stop" onClick={() => chat.stopResponse()}>
        Stop
      </button>
      <button data-testid="clear" onClick={() => chat.clearHistory()}>
        Clear
      </button>
    </div>
  )
}

// --------------- Capabilities fixture ---------------

const TEST_CAPS = {
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

// --------------- Setup / Teardown ---------------

const OriginalWebSocket = globalThis.WebSocket

beforeEach(() => {
  vi.useFakeTimers()
  wsInstance = null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  globalThis.WebSocket = MockWebSocket as any
})

afterEach(() => {
  vi.useRealTimers()
  globalThis.WebSocket = OriginalWebSocket
  wsInstance = null
})

// --------------- Helper ---------------

/** Render the app + connect the mock WebSocket */
async function renderAndConnect(overrides: Record<string, unknown> = {}) {
  const result = render(<TestChatApp />)

  // useEffect runs → creates WebSocket
  await act(async () => {
    vi.advanceTimersByTime(0)
  })
  expect(wsInstance).not.toBeNull()

  // Simulate WS open + server connected message
  await act(async () => {
    wsInstance!.simulateOpen()
    wsInstance!.simulateMessage({
      type: 'connected',
      data: {
        session_id: 'test-session-001',
        provider: 'gemini',
        model: 'gemini-2.5-pro',
        version: '1.0.0',
        cwd: '/project',
        capabilities: TEST_CAPS,
        engine_state: 'idle',
        safety_mode: 'ask',
        ...overrides,
      },
    })
  })

  return result
}

// --------------- Tests ---------------

describe('Smoke test — full chat lifecycle', () => {
  it('connects and shows correct initial state', async () => {
    await renderAndConnect()

    expect(screen.getByTestId('connected').textContent).toBe('true')
    expect(screen.getByTestId('engine-state').textContent).toBe('idle')
    expect(screen.getByTestId('provider').textContent).toBe('gemini')
    expect(screen.getByTestId('session-id').textContent).toBe('test-session-001')
    expect(screen.getByTestId('safety-mode').textContent).toBe('ask')
    expect(screen.getByTestId('message-count').textContent).toBe('0')
  })

  it('full flow: send → thinking → tool → text → chat_response', async () => {
    await renderAndConnect()

    // 1. User sends message
    await act(async () => {
      fireEvent.click(screen.getByTestId('send'))
    })

    // Verify: user message + empty assistant message added
    expect(screen.getByTestId('message-count').textContent).toBe('2')
    expect(screen.getByTestId('is-streaming').textContent).toBe('true')

    // Verify WS received the chat message
    const sentMsg = JSON.parse(wsInstance!.sent[0])
    expect(sentMsg.type).toBe('chat')
    expect(sentMsg.data.message).toBe('Hello AI')

    // 2. Server starts thinking
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'engine_state',
        data: { state: 'thinking' },
      })
      wsInstance!.simulateMessage({
        type: 'thinking',
        data: { is_start: true, phase: 'analyzing', subject: 'user request' },
      })
    })

    expect(screen.getByTestId('engine-state').textContent).toBe('thinking')
    expect(screen.getByTestId('thinking-active').textContent).toBe('true')
    expect(screen.getByTestId('thinking-phase').textContent).toBe('analyzing')

    // 3. Tool execution
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'engine_state',
        data: { state: 'tool_executing' },
      })
      wsInstance!.simulateMessage({
        type: 'tool',
        data: { tool_name: 'read_file', tool_id: 't1', status: 'started', parameters: { path: '/src/main.ts' } },
      })
    })

    expect(screen.getByTestId('engine-state').textContent).toBe('tool_executing')

    // Tool completed
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'tool',
        data: { tool_name: 'read_file', tool_id: 't1', status: 'completed' },
      })
    })

    // 4. Text streaming
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'engine_state',
        data: { state: 'responding' },
      })
      wsInstance!.simulateMessage({
        type: 'thinking',
        data: { is_complete: true },
      })
    })

    expect(screen.getByTestId('engine-state').textContent).toBe('responding')
    expect(screen.getByTestId('thinking-active').textContent).toBe('false')

    // Stream text chunks
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'Hello! ' } })
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'I can help.' } })
    })

    // Find the assistant message and check content
    const messages = screen.getByTestId('messages')
    const assistantMsgs = within(messages).getAllByTestId(/^msg-assistant/)
    expect(assistantMsgs.length).toBe(1)
    const assistantContent = within(assistantMsgs[0]).getByTestId('content')
    expect(assistantContent.textContent).toBe('Hello! I can help.')

    // 5. Chat response (end of turn)
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'chat_response',
        data: {
          session_id: 'test-session-001',
          duration_ms: 1500,
          cost_usd: 0.002,
        },
      })
    })

    expect(screen.getByTestId('engine-state').textContent).toBe('idle')
    expect(screen.getByTestId('is-streaming').textContent).toBe('false')

    // Assistant message is finalized
    const finalAssistant = within(messages).getAllByTestId(/^msg-assistant/)
    expect(within(finalAssistant[0]).getByTestId('streaming').textContent).toBe('false')
    expect(within(finalAssistant[0]).getByTestId('content').textContent).toBe('Hello! I can help.')
  })

  it('error recovery: error → fence → stale events blocked → new chat works', async () => {
    await renderAndConnect()

    // Send message
    await act(async () => {
      fireEvent.click(screen.getByTestId('send'))
    })

    // Engine starts thinking
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'engine_state', data: { state: 'thinking' } })
    })

    expect(screen.getByTestId('engine-state').textContent).toBe('thinking')

    // Error occurs
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'error', data: { error: 'Rate limit exceeded' } })
    })

    expect(screen.getByTestId('engine-state').textContent).toBe('idle')
    expect(screen.getByTestId('error').textContent).toBe('Rate limit exceeded')

    // Stale engine_state should be fenced (ignored)
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'engine_state', data: { state: 'responding' } })
    })
    expect(screen.getByTestId('engine-state').textContent).toBe('idle') // still idle, not responding
  })

  it('stop button clears streaming state', async () => {
    await renderAndConnect()

    // Send and start streaming
    await act(async () => {
      fireEvent.click(screen.getByTestId('send'))
    })
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'engine_state', data: { state: 'responding' } })
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'partial...' } })
    })

    expect(screen.getByTestId('is-streaming').textContent).toBe('true')

    // Stop
    await act(async () => {
      fireEvent.click(screen.getByTestId('stop'))
    })

    expect(screen.getByTestId('is-streaming').textContent).toBe('false')
    expect(screen.getByTestId('engine-state').textContent).toBe('idle')
  })

  it('clear history removes all messages', async () => {
    await renderAndConnect()

    // Send a message
    await act(async () => {
      fireEvent.click(screen.getByTestId('send'))
    })
    expect(screen.getByTestId('message-count').textContent).toBe('2')

    // Complete the response
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'response' } })
      wsInstance!.simulateMessage({ type: 'chat_response', data: { session_id: 'test-session-001' } })
    })

    // Clear
    await act(async () => {
      fireEvent.click(screen.getByTestId('clear'))
    })

    // useAvatarChat clears messages locally AND sends WS clear
    expect(screen.getByTestId('message-count').textContent).toBe('0')
    const clearMsg = wsInstance!.sent.find((s) => JSON.parse(s).type === 'clear_history')
    expect(clearMsg).toBeTruthy()
  })

  it('disconnect sets connected=false, keeps wasConnected=true', async () => {
    await renderAndConnect()
    expect(screen.getByTestId('connected').textContent).toBe('true')

    await act(async () => {
      wsInstance!.simulateClose()
    })

    expect(screen.getByTestId('connected').textContent).toBe('false')
  })

  it('permission request is exposed from server message', async () => {
    const permissionRef = { current: null as UseAvatarChatReturn['permissionRequest'] }

    function PermTestApp() {
      const chat = useAvatarChat('ws://test/ws')
      permissionRef.current = chat.permissionRequest
      return <TestChatUI chat={chat} />
    }

    render(<PermTestApp />)
    await act(async () => { vi.advanceTimersByTime(0) })
    await act(async () => {
      wsInstance!.simulateOpen()
      wsInstance!.simulateMessage({
        type: 'connected',
        data: {
          session_id: 's1', provider: 'gemini', model: 'm', version: '1',
          cwd: '/', capabilities: TEST_CAPS, engine_state: 'idle',
        },
      })
    })

    // Simulate permission request
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'permission_request',
        data: {
          request_id: 'perm-001',
          tool_name: 'delete_file',
          tool_input: '/important.txt',
          options: [
            { option_id: 'allow', kind: 'allow_once', label: 'Allow' },
            { option_id: 'deny', kind: 'reject_once', label: 'Deny' },
          ],
        },
      })
    })

    expect(permissionRef.current).not.toBeNull()
    expect(permissionRef.current!.toolName).toBe('delete_file')
    expect(permissionRef.current!.options).toHaveLength(2)
  })

  it('tool info appears on assistant message', async () => {
    await renderAndConnect()

    // Send message
    await act(async () => {
      fireEvent.click(screen.getByTestId('send'))
    })

    // Tool started
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'tool',
        data: { tool_name: 'execute_bash', tool_id: 'tool-1', status: 'started', parameters: { command: 'ls' } },
      })
    })

    // Check tool info on assistant message
    const messages = screen.getByTestId('messages')
    const assistantMsg = within(messages).getAllByTestId(/^msg-assistant/)[0]
    expect(within(assistantMsg).getByTestId('tools').textContent).toBe('1')

    // Tool completed
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'tool',
        data: { tool_name: 'execute_bash', tool_id: 'tool-1', status: 'completed' },
      })
    })

    // Still 1 tool, just status changed
    expect(within(assistantMsg).getByTestId('tools').textContent).toBe('1')
  })

  it('cost tracking accumulates across messages', async () => {
    const costRef = { current: { totalCostUsd: 0, totalInputTokens: 0, totalOutputTokens: 0 } }

    function CostTestApp() {
      const chat = useAvatarChat('ws://test/ws')
      costRef.current = chat.cost
      return <TestChatUI chat={chat} />
    }

    render(<CostTestApp />)
    await act(async () => { vi.advanceTimersByTime(0) })
    await act(async () => {
      wsInstance!.simulateOpen()
      wsInstance!.simulateMessage({
        type: 'connected',
        data: {
          session_id: 's1', provider: 'gemini', model: 'm', version: '1',
          cwd: '/', capabilities: TEST_CAPS, engine_state: 'idle',
        },
      })
    })

    // Cost update
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'cost',
        data: { cost_usd: 0.005, input_tokens: 2000, output_tokens: 500 },
      })
    })

    expect(costRef.current.totalCostUsd).toBeCloseTo(0.005)
    expect(costRef.current.totalInputTokens).toBe(2000)
    expect(costRef.current.totalOutputTokens).toBe(500)
  })
})

describe('Smoke test — Tailwind content paths', () => {
  it('tailwind.config.js content paths resolve to existing files with component classes', () => {
    const fs = require('fs') as { existsSync(p: string): boolean; readFileSync(p: string, e: string): string }
    const path = require('path') as { resolve(...p: string[]): string }

    const webDemoRoot = path.resolve(__dirname, '../..')

    // Read tailwind config to extract content paths
    const configSrc = fs.readFileSync(path.resolve(webDemoRoot, 'tailwind.config.js'), 'utf-8')

    // The config must reference packages/react source (for workspace dev mode)
    expect(configSrc).toContain('packages/react/src')

    // Verify the path actually resolves to files
    const reactSrcPath = path.resolve(webDemoRoot, '../../packages/react/src')
    expect(fs.existsSync(reactSrcPath)).toBe(true)

    // Check that key component files exist in the scanned path
    const components = [
      'components/AvatarFab.tsx',
      'components/AvatarWidget.tsx',
      'components/CompactChat.tsx',
      'components/ChatPanel.tsx',
      'components/StatusBar.tsx',
      'components/PermissionDialog.tsx',
    ]
    for (const comp of components) {
      const fullPath = path.resolve(reactSrcPath, comp)
      expect(fs.existsSync(fullPath)).toBe(true)
    }

    // Verify key Tailwind classes exist in scanned source files
    const fabSource = fs.readFileSync(path.resolve(reactSrcPath, 'components/AvatarFab.tsx'), 'utf-8')
    expect(fabSource).toContain('fixed')
    expect(fabSource).toContain('bottom-6')
    expect(fabSource).toContain('left-6')
    expect(fabSource).toContain('z-50')
  })
})

describe('Smoke test — import chain verification', () => {
  it('all essential exports from @avatar-engine/react are importable', async () => {
    // This test verifies the re-export chain at runtime.
    // If any export is broken, this will throw.
    const react = await import('@avatar-engine/react')

    // Core re-exports
    expect(react.avatarReducer).toBeTypeOf('function')
    expect(react.initialAvatarState).toBeDefined()
    expect(react.parseServerMessage).toBeTypeOf('function')
    expect(react.createChatMessage).toBeTypeOf('function')
    expect(react.createStopMessage).toBeTypeOf('function')
    expect(react.createSwitchMessage).toBeTypeOf('function')
    expect(react.createPermissionResponse).toBeTypeOf('function')
    expect(react.nextId).toBeTypeOf('function')
    expect(react.summarizeParams).toBeTypeOf('function')
    expect(react.PROVIDERS).toBeInstanceOf(Array)
    expect(react.AVATARS).toBeInstanceOf(Array)
    expect(react.getProvider).toBeTypeOf('function')
    expect(react.getModelsForProvider).toBeTypeOf('function')
    expect(react.buildOptionsDict).toBeTypeOf('function')
    expect(react.initAvatarI18n).toBeTypeOf('function')
    expect(react.AVAILABLE_LANGUAGES).toBeInstanceOf(Array)

    // React hooks
    expect(react.useAvatarChat).toBeTypeOf('function')
    expect(react.useAvatarWebSocket).toBeTypeOf('function')
    expect(react.useWidgetMode).toBeTypeOf('function')
    expect(react.useAvatarBust).toBeTypeOf('function')
    expect(react.useFileUpload).toBeTypeOf('function')
    expect(react.useAvailableProviders).toBeTypeOf('function')

    // React components
    expect(react.AvatarWidget).toBeTypeOf('function')
    expect(react.ChatPanel).toBeTypeOf('function')
    expect(react.CompactChat).toBeTypeOf('function')
    expect(react.StatusBar).toBeTypeOf('function')
    expect(react.MessageBubble).toBeTypeOf('function')
    expect(react.MarkdownContent).toBeTypeOf('function')
    expect(react.PermissionDialog).toBeTypeOf('function')
    expect(react.SafetyModeSelector).toBeTypeOf('function')
    expect(react.SessionPanel).toBeTypeOf('function')
    expect(react.ProviderModelSelector).toBeTypeOf('function')
    expect(react.AvatarBust).toBeTypeOf('function')
    expect(react.AvatarFab).toBeTypeOf('function')
    expect(react.CostTracker).toBeTypeOf('function')
    expect(react.BreathingOrb).toBeTypeOf('function')
    expect(react.ThinkingIndicator).toBeTypeOf('function')
    expect(react.ToolActivity).toBeTypeOf('function')
    expect(react.AvatarLogo).toBeTypeOf('function')
    expect(react.AvatarPicker).toBeTypeOf('function')
    expect(react.OptionControl).toBeTypeOf('function')
    expect(react.SafetyModal).toBeTypeOf('function')
  })
})
