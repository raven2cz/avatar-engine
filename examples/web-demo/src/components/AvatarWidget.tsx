/**
 * AvatarWidget — master container managing three display modes:
 *
 *   FAB       → floating action button (bottom-right)
 *   COMPACT   → bottom drawer with bust area + compact chat
 *   FULLSCREEN→ existing App content, unchanged
 *
 * Wraps the fullscreen content as children.
 * Compact mode uses its own CompactChat components.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { ChatMessage, UploadedFile } from '../api/types'
import { useWidgetMode } from '../hooks/useWidgetMode'
import { AvatarFab } from './AvatarFab'
import { CompactChat } from './CompactChat'

interface AvatarWidgetProps {
  children: ReactNode
  // Chat data (from useAvatarChat)
  messages: ChatMessage[]
  sendMessage: (text: string) => void
  stopResponse: () => void
  isStreaming: boolean
  connected: boolean
  provider: string
  model: string | null
  engineState: string
  pendingFiles?: UploadedFile[]
  uploading?: boolean
  uploadFile?: (file: File) => Promise<unknown>
  removeFile?: (fileId: string) => void
}

export function AvatarWidget({
  children,
  messages,
  sendMessage,
  stopResponse,
  isStreaming,
  connected,
  provider,
  model,
  engineState,
  pendingFiles,
  uploading,
  uploadFile,
  removeFile,
}: AvatarWidgetProps) {
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
  } = useWidgetMode()

  // Resize state
  const [resizingV, setResizingV] = useState(false)
  const [resizingH, setResizingH] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const resizeStartRef = useRef({ y: 0, h: 0, x: 0, w: 0 })

  // --- Vertical resize (top handle) ---
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

  // --- Horizontal resize (right handle) ---
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

  const bustAreaWidth = bustVisible ? 230 : 0

  return (
    <>
      {/* FULLSCREEN: existing app content, shown when mode is fullscreen */}
      <div
        className={`transition-opacity duration-300 ${
          mode === 'fullscreen' ? 'opacity-100' : mode === 'compact' ? 'opacity-100' : 'opacity-100'
        }`}
        style={mode === 'fullscreen' ? {} : mode === 'compact' ? { paddingBottom: compactHeight } : {}}
      >
        {children}
      </div>

      {/* FAB */}
      {mode === 'fab' && (
        <AvatarFab onClick={openCompact} />
      )}

      {/* COMPACT DRAWER */}
      <div
        ref={drawerRef}
        className={`fixed bottom-0 left-0 z-[999] flex overflow-visible transition-transform duration-500 ${
          mode === 'compact' ? 'translate-y-0' : 'translate-y-full pointer-events-none'
        }`}
        style={{
          width: compactWidth,
          maxWidth: '100%',
          height: compactHeight,
          transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* Vertical resize handle (top) */}
        <div
          className={`absolute top-[-14px] right-0 h-[28px] cursor-ns-resize z-[1002] flex items-center justify-center group ${resizingV ? 'active' : ''}`}
          style={{ left: bustAreaWidth }}
          onMouseDown={onResizeVStart}
        >
          <div className={`h-2 rounded transition-all ${resizingV ? 'w-24 bg-synapse shadow-[0_0_12px_rgba(99,102,241,0.4)]' : 'w-[72px] bg-slate-light group-hover:w-24 group-hover:bg-synapse group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]'}`}
            style={{
              backgroundImage: `repeating-linear-gradient(90deg, transparent, transparent 3px, rgba(255,255,255,${resizingV ? '0.2' : '0.08'}) 3px, rgba(255,255,255,${resizingV ? '0.2' : '0.08'}) 5px)`,
            }}
          />
        </div>

        {/* Horizontal resize handle (right) */}
        <div
          className={`absolute top-0 bottom-0 w-6 cursor-ew-resize z-[1002] flex items-center justify-center group ${resizingH ? 'active' : ''}`}
          style={{ right: -24 }}
          onMouseDown={onResizeHStart}
        >
          <div className={`w-2 rounded transition-all ${resizingH ? 'h-24 bg-synapse shadow-[0_0_12px_rgba(99,102,241,0.4)]' : 'h-[72px] bg-slate-light group-hover:h-24 group-hover:bg-synapse group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]'}`}
            style={{
              backgroundImage: `repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(255,255,255,${resizingH ? '0.2' : '0.08'}) 3px, rgba(255,255,255,${resizingH ? '0.2' : '0.08'}) 5px)`,
            }}
          />
        </div>

        {/* Bust area */}
        <div
          className="relative flex-shrink-0 overflow-visible z-[1001] transition-[width] duration-300"
          style={{ width: bustAreaWidth, transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)' }}
        >
          {bustVisible && (
            <>
              {/* Bust placeholder — Phase 2 will add AvatarBust here */}
              <div
                className="absolute bottom-0 left-[14px] w-[200px]"
                style={{ transform: 'translateY(2.8%)' }}
                data-state={
                  engineState === 'thinking' || engineState === 'tool_executing' ? 'thinking' :
                  engineState === 'responding' ? 'speaking' :
                  engineState === 'error' ? 'error' : 'idle'
                }
              >
                <div className="w-[200px] h-[300px] rounded-2xl bg-slate-dark/30 border border-white/5 flex items-center justify-center">
                  <span className="text-text-muted text-[0.6rem]">Bust Phase 2</span>
                </div>
              </div>
              {/* Glow pool */}
              <div className="absolute bottom-[2%] left-1/2 -translate-x-[40%] w-[180px] h-[50px] rounded-full opacity-0 pointer-events-none blur-[10px]"
                style={{
                  background: engineState === 'error'
                    ? 'radial-gradient(ellipse, rgba(244,63,94,0.2) 0%, transparent 70%)'
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
          <button
            onClick={toggleBust}
            className="absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-10 rounded-full z-[1003]
              flex items-center justify-center cursor-pointer
              bg-[rgba(15,15,23,0.9)] backdrop-blur-sm border border-white/[0.06]
              text-text-muted opacity-0 group-hover/panel:opacity-100 hover:opacity-100
              hover:bg-synapse/20 hover:border-synapse/40 hover:text-text-primary
              transition-all duration-200"
            title={bustVisible ? 'Hide bust (Ctrl+Shift+H)' : 'Show bust (Ctrl+Shift+H)'}
          >
            <div className="flex flex-col gap-[3px] items-center">
              <span className="block w-[10px] h-[1.5px] bg-current rounded-sm opacity-70" />
              <span className="block w-[10px] h-[1.5px] bg-current rounded-sm opacity-70" />
              <span className="block w-[10px] h-[1.5px] bg-current rounded-sm opacity-70" />
            </div>
          </button>

          <CompactChat
            messages={messages}
            provider={provider}
            model={model}
            connected={connected}
            engineState={engineState}
            isStreaming={isStreaming}
            pendingFiles={pendingFiles}
            uploading={uploading}
            onSend={sendMessage}
            onStop={stopResponse}
            onUpload={uploadFile}
            onRemoveFile={removeFile}
            onFullscreen={openFullscreen}
            onClose={closeTofab}
          />
        </div>
      </div>
    </>
  )
}
