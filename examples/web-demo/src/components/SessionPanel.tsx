/**
 * Session management modal — list, resume, and create sessions.
 *
 * Centered modal dialog triggered by clicking session ID in StatusBar.
 * Fetches session list from GET /api/avatar/sessions.
 * Shows project name from cwd, table layout with clickable rows.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Loader2, X, Pencil } from 'lucide-react'
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
  provider: string
  cwd: string
  capabilities: ProviderCapabilities | null
  onResume: (sessionId: string) => void
  onNewSession: () => void
  onTitleUpdated?: (title: string | null) => void
}

export function SessionPanel({
  open,
  onClose,
  provider,
  cwd,
  capabilities,
  onResume,
  onNewSession,
  onTitleUpdated,
}: SessionPanelProps) {
  const { t } = useTranslation()
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const canceledRef = useRef(false)

  const startEdit = useCallback((s: SessionInfo) => {
    canceledRef.current = false
    setEditingId(s.session_id)
    setEditValue(s.title || '')
  }, [])

  const cancelEdit = useCallback(() => {
    canceledRef.current = true
    setEditingId(null)
    setEditValue('')
    onTitleUpdated?.(null)
  }, [onTitleUpdated])

  const saveTitle = useCallback(async (sessionId: string, isCurrent: boolean) => {
    if (canceledRef.current) return
    canceledRef.current = true  // guard against double-fire (Enter + blur)
    const trimmed = editValue.trim()
    // Immediately update parent — don't wait for network round-trip.
    // Use server-provided is_current flag to avoid session ID format mismatch.
    if (isCurrent) {
      onTitleUpdated?.(trimmed || null)
    }
    // Update local session list optimistically
    if (trimmed) {
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === sessionId ? { ...s, title: trimmed } : s
        )
      )
    }
    setEditingId(null)
    try {
      await fetch(`${API_BASE}/sessions/${sessionId}/title`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: trimmed }),
      })
    } catch {
      // Revert on network failure
      if (isCurrent) {
        onTitleUpdated?.(null)
      }
    }
  }, [editValue, onTitleUpdated])

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

  // Reset editing state and live preview when modal closes
  useEffect(() => {
    if (!open) {
      canceledRef.current = true
      setEditingId(null)
      setEditValue('')
      // Don't call onTitleUpdated(null) here — keep the saved title
    }
  }, [open])

  if (!open) return null

  const projectName = basename(cwd)

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-[70] flex items-start justify-center px-4 pt-20 pb-6 pointer-events-none overflow-y-auto">
        <div
          className="pointer-events-auto w-full max-w-3xl max-h-[75vh] glass-panel rounded-2xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up flex flex-col overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header with gradient accent */}
          <div className="relative px-6 py-4 border-b border-slate-mid/30 flex-shrink-0">
            <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-synapse/50 to-transparent" />
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold gradient-text truncate">
                  {projectName || t('fullscreen.statusBar.sessions')}
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
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-gradient-to-r from-synapse/20 to-pulse/20 text-synapse border border-synapse/30 hover:from-synapse/30 hover:to-pulse/30 transition-all hover:shadow-lg hover:shadow-synapse/10"
            >
              <Plus className="w-4 h-4" />
              {t('fullscreen.sessions.newSession')}
            </button>
          </div>

          {/* Session list */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {!capabilities?.can_list_sessions ? (
              <div className="flex items-center justify-center py-12 text-text-muted text-sm">
                {t('fullscreen.sessions.notSupported', { provider })}
              </div>
            ) : loading ? (
              <div className="flex items-center justify-center py-12 text-text-muted text-sm">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                {t('fullscreen.sessions.loading')}
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <p className="text-sm">{t('fullscreen.sessions.noSessions')}</p>
                <p className="text-xs mt-1">{t('fullscreen.sessions.startConversation')}</p>
              </div>
            ) : (
              <div className="px-4 py-3">
                {/* Table header */}
                <div className="grid grid-cols-[1fr_120px_100px] gap-3 px-4 py-2 text-[10px] text-text-muted uppercase tracking-widest">
                  <span>{t('fullscreen.sessions.title')}</span>
                  <span>{t('fullscreen.sessions.sessionId')}</span>
                  <span className="text-right">{t('fullscreen.sessions.updated')}</span>
                </div>

                {/* Rows */}
                <div className="space-y-1 mt-1">
                  {sessions.map((s) => {
                    const isCurrent = s.is_current
                    return (
                      <div
                        key={s.session_id}
                        onClick={() => {
                          if (!isCurrent && editingId !== s.session_id) {
                            onResume(s.session_id)
                            onClose()
                          }
                        }}
                        className={`group/row w-full grid grid-cols-[1fr_120px_100px] gap-3 items-center px-4 py-3 rounded-xl text-left text-sm transition-all ${
                          isCurrent
                            ? 'bg-gradient-to-r from-synapse/10 to-pulse/5 border border-synapse/25 cursor-default shadow-sm shadow-synapse/5'
                            : 'hover:bg-slate-mid/25 border border-transparent hover:border-slate-mid/30 cursor-pointer'
                        }`}
                      >
                        {/* Title */}
                        <div className="min-w-0">
                          {editingId === s.session_id ? (
                            <input
                              autoFocus
                              value={editValue}
                              onChange={(e) => {
                                setEditValue(e.target.value)
                                if (isCurrent) {
                                  onTitleUpdated?.(e.target.value || null)
                                }
                              }}
                              onBlur={() => saveTitle(s.session_id, isCurrent)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveTitle(s.session_id, isCurrent)
                                if (e.key === 'Escape') { e.stopPropagation(); cancelEdit() }
                              }}
                              onClick={(e) => e.stopPropagation()}
                              className="w-full bg-slate-mid/40 border border-synapse/40 rounded px-2 py-0.5 text-sm text-text-primary outline-none focus:border-synapse/70"
                            />
                          ) : (
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span
                                className={`truncate ${isCurrent ? 'text-text-primary font-medium' : 'text-text-secondary'}`}
                              >
                                {s.title || s.session_id.slice(0, 24)}
                              </span>
                              <button
                                onClick={(e) => { e.stopPropagation(); startEdit(s) }}
                                className="flex-none p-0.5 rounded text-text-muted opacity-0 group-hover/row:opacity-60 hover:!opacity-100 hover:text-synapse transition-opacity"
                                title={t('fullscreen.sessions.renameSession')}
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Session ID */}
                        <div className="min-w-0">
                          {isCurrent ? (
                            <span className="text-xs text-synapse font-medium">{t('fullscreen.sessions.current')}</span>
                          ) : (
                            <span className="text-xs text-text-muted font-mono truncate block">
                              {s.session_id.slice(0, 10)}
                            </span>
                          )}
                        </div>

                        {/* Updated */}
                        <div className="text-right">
                          <span className="text-xs text-text-muted">
                            {s.updated_at ? timeAgo(s.updated_at) : '-'}
                          </span>
                        </div>
                      </div>
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
                {t('fullscreen.sessions.sessionCount', { count: sessions.length })} &middot; {provider}
              </span>
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg text-xs text-text-muted hover:text-text-secondary hover:bg-slate-mid/30 transition-colors"
              >
                {t('fullscreen.sessions.close')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
