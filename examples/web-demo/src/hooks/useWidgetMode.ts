/**
 * Widget mode state machine: fab ↔ compact ↔ fullscreen.
 *
 * Persists mode and compact dimensions to localStorage.
 * Registers global keyboard shortcuts (Escape, Ctrl+Shift+A/F/H).
 */

import { useCallback, useEffect, useState } from 'react'
import type { WidgetMode } from '../types/avatar'
import {
  LS_WIDGET_MODE,
  LS_COMPACT_HEIGHT,
  LS_COMPACT_WIDTH,
  LS_BUST_VISIBLE,
} from '../types/avatar'

const DEFAULT_COMPACT_WIDTH = 1030
const MIN_COMPACT_WIDTH = 530
const MIN_COMPACT_HEIGHT = 200
const DEFAULT_COMPACT_HEIGHT = 420

function loadMode(): WidgetMode {
  const v = localStorage.getItem(LS_WIDGET_MODE)
  if (v === 'compact' || v === 'fullscreen') return v
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
}

export function useWidgetMode(): UseWidgetModeReturn {
  const [mode, setModeState] = useState<WidgetMode>(loadMode)
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

  const setMode = useCallback((m: WidgetMode) => {
    setModeState(m)
    localStorage.setItem(LS_WIDGET_MODE, m)
  }, [])

  const openCompact = useCallback(() => setMode('compact'), [setMode])
  const openFullscreen = useCallback(() => setMode('fullscreen'), [setMode])
  const closeTofab = useCallback(() => setMode('fab'), [setMode])

  const toggleCompact = useCallback(() => {
    setModeState((prev) => {
      const next = prev === 'compact' ? 'fab' : 'compact'
      localStorage.setItem(LS_WIDGET_MODE, next)
      return next
    })
  }, [])

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

  // Keyboard shortcuts
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
        setModeState((prev) => {
          if (prev === 'fullscreen') {
            localStorage.setItem(LS_WIDGET_MODE, 'compact')
            return 'compact'
          }
          if (prev === 'compact') {
            localStorage.setItem(LS_WIDGET_MODE, 'fab')
            return 'fab'
          }
          return prev
        })
        return
      }

      if (e.ctrlKey && e.shiftKey) {
        switch (e.key.toUpperCase()) {
          case 'A': // Toggle compact
            e.preventDefault()
            setModeState((prev) => {
              const next = prev === 'compact' ? 'fab' : 'compact'
              localStorage.setItem(LS_WIDGET_MODE, next)
              return next
            })
            break
          case 'F': // Toggle fullscreen
            e.preventDefault()
            setModeState((prev) => {
              const next = prev === 'fullscreen' ? 'compact' : 'fullscreen'
              localStorage.setItem(LS_WIDGET_MODE, next)
              return next
            })
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
  }, [])

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
  }
}
