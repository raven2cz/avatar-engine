/**
 * === AVATAR WIDGET — Master Layout Container ===
 *
 * Manages three display modes with a single shared chat instance:
 *
 *   FAB        -> floating action button (bottom-LEFT)
 *   COMPACT    -> bottom drawer with avatar bust + compact chat
 *   FULLSCREEN -> overlay covering background content (existing StatusBar + ChatPanel)
 *
 * Architecture:
 *   - Background content (renderBackground prop or nothing) is always visible behind modes
 *   - Fullscreen content (children) is rendered as a fixed overlay
 *   - Compact drawer slides up from bottom-left
 *   - FAB shows when neither compact nor fullscreen is active
 *
 * CRITICAL: useAvatarChat is called ONCE in the parent. All props are shared
 * between compact and fullscreen modes. Mode transitions NEVER cause
 * WebSocket reconnection or state reinitialization.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { ChatMessage, UploadedFile, WidgetMode } from '@avatar-engine/core'
import { LS_SELECTED_AVATAR, LS_HINTS_SHOWN } from '@avatar-engine/core'
import { AVATARS, DEFAULT_AVATAR_ID } from '@avatar-engine/core'
import { useWidgetMode } from '../hooks/useWidgetMode'
import { useAvatarThumb } from '../hooks/useAvatarThumb'
import { AvatarFab } from './AvatarFab'
import { AvatarBust } from './AvatarBust'
import { AvatarPicker } from './AvatarPicker'
import { CompactChat } from './CompactChat'

/**
 * Props for the {@link AvatarWidget} component.
 *
 * All chat-related props are typically sourced from a single {@link useAvatarChat} call
 * and shared between compact and fullscreen modes to avoid WebSocket reconnections.
 *
 * @property children - Fullscreen content (e.g. StatusBar + ChatPanel) rendered as a fixed overlay.
 * @property messages - Chat message history from useAvatarChat.
 * @property sendMessage - Send a user message.
 * @property stopResponse - Abort the current assistant response.
 * @property isStreaming - Whether the assistant is currently streaming.
 * @property connected - Whether the WebSocket connection is active.
 * @property wasConnected - Whether a connection was previously established (reconnect UI).
 * @property initDetail - Human-readable initialization status.
 * @property error - Current error message, if any.
 * @property diagnostic - Current diagnostic message, if any.
 * @property provider - Active provider ID.
 * @property model - Active model ID.
 * @property engineState - Current engine state (idle, thinking, responding, etc.).
 * @property thinkingSubject - Subject of the current thinking phase, if any.
 * @property toolName - Name of the tool currently being executed.
 * @property version - Backend engine version string.
 * @property pendingFiles - Files queued for upload.
 * @property uploading - Whether a file upload is in progress.
 * @property uploadFile - Upload a file to the backend.
 * @property removeFile - Remove a pending file by ID.
 * @property switching - Whether a provider switch is in progress.
 * @property activeOptions - Currently active provider options.
 * @property availableProviders - Set of available provider IDs from the backend.
 * @property switchProvider - Switch to a different provider/model.
 * @property customProviders - Custom provider list; overrides built-in PROVIDERS.
 * @property onCompactModeRef - Ref to receive the openCompact callback for parent wiring.
 * @property avatars - Custom avatar list (default: built-in AVATARS).
 * @property avatarBasePath - Base path for avatar assets (default: "/avatars").
 * @property renderBackground - Optional render function for background content behind all modes.
 */
