/**
 * Widget mode state machine tests.
 *
 * Verifies: mode transitions, localStorage persistence, keyboard shortcuts,
 * and that mode changes don't cause any side effects beyond state updates.
 */

/// <reference types="vitest/globals" />
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWidgetMode } from '../hooks/useWidgetMode'
import { LS_WIDGET_MODE, LS_COMPACT_HEIGHT, LS_COMPACT_WIDTH, LS_BUST_VISIBLE, LS_DEFAULT_MODE } from '../types/avatar'

describe('useWidgetMode', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts in fab mode by default', () => {
    const { result } = renderHook(() => useWidgetMode())
    expect(result.current.mode).toBe('fab')
  })

  it('restores mode from localStorage', () => {
    localStorage.setItem(LS_WIDGET_MODE, 'compact')
    const { result } = renderHook(() => useWidgetMode())
    expect(result.current.mode).toBe('compact')
  })

  it('transitions fab → compact → fullscreen → compact → fab', () => {
    const { result } = renderHook(() => useWidgetMode())

    act(() => result.current.openCompact())
    expect(result.current.mode).toBe('compact')
    expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('compact')

    act(() => result.current.openFullscreen())
    expect(result.current.mode).toBe('fullscreen')
    expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('fullscreen')

    act(() => result.current.openCompact())
    expect(result.current.mode).toBe('compact')

    act(() => result.current.closeTofab())
    expect(result.current.mode).toBe('fab')
    expect(localStorage.getItem(LS_WIDGET_MODE)).toBe('fab')
  })

  it('toggleCompact cycles between fab and compact', () => {
    const { result } = renderHook(() => useWidgetMode())

    act(() => result.current.toggleCompact())
    expect(result.current.mode).toBe('compact')

    act(() => result.current.toggleCompact())
    expect(result.current.mode).toBe('fab')
  })

  it('persists compact dimensions to localStorage', () => {
    const { result } = renderHook(() => useWidgetMode())

    act(() => result.current.setCompactWidth(800))
    expect(result.current.compactWidth).toBe(800)
    expect(localStorage.getItem(LS_COMPACT_WIDTH)).toBe('800')

    act(() => result.current.setCompactHeight(500))
    expect(result.current.compactHeight).toBe(500)
    expect(localStorage.getItem(LS_COMPACT_HEIGHT)).toBe('500')
  })

  it('clamps width to minimum 530', () => {
    const { result } = renderHook(() => useWidgetMode())

    act(() => result.current.setCompactWidth(100))
    expect(result.current.compactWidth).toBe(530)
  })

  it('clamps height to minimum 200', () => {
    const { result } = renderHook(() => useWidgetMode())

    act(() => result.current.setCompactHeight(50))
    expect(result.current.compactHeight).toBe(200)
  })

  it('toggles bust visibility and persists', () => {
    const { result } = renderHook(() => useWidgetMode())
    expect(result.current.bustVisible).toBe(true)

    act(() => result.current.toggleBust())
    expect(result.current.bustVisible).toBe(false)
    expect(localStorage.getItem(LS_BUST_VISIBLE)).toBe('0')

    act(() => result.current.toggleBust())
    expect(result.current.bustVisible).toBe(true)
    expect(localStorage.getItem(LS_BUST_VISIBLE)).toBe('1')
  })

  it('restores bust visibility from localStorage', () => {
    localStorage.setItem(LS_BUST_VISIBLE, '0')
    const { result } = renderHook(() => useWidgetMode())
    expect(result.current.bustVisible).toBe(false)
  })

  describe('keyboard shortcuts', () => {
    it('Escape from fullscreen → compact', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'fullscreen')
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.mode).toBe('fullscreen')

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      })
      expect(result.current.mode).toBe('compact')
    })

    it('Escape from compact → fab', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      const { result } = renderHook(() => useWidgetMode())

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      })
      expect(result.current.mode).toBe('fab')
    })

    it('Escape from fab does nothing', () => {
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.mode).toBe('fab')

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      })
      expect(result.current.mode).toBe('fab')
    })

    it('Ctrl+Shift+A toggles compact', () => {
      const { result } = renderHook(() => useWidgetMode())

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'A', ctrlKey: true, shiftKey: true }))
      })
      expect(result.current.mode).toBe('compact')

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'A', ctrlKey: true, shiftKey: true }))
      })
      expect(result.current.mode).toBe('fab')
    })

    it('Ctrl+Shift+F toggles fullscreen', () => {
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      const { result } = renderHook(() => useWidgetMode())

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F', ctrlKey: true, shiftKey: true }))
      })
      expect(result.current.mode).toBe('fullscreen')

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F', ctrlKey: true, shiftKey: true }))
      })
      expect(result.current.mode).toBe('compact')
    })

    it('Ctrl+Shift+H toggles bust visibility', () => {
      const { result } = renderHook(() => useWidgetMode())

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'H', ctrlKey: true, shiftKey: true }))
      })
      expect(result.current.bustVisible).toBe(false)
    })
  })

  describe('default mode', () => {
    it('starts with fab as defaultMode', () => {
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.defaultMode).toBe('fab')
    })

    it('setDefaultMode persists to localStorage', () => {
      const { result } = renderHook(() => useWidgetMode())

      act(() => result.current.setDefaultMode('compact'))
      expect(result.current.defaultMode).toBe('compact')
      expect(localStorage.getItem(LS_DEFAULT_MODE)).toBe('compact')

      act(() => result.current.setDefaultMode('fullscreen'))
      expect(result.current.defaultMode).toBe('fullscreen')
      expect(localStorage.getItem(LS_DEFAULT_MODE)).toBe('fullscreen')
    })

    it('restores defaultMode from localStorage', () => {
      localStorage.setItem(LS_DEFAULT_MODE, 'compact')
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.defaultMode).toBe('compact')
    })

    it('uses defaultMode as initial mode when LS_WIDGET_MODE is absent', () => {
      localStorage.setItem(LS_DEFAULT_MODE, 'compact')
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.mode).toBe('compact')
    })

    it('uses defaultMode fullscreen as initial mode', () => {
      localStorage.setItem(LS_DEFAULT_MODE, 'fullscreen')
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.mode).toBe('fullscreen')
    })

    it('LS_WIDGET_MODE takes priority over LS_DEFAULT_MODE', () => {
      localStorage.setItem(LS_DEFAULT_MODE, 'fullscreen')
      localStorage.setItem(LS_WIDGET_MODE, 'compact')
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.mode).toBe('compact')
    })

    it('ignores invalid defaultMode values', () => {
      localStorage.setItem(LS_DEFAULT_MODE, 'invalid')
      const { result } = renderHook(() => useWidgetMode())
      expect(result.current.mode).toBe('fab')
      expect(result.current.defaultMode).toBe('fab')
    })
  })
})
