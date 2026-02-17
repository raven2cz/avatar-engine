/**
 * Consumer-Pattern Tests — verifies that @avatar-engine/react is fully
 * configurable and usable by external consumer applications.
 *
 * Tests cover:
 *   1. Initial config (auto-switch provider/model on connect)
 *   2. Response callbacks (onResponse)
 *   3. Custom provider lists (customProviders prop)
 *   4. Avatar path configuration
 *   5. CSS theming variables
 *   6. Exported types (compile-time verification)
 *   7. Programmatic API (AvatarChatOptions)
 */

/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { useAvatarChat } from '@avatar-engine/react'
import type {
  UseAvatarChatReturn,
  AvatarChatOptions,
  AvatarWidgetProps,
  AvatarBustProps,
  AvatarFabProps,
  AvatarPickerProps,
  ProviderModelSelectorProps,
  CompactChatProps,
  CompactHeaderProps,
  ChatMessage,
  AvatarConfig,
  ProviderConfig,
  SafetyMode,
} from '@avatar-engine/react'
import {
  PROVIDERS,
  AVATARS,
  getAvatarBasePath,
  getProvider,
  getModelsForProvider,
} from '@avatar-engine/react'

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

// --------------- Test component ---------------

function TestApp({ wsUrl = 'ws://test/ws', options }: { wsUrl?: string; options?: AvatarChatOptions }) {
  const chat = useAvatarChat(wsUrl, options)
  return <TestUI chat={chat} />
}

/** Backwards-compat: string apiBase (old signature) */
function TestAppLegacy({ wsUrl = 'ws://test/ws', apiBase }: { wsUrl?: string; apiBase?: string }) {
  const chat = useAvatarChat(wsUrl, apiBase)
  return <TestUI chat={chat} />
}

function TestUI({ chat }: { chat: UseAvatarChatReturn }) {
  return (
    <div>
      <div data-testid="connected">{String(chat.connected)}</div>
      <div data-testid="provider">{chat.provider}</div>
      <div data-testid="model">{chat.model || 'none'}</div>
      <div data-testid="is-streaming">{String(chat.isStreaming)}</div>
      <div data-testid="message-count">{chat.messages.length}</div>
      <div data-testid="messages">
        {chat.messages.map((m) => (
          <div key={m.id} data-testid={`msg-${m.role}-${m.id}`}>
            <span data-testid="content">{m.content}</span>
          </div>
        ))}
      </div>
      <button data-testid="send" onClick={() => chat.sendMessage('test')}>Send</button>
    </div>
  )
}

// --------------- Fixtures ---------------

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

// --------------- Helpers ---------------

async function connectWs(overrides: Record<string, unknown> = {}) {
  await act(async () => { vi.advanceTimersByTime(0) })
  expect(wsInstance).not.toBeNull()
  await act(async () => {
    wsInstance!.simulateOpen()
    wsInstance!.simulateMessage({
      type: 'connected',
      data: {
        session_id: 'sess-1',
        provider: 'gemini',
        model: 'gemini-2.5-pro',
        version: '1.0.0',
        cwd: '/project',
        capabilities: TEST_CAPS,
        engine_state: 'idle',
        safety_mode: 'safe',
        ...overrides,
      },
    })
  })
}

// =============================================
// 1. INITIAL CONFIG — auto-switch on connect
// =============================================