export interface AvatarWidgetProps {
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
  version?: string | null
  pendingFiles?: UploadedFile[]
  uploading?: boolean
  uploadFile?: (file: File) => Promise<unknown>
  removeFile?: (fileId: string) => void
  // Provider switching (for compact header dropdown)
  switching?: boolean
  activeOptions?: Record<string, string | number>
  availableProviders?: Set<string> | null
  switchProvider?: (provider: string, model?: string, options?: Record<string, string | number>) => void
  /** Custom provider list — overrides built-in PROVIDERS (order = priority) */
  customProviders?: import('@avatar-engine/core').ProviderConfig[]
  /** Ref to receive the openCompact callback — allows parent to wire it into StatusBar */
  onCompactModeRef?: React.MutableRefObject<(() => void) | null>
  /** Custom avatar list (default: built-in AVATARS) */
  avatars?: import('@avatar-engine/core').AvatarConfig[]
  /** Base path for avatar assets (default: '/avatars') */
  avatarBasePath?: string
  /** Optional background content (e.g., LandingPage) rendered behind all modes */
  renderBackground?: (props: {
    showFabHint: boolean
    version: string | null | undefined
    defaultMode: WidgetMode
    onDefaultModeChange: (mode: WidgetMode) => void
  }) => ReactNode
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
  version,
  pendingFiles,
  uploading,
  uploadFile,
  removeFile,
  switching,
  activeOptions,
  availableProviders,
  switchProvider,
  avatars: customAvatars,
  avatarBasePath,
  customProviders,
  onCompactModeRef,
  renderBackground,
}: AvatarWidgetProps) {
  const { t } = useTranslation()

  // --- Refs used by resize ---
  const drawerRef = useRef<HTMLDivElement>(null)

  // --- Crossfade transition state ---
  const [transitioning, setTransitioning] = useState(false)
  const transitionTimerRef = useRef<ReturnType<typeof setTimeout>>()

  const onTransition = useCallback((from: WidgetMode, to: WidgetMode, complete: () => void) => {
    if (transitionTimerRef.current) clearTimeout(transitionTimerRef.current)
    setTransitioning(true)
    complete()
    transitionTimerRef.current = setTimeout(() => {
      setTransitioning(false)
    }, 300)
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
    defaultMode,
    setDefaultMode,
  } = useWidgetMode(onTransition)

  // Expose openCompact to parent via ref
  useEffect(() => {
    if (onCompactModeRef) onCompactModeRef.current = openCompact
    return () => { if (onCompactModeRef) onCompactModeRef.current = null }
  }, [onCompactModeRef, openCompact])

  // --- Avatar selection (persisted to localStorage) ---
  const [selectedAvatarId, setSelectedAvatarId] = useState(() =>
    localStorage.getItem(LS_SELECTED_AVATAR) || DEFAULT_AVATAR_ID
  )
  const avatarList = customAvatars ?? AVATARS
  const selectedAvatar = avatarList.find((a) => a.id === selectedAvatarId) || avatarList[0]
  const [pickerOpen, setPickerOpen] = useState(false)
  const fabThumbUrl = useAvatarThumb(selectedAvatar, avatarBasePath)

  const handleAvatarSelect = useCallback((id: string) => {
    setSelectedAvatarId(id)
    localStorage.setItem(LS_SELECTED_AVATAR, id)
    setPickerOpen(false)
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

  useEffect(() => {
    if (resizingV || resizingH) {
      document.body.style.userSelect = 'none'
      document.body.style.cursor = resizingV ? 'ns-resize' : 'ew-resize'
    } else {
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [resizingV, resizingH])

  useEffect(() => {
    function handleResize() {
      if (compactHeight > window.innerHeight - 50) setCompactHeight(window.innerHeight - 50)
      if (compactWidth > window.innerWidth) setCompactWidth(window.innerWidth)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [compactHeight, compactWidth, setCompactHeight, setCompactWidth])

  const [isNarrow, setIsNarrow] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    function check() { setIsNarrow(window.innerWidth < 768) }
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  const showBust = bustVisible && !isNarrow
  const bustAreaWidth = showBust ? 230 : 0

  const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null
  const hasText = !!(lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming && lastMsg.content)

  return (
    <>
      {/* BACKGROUND */}
      {renderBackground?.({
        showFabHint,
        version,
        defaultMode,
        onDefaultModeChange: setDefaultMode,
      })}

      {/* FULLSCREEN OVERLAY */}
      <div
        className={`fixed inset-0 z-[2000] overflow-hidden transition-all duration-300 ${
          mode === 'fullscreen'
            ? 'opacity-100 scale-100'
            : transitioning
              ? 'opacity-0 scale-[0.98] pointer-events-none'
              : 'opacity-0 scale-[0.98] pointer-events-none'
        }`}
        aria-hidden={mode !== 'fullscreen'}
      >
        {children}
      </div>

      {/* FAB */}
      {mode === 'fab' && (
        <AvatarFab
          onClick={openCompact}
          avatarThumbUrl={fabThumbUrl}
        />
      )}

      {/* COMPACT DRAWER */}
      <div
        ref={drawerRef}
        className={`fixed bottom-0 left-0 z-[999] flex overflow-visible transition-transform duration-500 ${
          mode === 'compact' ? 'translate-y-0' : 'pointer-events-none'
        }`}
        style={{
          width: isNarrow ? '100%' : compactWidth,
          maxWidth: '100%',
          height: compactHeight,
          ...( mode !== 'compact' ? { transform: 'translateY(calc(100% + 14px))' } : {}),
          transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
          willChange: mode === 'compact' ? 'auto' : 'transform',
        }}
        role="dialog"
        aria-label={t('chat.panel')}
      >
        {/* Vertical resize handle */}
        <div
          className={`absolute top-[-14px] right-0 h-[28px] cursor-ns-resize z-[1002] flex items-center justify-center group ${resizingV ? 'active' : ''}`}
          style={{ left: bustAreaWidth }}
          onMouseDown={onResizeVStart}
          role="separator"
          aria-orientation="horizontal"
          aria-label={t('chat.resizeHeight')}
        >
          <div className={`h-2 rounded transition-all ${resizingV ? 'w-24 bg-synapse shadow-[0_0_12px_rgba(99,102,241,0.4)]' : 'w-[72px] bg-slate-light group-hover:w-24 group-hover:bg-synapse group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]'}`}
            style={{
              backgroundImage: `repeating-linear-gradient(90deg, transparent, transparent 3px, rgba(255,255,255,${resizingV ? '0.2' : '0.08'}) 3px, rgba(255,255,255,${resizingV ? '0.2' : '0.08'}) 5px)`,
            }}
          />
        </div>

        {/* Horizontal resize handle */}
        {!isNarrow && (
          <div
            className={`absolute top-0 bottom-0 w-6 cursor-ew-resize z-[1002] flex items-center justify-center group ${resizingH ? 'active' : ''}`}
            style={{ right: -24 }}
            onMouseDown={onResizeHStart}
            role="separator"
            aria-orientation="vertical"
            aria-label={t('chat.resizeWidth')}
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
                avatarBasePath={avatarBasePath}
              />
              <button
                onClick={() => setPickerOpen((v) => !v)}
                className="absolute bottom-[3.6%] left-[13px] w-8 h-8 rounded-full z-[1002]
                  flex items-center justify-center cursor-pointer
                  bg-black/55 backdrop-blur-sm border border-white/[0.06]
                  text-text-secondary text-[0.7rem]
                  opacity-0 hover:opacity-100 group-hover/bust:opacity-100
                  hover:bg-synapse/30 hover:border-synapse hover:text-white hover:scale-110
                  transition-all duration-200"
                title={t('avatar.change')}
                aria-label={t('avatar.choose')}
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
                  avatars={avatarList}
                  avatarBasePath={avatarBasePath}
                />
              )}
              <div className="absolute bottom-[2%] left-1/2 -translate-x-[40%] w-[180px] h-[50px] rounded-full pointer-events-none blur-[10px]"
                style={{
                  background: engineState === 'error'
                    ? 'radial-gradient(ellipse, rgb(var(--ae-error-rgb) / 0.2) 0%, transparent 70%)'
                    : engineState === 'responding'
                    ? 'radial-gradient(ellipse, rgb(var(--ae-pulse-rgb) / 0.25) 0%, transparent 70%)'
                    : 'radial-gradient(ellipse, rgb(var(--ae-accent-rgb) / 0.25) 0%, transparent 70%)',
                  opacity: engineState !== 'idle' ? 0.8 : 0,
                  transition: 'opacity 0.5s ease',
                }}
              />
            </>
          )}
        </div>

        {/* Chat panel */}
        <div className="relative flex-1 min-w-0 flex flex-col group/panel">
          {!isNarrow && (
            <button
              onClick={toggleBust}
              className="absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-10 rounded-full z-[1003]
                flex items-center justify-center cursor-pointer
                bg-[var(--ae-overlay-bust-toggle)] backdrop-blur-sm border border-white/[0.06]
                text-text-muted opacity-0 group-hover/panel:opacity-100 hover:opacity-100
                hover:bg-synapse/20 hover:border-synapse/40 hover:text-text-primary
                transition-all duration-200"
              title={bustVisible ? t('avatar.hideBust') : t('avatar.showBust')}
              aria-label={bustVisible ? t('avatar.hideLabel') : t('avatar.showLabel')}
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
            version={version}
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
            customProviders={customProviders}
            showExpandHint={showExpandHint}
          />
        </div>
      </div>

    </>
  )
}
