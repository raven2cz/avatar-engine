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
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { AvatarWidget } from '../components/AvatarWidget'
import { LS_WIDGET_MODE, LS_HINTS_SHOWN, LS_DEFAULT_MODE } from '../types/avatar'

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

const compactModeRef = { current: null as (() => void) | null }

function renderWidget(overrides = {}) {
  return render(
    <AvatarWidget {...defaultProps} {...overrides} onCompactModeRef={compactModeRef}>
      <div data-testid="fullscreen-content">
        <div data-testid="status-bar">StatusBar</div>
        <div data-testid="chat-panel">ChatPanel with messages</div>
        <button aria-label="Switch to compact mode" onClick={() => compactModeRef.current?.()}>Compact</button>
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

    it('return button in fullscreen goes to compact', async () => {
      vi.useFakeTimers()
      localStorage.setItem(LS_WIDGET_MODE, 'fullscreen')
      renderWidget()
      fireEvent.click(screen.getByRole('button', { name: /switch to compact mode/i }))
      // Crossfade transition — mode changes immediately, transitioning flag clears after 300ms
      await act(async () => { vi.advanceTimersByTime(400) })
      expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('compact')
      vi.useRealTimers()
    })
  })

  describe('landing page features', () => {
    it('renders startup mode selector buttons', () => {
      renderWidget()
      expect(screen.getByText('Startup Mode')).toBeInTheDocument()
      // Use getByRole to match accessible name (avoids collision with fullscreen children button)
      expect(screen.getByRole('button', { name: 'FAB' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Compact' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Fullscreen' })).toBeInTheDocument()
    })

    it('mode selector persists default mode to localStorage', () => {
      renderWidget()
      fireEvent.click(screen.getByRole('button', { name: 'Compact' }))
      expect(localStorage.getItem(LS_DEFAULT_MODE)).toBe('compact')
    })

    it('mode selector highlights the active default', () => {
      localStorage.setItem(LS_DEFAULT_MODE, 'fullscreen')
      renderWidget()
      const fsButton = screen.getByText('Fullscreen')
      expect(fsButton.className).toContain('text-synapse')
    })

    it('renders documentation link', () => {
      renderWidget()
      const link = screen.getByText('Documentation & README →')
      expect(link).toBeInTheDocument()
      expect(link.tagName).toBe('A')
      expect(link).toHaveAttribute('target', '_blank')
    })

    it('renders keyboard shortcuts section', () => {
      renderWidget()
      expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument()
      expect(screen.getByText('Ctrl+Shift+A')).toBeInTheDocument()
      expect(screen.getByText('Ctrl+Shift+F')).toBeInTheDocument()
    })
  })

  describe('compact message avatars', () => {
    it('renders SVG icons instead of text U/A in compact bubbles', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      // Should NOT contain plain text "U" or "A" as avatar letters
      const avatarIcons = document.querySelectorAll('.rounded-full svg')
      expect(avatarIcons.length).toBeGreaterThanOrEqual(2)
      // User avatar should have lucide User icon (has specific path)
      // Assistant avatar should have AvatarLogo SVG
    })

    it('compact bubbles use consistent rounded-xl (no pointed tips)', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      renderWidget()
      // No element should have rounded-tr-sm or rounded-tl-sm
      const allBubbles = document.querySelectorAll('.rounded-xl')
      expect(allBubbles.length).toBeGreaterThan(0)
      const tippedBubbles = document.querySelectorAll('.rounded-tr-sm, .rounded-tl-sm')
      expect(tippedBubbles.length).toBe(0)
    })
  })
})
