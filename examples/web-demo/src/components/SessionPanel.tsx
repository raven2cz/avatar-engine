/**
 * Session management modal — list, resume, and create sessions.
 *
 * Centered modal dialog triggered by clicking session ID in StatusBar.
 * Fetches session list from GET /api/avatar/sessions.
 * Shows project name from cwd, table layout with clickable rows.
 */

import { useState, useEffect } from 'react'
import { Plus, Loader2, X } from 'lucide-react'
import type { SessionInfo, ProviderCapabilities } from '../api/types'

// REST API base — matches Vite proxy config
const API_BASE =
  import.meta.env.DEV
    ? `http://${window.location.hostname}:5173/api/avatar`
    : `/api/avatar`

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function basename(path: string): string {
  if (!path) return ''
  const parts = path.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || path
}

interface SessionPanelProps {
  open: boolean
  onClose: () => void
  currentSessionId: string | null
  provider: string
  cwd: string
  capabilities: ProviderCapabilities | null
  onResume: (sessionId: string) => void
  onNewSession: () => void
}

export function SessionPanel({
  open,
  onClose,
  currentSessionId,
  provider,
  cwd,
  capabilities,
  onResume,
  onNewSession,
}: SessionPanelProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(false)

  // Fetch sessions when modal opens (if provider supports it)
  useEffect(() => {
    if (!open || !capabilities?.can_list_sessions) return
    let cancelled = false
    setLoading(true)
    fetch(`${API_BASE}/sessions`)
      .then((r) => r.json())
      .then((data: SessionInfo[]) => {
        if (!cancelled) setSessions(data)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, capabilities?.can_list_sessions])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  const projectName = basename(cwd)

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal — pt-20 accounts for browser chrome + status bar */}
      <div className="fixed inset-0 z-[70] flex items-start justify-center px-4 pt-20 pb-6 pointer-events-none overflow-y-auto">
        <div
          className="pointer-events-auto w-full max-w-2xl max-h-[75vh] glass-panel rounded-2xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-slate-mid/30 flex-shrink-0">
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-text-primary truncate">
                  {projectName || 'Sessions'}
                </h2>
                {cwd && (
                  <p className="text-xs text-text-muted font-mono mt-0.5 truncate">
                    {cwd}
                  </p>
                )}
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-slate-mid/30 transition-colors flex-shrink-0 ml-4"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* New session button */}
          <div className="px-6 py-3 border-b border-slate-mid/30 flex-shrink-0">
            <button
              onClick={() => { onNewSession(); onClose() }}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-gradient-to-r from-synapse/20 to-pulse/20 text-synapse border border-synapse/30 hover:from-synapse/30 hover:to-pulse/30 transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Session
            </button>
          </div>

          {/* Session list */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {!capabilities?.can_list_sessions ? (
              <div className="flex items-center justify-center py-12 text-text-muted text-sm">
                Session listing not supported for {provider}
              </div>
            ) : loading ? (
              <div className="flex items-center justify-center py-12 text-text-muted text-sm">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Loading sessions...
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <p className="text-sm">No previous sessions</p>
                <p className="text-xs mt-1">Start a conversation to create one</p>
              </div>
            ) : (
              <div className="px-3 py-2">
                {/* Table header */}
                <div className="grid grid-cols-[1fr_100px_90px] gap-2 px-3 py-2 text-xs text-text-muted uppercase tracking-wide">
                  <span>Title</span>
                  <span>Session ID</span>
                  <span className="text-right">Updated</span>
                </div>

                {/* Rows */}
                <div className="space-y-0.5">
                  {sessions.map((s) => {
                    const isCurrent = s.session_id === currentSessionId
                    return (
                      <button
                        key={s.session_id}
                        onClick={() => {
                          if (!isCurrent) {
                            onResume(s.session_id)
                            onClose()
                          }
                        }}
                        disabled={isCurrent}
                        className={`w-full grid grid-cols-[1fr_100px_90px] gap-2 items-center px-3 py-2.5 rounded-lg text-left text-sm transition-colors ${
                          isCurrent
                            ? 'bg-synapse/10 border border-synapse/25 cursor-default'
                            : 'hover:bg-slate-mid/20 border border-transparent'
                        }`}
                      >
                        {/* Title */}
                        <div className="min-w-0">
                          <span className="text-text-secondary truncate block">
                            {s.title || s.session_id.slice(0, 20)}
                          </span>
                        </div>

                        {/* Session ID */}
                        <div className="min-w-0">
                          {isCurrent ? (
                            <span className="text-xs text-synapse font-medium">current</span>
                          ) : (
                            <span className="text-xs text-text-muted font-mono truncate block">
                              {s.session_id.slice(0, 8)}
                            </span>
                          )}
                        </div>

                        {/* Updated */}
                        <div className="text-right">
                          <span className="text-xs text-text-muted">
                            {s.updated_at ? timeAgo(s.updated_at) : '-'}
                          </span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-3 border-t border-slate-mid/30 flex-shrink-0">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">
                {sessions.length} session{sessions.length !== 1 ? 's' : ''} &middot; {provider}
              </span>
              <button
                onClick={onClose}
                className="px-3 py-1 rounded-lg text-xs text-text-muted hover:text-text-secondary hover:bg-slate-mid/30 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
