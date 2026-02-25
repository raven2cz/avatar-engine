/**
 * Widget mode state machine: fab <-> compact <-> fullscreen.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { WidgetMode } from '@avatar-engine/core'
import {
  LS_WIDGET_MODE,
  LS_COMPACT_HEIGHT,
  LS_COMPACT_WIDTH,
  LS_BUST_VISIBLE,
  LS_DEFAULT_MODE,
} from '@avatar-engine/core'

const DEFAULT_COMPACT_WIDTH = 1030
const MIN_COMPACT_WIDTH = 530
const MIN_COMPACT_HEIGHT = 200
const DEFAULT_COMPACT_HEIGHT = 420

function loadMode(): WidgetMode {
  const v = localStorage.getItem(LS_WIDGET_MODE)
  if (v === 'compact' || v === 'fullscreen') return v
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

export type TransitionHandler = (
  from: WidgetMode,
  to: WidgetMode,
  complete: () => void,
) => void

/**
 * Return type for the {@link useWidgetMode} hook.
 *
 * @property mode - Current display mode: "fab", "compact", or "fullscreen".
 * @property setMode - Transition to a specific mode (respects transition handler).
 * @property openCompact - Shortcut to switch to compact mode.
 * @property openFullscreen - Shortcut to switch to fullscreen mode.
 * @property closeTofab - Shortcut to collapse back to the FAB.
 * @property toggleCompact - Toggle between fab and compact modes.
 * @property compactWidth - Current width of the compact drawer in pixels.
 * @property compactHeight - Current height of the compact drawer in pixels.
 * @property setCompactWidth - Set compact drawer width (clamped to minimum).
 * @property setCompactHeight - Set compact drawer height (clamped to minimum).
 * @property bustVisible - Whether the avatar bust is visible in compact mode.
 * @property toggleBust - Toggle avatar bust visibility.
 * @property defaultMode - Persisted default mode used on initial load.
 * @property setDefaultMode - Update the persisted default mode.
 */
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

/**
 * Manages the widget display mode state machine: fab, compact, and fullscreen.
 *
 * Persists mode, drawer dimensions, bust visibility, and default mode to localStorage.
 * Registers keyboard shortcuts (Escape, Ctrl+Shift+A/F/H) for mode transitions.
 *
 * @param onTransition - Optional callback invoked during compact/fullscreen transitions
 *   to enable custom animations. Call `complete()` to commit the mode change.
 *
 * @example
 * ```tsx
 * const { mode, openCompact, openFullscreen, closeTofab } = useWidgetMode();
 *
 * if (mode === 'fab') return <button onClick={openCompact}>Open</button>;
 * if (mode === 'compact') return <CompactView onExpand={openFullscreen} onClose={closeTofab} />;
 * return <FullscreenView />;
 * ```
 */
export function useWidgetMode(
  onTransition?: TransitionHandler,
  initialMode?: WidgetMode,
): UseWidgetModeReturn {
  const [mode, setModeState] = useState<WidgetMode>(() => {
    if (initialMode) {
      // Override persisted value — consumer explicitly requested a starting mode
      localStorage.setItem(LS_WIDGET_MODE, initialMode)
      return initialMode
    }
    return loadMode()
  })
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

  const commitMode = useCallback((m: WidgetMode) => {
    setModeState(m)
    modeRef.current = m
    localStorage.setItem(LS_WIDGET_MODE, m)
  }, [])

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

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
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
          case 'A':
            e.preventDefault()
            setMode(modeRef.current === 'compact' ? 'fab' : 'compact')
            break
          case 'F':
            e.preventDefault()
            setMode(modeRef.current === 'fullscreen' ? 'compact' : 'fullscreen')
            break
          case 'H':
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
