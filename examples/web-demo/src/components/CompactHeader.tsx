/**
 * Compact mode header — provider badge, state indicator, fullscreen/close buttons.
 * Minimal height (~38px), no session panel access.
 */

import type { EngineState } from '../api/types'

interface CompactHeaderProps {
  provider: string
  model: string | null
  connected: boolean
  engineState: EngineState | string
  onFullscreen: () => void
  onClose: () => void
}

const STATE_LABELS: Record<string, { label: string; cls: string }> = {
  thinking: { label: 'Thinking...', cls: 'bg-synapse/12 text-synapse' },
  responding: { label: 'Responding...', cls: 'bg-pulse/12 text-pulse' },
  tool_executing: { label: 'Running tool...', cls: 'bg-neural/12 text-neural' },
  error: { label: 'Error', cls: 'bg-red-500/12 text-red-400' },
}

export function CompactHeader({ provider, model, connected, engineState, onFullscreen, onClose }: CompactHeaderProps) {
  const stateInfo = STATE_LABELS[engineState]

  return (
    <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-mid/30 bg-black/20 min-h-[38px] flex-shrink-0 rounded-t-2xl">
      {/* Left: provider + model + state */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-synapse/10 border border-synapse/20 text-[0.65rem] font-medium text-synapse flex-shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400 shadow-[0_0_4px_theme(colors.emerald.400)]' : 'bg-red-400'}`} />
          {provider || 'Provider'}
        </span>
        {model && (
          <span className="text-[0.65rem] text-text-muted font-mono truncate">
            {model}
          </span>
        )}
        {stateInfo && (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[0.6rem] font-medium ${stateInfo.cls}`}>
            <span className="w-1 h-1 rounded-full bg-current animate-pulse" />
            {stateInfo.label}
          </span>
        )}
      </div>

      {/* Right: controls */}
      <div className="flex items-center gap-0.5 flex-shrink-0">
        {/* Fullscreen */}
        <button
          onClick={onFullscreen}
          className="w-6 h-6 rounded-md flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-white/8 transition-colors"
          title="Fullscreen (Ctrl+Shift+F)"
          aria-label="Expand to fullscreen"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
          </svg>
        </button>
        {/* Close */}
        <button
          onClick={onClose}
          className="w-6 h-6 rounded-md flex items-center justify-center text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors"
          title="Close (Esc)"
          aria-label="Close chat panel"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}
