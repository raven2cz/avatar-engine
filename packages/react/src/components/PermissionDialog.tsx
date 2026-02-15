/**
 * Permission request dialog — shown when AI requests approval for a destructive operation.
 *
 * Displays tool name, input, and available options from the ACP protocol.
 * Escape key or backdrop click cancels the request.
 */

import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert } from 'lucide-react'
import type { PermissionRequest } from '@avatar-engine/core'

interface PermissionDialogProps {
  request: PermissionRequest | null
  onRespond: (requestId: string, optionId: string, cancelled: boolean) => void
}

export function PermissionDialog({ request, onRespond }: PermissionDialogProps) {
  const { t } = useTranslation()

  // Close on Escape → cancel
  useEffect(() => {
    if (!request) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onRespond(request.requestId, '', true)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [request, onRespond])

  if (!request) return null

  // Separate allow and deny options
  const allowOptions = request.options.filter(
    (o) => o.kind === 'allow_once' || o.kind === 'allow_always'
  )
  const denyOptions = request.options.filter(
    (o) => o.kind === 'reject_once' || o.kind === 'reject_always'
  )

  // Fallback: if ACP didn't send structured options, show simple Allow/Deny
  const hasStructuredOptions = allowOptions.length > 0 || denyOptions.length > 0

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[2100] bg-black/50 backdrop-blur-sm"
        onClick={() => onRespond(request.requestId, '', true)}
      />

      {/* Dialog */}
      <div className="fixed inset-0 z-[2200] flex items-center justify-center px-4 py-6 pointer-events-none">
        <div
          className="pointer-events-auto w-full max-w-md glass-panel rounded-2xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="px-6 pt-6 pb-4 flex flex-col items-center text-center gap-3">
            <div className="w-12 h-12 rounded-full bg-amber-500/15 flex items-center justify-center">
              <ShieldAlert className="w-6 h-6 text-amber-400" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary">
              {t('safety.permissionTitle')}
            </h2>
          </div>

          {/* Content */}
          <div className="px-6 pb-4">
            <p className="text-sm text-text-secondary mb-3">
              {t('safety.permissionDesc')}
            </p>

            {/* Tool info */}
            <div className="space-y-2 mb-4">
              <div className="flex items-start gap-2 bg-obsidian/50 rounded-lg px-3 py-2 border border-slate-mid/30">
                <span className="text-xs text-text-muted shrink-0 mt-0.5">{t('safety.permissionTool')}:</span>
                <span className="text-sm text-text-primary font-mono break-all">{request.toolName}</span>
              </div>
              {request.toolInput && (
                <div className="flex items-start gap-2 bg-obsidian/50 rounded-lg px-3 py-2 border border-slate-mid/30">
                  <span className="text-xs text-text-muted shrink-0 mt-0.5">{t('safety.permissionInput')}:</span>
                  <span className="text-xs text-text-secondary font-mono break-all max-h-24 overflow-y-auto">
                    {request.toolInput}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="px-6 pb-6">
            {hasStructuredOptions ? (
              <div className="flex flex-col gap-2">
                {/* Allow options */}
                {allowOptions.map((opt) => (
                  <button
                    key={opt.option_id}
                    onClick={() => onRespond(request.requestId, opt.option_id, false)}
                    className="w-full py-2 rounded-lg text-sm font-medium text-white bg-emerald-600/80 border border-emerald-500/50 hover:bg-emerald-600 transition-colors"
                  >
                    {opt.kind === 'allow_always' ? `${t('safety.permissionAllow')} (always)` : t('safety.permissionAllow')}
                  </button>
                ))}
                {/* Deny options */}
                {denyOptions.map((opt) => (
                  <button
                    key={opt.option_id}
                    onClick={() => onRespond(request.requestId, opt.option_id, false)}
                    className="w-full py-2 rounded-lg text-sm font-medium text-text-secondary border border-slate-mid/40 hover:bg-slate-mid/20 transition-colors"
                  >
                    {opt.kind === 'reject_always' ? `${t('safety.permissionDeny')} (always)` : t('safety.permissionDeny')}
                  </button>
                ))}
                {/* Cancel fallback */}
                <button
                  onClick={() => onRespond(request.requestId, '', true)}
                  className="w-full py-1.5 rounded-lg text-xs text-text-muted hover:text-text-secondary transition-colors"
                >
                  {t('safety.permissionCancel')}
                </button>
              </div>
            ) : (
              /* Simple allow/deny when no structured options */
              <div className="flex gap-3">
                <button
                  onClick={() => onRespond(request.requestId, '', true)}
                  className="flex-1 py-2 rounded-lg text-sm font-medium text-text-secondary border border-slate-mid/40 hover:bg-slate-mid/20 transition-colors"
                >
                  {t('safety.permissionDeny')}
                </button>
                <button
                  onClick={() => onRespond(request.requestId, request.options[0]?.option_id || 'approved', false)}
                  className="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-emerald-600/80 border border-emerald-500/50 hover:bg-emerald-600 transition-colors"
                >
                  {t('safety.permissionAllow')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
