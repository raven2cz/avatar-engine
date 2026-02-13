/**
 * Widget mode state machine: fab ↔ compact ↔ fullscreen.
 *
 * Persists mode and compact dimensions to localStorage.
 * Registers global keyboard shortcuts (Escape, Ctrl+Shift+A/F/H).
 *
 * Optional `onTransition` callback intercepts compact↔fullscreen switches
 * so the caller can run a morph animation before the mode actually changes.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { WidgetMode } from '../types/avatar'
import {
  LS_WIDGET_MODE,
  LS_COMPACT_HEIGHT,
  LS_COMPACT_WIDTH,
  LS_BUST_VISIBLE,
  LS_DEFAULT_MODE,
} from '../types/avatar'

const DEFAULT_COMPACT_WIDTH = 1030
const MIN_COMPACT_WIDTH = 530
const MIN_COMPACT_HEIGHT = 200
const DEFAULT_COMPACT_HEIGHT = 420

function loadMode(): WidgetMode {
  const v = localStorage.getItem(LS_WIDGET_MODE)
  if (v === 'compact' || v === 'fullscreen') return v
  // Check user's preferred default (set from landing page)
  const def = localStorage.getItem(LS_DEFAULT_MODE)
  if (def === 'compact' || def === 'fullscreen') return def
  return 'fab'
}

function loadNumber(key: string, fallback: number): number {
  const v = localStorage.getItem(key)
  if (v) {
    const n = parseInt(v, 10)
    if (!isNaN(n) && n > 0) return n
  }
  return fallback
}

/**
 * Called before a compact↔fullscreen transition.
 * `complete()` must be called to actually apply the mode change.
 */
export type TransitionHandler = (
  from: WidgetMode,
  to: WidgetMode,
  complete: () => void,
) => void

export interface UseWidgetModeReturn {
  mode: WidgetMode
  setMode: (mode: WidgetMode) => void
  openCompact: () => void
  openFullscreen: () => void
  closeTofab: () => void
  toggleCompact: () => void
  compactWidth: number
  compactHeight: number
  setCompactWidth: (w: number) => void
  setCompactHeight: (h: number) => void
  bustVisible: boolean
  toggleBust: () => void
  defaultMode: WidgetMode
  setDefaultMode: (mode: WidgetMode) => void
}

export function useWidgetMode(
  onTransition?: TransitionHandler,
): UseWidgetModeReturn {
  const [mode, setModeState] = useState<WidgetMode>(loadMode)
  const modeRef = useRef(mode)
  modeRef.current = mode

  const onTransitionRef = useRef(onTransition)
  onTransitionRef.current = onTransition

  const [compactWidth, setCompactWidthState] = useState(() =>
    loadNumber(LS_COMPACT_WIDTH, DEFAULT_COMPACT_WIDTH)
  )
  const [compactHeight, setCompactHeightState] = useState(() =>
    loadNumber(LS_COMPACT_HEIGHT, DEFAULT_COMPACT_HEIGHT)
  )
  const [bustVisible, setBustVisible] = useState(() => {
    const v = localStorage.getItem(LS_BUST_VISIBLE)
    return v !== '0'
  })

  const [defaultMode, setDefaultModeState] = useState<WidgetMode>(() => {
    const v = localStorage.getItem(LS_DEFAULT_MODE)
    if (v === 'compact' || v === 'fullscreen') return v
    return 'fab'
  })

  const setDefaultMode = useCallback((m: WidgetMode) => {
    setDefaultModeState(m)
    localStorage.setItem(LS_DEFAULT_MODE, m)
  }, [])

  /** Commit a mode change (no animation). */
  const commitMode = useCallback((m: WidgetMode) => {
    setModeState(m)
    modeRef.current = m
    localStorage.setItem(LS_WIDGET_MODE, m)
  }, [])

  /**
   * Request a mode change. If an onTransition handler is registered and
   * the transition is compact↔fullscreen, the handler runs first and
   * calls complete() to finalize.
   */
  const setMode = useCallback((m: WidgetMode) => {
    const current = modeRef.current
    if (current === m) return

    const handler = onTransitionRef.current
    if (handler &&
      ((current === 'compact' && m === 'fullscreen') ||
       (current === 'fullscreen' && m === 'compact'))) {
      handler(current, m, () => commitMode(m))
      return
    }

    commitMode(m)
  }, [commitMode])

  const openCompact = useCallback(() => setMode('compact'), [setMode])
  const openFullscreen = useCallback(() => setMode('fullscreen'), [setMode])
  const closeTofab = useCallback(() => setMode('fab'), [setMode])

  const toggleCompact = useCallback(() => {
    const next = modeRef.current === 'compact' ? 'fab' : 'compact'
    setMode(next)
  }, [setMode])

  const setCompactWidth = useCallback((w: number) => {
    const clamped = Math.max(MIN_COMPACT_WIDTH, w)
    setCompactWidthState(clamped)
    localStorage.setItem(LS_COMPACT_WIDTH, String(clamped))
  }, [])

  const setCompactHeight = useCallback((h: number) => {
    const clamped = Math.max(MIN_COMPACT_HEIGHT, h)
    setCompactHeightState(clamped)
    localStorage.setItem(LS_COMPACT_HEIGHT, String(clamped))
  }, [])

  const toggleBust = useCallback(() => {
    setBustVisible((prev) => {
      const next = !prev
      localStorage.setItem(LS_BUST_VISIBLE, next ? '1' : '0')
      return next
    })
  }, [])

  // Keyboard shortcuts — all go through setMode for transition support
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        // Exception: Escape should still work from input
        if (e.key !== 'Escape') return
      }

      if (e.key === 'Escape') {
        e.preventDefault()
        const current = modeRef.current
        if (current === 'fullscreen') setMode('compact')
        else if (current === 'compact') setMode('fab')
        return
      }

      if (e.ctrlKey && e.shiftKey) {
        switch (e.key.toUpperCase()) {
          case 'A': // Toggle compact
            e.preventDefault()
            setMode(modeRef.current === 'compact' ? 'fab' : 'compact')
            break
          case 'F': // Toggle fullscreen
            e.preventDefault()
            setMode(modeRef.current === 'fullscreen' ? 'compact' : 'fullscreen')
            break
          case 'H': // Toggle bust visibility
            e.preventDefault()
            setBustVisible((prev) => {
              const next = !prev
              localStorage.setItem(LS_BUST_VISIBLE, next ? '1' : '0')
              return next
            })
            break
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [setMode])

  return {
    mode,
    setMode,
    openCompact,
    openFullscreen,
    closeTofab,
    toggleCompact,
    compactWidth,
    compactHeight,
    setCompactWidth,
    setCompactHeight,
    bustVisible,
    toggleBust,
    defaultMode,
    setDefaultMode,
  }
}
