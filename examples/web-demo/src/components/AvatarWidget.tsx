/**
 * === AVATAR WIDGET — Master Layout Container ===
 *
 * Manages three display modes with a single shared chat instance:
 *
 *   FAB        → floating action button (bottom-LEFT)
 *   COMPACT    → bottom drawer with avatar bust + compact chat
 *   FULLSCREEN → overlay covering landing page (existing StatusBar + ChatPanel)
 *
 * Architecture:
 *   - LandingPage is always rendered as the persistent background
 *   - Fullscreen content (children) is rendered as a fixed overlay
 *   - Compact drawer slides up from bottom-left
 *   - FAB shows when neither compact nor fullscreen is active
 *
 * CRITICAL: useAvatarChat is called ONCE in App.tsx. All props are shared
 * between compact and fullscreen modes. Mode transitions NEVER cause
 * WebSocket reconnection or state reinitialization.
 *
 * Integration guide:
 *   Replace <LandingPage> with your own app content. The widget wraps
 *   everything — just pass chat props and it handles FAB, compact drawer,
 *   and fullscreen overlay automatically.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { ChatMessage, UploadedFile } from '../api/types'
import type { WidgetMode } from '../types/avatar'
import { useWidgetMode } from '../hooks/useWidgetMode'
import { useAvatarThumb } from '../hooks/useAvatarThumb'
import { LS_SELECTED_AVATAR, LS_HINTS_SHOWN } from '../types/avatar'
import { AVATARS, DEFAULT_AVATAR_ID, getAvatarById } from '../config/avatars'
import { LandingPage } from './LandingPage'
import { AvatarFab } from './AvatarFab'
import { AvatarBust } from './AvatarBust'
import { AvatarPicker } from './AvatarPicker'
import { CompactChat } from './CompactChat'

interface AvatarWidgetProps {
  /** Fullscreen content (StatusBar + ChatPanel + CostTracker) — rendered as overlay */
  children: ReactNode
  // Chat data (shared between compact and fullscreen, from single useAvatarChat)
  messages: ChatMessage[]
  sendMessage: (text: string) => void
  stopResponse: () => void
  isStreaming: boolean
  connected: boolean
  wasConnected?: boolean
  initDetail?: string
  error?: string | null
  diagnostic?: string | null
  provider: string
  model: string | null
  engineState: string
  thinkingSubject?: string
  toolName?: string
  pendingFiles?: UploadedFile[]
  uploading?: boolean
  uploadFile?: (file: File) => Promise<unknown>
  removeFile?: (fileId: string) => void
  // Provider switching (for compact header ⋯ dropdown)
  switching?: boolean
  activeOptions?: Record<string, string | number>
  availableProviders?: Set<string> | null
  switchProvider?: (provider: string, model?: string, options?: Record<string, string | number>) => void
}