describe('Consumer: initial config', () => {
  it('auto-switches provider on first connect when initialProvider differs', async () => {
    render(<TestApp options={{ initialProvider: 'claude', initialModel: 'claude-sonnet-4-5-20250929' }} />)
    await connectWs({ provider: 'gemini' })

    // Should have sent a switch message
    const switchMsg = wsInstance!.sent.find((s) => JSON.parse(s).type === 'switch')
    expect(switchMsg).toBeTruthy()
    const parsed = JSON.parse(switchMsg!)
    expect(parsed.data.provider).toBe('claude')
    expect(parsed.data.model).toBe('claude-sonnet-4-5-20250929')
  })

  it('does NOT auto-switch when server already on requested provider', async () => {
    render(<TestApp options={{ initialProvider: 'gemini' }} />)
    await connectWs({ provider: 'gemini' })

    const switchMsg = wsInstance!.sent.find((s) => JSON.parse(s).type === 'switch')
    expect(switchMsg).toBeUndefined()
  })

  it('auto-switches when same provider but different model requested', async () => {
    render(<TestApp options={{ initialProvider: 'gemini', initialModel: 'gemini-3-flash' }} />)
    await connectWs({ provider: 'gemini', model: 'gemini-2.5-pro' })

    const switchMsg = wsInstance!.sent.find((s) => JSON.parse(s).type === 'switch')
    expect(switchMsg).toBeTruthy()
    const parsed = JSON.parse(switchMsg!)
    expect(parsed.data.model).toBe('gemini-3-flash')
  })

  it('passes initialOptions on auto-switch', async () => {
    render(<TestApp options={{
      initialProvider: 'claude',
      initialOptions: { thinking_level: 'high' },
    }} />)
    await connectWs({ provider: 'gemini' })

    const switchMsg = wsInstance!.sent.find((s) => JSON.parse(s).type === 'switch')
    expect(switchMsg).toBeTruthy()
  })

  it('applies initialOptions even without initialModel on same provider', async () => {
    render(<TestApp options={{
      initialProvider: 'gemini',
      initialOptions: { thinking_level: 'low' },
    }} />)
    await connectWs({ provider: 'gemini' })

    // Should still switch because initialOptions is set
    const switchMsg = wsInstance!.sent.find((s) => JSON.parse(s).type === 'switch')
    expect(switchMsg).toBeTruthy()
    const parsed = JSON.parse(switchMsg!)
    expect(parsed.data.provider).toBe('gemini')
  })

  it('only auto-switches once (not on reconnect)', async () => {
    // Track all switch messages across WS instances
    const allSwitchMessages: string[] = []
    const OrigSend = MockWebSocket.prototype.send
    MockWebSocket.prototype.send = function(data: string) {
      OrigSend.call(this, data)
      try { if (JSON.parse(data).type === 'switch') allSwitchMessages.push(data) } catch {}
    }

    render(<TestApp options={{ initialProvider: 'claude' }} />)
    await connectWs({ provider: 'gemini' })

    expect(allSwitchMessages.length).toBe(1)

    // Simulate disconnect + reconnect
    await act(async () => {
      wsInstance!.readyState = MockWebSocket.CLOSED
      wsInstance!.onclose?.(new CloseEvent('close'))
    })

    // Advance past reconnect delay — creates new WS instance
    await act(async () => { vi.advanceTimersByTime(4000) })
    if (wsInstance && wsInstance.readyState === MockWebSocket.CONNECTING) {
      await act(async () => {
        wsInstance!.simulateOpen()
        wsInstance!.simulateMessage({
          type: 'connected',
          data: {
            session_id: 'sess-2',
            provider: 'gemini',
            model: 'gemini-3-pro-preview',
            version: '1.0.0',
            cwd: '/project',
            capabilities: TEST_CAPS,
            engine_state: 'idle',
          },
        })
      })
    }

    // Should still be just 1 switch total (no double-switch on reconnect)
    expect(allSwitchMessages.length).toBe(1)

    // Restore
    MockWebSocket.prototype.send = OrigSend
  })
})

// =============================================
// 2. RESPONSE CALLBACKS
// =============================================

describe('Consumer: onResponse callback', () => {
  it('calls onResponse when chat_response arrives', async () => {
    const onResponse = vi.fn()
    render(<TestApp options={{ onResponse }} />)
    await connectWs()

    // Send a message
    await act(async () => {
      screen.getByTestId('send').click()
    })

    // Simulate text streaming
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'Hello human!' } })
    })

    // Simulate chat_response
    await act(async () => {
      wsInstance!.simulateMessage({
        type: 'chat_response',
        data: { content: '', duration_ms: 1500, cost_usd: 0.01 },
      })
    })

    // onResponse called via queueMicrotask — flush it
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(onResponse).toHaveBeenCalledTimes(1)
    const responseMsg: ChatMessage = onResponse.mock.calls[0][0]
    expect(responseMsg.role).toBe('assistant')
    expect(responseMsg.content).toBe('Hello human!')
    expect(responseMsg.isStreaming).toBe(false)
    expect(responseMsg.durationMs).toBe(1500)
  })

  it('does NOT call onResponse when no callback is provided', async () => {
    // This test just verifies no crash when onResponse is undefined
    render(<TestApp />)
    await connectWs()

    await act(async () => {
      screen.getByTestId('send').click()
    })
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'response' } })
      wsInstance!.simulateMessage({
        type: 'chat_response',
        data: { content: '', duration_ms: 100 },
      })
    })

    // No crash means pass
    expect(screen.getByTestId('is-streaming').textContent).toBe('false')
  })

  it('survives onResponse throwing an error', async () => {
    const onResponse = vi.fn(() => { throw new Error('consumer bug') })
    render(<TestApp options={{ onResponse }} />)
    await connectWs()

    await act(async () => {
      screen.getByTestId('send').click()
    })
    await act(async () => {
      wsInstance!.simulateMessage({ type: 'text', data: { text: 'ok' } })
      wsInstance!.simulateMessage({
        type: 'chat_response',
        data: { content: '', duration_ms: 50 },
      })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // onResponse was called (and threw), but the hook didn't crash
    expect(onResponse).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('is-streaming').textContent).toBe('false')
  })
})

