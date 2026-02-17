/**
 * Three-mode safety selector: Safe / Ask / Unrestricted.
 *
 * Used in both ProviderModelSelector (fullscreen) and CompactHeader (compact).
 * Transition to "unrestricted" requires confirmation via SafetyModal.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Shield, ShieldQuestion, ShieldOff } from 'lucide-react'
import type { SafetyMode } from '@avatar-engine/core'
import { SafetyModal } from './SafetyModal'

export interface SafetyModeSelectorProps {
  value: SafetyMode
  onChange: (mode: SafetyMode) => void
  provider?: string
  compact?: boolean
}

const ALL_MODES: SafetyMode[] = ['safe', 'ask', 'unrestricted']
// Providers without ACP permission protocol — Ask mode is not available
const NO_ASK_PROVIDERS = new Set(['claude', 'codex'])

export function SafetyModeSelector({ value, onChange, provider, compact = false }: SafetyModeSelectorProps) {
  const { t } = useTranslation()
  const [pendingUnrestricted, setPendingUnrestricted] = useState(false)

  const supportsAsk = !provider || !NO_ASK_PROVIDERS.has(provider)
  const modes = supportsAsk ? ALL_MODES : ALL_MODES.filter((m) => m !== 'ask')

  // Auto-switch from "ask" to "safe" when provider doesn't support Ask mode
  useEffect(() => {
    if (!supportsAsk && value === 'ask') {
      onChange('safe')
    }
  }, [supportsAsk, value, onChange])

  const handleClick = (mode: SafetyMode) => {
    if (mode === value) return
    if (mode === 'unrestricted') {
      // Require confirmation before enabling unrestricted mode
      setPendingUnrestricted(true)
    } else {
      onChange(mode)
    }
  }

  const icon = (mode: SafetyMode) => {
    const size = compact ? 'w-3 h-3' : 'w-3.5 h-3.5'
    switch (mode) {
      case 'safe': return <Shield className={`${size} text-emerald-400`} />
      case 'ask': return <ShieldQuestion className={`${size} text-amber-400`} />
      case 'unrestricted': return <ShieldOff className={`${size} text-red-400`} />
    }
  }

  const label = (mode: SafetyMode) => {
    switch (mode) {
      case 'safe': return t('safety.safe')
      case 'ask': return t('safety.ask')
      case 'unrestricted': return t('safety.unrestricted')
    }
  }

  const desc = (() => {
    switch (value) {
      case 'safe': return t('safety.safeDesc')
      case 'ask': return t('safety.askDesc')
      case 'unrestricted': return t('safety.unrestrictedDesc')
    }
  })()

  const textSize = compact ? 'text-[0.6rem]' : 'text-[0.65rem]'
  const btnText = compact ? 'text-[0.6rem]' : 'text-xs'
  const gap = compact ? 'gap-0' : 'gap-0.5'
  const pad = compact ? 'px-1.5 py-0.5' : 'px-2 py-1'

  return (
    <>
      <div className="px-2 py-1.5">
        <div className="flex flex-col gap-1.5">
          {/* Label + current description */}
          <div className="flex items-center gap-1.5 px-1">
            {icon(value)}
            <span className={`${compact ? 'text-xs' : 'text-sm'} text-text-primary leading-tight`}>
              {t('safety.label')}
            </span>
            <span className={`${textSize} text-text-muted leading-tight ml-auto`}>
              {desc}
            </span>
          </div>

          {/* Three-mode toggle */}
          <div className={`flex ${gap} rounded-lg bg-obsidian/50 p-0.5 border border-slate-mid/30`}>
            {modes.map((mode) => {
              const active = mode === value
              return (
                <button
                  key={mode}
                  onClick={() => handleClick(mode)}
                  className={`flex-1 flex items-center justify-center gap-1 ${pad} rounded-md ${btnText} font-medium transition-all ${
                    active
                      ? mode === 'safe'
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : mode === 'ask'
                          ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                          : 'bg-red-500/15 text-red-400 border border-red-500/30'
                      : 'text-text-muted hover:text-text-secondary hover:bg-slate-mid/20 border border-transparent'
                  }`}
                >
                  {icon(mode)}
                  {label(mode)}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Confirmation modal for unrestricted mode */}
      <SafetyModal
        open={pendingUnrestricted}
        onConfirm={() => {
          onChange('unrestricted')
          setPendingUnrestricted(false)
        }}
        onCancel={() => setPendingUnrestricted(false)}
      />
    </>
  )
}