export function AvatarWidget({
  children,
  messages,
  sendMessage,
  stopResponse,
  isStreaming,
  connected,
  wasConnected,
  initDetail,
  error,
  diagnostic,
  provider,
  model,
  engineState,
  thinkingSubject,
  toolName,
  pendingFiles,
  uploading,
  uploadFile,
  removeFile,
  switching,
  activeOptions,
  availableProviders,
  switchProvider,
}: AvatarWidgetProps) {
  // --- Refs used by morph transition and resize ---
  const drawerRef = useRef<HTMLDivElement>(null)

  // --- Morph transition state (clip-path animation between modes) ---
  const [morphActive, setMorphActive] = useState(false)
  const [morphClip, setMorphClip] = useState('')
  const [morphTransition, setMorphTransition] = useState(false)
  const morphTimerRef = useRef<ReturnType<typeof setTimeout>>()

  const onTransition = useCallback((from: WidgetMode, to: WidgetMode, complete: () => void) => {
    // Clear any in-progress morph
    if (morphTimerRef.current) clearTimeout(morphTimerRef.current)

    const vw = window.innerWidth
    const vh = window.innerHeight

    if (from === 'compact' && to === 'fullscreen') {
      // Capture compact drawer rect
      const rect = drawerRef.current?.getBoundingClientRect()
      if (!rect) { complete(); return }
      const compactClip = `inset(${rect.top}px ${vw - rect.right}px ${vh - rect.bottom}px ${rect.left}px round 16px 16px 0 0)`

      // Phase 1: show morph at compact position (no transition)
      setMorphActive(true)
      setMorphTransition(false)
      setMorphClip(compactClip)

      // Phase 2: animate to fullscreen (double-rAF ensures paint)
      requestAnimationFrame(() => requestAnimationFrame(() => {
        setMorphTransition(true)
        setMorphClip('inset(0 0 0 0 round 0)')
      }))

      // Phase 3: switch mode, remove morph
      morphTimerRef.current = setTimeout(() => {
        complete()
        requestAnimationFrame(() => setMorphActive(false))
      }, 480)

    } else if (from === 'fullscreen' && to === 'compact') {
      // Calculate target compact rect from current dimensions
      const w = window.innerWidth < 768 ? vw : compactWidthRef.current
      const h = compactHeightRef.current
      const targetClip = `inset(${vh - h}px ${vw - w}px 0 0 round 16px 16px 0 0)`

      // Phase 1: show morph at full viewport
      setMorphActive(true)
      setMorphTransition(false)
      setMorphClip('inset(0 0 0 0 round 0)')

      // Phase 2: switch mode immediately (drawer appears behind morph)
      requestAnimationFrame(() => {
        complete()
        // Phase 3: animate morph shrinking to compact rect
        requestAnimationFrame(() => {
          setMorphTransition(true)
          setMorphClip(targetClip)
        })
      })

      // Phase 4: remove morph
      morphTimerRef.current = setTimeout(() => {
        setMorphActive(false)
      }, 520)
    }
  }, [])

  const {
    mode,
    openCompact,
    openFullscreen,
    closeTofab,
    compactWidth,
    compactHeight,
    setCompactWidth,
    setCompactHeight,
    bustVisible,
    toggleBust,
  } = useWidgetMode(onTransition)

  // Refs for compact dimensions (used in onTransition closure)
  const compactWidthRef = useRef(compactWidth)
  compactWidthRef.current = compactWidth
  const compactHeightRef = useRef(compactHeight)
  compactHeightRef.current = compactHeight

  // --- Avatar selection (persisted to localStorage) ---
  const [selectedAvatarId, setSelectedAvatarId] = useState(() =>
    localStorage.getItem(LS_SELECTED_AVATAR) || DEFAULT_AVATAR_ID
  )
  const selectedAvatar = getAvatarById(selectedAvatarId) || AVATARS[0]
  const [pickerOpen, setPickerOpen] = useState(false)
  const fabThumbUrl = useAvatarThumb(selectedAvatar)

  const handleAvatarSelect = useCallback((id: string) => {
    setSelectedAvatarId(id)
    localStorage.setItem(LS_SELECTED_AVATAR, id)
  }, [])

  // --- First-time hints (fab arrow, expand pulsing dot) ---
  const [hintsShown, setHintsShown] = useState<Set<string>>(() => {
    const v = localStorage.getItem(LS_HINTS_SHOWN)
    return new Set(v ? v.split(',').filter(Boolean) : [])
  })

  const markHint = useCallback((key: string) => {
    setHintsShown((prev) => {
      if (prev.has(key)) return prev
      const next = new Set(prev).add(key)
      localStorage.setItem(LS_HINTS_SHOWN, [...next].join(','))
      return next
    })
  }, [])

  // Dismiss hints on mode transitions
  useEffect(() => {
    if (mode === 'compact') markHint('fab')
    if (mode === 'fullscreen') markHint('expand')
  }, [mode, markHint])

  const showFabHint = mode === 'fab' && !hintsShown.has('fab')
  const showExpandHint = mode === 'compact' && !hintsShown.has('expand')

  // --- Compact drawer resize ---
  const [resizingV, setResizingV] = useState(false)
  const [resizingH, setResizingH] = useState(false)
  const resizeStartRef = useRef({ y: 0, h: 0, x: 0, w: 0 })

  // Vertical resize (top handle)
  const onResizeVStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizeStartRef.current = { y: e.clientY, h: compactHeight, x: 0, w: 0 }
    setResizingV(true)
  }, [compactHeight])

  useEffect(() => {
    if (!resizingV) return
    const onMove = (e: MouseEvent) => {
      const dy = resizeStartRef.current.y - e.clientY
      const newH = Math.min(window.innerHeight - 50, Math.max(200, resizeStartRef.current.h + dy))
      setCompactHeight(newH)
    }
    const onUp = () => setResizingV(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [resizingV, setCompactHeight])

  // Horizontal resize (right handle)
  const onResizeHStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizeStartRef.current = { y: 0, h: 0, x: e.clientX, w: compactWidth }
    setResizingH(true)
  }, [compactWidth])

  useEffect(() => {
    if (!resizingH) return
    const onMove = (e: MouseEvent) => {
      const dx = e.clientX - resizeStartRef.current.x
      const newW = Math.min(window.innerWidth, Math.max(530, resizeStartRef.current.w + dx))
      setCompactWidth(newW)
    }
    const onUp = () => setResizingH(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [resizingH, setCompactWidth])

  // Prevent text selection during resize
  useEffect(() => {
    if (resizingV || resizingH) {
      document.body.style.userSelect = 'none'
      document.body.style.cursor = resizingV ? 'ns-resize' : 'ew-resize'
    } else {
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [resizingV, resizingH])

  // Clamp dimensions on window resize
  useEffect(() => {
    function handleResize() {
      if (compactHeight > window.innerHeight - 50) setCompactHeight(window.innerHeight - 50)
      if (compactWidth > window.innerWidth) setCompactWidth(window.innerWidth)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [compactHeight, compactWidth, setCompactHeight, setCompactWidth])

  // Responsive: hide bust on narrow screens (<768px)
  const [isNarrow, setIsNarrow] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    function check() { setIsNarrow(window.innerWidth < 768) }
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  const showBust = bustVisible && !isNarrow
  const bustAreaWidth = showBust ? 230 : 0

  // Bust should only animate speaking when the current assistant message
  // has actual text content — prevents lip-sync before text appears in chat.
  const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null
  const hasText = !!(lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming && lastMsg.content)

  return (
    <>
      {/* ============================================================ */}
      {/* BACKGROUND: Demo landing page — always visible behind modes  */}
      {/* Replace LandingPage with your own app content when           */}
      {/* integrating Avatar Engine into an existing application.      */}
      {/* ============================================================ */}
      <LandingPage showFabHint={showFabHint} />

      {/* ============================================================ */}
      {/* FULLSCREEN OVERLAY — existing app content (StatusBar, Chat)  */}
      {/* Always in the DOM to preserve React state; hidden via CSS    */}
      {/* when not in fullscreen mode. No unmount → no reinit.         */}
      {/* ============================================================ */}
      <div
        className={`fixed inset-0 z-[2000] ${
          morphActive ? '' : 'transition-opacity duration-300'
        } ${
          mode === 'fullscreen'
            ? 'opacity-100'
            : 'opacity-0 pointer-events-none'
        }`}
        aria-hidden={mode !== 'fullscreen'}
      >
        {children}
      </div>

      {/* Fullscreen → compact return button (top-right, like normal windows) */}
      {mode === 'fullscreen' && !morphActive && (
        <button
          onClick={openCompact}
          className="fixed top-4 right-4 z-[2001] w-10 h-10 rounded-xl
            bg-slate-dark/80 backdrop-blur-sm border border-white/10
            flex items-center justify-center
            text-text-muted hover:text-synapse hover:border-synapse/40
            opacity-60 hover:opacity-100
            transition-all duration-200 hover:scale-105"
          title="Compact mode (Esc)"
          aria-label="Switch to compact mode"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
          </svg>
        </button>
      )}

      {/* Morph transition overlay — clip-path animated between compact rect and full viewport */}
      {morphActive && (
        <div
          className="fixed inset-0 z-[2500] bg-[rgba(18,18,35,0.96)] backdrop-blur-[24px] border-t border-l border-white/[0.08]"
          style={{
            clipPath: morphClip,
            transition: morphTransition
              ? 'clip-path 480ms cubic-bezier(0.16, 1, 0.3, 1)'
              : 'none',
          }}
        />
      )}

      {/* ============================================================ */}
      {/* FAB — floating action button, bottom-left                    */}
      {/* ============================================================ */}
      {mode === 'fab' && (
        <AvatarFab
          onClick={openCompact}
          avatarThumbUrl={fabThumbUrl}
        />
      )}

      {/* ============================================================ */}
      {/* COMPACT DRAWER — bottom-left, resizable, with avatar bust    */}
      {/* ============================================================ */}
      <div
        ref={drawerRef}
        className={`fixed bottom-0 left-0 z-[999] flex overflow-visible ${
          morphActive ? '' : 'transition-transform duration-500'
        } ${
          mode === 'compact' ? 'translate-y-0' : 'translate-y-full pointer-events-none'
        }`}
        style={{
          width: isNarrow ? '100%' : compactWidth,
          maxWidth: '100%',
          height: compactHeight,
          transitionTimingFunction: morphActive ? undefined : 'cubic-bezier(0.16, 1, 0.3, 1)',
          willChange: mode === 'compact' ? 'auto' : 'transform',
        }}
        role="dialog"
        aria-label="Chat panel"
      >
        {/* Vertical resize handle (top) */}
        <div
          className={`absolute top-[-14px] right-0 h-[28px] cursor-ns-resize z-[1002] flex items-center justify-center group ${resizingV ? 'active' : ''}`}
          style={{ left: bustAreaWidth }}
          onMouseDown={onResizeVStart}
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize chat height"
        >
          <div className={`h-2 rounded transition-all ${resizingV ? 'w-24 bg-synapse shadow-[0_0_12px_rgba(99,102,241,0.4)]' : 'w-[72px] bg-slate-light group-hover:w-24 group-hover:bg-synapse group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]'}`}
            style={{
              backgroundImage: `repeating-linear-gradient(90deg, transparent, transparent 3px, rgba(255,255,255,${resizingV ? '0.2' : '0.08'}) 3px, rgba(255,255,255,${resizingV ? '0.2' : '0.08'}) 5px)`,
            }}
          />
        </div>

        {/* Horizontal resize handle (right) — hidden on narrow */}
        {!isNarrow && (
          <div
            className={`absolute top-0 bottom-0 w-6 cursor-ew-resize z-[1002] flex items-center justify-center group ${resizingH ? 'active' : ''}`}
            style={{ right: -24 }}
            onMouseDown={onResizeHStart}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize chat width"
          >
            <div className={`w-2 rounded transition-all ${resizingH ? 'h-24 bg-synapse shadow-[0_0_12px_rgba(99,102,241,0.4)]' : 'h-[72px] bg-slate-light group-hover:h-24 group-hover:bg-synapse group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]'}`}
              style={{
                backgroundImage: `repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(255,255,255,${resizingH ? '0.2' : '0.08'}) 3px, rgba(255,255,255,${resizingH ? '0.2' : '0.08'}) 5px)`,
              }}
            />
          </div>
        )}

        {/* Bust area */}
        <div
          className="relative flex-shrink-0 overflow-visible z-[1001] transition-[width] duration-300 group/bust"
          style={{ width: bustAreaWidth, transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)' }}
        >
          {showBust && (
            <>
              <AvatarBust
                avatar={selectedAvatar}
                engineState={engineState}
                hasText={hasText}
                className="absolute bottom-0 left-[14px] w-[200px]"
              />
              {/* Character picker button — appears on hover */}
              <button
                onClick={() => setPickerOpen((v) => !v)}
                className="absolute bottom-[3.6%] left-[13px] w-8 h-8 rounded-full z-[1002]
                  flex items-center justify-center cursor-pointer
                  bg-black/55 backdrop-blur-sm border border-white/[0.06]
                  text-text-secondary text-[0.7rem]
                  opacity-0 hover:opacity-100 group-hover/bust:opacity-100
                  hover:bg-synapse/30 hover:border-synapse hover:text-white hover:scale-110
                  transition-all duration-200"
                title="Change avatar"
                aria-label="Choose avatar character"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              </button>
              {pickerOpen && (
                <AvatarPicker
                  selectedId={selectedAvatarId}
                  onSelect={handleAvatarSelect}
                  onClose={() => setPickerOpen(false)}
                />
              )}
              {/* Glow pool under bust */}
              <div className="absolute bottom-[2%] left-1/2 -translate-x-[40%] w-[180px] h-[50px] rounded-full pointer-events-none blur-[10px]"
                style={{
                  background: engineState === 'error'
                    ? 'radial-gradient(ellipse, rgba(244,63,94,0.2) 0%, transparent 70%)'
                    : engineState === 'responding'
                    ? 'radial-gradient(ellipse, rgba(139,92,246,0.25) 0%, transparent 70%)'
                    : 'radial-gradient(ellipse, rgba(99,102,241,0.25) 0%, transparent 70%)',
                  opacity: engineState !== 'idle' ? 0.8 : 0,
                  transition: 'opacity 0.5s ease',
                }}
              />
            </>
          )}
        </div>

        {/* Pill toggle — on left edge of chat panel */}
        <div className="relative flex-1 min-w-0 flex flex-col group/panel">
          {!isNarrow && (
            <button
              onClick={toggleBust}
              className="absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-10 rounded-full z-[1003]
                flex items-center justify-center cursor-pointer
                bg-[rgba(15,15,23,0.9)] backdrop-blur-sm border border-white/[0.06]
                text-text-muted opacity-0 group-hover/panel:opacity-100 hover:opacity-100
                hover:bg-synapse/20 hover:border-synapse/40 hover:text-text-primary
                transition-all duration-200"
              title={bustVisible ? 'Hide bust (Ctrl+Shift+H)' : 'Show bust (Ctrl+Shift+H)'}
              aria-label={bustVisible ? 'Hide avatar bust' : 'Show avatar bust'}
            >
              <div className="flex flex-col gap-[3px] items-center">
                <span className="block w-[10px] h-[1.5px] bg-current rounded-sm opacity-70" />
                <span className="block w-[10px] h-[1.5px] bg-current rounded-sm opacity-70" />
                <span className="block w-[10px] h-[1.5px] bg-current rounded-sm opacity-70" />
              </div>
            </button>
          )}

          <CompactChat
            messages={messages}
            provider={provider}
            model={model}
            connected={connected}
            wasConnected={wasConnected}
            initDetail={initDetail}
            error={error}
            diagnostic={diagnostic}
            engineState={engineState}
            thinkingSubject={thinkingSubject}
            toolName={toolName}
            isStreaming={isStreaming}
            pendingFiles={pendingFiles}
            uploading={uploading}
            onSend={sendMessage}
            onStop={stopResponse}
            onUpload={uploadFile}
            onRemoveFile={removeFile}
            onFullscreen={openFullscreen}
            onClose={closeTofab}
            switching={switching}
            activeOptions={activeOptions}
            availableProviders={availableProviders}
            onSwitchProvider={switchProvider}
            showExpandHint={showExpandHint}
          />
        </div>
      </div>
    </>
  )
}
