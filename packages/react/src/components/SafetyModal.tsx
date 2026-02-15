/**
 * Safety confirmation modal — shown when user tries to disable safety instructions.
 * Pattern follows PromoModal.tsx (backdrop + escape + centered panel).
 */

import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldOff } from 'lucide-react'

interface SafetyModalProps {
  open: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function SafetyModal({ open, onConfirm, onCancel }: SafetyModalProps) {
  const { t } = useTranslation()

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onCancel])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-[70] flex items-center justify-center px-4 py-6 pointer-events-none">
        <div
          className="pointer-events-auto w-full max-w-md glass-panel rounded-2xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="px-6 pt-6 pb-4 flex flex-col items-center text-center gap-3">
            <div className="w-12 h-12 rounded-full bg-red-500/15 flex items-center justify-center">
              <ShieldOff className="w-6 h-6 text-red-400" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary">
              {t('safety.modalTitle')}
            </h2>
          </div>

          {/* Content */}
          <div className="px-6 pb-4">
            <p className="text-sm text-text-secondary mb-3">
              {t('safety.modalDescription')}
            </p>
            <ul className="space-y-1.5 mb-4">
              <li className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-red-400 mt-0.5">•</span>
                {t('safety.modalRisk1')}
              </li>
              <li className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-red-400 mt-0.5">•</span>
                {t('safety.modalRisk2')}
              </li>
              <li className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-red-400 mt-0.5">•</span>
                {t('safety.modalRisk3')}
              </li>
            </ul>
            <p className="text-xs text-text-muted">
              {t('safety.modalWarning')}
            </p>
          </div>

          {/* Actions */}
          <div className="px-6 pb-6 flex gap-3">
            <button
              onClick={onCancel}
              className="flex-1 py-2 rounded-lg text-sm font-medium text-text-secondary border border-slate-mid/40 hover:bg-slate-mid/20 transition-colors"
            >
              {t('safety.cancel')}
            </button>
            <button
              onClick={onConfirm}
              className="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-red-500/80 border border-red-500/50 hover:bg-red-500 transition-colors"
            >
              {t('safety.disable')}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
