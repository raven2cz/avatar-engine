/**
 * Promo modal — shown on first visit with demo video and library description.
 * Pattern follows SessionPanel.tsx (backdrop + centered modal).
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Play } from 'lucide-react'

interface PromoModalProps {
  open: boolean
  onClose: () => void
  showNextTime: boolean
  onShowNextTimeChange: (checked: boolean) => void
  version?: string | null
}

export function PromoModal({
  open,
  onClose,
  showNextTime,
  onShowNextTimeChange,
  version,
}: PromoModalProps) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [ended, setEnded] = useState(false)

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Reset state when modal reopens
  useEffect(() => {
    if (open) {
      setPlaying(false)
      setEnded(false)
      const video = videoRef.current
      if (video) {
        video.currentTime = 0
        video.pause()
      }
    }
  }, [open])

  const handlePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    video.muted = false
    video.currentTime = 0
    video.play()
    setPlaying(true)
    setEnded(false)
  }, [])

  const handleEnded = useCallback(() => {
    const video = videoRef.current
    if (video) {
      video.currentTime = 0
      video.pause()
    }
    setPlaying(false)
    setEnded(true)
  }, [])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-[70] flex items-center justify-center px-4 py-6 pointer-events-none overflow-y-auto">
        <div
          className="pointer-events-auto w-full max-w-2xl glass-panel rounded-2xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up flex flex-col overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header with gradient accent */}
          <div className="relative px-6 py-4 border-b border-slate-mid/30 flex-shrink-0">
            <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-synapse/50 to-transparent" />
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold gradient-text">
                {t('promo.title')}
                {version && (
                  <span className="text-sm text-text-muted/50 font-mono font-normal ml-2">
                    v{version}
                  </span>
                )}
              </h2>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-slate-mid/30 transition-colors flex-shrink-0 ml-4"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Content — responsive layout */}
          <div className="flex flex-col md:flex-row gap-5 p-6 overflow-y-auto">
            {/* Video column */}
            <div className="flex-shrink-0 flex flex-col items-center">
              <div className="relative cursor-pointer" onClick={handlePlay}>
                <video
                  ref={videoRef}
                  src="/promo/avatar-demo.mp4"
                  playsInline
                  preload="metadata"
                  onEnded={handleEnded}
                  className={`w-full md:w-[280px] max-h-[420px] rounded-xl border border-white/[0.06] object-cover transition-all duration-300 ${
                    !playing ? 'brightness-[0.6]' : ''
                  }`}
                />
                {/* Play button overlay — shown when not playing */}
                {!playing && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-14 h-14 rounded-full bg-synapse/80 backdrop-blur-sm flex items-center justify-center shadow-lg shadow-synapse/30 hover:bg-synapse hover:scale-110 transition-all duration-200">
                      <Play className="w-7 h-7 text-white ml-0.5" fill="white" />
                    </div>
                  </div>
                )}
              </div>
              <span className="text-text-muted/50 text-[0.6rem] mt-1.5">
                {t(`promo.${ended ? 'replayVideo' : 'clickToPlay'}`)}
              </span>
            </div>

            {/* Text column */}
            <div className="flex-1 min-w-0 flex flex-col gap-3">
              <p className="text-text-secondary text-sm leading-relaxed">
                {t('promo.description1')}
              </p>
              <div className="h-[1px] bg-slate-mid/30" />
              <p className="text-text-secondary text-sm leading-relaxed">
                {t('promo.description2')}
              </p>
              <div className="h-[1px] bg-slate-mid/30" />
              <p className="text-text-secondary text-sm leading-relaxed">
                {t('promo.description3')}
              </p>
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-3 border-t border-slate-mid/30 flex-shrink-0">
            <label className="flex items-center gap-2 cursor-pointer select-none w-fit">
              <input
                type="checkbox"
                checked={showNextTime}
                onChange={(e) => onShowNextTimeChange(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-slate-mid/50 bg-slate-dark accent-synapse cursor-pointer"
              />
              <span className="text-xs text-text-muted">
                {t('promo.showNextTime')}
              </span>
            </label>
          </div>
        </div>
      </div>
    </>
  )
}