// =============================================
// 3. BACKWARDS COMPATIBILITY
// =============================================

describe('Consumer: backwards compatibility', () => {
  it('accepts string apiBase as second argument (legacy signature)', async () => {
    // This should NOT crash — verifies the overloaded signature works
    render(<TestAppLegacy apiBase="/custom/api" />)
    await connectWs()
    expect(screen.getByTestId('connected').textContent).toBe('true')
  })

  it('works with no options at all', async () => {
    render(<TestApp />)
    await connectWs()
    expect(screen.getByTestId('connected').textContent).toBe('true')
  })
})

// =============================================
// 4. AVATAR PATH CONFIGURATION
// =============================================

describe('Consumer: avatar path configuration', () => {
  it('getAvatarBasePath uses default /avatars base', () => {
    expect(getAvatarBasePath('af_bella')).toBe('/avatars/af_bella')
    expect(getAvatarBasePath('astronaut')).toBe('/avatars/astronaut')
  })

  it('getAvatarBasePath accepts custom base path', () => {
    expect(getAvatarBasePath('af_bella', '/cdn/assets/avatars')).toBe('/cdn/assets/avatars/af_bella')
    expect(getAvatarBasePath('custom', 'https://cdn.example.com/avatars')).toBe('https://cdn.example.com/avatars/custom')
  })

  it('AVATARS array has expected structure', () => {
    expect(AVATARS.length).toBeGreaterThan(0)
    for (const avatar of AVATARS) {
      expect(avatar.id).toBeTruthy()
      expect(avatar.name).toBeTruthy()
      expect(avatar.poses).toBeDefined()
      expect(typeof avatar.speakingFrames).toBe('number')
      expect(typeof avatar.speakingFps).toBe('number')
    }
  })

  it('AvatarConfig type can define custom avatars', () => {
    // Type-level test: custom avatar configuration
    const customAvatar: AvatarConfig = {
      id: 'robot',
      name: 'Robot Assistant',
      poses: { idle: 'idle.webp', speaking: 'speak.webp', thinking: 'think.webp' },
      speakingFrames: 8,
      speakingFps: 12,
    }
    expect(customAvatar.id).toBe('robot')
    expect(customAvatar.poses.idle).toBe('idle.webp')
  })
})

// =============================================
// 5. CSS THEMING VARIABLES
// =============================================

