/**
 * AvatarWidget integration tests.
 *
 * Verifies:
 *   - Mode transitions render correct UI elements
 *   - Messages persist across mode switches (no reinit)
 *   - Fullscreen content stays in DOM (not unmounted) to preserve state
 *   - First-time hints show and dismiss correctly
 *   - Compact header dropdown shows provider switching UI
 */

/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AvatarWidget } from '../components/AvatarWidget'
import { LS_WIDGET_MODE, LS_HINTS_SHOWN } from '../types/avatar'

// Mock avatar assets (canvas operations not available in jsdom)
vi.mock('../hooks/useAvatarThumb', () => ({
  useAvatarThumb: () => undefined,
}))
vi.mock('../hooks/useAvatarBust', () => ({
  useAvatarBust: () => ({ frameDataUrl: null, bustState: 'idle' }),
}))
vi.mock('../components/AvatarBust', () => ({
  AvatarBust: () => <div data-testid="avatar-bust" />,
}))
vi.mock('../components/AvatarPicker', () => ({
  AvatarPicker: () => <div data-testid="avatar-picker" />,
}))

const defaultProps = {
  messages: [
    { id: '1', role: 'user' as const, content: 'Hello', timestamp: Date.now(), tools: [], isStreaming: false },
    { id: '2', role: 'assistant' as const, content: 'Hi there!', timestamp: Date.now(), tools: [], isStreaming: false },
  ],
  sendMessage: vi.fn(),
  stopResponse: vi.fn(),
  isStreaming: false,
  connected: true,
  provider: 'gemini',
  model: 'gemini-2.5-pro',
  engineState: 'idle',
  pendingFiles: [],
}

function renderWidget(overrides = {}) {
  return render(
    <AvatarWidget {...defaultProps} {...overrides}>
      <div data-testid="fullscreen-content">
        <div data-testid="status-bar">StatusBar</div>
        <div data-testid="chat-panel">ChatPanel with messages</div>
      </div>
    </AvatarWidget>
  )
}

describe('AvatarWidget integration', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  describe('mode rendering', () => {
    it('renders FAB in default (fab) mode', () => {
      renderWidget()
      expect(screen.getByRole('button', { name: /open chat panel/i })).toBeInTheDocument()
    })

    it('renders landing page in all modes', () => {
      renderWidget()
      // Landing page title should always be visible
      expect(screen.getByText('Avatar Engine')).toBeInTheDocument()
    })

    it('fullscreen content is in DOM but hidden in fab mode', () => {
      renderWidget()
      const content = screen.getByTestId('fullscreen-content')
      expect(content).toBeInTheDocument()
      // The overlay container should have opacity-0 and pointer-events-none
      const overlay = content.closest('[aria-hidden]')
      expect(overlay).toHaveAttribute('aria-hidden', 'true')
    })

    it('clicking FAB opens compact mode', () => {
      renderWidget()
      fireEvent.click(screen.getByRole('button', { name: /open chat panel/i }))
      // Compact header should appear with provider name
      expect(screen.getByText('gemini')).toBeInTheDocument()
      expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('compact')
    })

    it('compact mode shows fullscreen button', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      expect(screen.getByRole('button', { name: /expand to fullscreen/i })).toBeInTheDocument()
    })

    it('fullscreen mode shows return button', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'fullscreen')
      renderWidget()
      expect(screen.getByRole('button', { name: /switch to compact mode/i })).toBeInTheDocument()
    })

    it('fullscreen overlay is visible in fullscreen mode', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'fullscreen')
      renderWidget()
      const content = screen.getByTestId('fullscreen-content')
      const overlay = content.closest('[aria-hidden]')
      expect(overlay).toHaveAttribute('aria-hidden', 'false')
    })
  })

  describe('state persistence across mode switches', () => {
    it('fullscreen content stays in DOM during compact mode', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      // Fullscreen content must exist (hidden) to avoid remounting
      expect(screen.getByTestId('fullscreen-content')).toBeInTheDocument()
      expect(screen.getByTestId('status-bar')).toBeInTheDocument()
      expect(screen.getByTestId('chat-panel')).toBeInTheDocument()
    })

    it('fullscreen content stays in DOM during fab mode', () => {
      renderWidget()
      expect(screen.getByTestId('fullscreen-content')).toBeInTheDocument()
    })

    it('messages are shown in compact mode', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      expect(screen.getByText('Hello')).toBeInTheDocument()
    })
  })

  describe('first-time hints', () => {
    it('shows fab hint arrow on first visit', () => {
      renderWidget()
      expect(screen.getByText('Open chat')).toBeInTheDocument()
    })

    it('hides fab hint after opening compact', () => {
      renderWidget()
      fireEvent.click(screen.getByRole('button', { name: /open chat panel/i }))
      expect(screen.queryByText('Open chat')).not.toBeInTheDocument()
      expect(localStorage.getItem(LS_HINTS_SHOWN)).toContain('fab')
    })

    it('does not show fab hint on return visits', () => {
      localStorage.setItem(LS_HINTS_SHOWN, 'fab')
      renderWidget()
      expect(screen.queryByText('Open chat')).not.toBeInTheDocument()
    })

    it('shows expand hint in compact mode on first visit', () => {
      localStorage.setItem(LS_HINTS_SHOWN, 'fab')
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      // The expand hint is a pulsing dot on the fullscreen button
      const fsButton = screen.getByRole('button', { name: /expand to fullscreen/i })
      expect(fsButton.parentElement?.querySelector('.animate-ping')).toBeInTheDocument()
    })

    it('hides expand hint after visiting fullscreen', () => {
      localStorage.setItem(LS_HINTS_SHOWN, 'fab,expand')
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      const fsButton = screen.getByRole('button', { name: /expand to fullscreen/i })
      expect(fsButton.parentElement?.querySelector('.animate-ping')).not.toBeInTheDocument()
    })
  })

  describe('compact header provider dropdown', () => {
    it('shows ⋯ menu button when switchProvider is provided', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget({ switchProvider: vi.fn() })
      expect(screen.getByRole('button', { name: /provider and model settings/i })).toBeInTheDocument()
    })

    it('does not show ⋯ menu when switchProvider is not provided', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      expect(screen.queryByRole('button', { name: /provider and model settings/i })).not.toBeInTheDocument()
    })
  })

  describe('close and escape', () => {
    it('close button in compact returns to fab', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      fireEvent.click(screen.getByRole('button', { name: /close chat panel/i }))
      expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('fab')
    })

    it('return button in fullscreen goes to compact', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'fullscreen')
      renderWidget()
      fireEvent.click(screen.getByRole('button', { name: /switch to compact mode/i }))
      expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('compact')
    })
  })
})