describe('Consumer: CSS theming variables', () => {
  it('avatar.css contains all required CSS variable categories', () => {
    const fs = require('fs') as { readFileSync(p: string, e: string): string }
    const path = require('path') as { resolve(...p: string[]): string }

    const cssPath = path.resolve(__dirname, '../../../../packages/react/src/styles/avatar.css')
    const css = fs.readFileSync(cssPath, 'utf-8')

    // Accent colors
    expect(css).toContain('--ae-accent-rgb:')
    expect(css).toContain('--ae-pulse-rgb:')
    expect(css).toContain('--ae-neural-rgb:')
    expect(css).toContain('--ae-accent:')
    expect(css).toContain('--ae-pulse:')

    // Background/surface colors
    expect(css).toContain('--ae-bg-obsidian-rgb:')
    expect(css).toContain('--ae-bg-deep-rgb:')
    expect(css).toContain('--ae-bg-mid-rgb:')
    expect(css).toContain('--ae-bg-light-rgb:')

    // Text colors
    expect(css).toContain('--ae-text-primary-rgb:')
    expect(css).toContain('--ae-text-secondary-rgb:')
    expect(css).toContain('--ae-text-muted-rgb:')

    // Glass composites
    expect(css).toContain('--ae-glass-bg:')
    expect(css).toContain('--ae-glass-panel-bg:')

    // Code block theme
    expect(css).toContain('--ae-code-bg:')
    expect(css).toContain('--ae-code-header-bg:')

    // Phase colors (BreathingOrb)
    expect(css).toContain('--ae-phase-thinking-1:')
    expect(css).toContain('--ae-phase-responding-1:')
    expect(css).toContain('--ae-phase-error-1:')

    // Overlay surfaces
    expect(css).toContain('--ae-overlay-chat:')
    expect(css).toContain('--ae-overlay-input:')
    expect(css).toContain('--ae-overlay-picker:')

    // Gradient
    expect(css).toContain('--ae-gradient:')
  })

  it('tailwind preset references CSS variables, not hardcoded colors', () => {
    const fs = require('fs') as { readFileSync(p: string, e: string): string }
    const path = require('path') as { resolve(...p: string[]): string }

    const presetPath = path.resolve(__dirname, '../../../../packages/react/tailwind-preset.js')
    const preset = fs.readFileSync(presetPath, 'utf-8')

    // Preset should use cssVar() helper function
    expect(preset).toContain('cssVar(')
    expect(preset).toContain('--ae-accent-rgb')
    expect(preset).toContain('--ae-pulse-rgb')
    expect(preset).toContain('--ae-bg-obsidian-rgb')
    expect(preset).toContain('--ae-text-primary-rgb')

    // Should NOT have hardcoded hex colors in the theme extend section
    // (cssVar function wraps them as rgb(var(...)))
    const themeSection = preset.slice(preset.indexOf('theme:'))
    expect(themeSection).not.toMatch(/['"]#[0-9a-f]{6}['"]/) // no quoted hex colors in theme
  })
})

// =============================================
// 6. CUSTOM PROVIDERS
// =============================================

describe('Consumer: custom provider configuration', () => {
  it('PROVIDERS array has expected structure', () => {
    expect(PROVIDERS.length).toBeGreaterThanOrEqual(3)
    for (const p of PROVIDERS) {
      expect(p.id).toBeTruthy()
      expect(p.label).toBeTruthy()
      expect(p.defaultModel).toBeTruthy()
      expect(p.models).toBeInstanceOf(Array)
      expect(p.models.length).toBeGreaterThan(0)
      expect(p.gradient).toBeTruthy()
      expect(p.dotColor).toBeTruthy()
    }
  })

  it('ProviderConfig type can define custom providers', () => {
    const customProvider: ProviderConfig = {
      id: 'openai',
      label: 'OpenAI',
      defaultModel: 'gpt-4o',
      models: ['gpt-4o', 'gpt-4o-mini', 'o1'],
      gradient: 'from-green-500/20 to-emerald-500/20 border-green-500/30 text-green-400',
      dotColor: 'bg-green-400',
      options: [
        {
          key: 'temperature',
          label: 'Temperature',
          type: 'slider',
          defaultValue: 1,
          min: 0,
          max: 2,
          step: 0.1,
        },
      ],
    }
    expect(customProvider.id).toBe('openai')
    expect(customProvider.models).toContain('gpt-4o')
    expect(customProvider.options?.[0].key).toBe('temperature')
  })

  it('getProvider returns config by ID', () => {
    const gemini = getProvider('gemini')
    expect(gemini).toBeDefined()
    expect(gemini!.label).toBe('Gemini')

    const unknown = getProvider('nonexistent')
    expect(unknown).toBeUndefined()
  })

  it('getModelsForProvider returns models list', () => {
    const models = getModelsForProvider('gemini')
    expect(models.length).toBeGreaterThan(0)
    expect(models).toContain('gemini-3-pro-preview')
  })
})

// =============================================
// 7. EXPORTED TYPES (compile-time)
// =============================================

describe('Consumer: exported types exist at runtime', () => {
  it('AvatarChatOptions is importable and usable', () => {
    // Type-level verification
    const opts: AvatarChatOptions = {
      apiBase: '/api/custom',
      initialProvider: 'claude',
      initialModel: 'claude-sonnet-4-5-20250929',
      initialOptions: { thinking_level: 'high' },
      onResponse: (msg: ChatMessage) => { void msg },
    }
    expect(opts.apiBase).toBe('/api/custom')
    expect(opts.initialProvider).toBe('claude')
  })

  it('component prop types are importable', () => {
    // Verify that exported prop types contain expected required fields
    const _avatarWidget: Partial<AvatarWidgetProps> = { provider: 'gemini', connected: true }
    const _avatarBust: Partial<AvatarBustProps> = { engineState: 'idle' }
    const _avatarFab: Partial<AvatarFabProps> = { onClick: () => {} }
    const _avatarPicker: Partial<AvatarPickerProps> = { selectedId: 'af_bella', onSelect: () => {}, onClose: () => {} }
    const _providerSelector: Partial<ProviderModelSelectorProps> = { currentProvider: 'gemini' }
    const _compactChat: Partial<CompactChatProps> = { provider: 'gemini' }
    const _compactHeader: Partial<CompactHeaderProps> = { provider: 'gemini' }

    // If this compiles, the types are correctly exported
    expect(_avatarWidget.provider).toBe('gemini')
    expect(_avatarBust.engineState).toBe('idle')
    expect(_avatarPicker.selectedId).toBe('af_bella')
    expect(_providerSelector.currentProvider).toBe('gemini')
    expect(_compactChat.provider).toBe('gemini')
    expect(_compactHeader.provider).toBe('gemini')
    expect(typeof _avatarFab.onClick).toBe('function')
  })

  it('SafetyMode type values are valid', () => {
    const modes: SafetyMode[] = ['safe', 'ask', 'unrestricted']
    for (const mode of modes) {
      expect(typeof mode).toBe('string')
    }
  })
})

// =============================================
// 8. API BASE CONFIGURATION
// =============================================

describe('Consumer: API base configuration', () => {
  it('no hardcoded dev ports in hooks', () => {
    const fs = require('fs') as { readFileSync(p: string, e: string): string; readdirSync(p: string): string[] }
    const path = require('path') as { resolve(...p: string[]): string }

    const hooksDir = path.resolve(__dirname, '../../../../packages/react/src/hooks')
    const hookFiles = fs.readdirSync(hooksDir).filter((f: string) => f.endsWith('.ts') || f.endsWith('.tsx'))

    for (const file of hookFiles) {
      const content = fs.readFileSync(path.resolve(hooksDir, file), 'utf-8')
      // No hardcoded localhost:5173 or similar dev ports
      expect(content).not.toContain('localhost:5173')
      expect(content).not.toContain('127.0.0.1:5173')
      expect(content).not.toContain('import.meta.env?.DEV')
    }
  })

  it('no hardcoded dev ports in components', () => {
    const fs = require('fs') as { readFileSync(p: string, e: string): string; readdirSync(p: string): string[] }
    const path = require('path') as { resolve(...p: string[]): string }

    const componentsDir = path.resolve(__dirname, '../../../../packages/react/src/components')
    const componentFiles = fs.readdirSync(componentsDir).filter((f: string) => f.endsWith('.tsx'))

    for (const file of componentFiles) {
      const content = fs.readFileSync(path.resolve(componentsDir, file), 'utf-8')
      expect(content).not.toContain('localhost:5173')
      expect(content).not.toContain('127.0.0.1:5173')
    }
  })
})

// =============================================
// 9. CONSUMER INTEGRATION PATTERN
// =============================================

describe('Consumer: integration pattern', () => {
  it('useAvatarChat provides all fields needed for AvatarWidget', async () => {
    // Verify the return type has all props that AvatarWidget needs
    const chatRef = { current: null as UseAvatarChatReturn | null }

    function RefApp() {
      const chat = useAvatarChat('ws://test/ws')
      chatRef.current = chat
      return <TestUI chat={chat} />
    }

    render(<RefApp />)
    await connectWs()

    const chat = chatRef.current!

    // All AvatarWidget required data fields exist
    expect(chat.messages).toBeInstanceOf(Array)
    expect(typeof chat.sendMessage).toBe('function')
    expect(typeof chat.stopResponse).toBe('function')
    expect(typeof chat.isStreaming).toBe('boolean')
    expect(typeof chat.connected).toBe('boolean')
    expect(typeof chat.wasConnected).toBe('boolean')
    expect(typeof chat.provider).toBe('string')
    expect(chat.engineState).toBeDefined()
    expect(typeof chat.switching).toBe('boolean')
    expect(typeof chat.switchProvider).toBe('function')
    expect(typeof chat.resumeSession).toBe('function')
    expect(typeof chat.newSession).toBe('function')
    expect(typeof chat.clearHistory).toBe('function')
    expect(typeof chat.sendPermissionResponse).toBe('function')
    expect(typeof chat.uploadFile).toBe('function')
    expect(typeof chat.removeFile).toBe('function')
    expect(chat.pendingFiles).toBeInstanceOf(Array)
    expect(typeof chat.uploading).toBe('boolean')
    expect(chat.cost).toBeDefined()
    expect(chat.thinking).toBeDefined()
    expect(chat.safetyMode).toBeDefined()
  })
})
